"""The outside services this site holds an account with, one package each.

A site does things that are not its own to do: it makes somebody a login, gives
them a mailbox, sends a message, takes a payment. Each of those is an account
with a third party, a credential to keep, a token to mint, and a handful of
calls -- and each of them is a package under here.

What is here now is `auth0` and `google_workspace`. What is expected is more of
them, which is the whole reason this module exists.

Why one module and not one per service
---------------------------------------
Because a Frappe module is not a folder. It is a line in `modules.txt`, a
`Module Def` on every site the app is installed on, a name in the doctype
dropdown, an entry in the desk's module list, and a directory the doctype sync
walks on every migrate. That is a fair price for `Statement` or `Requests`,
which are bodies of work. It is not a fair price for the eighty lines it takes
to talk to an SMS gateway, and an app that expected a dozen of those would pay
it a dozen times for nothing.

What actually earns a module is owning a doctype -- `commons.commons_core` says
so in as many words -- and every integration owns exactly one: its settings
Single. Those all live in this module's `doctype/` folder, which is the one
place Frappe will look for them, and the code that uses each one lives in a
plain package beside it. One module, one line, one `Module Def`, and the next
integration is a directory rather than a migration.

The cost, paid once: the dotted path to an integration is
`commons.api_integrations.<service>` rather than `commons.<service>`, and a
Server Script calling one names it that way.

The layout
----------
::

	api_integrations/
		<service>/                     the code: client, operations, endpoints
		doctype/<service>_settings/    the credentials, as a Single

Nothing at the root but this file. There is no shared client, no base class and
no common error type, and that is not an omission waiting to be corrected --
`auth0` and `google_workspace` are the same *shape* and share no *code*, because
the interesting part of each is exactly where they differ: one asks for a token
on its own behalf, the other signs an assertion to impersonate an
administrator. A base class over those two would be a place to put an `if`.

What would earn a place at the root is something every integration genuinely
needs and none of them should answer twice -- a registry of which services this
site has configured, say, for a page deciding what to draw. When there is a
third integration and two of them want the same thing, that is the moment; not
before, and not on the strength of two things looking alike.

What belongs in here
--------------------
The test is a service this site holds an account with, reached over the network,
that knows nothing about any doctype. Every package here is a library: it takes
an address, an id, a message, and returns an id or an answer. What on this site
should have a Google account, which record holds the Auth0 id, when the mail
goes out -- none of that is decided here. It is decided by whatever is wired to
it, and that is somebody else's section, or a Server Script, or a document
event.

The inverse is the useful half of the test. Something that reads this site's
doctypes and calls out to a service is not an integration in this sense, it is a
feature that happens to make a call, and it belongs with the section whose
doctypes it reads. `commons.statement` would not move in here if it learned to
email a statement.

The shape each one takes
------------------------
Not enforced, and worth following anyway, because it is the shape both of these
arrived at independently and every reader of the second one gets it for free:

``client``
	The way in. The credentials off the Single, the token and its cache, and one
	public function that makes an authenticated call. An error type carrying the
	HTTP status, so callers can tell a refusal from an outage. An `available()`
	that answers whether the site has this service at all, the way
	`commons.statement.ledger.available` does, so a page can leave a button out
	rather than offer one that explains itself after being pressed.

``<operations>``
	The verbs, as plain functions over addresses and ids. `users` in both of the
	current two. No permission checks, no session assumed, callable from a patch
	or a scheduled job.

``api``
	The whitelisted surface, and nothing whitelisted that has not been permission
	checked. Named arguments rather than a forwarded body, so what a browser can
	write is the signature rather than whatever the remote service accepts.

And the one rule that is not a convention: **nothing whitelisted ever returns a
credential the site holds.** Not a client secret, not a private key, and above
all not a management token -- a token that can create and delete every account
at the other end must not be obtainable by asking this site for it. Callers ask
for the thing they wanted, not for the means to do it themselves.
`commons.api_integrations.auth0.api` explains what that replaced and why a
Server Script cannot be trusted to do it instead.
"""
