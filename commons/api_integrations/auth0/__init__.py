"""Accounts on Auth0: the credentials, the token, and the actions, in one place.

This site is a register of who exists; Auth0 is where those people sign in.
Something has to make an account in the second for a person in the first, and
this integration is that something -- as a library of plain functions, not as a
feature. It knows nothing about any doctype. What gets an Auth0 account, when,
and where the resulting id is kept are decisions for whatever is wired to it,
and those decisions are made elsewhere.

What is here
------------
`client` is the way in: the credentials, the Management API token, and one
function, `management`, that makes an authenticated call with it. `users` is the
set of user operations built on that -- find, create, create-or-find, update,
delete, password ticket, verification mail. `api` is the whitelisted surface for
a Server Script or the desk. `commons.api_integrations.doctype.auth0_settings`
is where a System Manager puts the tenant and its credentials -- it sits in the
module's own doctype folder rather than here, because a Frappe module owns its
doctypes at one fixed path and an integration under it is a plain package.

The Management API is large and `users` covers what has been needed. Everything
else is a call rather than a change to this integration, because `client.management`
is public and carries the token, the retry and the error handling::

        client.management("GET", "roles")
        client.management("POST", f"users/{user_id}/roles", json_body={"roles": [...]})

Why app code and not a Server Script
-------------------------------------
This replaced five Server Scripts with a copy of the same twenty lines in each,
and a copy of the client secret in each. The secret is the obvious problem and
not the only one.

A Server Script's body is a row in `tabServer Script`. Anyone with System
Manager can read it in the desk, it is in every database backup as plain text,
and it is exported by name into fixtures. A client secret in one is published to
everyone who can open the Server Script list. Here it is a `Password` field on a
Single -- encrypted in `__Auth`, unreadable once saved, absent from exports --
and the sandbox those scripts run in cannot read it at all. A script may use
Auth0 through this module and still have no way to see the credential it is
using.

The second problem is that a Server Script cannot return a value. It answers by
writing to `frappe.response`, which is the body of whatever HTTP request set the
chain off -- so the obvious fix for the duplication, one script that fetches a
token for the others to call, ends with a Management API token in a response
body sent to a browser. That token can create and delete every user on the
tenant. Nothing here is whitelisted that returns a token, and `api` says so
again where somebody would be tempted to add one.

The third is that none of those scripts could tell one failure from another.
`frappe.make_post_request` raises an `HTTPError` whose status has to be dug out
of `e.response`, and a DNS failure or a timeout raises one with no `.response`
at all -- so the `except` clause written to report the real problem fails with
an `AttributeError` about the reporting. `client.Auth0Error` carries the status
as an attribute, which is what lets `users.ensure` treat a 409 as an ordinary
outcome and `users.delete` treat a 404 as success.

Setting it up
-------------
Open `Auth0 Settings` and fill in the tenant domain, the client id and the
client secret of a machine-to-machine application authorized for the Management
API. Grant that application the scopes for the actions in use -- `create:users`
and `read:users` to make accounts, `update:users` to change them,
`delete:users` to remove them, `create:user_tickets` for password links.

A site that has not done this has no Auth0: `client.available` is false, the
endpoints say so plainly rather than failing at the first request, and nothing
else in the app changes. That is the shape the rest of this app uses for things
a site may or may not have -- see `commons.statement.ledger.available`.
"""
