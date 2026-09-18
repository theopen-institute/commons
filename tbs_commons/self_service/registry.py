"""Which doctypes this app offers as self-service records, and who owns each one.

The layer that makes `Record Change Request` generic mean something. The request
document names a doctype and a document; everything that turns that pair into
"your record, and these are the fields you may propose" is here, and it is read
from `Self Service Record` documents rather than written into the app.

Two consequences worth being explicit about.

A doctype with no enabled record is not self-service, whatever anyone's
permissions say. `policy()` throws rather than falling back to something
permissive: the default for a doctype nobody has configured is that its fields
are not an employee's to propose, and a registry that guessed otherwise would
turn every new doctype on the site into a self-service form.

Ownership can chain. `Employee` names its owner directly through `user_id`; a
record that hangs off the employee rather than off the login names its `Employee`
instead, and `owner_of` follows that to the same answer. That is what lets a
second record type be added as a document rather than as a second idea of what
"mine" means.

Two functions here read records, and they answer different questions, so they
reach the database differently.

`session_records` returns record *data* to a caller, so it goes through
`frappe.get_list` and is subject to every permission the site has configured --
role permissions, User Permissions, and this app's gate in
`tbs_commons.safer_permissions`. An administrator who gates a doctype has said
what they mean, and this module is not the place to overrule them.

`owner_of` answers only "whose record is this", returns a username and no record
data, and is what `validate_raiser` consults before deciding whether a proposal
is yours to raise. That stays a raw read on purpose -- ownership is a fact about
the row rather than a right over it, and a permission check there would make the
answer depend on who is asking. It grants nothing: every caller that goes on to
*return* or *change* anything does its own permission check.
"""

import json

import frappe

CONFIG = "Self Service Record"

# Where the resolved registry is cached. Named once: a key spelled twice is a
# key that can be read under one spelling and invalidated under another.
POLICY_CACHE_KEY = "tbs_commons_self_service_policies"

# How deep an ownership chain may run before it is treated as a cycle. Chains are
# a configuration, so a mistake in one is a hang rather than an error unless
# something counts -- and a real chain is one or two links.
MAX_CHAIN = 5

# How a stored field type reads as a form control. The frontend draws from this
# rather than from a fieldtype it would have to know Frappe's vocabulary for, and
# a type absent here is shown read-only rather than guessed at.
CONTROL_TYPES = {
	"Data": "text",
	"Select": "select",
	"Link": "link",
	"Date": "date",
	"Small Text": "textarea",
	"Text": "textarea",
	"Long Text": "textarea",
	"Text Editor": "textarea",
	"Check": "check",
	"Int": "number",
	"Float": "number",
	"Currency": "number",
	"Phone": "tel",
}

# `Data` fields carry their flavour in `options`, which is where an email or a
# phone number is distinguished from any other short string.
DATA_CONTROL_TYPES = {"Email": "email", "Phone": "tel", "URL": "url"}


def policies() -> dict[str, dict]:
	"""Every enabled configuration, keyed by the doctype it governs.

	Cached for the site and dropped whenever a `Self Service Record` is saved or
	deleted (see `SelfServiceRecord.clear_registry_cache`), because this answer
	sits on the path of every self-service permission check.

	Read with `frappe.get_all` and an explicit field list rather than by loading
	each document: this runs before a page renders anything, and the child rows
	are the only part that needs a second query.
	"""

	def build() -> dict[str, dict]:
		found: dict[str, dict] = {}
		parents = frappe.get_all(
			CONFIG,
			filters={"enabled": 1},
			fields=[
				"name",
				"document_type",
				"label",
				"route_slug",
				"icon",
				"nav_order",
				"read_only_notice",
				"empty_notice",
				"owner_field",
				"owner_doctype",
				"title_field",
				"is_singular",
				"allow_new",
				"allow_delete",
				"record_filters",
			],
		)
		if not parents:
			return found
		rows = frappe.get_all(
			"Self Service Field",
			filters={"parent": ["in", [p.name for p in parents]], "parenttype": CONFIG},
			fields=[
				"parent",
				"section",
				"fieldname",
				"viewable",
				"proposable",
				"free_text",
				"idx",
			],
			order_by="parent asc, idx asc",
			parent_doctype=CONFIG,
		)
		by_parent: dict[str, list] = {}
		for row in rows:
			by_parent.setdefault(row.parent, []).append(row)

		for parent in parents:
			fields = by_parent.get(parent.name) or []
			found[parent.document_type] = {
				"doctype": parent.document_type,
				"label": parent.label,
				"slug": parent.route_slug,
				"icon": parent.icon or None,
				"nav_order": parent.nav_order or 0,
				"read_only_notice": parent.read_only_notice or None,
				"empty_notice": parent.empty_notice or None,
				"owner_field": parent.owner_field,
				"owner_doctype": parent.owner_doctype or None,
				"title_field": parent.title_field or None,
				"singular": bool(parent.is_singular),
				"allow_new": bool(parent.allow_new),
				"allow_delete": bool(parent.allow_delete),
				"filters": _parse_filters(parent.record_filters),
				"fields": fields,
				"display": tuple(row.fieldname for row in fields if row.viewable),
				"proposable": tuple(row.fieldname for row in fields if row.viewable and row.proposable),
			}
		return found

	# Not `shared`: that flag drops the site name from the key, so every site on
	# a bench would read whichever one warmed the cache last -- one site's
	# proposable fields answering another site's permission check. Per-site is
	# what "cached for the site" meant, and it is what the key does now.
	return frappe.cache.get_value(POLICY_CACHE_KEY, build)


