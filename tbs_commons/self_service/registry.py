"""Which doctypes this app offers as self-service records, and who owns each one.

The layer that makes `Record Change Request` generic mean something. The request
document names a doctype and a document; everything that turns that pair into
"your record, and these are the fields you may propose" is here, and it is
assembled from the `self_service_records` hook rather than written into the
request doctype.

Two consequences worth being explicit about.

A doctype with no policy is not self-service, whatever anyone's permissions say.
`policy()` throws rather than falling back to something permissive: the default
for a doctype nobody has thought about is that its fields are not an employee's
to propose, and a registry that guessed otherwise would turn every new doctype on
the site into a self-service form.

Ownership can chain. `Employee` names its owner directly through `user_id`; a
record that hangs off the employee rather than off the login names its `Employee`
instead, and `owner_of` follows that to the same answer. That is what lets a
second HR record about the same person be added as a registry entry rather than
as a second idea of what "mine" means -- see `policies`.

Two functions here read records, and they answer different questions, so they
reach the database differently.

`session_record` returns record *data* to a caller, so it goes through
`frappe.get_list` and is subject to every permission the site has configured --
role permissions, User Permissions, and this app's own gate in
`tbs_commons.safer_permissions`. It used to use `frappe.db.get_value`, on the
reasoning that "may I read the directory" and "may I read myself" are different
questions. They are, but that is an argument for configuring the answer, not for
a whitelisted endpoint deciding it in spite of the configuration: an
administrator who gates the `Employee` role has said what they mean, and this
module is not the place to overrule them. A user whose site denies them their
own record now gets `None`, and the page says so.

`owner_of` answers only "whose record is this", returns a username and no record
data, and is what `validate_raiser` consults before deciding whether a proposal
is yours to raise. That stays a raw read on purpose -- ownership is a fact about
the row rather than a right over it, and a permission check there would make the
answer depend on who is asking. It grants nothing: every caller that goes on to
*return* or *change* anything does its own permission check.
"""

import frappe

HOOK = "self_service_records"

# How deep an ownership chain may run before it is treated as a cycle. Chains are
# a configuration, so a mistake in one is a hang rather than an error unless
# something counts -- and a real chain is one or two links.
MAX_CHAIN = 5


def policies() -> dict[str, dict]:
	"""Every registered policy, keyed by the doctype it governs.

	Cached for the request. The hook is resolved through `frappe.get_attr` so an
	app registers a dotted path to its policy dict rather than inlining forty
	field names in its `hooks.py`.

	A later entry for a doctype replaces an earlier one, which is Frappe's usual
	hook precedence and makes overriding this app's `Employee` policy -- to widen
	or narrow the proposable list for one site -- a matter of adding an app.
	"""

	def build() -> dict[str, dict]:
		found: dict[str, dict] = {}
		for path in frappe.get_hooks(HOOK) or []:
			policy = frappe.get_attr(path)
			if not isinstance(policy, dict) or not policy.get("doctype"):
				frappe.throw(frappe._("{0} is not a self-service policy: it needs a `doctype`.").format(path))
			found[policy["doctype"]] = policy
		return found

	return frappe.cache.get_value("tbs_commons_self_service_policies", build, shared=True)


def registered() -> list[str]:
	"""The doctypes that are self-service here, in no particular order."""
	return sorted(policies())


def policy(doctype: str) -> dict:
	"""The policy for `doctype`, or a refusal.

	Throwing rather than returning None: every caller needs the answer, and a
	doctype nobody registered is not a doctype whose fields are anyone's to
	propose. Saying so once here means no caller has to remember to check.
	"""
	found = policies().get(doctype)
	if not found:
		frappe.throw(
			frappe._("{0} records cannot be changed through a request.").format(doctype),
			frappe.PermissionError,
		)
	return found


def proposable_fields(doctype: str) -> list[str]:
	"""The policy's proposable list, less anything this site's doctype no longer has.

	A field can go missing two ways: it is renamed or dropped upstream, or a site
	hides it with a Property Setter. Either way the honest answer is that it is
	not proposable here, and filtering on the meta gives that answer in the one
	place both the form and the validation read -- rather than as a save that
	throws on a field the form had no business offering.
	"""
	meta = frappe.get_meta(doctype)
	return [fieldname for fieldname in policy(doctype).get("proposable") or () if meta.has_field(fieldname)]


def display_fields(doctype: str) -> list[str]:
	"""What a read-only page may show, `name` always included.

	Same filtering as `proposable_fields`, and for the same reason: a page that
	asks for a field the doctype no longer has fails the whole read rather than
	quietly showing one row fewer.
	"""
	meta = frappe.get_meta(doctype)
	fields = [fieldname for fieldname in policy(doctype).get("display") or () if meta.has_field(fieldname)]
	return ["name", *fields]


