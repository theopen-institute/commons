"""Accounts in Google Workspace: the delegation, the token, and the actions.

This site is a register of who exists; Google Workspace is where those people
get a mailbox and a company address. Something has to make an account in the
second for a person in the first, and this integration is that something -- as a
library of plain functions, not as a feature. It knows nothing about any
doctype. What gets a Workspace account, when, and where the resulting id is kept
are decisions for whatever is wired to it, and those decisions are made
elsewhere.

It is deliberately the same shape as `commons.api_integrations.auth0`, because
it is the same problem: a settings Single holding a credential, one way in that carries the
token, a library of operations over addresses and ids, and a whitelisted surface
with a role check on it. Where it differs from Auth0 it differs because Google
does, and each of those places says so.

What is here
------------
`client` is the way in: the settings, the delegated access token, and one
function, `directory`, that makes an authenticated Admin SDK call with it.
`users` is the set of operations built on that -- find, create, create-or-find,
update, suspend, delete, password, photo, aliases. `api` is the whitelisted
surface for a Server Script or the desk.
`commons.api_integrations.doctype.google_workspace_settings` is where a System
Manager puts the service account and the administrator it acts as -- it sits in
the module's own doctype folder rather than here, for the reason
`commons.api_integrations` gives.

The Directory API is large and `users` covers what has been needed. Everything
else is a call rather than a change to this integration, because `client.directory`
is public and carries the token, the retry and the error handling::

        client.directory("GET", "orgunits", params={"customerId": "my_customer"})
        client.directory("GET", f"users/{key}/tokens")

with one caveat that has no equivalent in the Auth0 integration: a call needing a
scope this app does not already ask for will fail until that scope is added
*twice* -- in `Extra Scopes` on the settings, and in the Admin console's
domain-wide delegation screen. See `client.SCOPES`.

Three ways Google is not Auth0
-------------------------------
*There is no machine-to-machine grant.* The Directory API has no equivalent of
client credentials: nothing can act on its own behalf, only on behalf of an
administrator. So the credential is a service account key, the token request is
a signed JWT assertion, and the account every call is really made by is the
human named in `Admin Email`. `client` says what that means for setting it up
and for the error you get when it is set up wrongly.

*There is no password-change ticket.* Auth0 hands out a one-time URL and this
app never knows anybody's password. Google has nothing of the kind for an
account an administrator created, so a credential has to be generated here,
returned to whoever is enrolling, and delivered by them. `users.generate_password`
and `users.set_password` are that, and `users.create` explains the consequences
-- including why the request body of exactly two calls in this integration is the
one thing that must never reach an Error Log, and what `client._send` does about
it.

*Nothing here is immediate.* Auth0 creates an account and it is usable. Google
creates an account, answers 200, and then takes its time: a `GET` seconds later
can still be a 404, a photo upload can fail against an account that plainly
exists, and an alias can take hours to start receiving mail. Anything this
integration does after a create belongs in a background job that can retry, not on
the line after it. `users.create` says which calls are affected.

And one way it is worse than Auth0 for reasons that are not technical: an Auth0
account is free and a Workspace account is billed, monthly, until somebody
deletes it. Whatever is wired to `ensure_user` is wired to a recurring cost, and
`api` is stricter than its Auth0 counterpart on that account -- it offers no
delete, and `users.delete` is in the library for a controller that means it.

Setting it up
-------------
In a Google Cloud project, enable the **Admin SDK API**, create a service
account, and generate a JSON key for it. Copy that service account's numeric
**OAuth client ID** -- the number, not its `@...iam.gserviceaccount.com`
address.

In the Workspace Admin console, under Security → Access and data control → API
controls → **Domain-wide delegation**, add that client ID with the scopes in
`client.SCOPES`, comma separated and exact. A scope that differs by a character
is a scope that is not granted, and what comes back is a 403 about
authorisation rather than anything naming the scope.

Then open `Google Workspace Settings` and fill in the administrator to act as --
a super admin, or a custom role holding the User Management privilege, and best
a dedicated non-human account rather than somebody who will one day leave -- and
paste the key file's contents.

A site that has not done this has no Google Workspace: `client.available` is
false, the endpoints say so plainly rather than failing at the first request,
and nothing else in the app changes. That is the shape the rest of this app uses
for things a site may or may not have -- see `commons.statement.ledger.available`.

One thing to check before wiring anything to it: Google increasingly discourages
service account keys, and an organisation with the
`iam.disableServiceAccountKeyCreation` policy in force cannot create one at all
until the project is exempted. That is a conversation with whoever administers
the Cloud organisation, and it is better had before the code than after it.
"""