def _parse_filters(raw: str | None) -> dict:
	"""Stored JSON, or nothing. Never an error: the document validated it on the
	way in, and a page is not the place to discover that it did not."""
	if not (raw or "").strip():
		return {}
	try:
		parsed = json.loads(raw)
	except ValueError:
		return {}
	return parsed if isinstance(parsed, dict) else {}


def registered() -> list[str]:
	"""The doctypes that are self-service here, in the order they should be offered."""
	return [
		current["doctype"]
		for current in sorted(policies().values(), key=lambda row: (row["nav_order"], row["label"]))
	]


def by_slug(slug: str) -> dict:
	"""The configuration a page address refers to, or a refusal.

	Throwing rather than returning None: a slug nobody configured is not a page,
	and every caller needs the answer rather than a `None` to check for.
	"""
	for current in policies().values():
		if current["slug"] == slug:
			return current
	frappe.throw(
		frappe._("There is no self-service page at {0}.").format(slug),
		frappe.DoesNotExistError,
	)


def field_definitions(doctype: str) -> list[dict]:
	"""Every viewable field, grouped into sections, as the page should draw it.

	The configuration says which fields and how they are grouped; everything
	else -- the label, the control, a select's options, a link's target, whether
	it is mandatory -- is read from the doctype's own meta here. Restating any of
	that in the configuration would mean a label that drifts from the one the
	desk shows and a select whose options are a year out of date.

	A field the doctype no longer has is dropped rather than trusted: an upstream
	rename shows up as a field quietly leaving the page, not as a read that
	throws.
	"""
	meta = frappe.get_meta(doctype)
	sections: list[dict] = []
	index: dict[str, dict] = {}

	for row in policy(doctype)["fields"]:
		if not row.viewable or not meta.has_field(row.fieldname):
			continue
		field = meta.get_field(row.fieldname)
		section = index.get(row.section)
		if section is None:
			section = {"title": row.section, "fields": []}
			index[row.section] = section
			sections.append(section)
		section["fields"].append(
			{
				"fieldname": row.fieldname,
				"label": frappe._(field.label) if field.label else row.fieldname,
				"type": "text" if row.free_text else _control_type(field),
				"options": _select_options(field),
				# A free-form field is drawn as a text box rather than a link
				# search, so the page is not told what to search. The value is
				# still destined for that link -- see `free_text` on the row.
				"doctype": (field.options if field.fieldtype == "Link" and not row.free_text else None),
				"free_text": bool(row.free_text),
				"required": bool(field.reqd),
				"description": frappe._(field.description) if field.description else None,
				"proposable": bool(row.proposable),
			}
		)
	return sections


def _control_type(field) -> str:
	if field.fieldtype == "Data":
		return DATA_CONTROL_TYPES.get(field.options or "", "text")
	return CONTROL_TYPES.get(field.fieldtype, "text")


def _select_options(field) -> list[str]:
	if field.fieldtype != "Select":
		return []
	return [option.strip() for option in (field.options or "").split("\n") if option.strip()]


