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
an address or an Auth0 id and no document, so there is no record to check a
permission against and no per-user rule to apply: whoever can call them can make
an account for any address on the tenant. A site wiring this to a doctype -- a
button on a record, a hook on save -- should call `commons.auth0.users` directly
from that controller and check the permission on *that record* instead, which is
a real check rather than this one. These are for the administrative case and for
Server Scripts.

What is not here, and must not be added, is an endpoint that returns a
Management API token. That is the shape this section replaced -- one Server
Script fetching a token for others to use -- and it cannot be done safely. A
Server Script of type API has no return value; it answers by writing to
`frappe.response`, which *is* the body of the HTTP request that started the
chain. A token returned that way is delivered to the browser, and a Management
API token can create and delete any user on the tenant. The token stays inside
`client`, and callers ask for the thing they wanted rather than for the
credential to do it themselves.

Calling this from a Server Script
---------------------------------
`frappe.call` in the sandbox resolves dotted paths to whitelisted methods, and
unlike a script calling a script it returns a value::

	user_id = frappe.call("commons.auth0.api.ensure_user", email=doc["member_id"])
	frappe.db.set_value(doc["doctype"], doc["name"], "custom_auth0_id", user_id)

That is the whole of what those scripts need to contain now: no domain, no
client id, no secret, no token, and no `except` clause reaching for a status
code on an exception that may not have one.
"""

import frappe
from frappe import _

from commons.auth0 import client, users

# Who may reach the tenant over HTTP. See the module docstring on why this is a
# role and not a document permission.
ROLE = "System Manager"


def _permitted() -> None:
	"""Refuse anyone without the role, before anything reaches Auth0.

	Its own function rather than a decorator so that the check is visible in
	each endpoint, and so that adding one that is *not* checked has to be done
	on purpose rather than by forgetting an import.
	"""
	if ROLE not in frappe.get_roles():
		frappe.throw(_("Not permitted to manage Auth0 accounts."), frappe.PermissionError)


@frappe.whitelist()
def configured() -> bool:
	"""Whether this site has Auth0 set up, for a caller deciding what to draw.

	Says nothing about the credentials themselves, only that there are some --
	which is why this is the one endpoint here without a role check. The
	alternative is a button that exists on every site and explains itself only
	after being pressed.
	"""
	return client.available()


@frappe.whitelist()
def ensure_user(email: str) -> str:
	"""The Auth0 account id for this address, creating the account if there is none.

	The endpoint nearly everything wants. Idempotent by construction -- see
	`users.ensure` -- so it is safe to call again after a timeout, a retry, or
	somebody pressing the button twice.

	It does not take the extra creation fields `users.create` accepts. A
	whitelisted method that forwards an arbitrary body to an identity provider
	is a way to set `app_metadata`, or `email_verified`, on somebody else's
	account from the browser. A caller that needs those has a controller and
	should use `users` from it.
	"""
	_permitted()
	return users.ensure(email)


@frappe.whitelist()
def find_user(email: str) -> str | None:
	"""The id of the account this site manages for this address, or `None`.

	A read, so it makes nothing -- for a page that wants to show whether
	somebody has an account before offering to create one.

	This site's connection only. An address that exists on the tenant solely
	through a federated login -- Azure AD, Google -- answers `None` here,
	because that is a different account and not one this site made or can set a
	password on. `users.find` says why that is the useful answer.
	"""
	_permitted()
	return users.find(email)


@frappe.whitelist()
def get_user(user_id: str) -> dict | None:
	"""One account as Auth0 holds it, or `None` if there is no such account.

	The whole record, including `app_metadata`. It is behind the role check for
	that reason: it is the most revealing thing here.
	"""
	_permitted()
	return users.get(user_id)


@frappe.whitelist()
def password_change_ticket(
	user_id: str,
	result_url: str | None = None,
	mark_email_as_verified: bool = False,
	include_email_in_redirect: bool | None = None,
) -> str:
	"""A one-time URL where the holder of this account can set their password.

	How somebody enrolled by this site first gets in; `users.create` explains
	why they need it. The link is a credential for the seconds it lives -- it is
	returned to the caller to be sent on, and should not be logged, printed or
	put in a field.

	`mark_email_as_verified` is exposed because the caller is the only thing
	that knows how the link is being delivered, and that is what decides whether
	using it proves anything -- `users.password_change_ticket` says which way
	round. It is a claim that somebody owns an address, so it sits behind the
	same role check as everything else here.
	"""
	_permitted()
	return users.password_change_ticket(
		user_id,
		result_url=result_url,
		mark_email_as_verified=mark_email_as_verified,
		include_email_in_redirect=include_email_in_redirect,
	)


@frappe.whitelist()
def send_verification_email(user_id: str) -> dict:
	"""Ask Auth0 to send its "confirm your address" mail to this account."""
	_permitted()
	return users.send_verification_email(user_id)
