"""The ways in from outside: a Server Script, a desk button, the SPA.

Thin wrappers over `users`, and the reason they are separate from it is the
first line of each: a permission check. `users` is the library -- callable from
a document event, a patch, a scheduled job, with no session in sight -- and
putting a check inside it would make all of those impossible without the
`ignore_permissions` argument nobody can audit. This module is the other half:
everything reachable over HTTP, and nothing reachable over HTTP that has not
been checked.

Who may call these
------------------
`System Manager`, and that is a deliberately blunt answer. These endpoints take
an address or a Google id and no document, so there is no record to check a
permission against and no per-user rule to apply: whoever can call them can make
an account for any address in the domain. A site wiring this to a doctype -- a
button on a record, a hook on save -- should call `commons.api_integrations.google_workspace.users`
directly from that controller and check the permission on *that record* instead,
which is a real check rather than this one. These are for the administrative
case and for Server Scripts.

Why these are not the Auth0 endpoints with the names changed
-------------------------------------------------------------
Two differences, and both are the same difference: a Workspace account costs
money and holds a person's mail.

*Nothing here deletes.* `commons.api_integrations.google_workspace.users.delete` exists and is
not wrapped. Deleting takes somebody's mailbox and their Drive with it and holds
their address for twenty days afterwards, and that is not a thing to be one
mistyped id away from over HTTP. `suspend_user` is what offboarding wants and is
reversible; a controller that genuinely means to delete calls the library.

*Creating is a purchase.* Whatever is wired to `ensure_user` is wired to a
recurring bill, so it is idempotent by construction -- see
`commons.api_integrations.google_workspace.users.ensure` -- and safe to call again after a
timeout, a retry, or somebody pressing the button twice.

Why these take named arguments and not a body
----------------------------------------------
`commons.api_integrations.auth0.api.ensure_user` takes an address and nothing else, on the
grounds that a whitelisted method forwarding an arbitrary body to an identity
provider is a way to set anything at all on somebody else's account from a
browser. That reasoning is right and the same conclusion would make this integration
useless, because the fields are the point: a Server Script here has to be able
to send a phone number and a recovery address.

So the allowlist is the signature. Every field these endpoints will write is a
named argument with a name of this app's choosing, mapped to Google's spelling
in `_profile` below. What is *not* reachable is everything not named there --
`isAdmin`, `customSchemas`, `hashFunction`, `suspended` on a create, `emails`
with its replace-the-whole-list behaviour. Adding a field is adding an argument,
which is a decision somebody makes on purpose rather than by forwarding a dict.

Credentials in return values
----------------------------
`ensure_user` and `set_user_password` return a password. There is no way around
that -- Google has no equivalent of Auth0's one-time ticket, so an account this
app creates is reachable only by a credential this app generates -- and it makes
those two the only endpoints in either integration whose *response body* is a
secret.

It is good for one sign-in, because both set `changePasswordAtNextLogin`. It
should be shown to whoever is enrolling the person and then forgotten: not
logged, not put in a field, not emailed to a list, not left in a comment on the
record. `ensure_user` returns `None` for it rather than a fresh one when the
account already existed, so a caller cannot mistake an idempotent second call
for a working credential.

Calling this from a Server Script
---------------------------------
`frappe.call` in the sandbox resolves dotted paths to whitelisted methods, and
unlike a script calling a script it returns a value::

        answer = frappe.call(
            "commons.api_integrations.google_workspace.api.ensure_user",
            email=doc["company_email"],
            given_name=doc["first_name"],
            family_name=doc["last_name"],
            phone=doc["cell_number"],
            recovery_email=doc["personal_email"],
        )
        frappe.db.set_value(doc["doctype"], doc["name"], "custom_google_id", answer["id"])
        if answer["created"]:
            # hand answer["password"] to whoever is enrolling them, and keep no copy
            ...

That is the whole of what such a script needs to contain: no domain, no service
account, no private key, no assertion, and no `except` clause reaching for a
status code on an exception that may not have one.
"""

import frappe
from frappe import _

from commons.api_integrations.google_workspace import client, users

# Who may reach the domain over HTTP. See the module docstring on why this is a
# role and not a document permission.
ROLE = "System Manager"


def _permitted() -> None:
	"""Refuse anyone without the role, before anything reaches Google.

	Its own function rather than a decorator so that the check is visible in
	each endpoint, and so that adding one that is *not* checked has to be done
	on purpose rather than by forgetting an import.
	"""
	if ROLE not in frappe.get_roles():
		frappe.throw(_("Not permitted to manage Google Workspace accounts."), frappe.PermissionError)