def policy(doctype: str) -> dict:
	"""The policy for `doctype`, or a refusal.

	Throwing rather than returning None: every caller needs the answer, and a
	doctype nobody registered is not a doctype whose fields are anyone's to
	propose. Saying so once here means no caller has to remember to check.
	"""
	found = policies().get(doctype)
	if not found:
		frappe.throw(
			frappe._("{0} is not set up for self service.").format(frappe._(doctype)),
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
	"""Every field the page needs to fetch, not only the ones it lays out.

	The configured fields are what the sections render. A page needs a little
	more than that to draw itself -- the record's id, the title it is known by,
	its image where the doctype has one, and when it was last touched -- and none
	of those belong in the configuration as rows, because they are not facts the
	page lists. They are added here instead, so an administrator configuring a
	record type never has to know that a header exists.

	Same filtering as the section fields, and for the same reason: a field the
	doctype no longer has is dropped rather than requested, since asking for one
	fails the whole read instead of quietly showing one row fewer.
	"""
	current = policy(doctype)
	meta = frappe.get_meta(doctype)
	essentials = [
		"name",
		current.get("title_field"),
		getattr(meta, "image_field", None),
		"modified",
	]

	seen: list[str] = []
	for fieldname in [*essentials, *current["display"]]:
		if not fieldname or fieldname in seen:
			continue
		if fieldname != "name" and not meta.has_field(fieldname):
			continue
		seen.append(fieldname)
	return seen


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


def owner_value(doctype: str):
	"""The value this policy's `owner_field` should equal for the session user.

	The session user for a policy that names its owner directly, and the name of
	the owning record for one that chains -- an employee's bank accounts are
	found by their employee id, not by their login. `None` when the chain does
	not reach a record this user owns, which every caller reads as "nothing to
	look for".

	Sent to the frontend as well, so a page that lists these rows through the
	document API filters on the same value the server would, without knowing
	whether the policy chains.
	"""
	current = policy(doctype)
	if not current.get("owner_doctype"):
		return frappe.session.user
	parent = session_record(current["owner_doctype"], ["name"])
	return parent.name if parent else None


def session_records(doctype: str, fieldnames: list[str] | None = None, limit: int = 0) -> list:
	"""The records of `doctype` this session owns and may read.

	Through `frappe.get_list`, so the site's permissions decide what comes back.
	The owner filter narrows it to this user's own rows; it is not what makes the
	read safe, and is not trusted to be. A user the site withholds these records
	from gets an empty list whether they own them or not.

	Empty for a user with no read permission at all, rather than the throw
	`get_list` would raise: "you have none here" is the same answer as far as
	every caller is concerned, and one of them is a permissions endpoint that
	must not 500 on the way to saying so.
	"""
	current = policy(doctype)
	if not frappe.has_permission(doctype, "read"):
		return []
	value = owner_value(doctype)
	if value is None:
		return []
	return frappe.get_list(
		doctype,
		filters={current["owner_field"]: value, **(current.get("filters") or {})},
		fields=fieldnames or ["name"],
		limit_page_length=limit,
	)


def session_record(doctype: str, fieldnames: list[str] | None = None):
	"""The one record of `doctype` this session owns and may read, or None.

	Only for a policy marked `singular` -- one employee record per login, so "my
	record" has a single answer and a page can ask for it without naming one. A
	policy that is not singular has no such answer and says so, rather than
	returning whichever row the database offered first: an employee with three
	bank accounts has no "my bank account", and a caller that wanted one is a
	caller with a bug.
	"""
	if not policy(doctype).get("singular"):
		frappe.throw(
			frappe._("There is no single {0} record for a user.").format(doctype),
			frappe.ValidationError,
		)
	rows = session_records(doctype, fieldnames, limit=1)
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
	value = owner_value(doctype)
	if value is None:
		return False
	return bool(frappe.db.exists(doctype, {current["owner_field"]: value, **(current.get("filters") or {})}))


def clear_cache() -> None:
	"""Drop the resolved registry.

	Called whenever a `Self Service Record` is saved or deleted, and on migrate.
	Without it a configuration change would appear to do nothing until something
	else happened to clear the cache.
	"""
	frappe.cache.delete_value(POLICY_CACHE_KEY)
