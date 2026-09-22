"""Accounts on Auth0: the user operations, as plain functions over addresses and ids.

Nothing here knows about a doctype, a field or a record. These take an address
or an Auth0 user id and return an account or an id, and whatever on this site
wants to hold on to the result decides that for itself -- a document event, a
button, a Server Script, a patch. That is the whole reason this is a section of
its own rather than five lines inside somebody's controller.

Addresses in, ids out
---------------------
An address is what the two systems can agree on to begin with: Auth0's database
connections treat email as unique within a connection, and a site's own records
are usually keyed or indexed by it too. So "does this person have an account"
starts as a question about an address.

What should be stored afterwards is the `user_id` -- `auth0|65f...` -- and not
the address. An address can be changed, by the person or by an administrator, on
either side and without the other being told; an integration that re-derives the
account from the current address quietly starts pointing at a different one, or
at nothing, the first time that happens. The id never moves. Every function that
creates or finds an account here returns the id for that reason.

Extending this
--------------
The Management API is large and this is the part of it this app has needed.
Anything else is a call rather than a change here::

	client.management("GET", "roles")
	client.management("POST", f"users/{user_id}/roles", json_body={"roles": [...]})
	client.management("GET", "users", params={"q": 'email:"a@b.c"', "search_engine": "v3"})

`client.management` is public and carries the token, the retry and the error
handling, so a wrapper is worth adding here only when there is something to say
beyond the path -- which is what each of the functions below has.
"""

from urllib.parse import quote

import frappe
from frappe import _

from commons.auth0 import client

# "A user with this email already exists in this connection."
ALREADY_EXISTS = 409

# "No such user." Meaningful to `delete`, which is asked to reach an end state
# rather than to perform an act.
NOT_FOUND = 404

# The length of the password new accounts are given. Not a number anybody needs
# to match -- see `create` on why nothing ever reads it back.
PASSWORD_LENGTH = 32


def _segment(user_id: str) -> str:
	"""An Auth0 user id, escaped to be one path segment and no more.

	`safe=""` rather than Frappe's own `quoted`, which leaves `/` alone because
	it is meant for whole URLs. An id is a provider name and an identifier
	joined by a pipe -- `auth0|65f...`, `google-oauth2|1057...` -- and the pipe
	has to be escaped for the path to be valid at all. Nothing stops a federated
	provider putting a slash in one, and an unescaped slash there does not fail:
	it reaches a different endpoint.
	"""
	return quote(user_id, safe="")


def get(user_id: str) -> dict | None:
	"""One account by its Auth0 id, or `None` if there is no such account.

	`None` rather than a refusal, because the ordinary caller is checking
	whether an id it stored a year ago still points at anything -- an account
	deleted in the Auth0 dashboard is a state to handle, not an error to raise.
	Every other refusal still raises: a missing scope must not read as an
	account that is not there.
	"""
	try:
		return client.management("GET", f"users/{_segment(user_id)}")
	except client.Auth0Error as refusal:
		if refusal.status == NOT_FOUND:
			return None
		raise


def find(email: str) -> str | None:
	"""The id of the account holding this address, or `None`.

	`users-by-email` rather than a search query: it is the endpoint Auth0
	documents for exactly this, it is not subject to the search index's eventual
	consistency -- an account created a second ago is findable by it and is
	frequently not yet findable by search -- and it does not need the extra
	scopes the general search endpoint tends to want. It does need `read:users`,
	which is the grant most likely to be missing on an application set up only
	to create accounts.

	More than one match is possible in principle: the same address in two
	connections on the same tenant. The first with an id is taken, because a
	tenant that grew a second connection needs to say which one it means rather
	than have this answer differently depending on the order Auth0 replied in.
	Callers that care should use `search` and look at `identities`.
	"""
	for match in search_by_email(email):
		if match.get("user_id"):
			return match["user_id"]
	return None


def search_by_email(email: str) -> list[dict]:
	"""Every account holding this address, whole, in Auth0's order.

	The unreduced answer behind `find`, for the callers that need to see more
	than an id -- which connection an account is in, whether the address is
	verified, what is in `app_metadata`.
	"""
	return client.management("GET", "users-by-email", params={"email": email}) or []


def create(email: str, **fields) -> str:
	"""A new account for this address, and the id it was given.

	`fields` goes to Auth0 as it is, so anything the endpoint accepts can be
	passed without this function growing an argument for it -- `given_name`,
	`family_name`, `name`, `nickname`, `picture`, `user_metadata`,
	`app_metadata`, `verify_email`. Anything given there wins over the defaults
	below, including `password` and `connection`, so a caller with its own
	arrangement is not fighting this one.

	The default password is random and is thrown away. Nobody is told it, it is
	not stored, and it is not derivable: an account made here is reached by its
	holder through Auth0's own password reset or invitation flow, which is the
	only way somebody ends up with a credential this site never knew. Pass
	`verify_email=True` to have Auth0 send that mail on creation, or use
	`password_change_ticket` to hand out a link.

	`frappe.generate_hash(length=...)` with no text, which is the random one.
	Its two-argument form hashes whatever it is given, so a fixed salt passed to
	it gives every account created by the same code the same password -- one
	shared credential across every user on the tenant, sitting in the source
	that made them.

	`email_verified` is `False`, the boolean. Auth0 reads the string `"false"`
	as a value rather than as a negative, and an account created with it is
	marked verified -- the wrong side of the one flag that decides whether
	somebody has to prove they own the address they signed up with.
	"""
	body = {
		"connection": client.credentials().connection,
		"email": email,
		"email_verified": False,
		"password": frappe.generate_hash(length=PASSWORD_LENGTH),
	}
	body.update(fields)

	created = client.management("POST", "users", json_body=body)
	user_id = (created or {}).get("user_id")
	if not user_id:
		frappe.throw(_("Auth0 created the account but returned no user id."), exc=client.Auth0Error)
	return user_id