def _refuse_administrators(user_key: str) -> None:
	"""Refuse to change an administrator's account from here.

	Every call this integration makes runs as the super administrator it is
	delegated to act for, so without this a System Manager on the site could
	reset a domain administrator's password -- or point their recovery address at
	themselves -- and hold the whole Workspace domain. Site roles and domain
	administration are kept apart: administrators, delegated administrators and
	the account this integration impersonates are managed in the Admin console,
	where Google asks who is making the change. An account Google does not know is
	left to the call itself to report.
	"""
	record = users.get(user_key)
	if not record:
		return
	impersonated = (client.credentials().admin_email or "").strip().lower()
	addresses = {(record.get("primaryEmail") or "").lower()} | {
		(entry.get("address") or "").lower() for entry in record.get("emails") or []
	}
	if (
		record.get("isAdmin")
		or record.get("isDelegatedAdmin")
		or (impersonated and impersonated in addresses)
	):
		frappe.throw(
			_(
				"{0} is a Google Workspace administrator. Change administrator accounts in the Admin console."
			).format(record.get("primaryEmail") or user_key),
			frappe.PermissionError,
		)


def _phone(number: str) -> str:
	"""A recovery number in the form Google insists on, or a sentence saying so.

	`recoveryPhone` must be E.164 -- a leading `+`, then digits, nothing else.
	Google rejects anything that is not, with a 400 naming a field rather than
	the rule, and the value a site has on file is nearly always spaced, bracketed
	or written with a leading zero instead. The spacing is cleaned up here
	because it is unambiguous; the missing country code is not, so that is
	asked for rather than guessed at.
	"""
	cleaned = "".join(piece for piece in number.strip() if piece.isdigit() or piece == "+")
	if not cleaned.startswith("+") or len(cleaned) < 8:
		frappe.throw(
			_(
				"{0} is not a recovery number Google will take. It has to be in international"
				" form, starting with + and the country code -- +254712345678, not 0712345678."
			).format(number)
		)
	return cleaned


def _profile(
	phone: str | None = None,
	recovery_email: str | None = None,
	recovery_phone: str | None = None,
	job_title: str | None = None,
	department: str | None = None,
	employee_id: str | None = None,
	org_unit_path: str | None = None,
) -> dict:
	"""The named arguments above, in Google's spelling, with the blanks left out.

	The allowlist the module docstring describes, in one place because
	`ensure_user` and `update_user` offer the same fields and must not drift.

	Anything left `None` is absent from the result rather than sent as null. On
	a create that is the difference between a field Google fills in for itself
	and one it is told to leave empty; on an update it is the difference between
	not touching a value and erasing it. There is deliberately no way to erase
	one through this module -- `users.update` is where that is done, by a caller
	that means it.

	`phones`, `organizations` and `externalIds` are Google's list-valued fields,
	and passing one entry *replaces* every entry that was there. That is right
	on a create and is a thing to know on an update, which is why `update_user`
	says so again. A person with two numbers on file is beyond what these
	endpoints do; `users.update` and a read-append-write is how that is done.
	"""
	built: dict = {}

	if phone:
		built["phones"] = [{"value": phone.strip(), "type": "work", "primary": True}]
	if recovery_email:
		built["recoveryEmail"] = recovery_email.strip()
	if recovery_phone:
		built["recoveryPhone"] = _phone(recovery_phone)
	if job_title or department:
		organization: dict = {"primary": True}
		if job_title:
			organization["title"] = job_title.strip()
		if department:
			organization["department"] = department.strip()
		built["organizations"] = [organization]
	if employee_id:
		built["externalIds"] = [{"value": employee_id.strip(), "type": "organization"}]
	if org_unit_path:
		built["orgUnitPath"] = org_unit_path.strip()

	return built


@frappe.whitelist()
def configured() -> bool:
	"""Whether this site has Google Workspace set up, for a caller deciding what to draw.

	Says nothing about the credentials themselves, only that there are some --
	which is why this is the one endpoint here without a role check. The
	alternative is a button that exists on every site and explains itself only
	after being pressed.
	"""
	return client.available()


@frappe.whitelist()
def find_user(email: str) -> str | None:
	"""The id of the account reachable at this address, or `None`.

	A read, so it makes nothing -- for a page that wants to show whether
	somebody has an account before offering to create one, and for a script
	checking before it spends money.

	Aliases count, because Google resolves them. An address that is somebody
	else's alias answers with *their* id, which is the useful answer to "is this
	address free" and a surprising one to anybody reading it as "is this their
	account". `user_aliases` tells the two apart.
	"""
	_permitted()
	return users.find(email)


@frappe.whitelist()
def get_user(user_key: str) -> dict | None:
	"""One account as Google holds it, or `None` if there is no such account.

	The whole directory record -- addresses, aliases, phone numbers, org unit,
	last login, whether they are an administrator. It is behind the role check
	for that reason: it is the most revealing thing here.
	"""
	_permitted()
	return users.get(user_key)