def title_of(doctype: str, name: str) -> str:
	"""How a record reads in a queue, without loading the whole document."""
	field = policy(doctype).get("title_field")
	if not field:
		return name
	return frappe.db.get_value(doctype, name, field) or name


def owner_of(doctype: str, name: str) -> str | None:
	"""The User who owns this record, following the policy chain, or None.

	`None` is a real answer and not an error: a record whose owner field is
	blank -- an employee with no login yet -- belongs to nobody, and the callers
	read that as "not yours" rather than as a failure.

	A raw read, deliberately and narrowly: it returns a username, never record
	data, and grants nothing on its own. See the module docstring.
	"""
	seen: set[tuple[str, str]] = set()
	for _ in range(MAX_CHAIN):
		if (doctype, name) in seen:
			# A configuration that points a chain back at itself. Nobody owns a
			# record whose ownership is circular, and saying so beats looping.
			return None
		seen.add((doctype, name))

		current = policy(doctype)
		value = frappe.db.get_value(doctype, name, current["owner_field"])
		if not value:
			return None
		# A record that meets the doctype's own conditions is claimable; one that
		# does not -- a leaver's employee record -- belongs to nobody any more.
		if not _matches(doctype, name, current.get("filters")):
			return None

		next_doctype = current.get("owner_doctype")
		if not next_doctype:
			return value
		doctype, name = next_doctype, value
	return None


def _matches(doctype: str, name: str, filters: dict | None) -> bool:
	"""Whether this record still meets the extra conditions its policy sets."""
	if not filters:
		return True
	return bool(frappe.db.exists(doctype, {"name": name, **filters}))


def session_owns(doctype: str, name: str) -> bool:
	"""Whether the session user owns this record."""
	return owner_of(doctype, name) == frappe.session.user


def session_record(doctype: str, fieldnames: list[str] | None = None):
	"""The one record of `doctype` this session owns and may read, or None.

	Only meaningful for a policy marked `singular` -- one employee record per
	login, so "my record" has a single answer and a page can ask for it without
	naming one. A policy that is not singular has no such answer and says so,
	rather than returning whichever row the database offered first.

	Through `frappe.get_list`, so the site's permissions decide what comes back.
	The owner filter narrows it to this user's own row; it is not what makes the
	read safe, and is not trusted to be. A user the site withholds the record
	from gets `None` here whether they own it or not -- see the module docstring.

	`None` for a user with no read permission at all, rather than the throw
	`get_list` would raise: "you have no record here" is the same answer as far
	as every caller is concerned, and one of them is a permissions endpoint that
	must not 500 on the way to saying so.
	"""
	current = policy(doctype)
	if not current.get("singular"):
		frappe.throw(
			frappe._("There is no single {0} record for a user.").format(doctype),
			frappe.ValidationError,
		)
	if not frappe.has_permission(doctype, "read"):
		return None

	if current.get("owner_doctype"):
		# A chained policy's owner field names another record, not a user, so
		# the lookup starts from whichever record *that* policy calls this
		# session's -- and a singular chained record is one row against it.
		parent = session_record(current["owner_doctype"], ["name"])
		if not parent:
			return None
		match = {current["owner_field"]: parent.name}
	else:
		match = {current["owner_field"]: frappe.session.user}

	rows = frappe.get_list(
		doctype,
		filters={**match, **(current.get("filters") or {})},
		fields=fieldnames or ["name"],
		limit_page_length=1,
	)
	return rows[0] if rows else None


def record_exists(doctype: str) -> bool:
	"""Whether a record of `doctype` this user owns exists at all.

	A raw read, and the second one in this module -- see `owner_of` for the first
	and the reasoning both share. It returns a boolean and never record data, so
	the only thing it can disclose is that somebody has created a row against the
	caller's own login. That is a bounded disclosure and a useful one: it is the
	difference between "nobody has set your record up" and "your record is there
	and you are not allowed to see it", and those two have different people to
	ask about them.

	The policy's filters apply, so a record the policy no longer claims -- an
	employee marked Left -- reads as absent rather than as forbidden. That is the
	honest answer: nothing is withholding it from them, it has stopped being
	theirs.
	"""
	current = policy(doctype)
	if current.get("owner_doctype"):
		parent = session_record(current["owner_doctype"], ["name"])
		if not parent:
			return False
		match = {current["owner_field"]: parent.name}
	else:
		match = {current["owner_field"]: frappe.session.user}
	return bool(frappe.db.exists(doctype, {**match, **(current.get("filters") or {})}))


def clear_cache() -> None:
	"""Drop the resolved registry. Called when an app is installed or removed."""
	frappe.cache.delete_value("tbs_commons_self_service_policies", shared=True)