def ensure(email: str, **fields) -> str:
	"""This address's account id, creating the account if there is not one.

	Create first, look up only if that is refused. The other order -- look up,
	create if absent -- costs an extra call on the ordinary path and is still
	wrong: two requests can both find nothing and both try to create, and one of
	them gets the 409 anyway. Auth0's own uniqueness check is the authority on
	whether an account exists, so it is what gets asked, and the lookup is the
	recovery rather than the test.

	The recovery is needed because the 409 body does not carry the id of the
	account it is complaining about, only that there is one. That is what makes
	`read:users` a required scope even on a tenant where this site never does
	anything but create, and it is reached on the ordinary run of things: anyone
	enrolled twice, any record re-saved, any button pressed a second time.

	`fields` is applied only when the account is created. An existing account is
	returned as it stands and not quietly rewritten to match what this caller
	happened to pass -- overwriting somebody's name or metadata is a decision,
	and `update` is where it is made deliberately.

	`None` from `find` after a 409 is genuinely contradictory: Auth0 has said in
	one breath that the address is taken and in the next that nothing holds it.
	The honest readings are a missing `read:users` scope or an account in
	another connection, so it says so rather than returning nothing and letting
	a caller store an empty id.
	"""
	try:
		return create(email, **fields)
	except client.Auth0Error as refusal:
		if refusal.status != ALREADY_EXISTS:
			raise

	existing = find(email)
	if not existing:
		frappe.throw(
			_(
				"Auth0 says an account already exists for {0}, but no account with that address"
				" could be found. Check that this application has the read:users scope, and that"
				" the account is not in a different connection."
			).format(email),
			exc=client.Auth0Error,
		)
	return existing


def update(user_id: str, **fields) -> dict:
	"""Change an account, and return it as Auth0 now holds it.

	A PATCH, so only what is passed is touched and everything else is left
	alone. Two things Auth0 is particular about, both of which read as puzzling
	400s: `email` and `password` may not be changed in the same request as other
	attributes, and changing either on a database account requires `connection`
	in the body as well.

	`user_metadata` and `app_metadata` are merged by Auth0 a level deep rather
	than replaced, and a key set to `null` is how one is removed.
	"""
	return client.management("PATCH", f"users/{_segment(user_id)}", json_body=fields)


def delete(user_id: str) -> None:
	"""Remove an account, or do nothing if it is already gone.

	An end state rather than an act: a caller tidying up after a record has no
	use for a 404 about an account somebody removed in the dashboard last month,
	and treating it as an error means every caller writes the same `try` around
	it. Every other refusal still raises.
	"""
	try:
		client.management("DELETE", f"users/{_segment(user_id)}")
	except client.Auth0Error as refusal:
		if refusal.status != NOT_FOUND:
			raise


def password_change_ticket(user_id: str, result_url: str | None = None, ttl_seconds: int | None = None) -> str:
	"""A one-time URL where somebody can set their own password.

	The answer to the question `create` raises -- an account exists, its
	password is random and unknown, so how does its holder ever get in. This is
	a link that can be sent to them, or shown once to whoever is enrolling them,
	and it is the only way a credential this site never knew becomes one they
	can use.

	`result_url` is where Auth0 sends them afterwards; without it they land on
	Auth0's own confirmation page. `ttl_seconds` overrides the tenant's default
	lifetime -- worth setting deliberately for a link that goes into a letter or
	an onboarding mail rather than a session somebody is sitting in.

	Needs `create:user_tickets`, which is a separate grant from the user scopes.
	"""
	body: dict = {"user_id": user_id}
	if result_url:
		body["result_url"] = result_url
	if ttl_seconds:
		body["ttl_sec"] = ttl_seconds

	ticket = client.management("POST", "tickets/password-change", json_body=body)
	url = (ticket or {}).get("ticket")
	if not url:
		frappe.throw(_("Auth0 returned no password change ticket."), exc=client.Auth0Error)
	return url


def send_verification_email(user_id: str) -> dict:
	"""Ask Auth0 to send its "confirm your address" mail, and return the job.

	A job rather than a send: Auth0 queues it and answers with an id, so a
	successful return means accepted, not delivered. Whether the mail actually
	goes anywhere depends on the tenant having an email provider configured --
	a tenant still on Auth0's development mailer will accept this and deliver
	nothing useful.
	"""
	return client.management("POST", "jobs/verification-email", json_body={"user_id": user_id})