@frappe.whitelist()
def search_users(query: str, max_results: int = users.PAGE_SIZE) -> list[dict]:
	"""Accounts matching a Directory API search expression -- one page of them.

	`"givenName:ann*"`, `"orgUnitPath=/Staff"`, `"isSuspended=true"`. Served from
	Google's search index, which lags the directory by minutes, so this answers
	questions about the domain and not the question of whether one account
	exists -- `find_user` is that one.
	"""
	_permitted()
	return users.search(query, max_results=max_results)


@frappe.whitelist()
def ensure_user(
	email: str,
	given_name: str,
	family_name: str,
	phone: str | None = None,
	recovery_email: str | None = None,
	recovery_phone: str | None = None,
	job_title: str | None = None,
	department: str | None = None,
	employee_id: str | None = None,
	org_unit_path: str | None = None,
) -> dict:
	"""The account for this address, creating it if there is none, and how to sign in.

	The endpoint nearly everything wants, and the one that spends money.
	Idempotent by construction, so it is safe to call again after a timeout, a
	retry, or somebody pressing the button twice -- and the answer says which
	of those happened::

	        {"id": "114...", "created": True, "password": "xK4$..."}
	        {"id": "114...", "created": False, "password": None}

	`created` is not a guess and not the result of a lookup done beforehand,
	which a second request arriving in between would make wrong. It is which
	branch Google's own uniqueness check sent this down: a 409 means the account
	was already there, the generated password was never applied to anything, and
	returning it would hand the caller a credential that does not work.

	So `password` is present exactly once in an account's life, on the call that
	created it. It is good for one sign-in and then has to be changed. Read the
	module docstring on what to do with it, which is mostly a list of things not
	to do with it.

	The fields are applied only on creation. An account that already exists is
	returned as it stands and not rewritten to match what this caller happened
	to pass -- `update_user` is where that is done deliberately.

	`recovery_email` is the field to reach for when somebody says "alternate
	email address" and means a personal one. An alternate address at *your own*
	domain is an alias and is `add_user_alias`; both are worth setting, and
	neither is the directory's `emails` list, which these endpoints do not touch
	for the reason `_profile` gives.
	"""
	_permitted()

	fields = _profile(
		phone=phone,
		recovery_email=recovery_email,
		recovery_phone=recovery_phone,
		job_title=job_title,
		department=department,
		employee_id=employee_id,
		org_unit_path=org_unit_path,
	)

	password = users.generate_password()
	try:
		user_id = users.create(email, given_name, family_name, password=password, **fields)
	except client.GoogleWorkspaceError as refusal:
		if refusal.status != users.ALREADY_EXISTS:
			raise
		# The password was never applied to anything. Saying so is the whole
		# point of this branch being separate.
		return {"id": users.recover_existing(email), "created": False, "password": None}

	return {"id": user_id, "created": True, "password": password}


@frappe.whitelist()
def update_user(
	user_key: str,
	given_name: str | None = None,
	family_name: str | None = None,
	phone: str | None = None,
	recovery_email: str | None = None,
	recovery_phone: str | None = None,
	job_title: str | None = None,
	department: str | None = None,
	employee_id: str | None = None,
	org_unit_path: str | None = None,
) -> dict:
	"""Change an existing account, and return it as Google now holds it.

	Only the arguments given are touched; anything left out is left alone. There
	is no way to *clear* a field here, deliberately -- an omitted argument and an
	argument meaning "erase this" would be the same value over HTTP, and
	`users.update` is where a caller that means to erase says so.

	`phone`, `job_title`/`department` and `employee_id` each write one of
	Google's list-valued fields, and a list-valued field is replaced whole. So
	setting a phone number here removes any other number on the account, and
	setting a job title removes any other organisation entry. For an account
	this app created that is exactly right, because it put the single entry
	there; for one maintained in the Admin console as well it is worth knowing
	before the first call. `commons.api_integrations.google_workspace.users.update` shows the
	read-append-write for the other case.

	Not reachable here: the primary address. Changing it renames the account and
	leaves the old address behind as an alias, which is a migration rather than
	an edit and should not be a stray argument on a general-purpose update.
	"""
	_permitted()
	_refuse_administrators(user_key)

	fields = _profile(
		phone=phone,
		recovery_email=recovery_email,
		recovery_phone=recovery_phone,
		job_title=job_title,
		department=department,
		employee_id=employee_id,
		org_unit_path=org_unit_path,
	)

	name: dict = {}
	if given_name:
		name["givenName"] = given_name.strip()
	if family_name:
		name["familyName"] = family_name.strip()
	if name:
		# Google merges this one rather than replacing it, so a given name on
		# its own does not take the family name with it.
		fields["name"] = name

	if not fields:
		frappe.throw(_("Nothing to change."))

	return users.update(user_key, **fields)


@frappe.whitelist()
def set_user_password(user_key: str, change_at_next_login: bool = True) -> str:
	"""Give this account a new password, and return it.

	How somebody gets back in when the one from `ensure_user` was lost, never
	delivered, or never generated because the account was made before this app
	touched it. The nearest thing here to Auth0's password change ticket, and
	notably less safe: a ticket can only be used by whoever opens it, and this
	is a credential that works for anybody who reads it.

	Which is why it is the caller's job to move it and nobody's job to keep it.
	It is returned and not stored, it is good for one sign-in, and it should go
	by a channel that is not the same one somebody has just lost access to.

	The password is generated here rather than accepted as an argument. A
	password chosen by the caller travels through a request body, a Server
	Script, possibly a form field and whatever logs any of those keep, and there
	is no reason for anybody to choose one -- the account holder picks their own
	on the next screen.

	`change_at_next_login` is on unless a caller turns it off, and the one
	reason to turn it off is a shared mailbox or a service account where there
	is no person to do the picking.
	"""
	_permitted()
	_refuse_administrators(user_key)
	return users.set_password(user_key, change_at_next_login=change_at_next_login)


@frappe.whitelist()
def suspend_user(user_key: str, suspended: bool = True) -> dict:
	"""Suspend this account, or restore it, and return it as it now stands.

	What offboarding means here. The mail, the files, the group memberships and
	the address all survive, so nothing is lost and the address cannot be handed
	to somebody else by mistake; restoring is this call with `suspended` false.

	It does not stop the billing -- a suspended account still holds its licence.
	Deleting is what stops that, and deleting is not reachable over HTTP; see
	the module docstring.
	"""
	_permitted()
	_refuse_administrators(user_key)
	return users.suspend(user_key, suspended=suspended)


@frappe.whitelist()
def user_aliases(user_key: str) -> list[str]:
	"""Every additional address this account receives mail at."""
	_permitted()
	return users.aliases(user_key)


@frappe.whitelist()
def add_user_alias(user_key: str, alias: str) -> dict:
	"""Give this account another address at a domain this Workspace account owns.

	What "a second email address at our domain" actually is. It is not a change
	to the directory's `emails` list, and it is not free of delay: Google allows
	up to twenty-four hours before mail sent to a new alias is delivered, so an
	alias added and then tested immediately looks broken when it is only young.

	A duplicate is refused rather than ignored, because an alias that already
	exists may be on somebody else's account.
	"""
	_permitted()
	_refuse_administrators(user_key)
	return users.add_alias(user_key, alias)


@frappe.whitelist()
def remove_user_alias(user_key: str, alias: str) -> None:
	"""Take an address away from this account, or do nothing if it has none."""
	_permitted()
	_refuse_administrators(user_key)
	users.remove_alias(user_key, alias)


@frappe.whitelist()
def set_user_photo(user_key: str, file_url: str) -> dict:
	"""Put a `File` on this site onto this account as its profile photo.

	A `File` rather than the bytes, because that is what both callers actually
	have: the SPA uploads through Frappe's own uploader and gets a `file_url`
	back, and a Server Script has one on a record. The library takes bytes --
	`commons.api_integrations.google_workspace.users.set_photo` -- for anything that does not.

	`encodings=[]` on `get_content` is not a detail. Left to itself it tries
	`utf-8-sig`, `utf-8`, `windows-1250` and `windows-1252` in turn and returns a
	`str` if any of them succeeds -- and `windows-1252` decodes very nearly any
	byte sequence, so a JPEG comes back as mojibake that re-encodes to different
	bytes than the ones on disk. Asking for no decoding at all is how the file
	that was uploaded is the file that is sent.

	Called straight after `ensure_user` this will sometimes fail against an
	account that was genuinely created, because a new account is not immediately
	addressable -- see `commons.api_integrations.google_workspace.users`. Somewhere that can retry
	is where this belongs.
	"""
	_permitted()
	_refuse_administrators(user_key)

	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		frappe.throw(_("There is no file at {0} on this site.").format(file_url))

	content = frappe.get_doc("File", name).get_content(encodings=[])
	if not isinstance(content, bytes):
		# Unreachable while `encodings=[]` means what it says. Refused rather
		# than re-encoded, because the bytes cannot be recovered without knowing
		# which codec decoded them -- and a photo that is silently wrong is
		# worse than one that did not upload.
		frappe.throw(
			_("{0} could not be read as an image. It may not be a file this site holds on disk.").format(
				file_url
			)
		)

	return users.set_photo(user_key, content)


@frappe.whitelist()
def remove_user_photo(user_key: str) -> None:
	"""Take the photo off this account, or do nothing if it has none.

	Google goes back to drawing the letter avatar from the person's name.
	"""
	_permitted()
	_refuse_administrators(user_key)
	users.remove_photo(user_key)
