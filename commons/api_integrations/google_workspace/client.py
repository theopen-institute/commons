"""The way in to Google Workspace: the delegation, the token, and one call.

Everything this integration does to Google goes through `directory` below, and
`directory` is public for exactly that reason. The Admin SDK has a great many
endpoints; `users` wraps the handful this app has needed so far, and anything
else is one line at the call site rather than a change to this file::

        client.directory("GET", "orgunits", params={"customerId": "my_customer"})
        client.directory("POST", f"users/{key}/makeAdmin", json_body={"status": True})

Why a service account acting as somebody
-----------------------------------------
The Auth0 integration asks for a token on its own behalf and gets one. There is no
such thing here. The Directory API will not act for an application, only for an
administrator, so a token is obtained by a service account *impersonating* one
-- domain-wide delegation -- and every call this app makes is made, as far as
the audit log is concerned, by the person in `Admin Email`.

Three consequences worth knowing before the first 403.

The scopes are granted in two places and must match in both. They are a
constant here, sent with the assertion, and they are also pasted into the Admin
console's domain-wide delegation screen against the service account's numeric
client id. Google grants the intersection and says nothing about the difference:
a scope missing from the console is not an error at the token request, it is a
403 on some call hours later, and the 403 does not name the scope. `_decode`
adds the sentence nobody wants to have to work out for themselves.

The administrator is a real account and outlives nothing. Naming a person means
the integration stops the day they leave, mid-offboarding, which is the worst
available moment. A dedicated admin account is not a nicety.

The credential is a private key. `client_secret` in the Auth0 integration is a
string Auth0 can revoke; this is an RSA private key that signs assertions, and
it is held the same way and for the same reasons -- a `Password` field,
encrypted in `__Auth`, read by `settings` and returned by nothing.

What the single way in settles, once
-------------------------------------
*The key is read, never returned.* `settings` is not whitelisted and nothing
that is whitelisted returns what it reads. `GoogleWorkspaceError` carries a
status code and Google's own message; it never carries the request body.

*The token is cached.* A delegated token is good for an hour. `google-auth`
caches one per credentials object, which on a bench means per worker, per hour,
per process -- so the token exchange happens far more often than it needs to.
It is held in Redis instead, with an expiry a little shorter than Google's own,
so it is dropped before it stops working rather than after. Redis rather than a
field beside the key, for the reason `commons.api_integrations.auth0.client` gives at length: a
live token that can create and delete every account in the domain does not
belong in the database or in every backup of it.

*A rejected token is retried once.* A cached token can stop working before its
expiry: the key is rotated or disabled, the delegation is withdrawn, the
impersonated administrator is suspended. That arrives as a 401 on some unrelated
call. Once, immediately, with a fresh token, is the difference between "somebody
rotated the key last week" and an error nobody can place. A second refusal
stands, so a genuinely withdrawn delegation fails on the second call rather than
looping.

*No request body is ever logged.* This is not a general precaution, it is about
two calls. `users.create` and `users.set_password` put a real, usable,
about-to-be-handed-to-somebody password in the body, and `frappe.log_error`
writes local variables into the Error Log -- `frappe.utils._get_traceback_sanitizer`
redacts a local *named* `password`, `token` or `key`, which a body dict named
`json_body` is not, and a bearer token in a local named `bearer` is not either.
So `_send` logs an explicit message rather than letting `log_error` reach for
the context it would otherwise take. Removing that argument puts credentials in
a doctype any System Manager can read.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import Any

import frappe
from frappe import _

from commons.api_integrations import http

SETTINGS = "Google Workspace Settings"

# Every path in this integration is relative to this. The Admin SDK lives on its own
# host rather than under googleapis.com/admin, and the `directory/v1` is the API
# rather than the version of the host.
BASE = "https://admin.googleapis.com/admin/directory/v1/"

# What this app asks to be allowed to do, and what has to be pasted -- exactly,
# comma separated -- into the Admin console's domain-wide delegation screen.
#
# Two, not one. `admin.directory.user` covers the account itself and its photo;
# aliases are a separate scope even though they are an endpoint under the same
# user. A site that grants only the first gets working accounts and a 403 the
# first time anybody adds an alias.
#
# Deliberately not the `.readonly` variants and deliberately not anything
# broader. A token minted here can create, change and delete every account in
# the domain, which is already the largest thing this app holds; there is no
# reason for it to also reach groups, roles or devices.
SCOPES = (
	"https://www.googleapis.com/auth/admin.directory.user",
	"https://www.googleapis.com/auth/admin.directory.user.alias",
)

# What Google calls "the customer this administrator belongs to", which is what
# is wanted in every case where the alternative is looking up an id nobody has
# any other use for. Configurable only for a reseller acting across customers.
DEFAULT_CUSTOMER = "my_customer"

# Where new accounts land when the settings name no other organisational unit.
# The root, which is where an account created through the Admin console goes
# too, and which carries whatever licence assignment the domain has set on it.
DEFAULT_ORG_UNIT_PATH = "/"

# Dropped from the cache this many seconds before Google says it expires, so a
# call that starts just under the wire still has a token that is good when it
# lands. Proportionally larger than the Auth0 integration's margin of the same name
# because the token it guards lives an hour rather than a day.
EXPIRY_MARGIN = 300

# What a token is kept for when the SDK reports no expiry. It always reports
# one; this is so that an unexpected object shortens the cache rather than
# caching something until the next deploy.
FALLBACK_TTL = 3600

# Connect and read timeouts, and the retry policy, are the integrations' shared
# ones -- see `commons.api_integrations.http`.
TIMEOUT = http.TIMEOUT


class GoogleWorkspaceError(frappe.ValidationError):
	"""A call Google refused, with the status it refused it with.

	A `ValidationError` so the message reaches whoever pressed the button rather
	than becoming a 500 with a traceback -- what went wrong is nearly always
	something a person can act on (the address is taken, the delegation is
	missing a scope) rather than a bug.

	`status` is on it because callers need to tell refusals apart:
	`users.ensure` treats 409 as "it already exists, go and find it", and
	`users.get` and `users.delete` treat 404 as "there is no such account".
	Reading a status off an exception is otherwise a guess.
	"""

	def __init__(self, message: str, status: int | None = None):
		super().__init__(message)
		self.status = status


@dataclass(frozen=True)
class Credentials:
	"""What `Google Workspace Settings` holds, parsed and with the blanks filled in."""

	key: dict
	admin_email: str
	customer_id: str
	org_unit_path: str
	scopes: tuple[str, ...]

	@property
	def service_account_email(self) -> str:
		"""The `...iam.gserviceaccount.com` address the key belongs to.

		Used to key the token cache and to name the right service account in an
		error. Not the numeric client id, which is what the delegation screen
		wants and which nothing here needs.
		"""
		return self.key.get("client_email") or ""


def settings() -> dict:
	"""What the `Google Workspace Settings` Single holds, key included.

	Guarded by the doctype's existence for the window
	`commons.commons_core.settings` describes: code lands before the migrate
	that creates its doctype, and for that one window there is no Single to read
	at all. That reads as unconfigured rather than as an error.

	`get_password` rather than the attribute: a `Password` field's value lives
	encrypted in `__Auth`, and the document's own attribute holds a placeholder.
	`raise_exception=False` because a site part-way through being set up has no
	key yet, and `available` is the thing entitled to have an opinion about that.
	"""
	if not frappe.db.exists("DocType", SETTINGS, cache=True):
		return {}

	document = frappe.get_cached_doc(SETTINGS)
	return {
		"admin_email": (document.admin_email or "").strip(),
		"service_account_key": document.get_password("service_account_key", raise_exception=False) or "",
		"customer_id": (document.customer_id or "").strip(),
		"org_unit_path": (document.org_unit_path or "").strip(),
		"extra_scopes": (document.extra_scopes or "").strip(),
	}


def available() -> bool:
	"""Whether this site has a Workspace domain to talk to at all.

	The two things without which not one call can be made: a key to sign with
	and somebody to sign as. Asked the way the rest of this app asks it -- see
	`commons.statement.ledger.available` -- so a page or a button can leave
	itself out instead of offering something that only explains itself after
	being pressed.

	It does not check that the key parses. A site that has pasted something
	wrong has configured this integration, badly, and should be told so by
	`credentials` in a sentence naming the problem rather than by a button
	quietly disappearing.
	"""
	held = settings()
	return bool(held.get("admin_email") and held.get("service_account_key"))


def extra_scopes(raw: str) -> tuple[str, ...]:
	"""Scopes a site has added beyond `SCOPES`, from one free-text field.

	Split on whatever somebody pasted -- commas, spaces, newlines -- because the
	Admin console's own field is comma separated and the Google documentation
	lists them one per line, and both are going to end up in this box.

	Only entries that look like scopes are kept, so a stray comma or a trailing
	line does not become a scope Google then refuses the whole token request
	over.
	"""
	found = []
	for piece in raw.replace(",", " ").split():
		if piece.startswith("https://www.googleapis.com/auth/") and piece not in found:
			found.append(piece)
	return tuple(found)


def credentials() -> Credentials:
	"""The settings, parsed, or a refusal naming what is wrong with them.

	Named, because every failure this replaces is a `KeyError` or a
	`JSONDecodeError` in a log and the fix is one field somebody has to be told
	to fill in.

	The key is checked for being the right *kind* of JSON, not merely for being
	JSON. Pasting the OAuth client secret file instead of the service account
	key is the commonest way to spend an afternoon here: it is valid JSON, it
	has a `client_id` in it, and it is wrapped in `installed` or `web`, which is
	the tell. Saying so is worth the four lines.
	"""
	held = settings()
	missing = [key for key in ("admin_email", "service_account_key") if not held.get(key)]
	if missing:
		frappe.throw(
			_("Google Workspace is not configured on this site. Missing: {0}. Set them in {1}.").format(
				", ".join(missing), _(SETTINGS)
			),
			title=_("Google Workspace Not Configured"),
		)

	try:
		key = json.loads(held["service_account_key"])
	except ValueError:
		frappe.throw(
			_(
				"The service account key in {0} is not valid JSON. Paste the whole contents of"
				" the key file downloaded from Google Cloud, braces included."
			).format(_(SETTINGS)),
			title=_("Google Workspace Not Configured"),
		)

	if not isinstance(key, dict) or "installed" in key or "web" in key:
		frappe.throw(
			_(
				"That looks like an OAuth client secret rather than a service account key."
				" The file wanted here has a client_email and a private_key at its top level"
				" and is downloaded from the service account's Keys tab."
			),
			title=_("Google Workspace Not Configured"),
		)

	absent = [field for field in ("client_email", "private_key", "token_uri") if not key.get(field)]
	if absent:
		frappe.throw(
			_("The service account key in {0} is missing: {1}.").format(_(SETTINGS), ", ".join(absent)),
			title=_("Google Workspace Not Configured"),
		)

	return Credentials(
		key=key,
		admin_email=held["admin_email"],
		customer_id=held.get("customer_id") or DEFAULT_CUSTOMER,
		org_unit_path=held.get("org_unit_path") or DEFAULT_ORG_UNIT_PATH,
		scopes=SCOPES + extra_scopes(held.get("extra_scopes") or ""),
	)


def cache_key(creds: Credentials) -> str:
	"""Where this domain's token is kept.

	Keyed by the service account and the administrator it acts as, because a
	token is issued to that pair and is useless to any other -- changing either
	must not keep serving the token belonging to the old one until it happens to
	expire.

	Neither the private key nor the scopes are in the key. Cache keys are
	readable in Redis and turn up in monitoring, and a key long enough to hold
	an RSA private key is not a cache key. Rotating the key, or adding a scope,
	therefore leaves this unchanged -- which is what `forget_token` is for, and
	why it runs whenever the settings are saved.
	"""
	return f"google_workspace_token::{creds.service_account_email}::{creds.admin_email}"


def forget_token() -> None:
	"""Drop the cached token, so the next call fetches a new one.

	Called when the settings are saved. Neither a rotated key nor an added scope
	changes the cache key, so without this the previous token goes on working,
	or goes on failing, for up to an hour after somebody thought they had
	changed something -- and an added scope in particular fails in the most
	confusing way available, as a 403 on the very call that was just enabled.

	Silent on a site with nothing configured, because saving a half-filled form
	is how a site gets configured and it must not fail on the way.
	"""
	if not available():
		return
	try:
		creds = credentials()
	except frappe.ValidationError:
		# A key that does not parse has no token to forget, and refusing to save
		# the form that is about to fix it would be the wrong way round.
		return
	frappe.cache.delete_value(cache_key(creds))


def token(refresh: bool = False) -> str:
	"""A delegated access token for this domain, from the cache where possible.

	`refresh` is for the one caller below that has just been told by Google that
	the cached one is no good.

	No lock around the fetch. Two requests arriving on a cold cache both mint a
	token and the second overwrites the first in Redis -- which costs one extra
	assertion exchange and breaks nothing, because the tokens are independent
	and both stay valid. A lock would cost a round trip on every call to avoid
	that.
	"""
	creds = credentials()
	key = cache_key(creds)

	if not refresh:
		# `expires=True` keeps this out of the per-request local cache, which
		# has no notion of the TTL that is the whole point of the entry.
		cached = frappe.cache.get_value(key, expires=True)
		if cached:
			return cached

	access, lifetime = _issue(creds)
	# Never negative, and never so short that the entry is gone before the call
	# it was fetched for.
	frappe.cache.set_value(key, access, expires_in_sec=max(int(lifetime) - EXPIRY_MARGIN, 60))
	return access


def _issue(creds: Credentials) -> tuple[str, int]:
	"""Sign an assertion, exchange it, and return the token and its lifetime.

	`google-auth` is imported here rather than at the top of the module. It
	pulls in `cryptography`, which is not free to import, and it is needed only
	when a token is actually minted -- so a request that finds one in the cache,
	which is nearly all of them, does not pay for it. It also leaves this module
	importable, and most of it testable, without the SDK in the room.

	The refusal this exists to translate is `unauthorized_client`. It is what
	Google says when the service account's client id is not authorised for these
	scopes in the Admin console, and it is the failure every first setup hits.
	Left as it comes it is an `unauthorized_client` with no indication of which
	half of a two-sided configuration is wrong, so it is answered with the two
	things to go and look at and the two values to compare.

	`invalid_grant` is the other one, and it means the administrator rather than
	the scopes: no such account in this domain, or suspended, or not allowed to
	manage users.
	"""
	from google.auth.exceptions import GoogleAuthError
	from google.auth.transport.requests import Request
	from google.oauth2 import service_account

	class _TimedRequest(Request):
		"""google-auth's transport, with `commons.api_integrations.http`'s timeout by default."""

		def __call__(self, *args, timeout=None, **kwargs):
			return super().__call__(*args, timeout=timeout or http.TIMEOUT, **kwargs)

	try:
		delegated = service_account.Credentials.from_service_account_info(
			creds.key, scopes=list(creds.scopes)
		).with_subject(creds.admin_email)
	except (ValueError, KeyError, TypeError) as bad:
		frappe.throw(
			_("The service account key in {0} could not be read: {1}").format(_(SETTINGS), str(bad)),
			exc=GoogleWorkspaceError,
		)

	try:
		# The integrations' session, and their timeout: google-auth's own default
		# is two minutes, and the refresh passes none of its own.
		delegated.refresh(_TimedRequest(session=http.session()))
	except GoogleAuthError as refused:
		frappe.throw(
			_(
				"Google would not issue a token for {0} acting as {1}: {2}"
				" Check that the service account's numeric client ID is authorised for these"
				" scopes in the Admin console under Security → Access and data control → API"
				" controls → Domain-wide delegation, that the scopes there match exactly, and"
				" that the administrator above exists in this domain and can manage users."
				" Scopes asked for: {3}"
			).format(
				creds.service_account_email,
				creds.admin_email,
				str(refused),
				", ".join(creds.scopes),
			),
			exc=GoogleWorkspaceError,
		)

	if not delegated.token:
		# Reached only if the SDK returns without raising and without a token,
		# which is worth saying out loud rather than caching an empty string.
		frappe.throw(_("Google issued no access token."), exc=GoogleWorkspaceError)

	return delegated.token, _lifetime(delegated.expiry)


def _lifetime(expiry) -> int:
	"""Seconds until a token expires, from whatever the SDK put on it.

	`google-auth` has historically carried a naive UTC datetime here and newer
	versions an aware one. Comparing a naive to an aware datetime raises, in the
	middle of a working call, so the naive one is read as UTC -- which is what
	it is -- rather than assumed not to occur.

	An expiry already in the past answers zero rather than falling back to
	`FALLBACK_TTL`. It means the clock here and Google's disagree, and the
	safe reading of that is a token with no life left rather than one with a
	full hour of it -- `token` floors the cache entry at a minute, so the effect
	is that a skewed clock re-mints often instead of serving a dead token until
	the hour is up.
	"""
	if not expiry:
		return FALLBACK_TTL
	if expiry.tzinfo is None:
		expiry = expiry.replace(tzinfo=UTC)
	return max(int((expiry - datetime.now(UTC)).total_seconds()), 0)


def directory(
	method: str,
	path: str,
	json_body: dict | None = None,
	params: dict | None = None,
) -> Any:
	"""One Admin SDK Directory call, with the token on it and the 401 retried.

	`path` is relative to `BASE` -- `users`, `users/{key}`,
	`users/{key}/aliases` -- so nothing repeats the host or the API version, and
	nothing else in this app has to know how a token is obtained.

	The retry is for a token that stopped working before its cached expiry; the
	module docstring says when that happens. It is deliberately not a retry of
	anything else: a 429, or a 403 whose reason is `quotaExceeded`, is Google's
	rate limiter -- the Directory API allows a couple of thousand requests a
	minute and bulk work should be spread out rather than hammered -- and a 5xx
	is retried with backoff by `commons.api_integrations.http` where that is safe.
	"""
	url = f"{BASE}{path.lstrip('/')}"

	response = _send(method, url, token(), json_body, params)
	if response.status_code == 401:
		response = _send(method, url, token(refresh=True), json_body, params)

	return _decode(response)


def _send(method: str, url: str, bearer: str | None, json_body: dict | None, params: dict | None):
	"""The HTTP call itself, returning the response whatever its status.

	`requests` through `commons.api_integrations.http`, rather than the `googleapiclient`
	discovery machinery, for three reasons. `users.ensure` is built entirely
	around telling one status from another, and `HttpError` buries it in
	`.resp.status` while a transport failure raises something with no status at
	all. The discovery client is also a second error vocabulary, a second retry
	policy and a second idea of a timeout sitting beside the one the rest of
	this app uses. And a REST call is what the Google documentation is written
	in, so a path here can be checked against the reference without translation.

	The explicit `message` on `log_error` is not decoration. Without it,
	`log_error` takes `frappe.get_traceback(with_context=True)`, which writes
	every local in every frame into the Error Log -- including `json_body`,
	which for `users.create` and `users.set_password` holds a real password, and
	`bearer`, which holds a token that can delete the whole domain. Frappe's
	sanitiser redacts locals *named* `password`, `token` or `key` and dict keys
	only inside a local named `_secret`, so neither of those is covered. Passing
	the plain traceback keeps the frames out of it entirely.
	"""
	session = http.session()
	headers = {"Content-Type": "application/json"}
	if bearer:
		headers["Authorization"] = f"Bearer {bearer}"

	try:
		return session.request(method, url, headers=headers, json=json_body, params=params, timeout=TIMEOUT)
	except Exception as exception:
		# A refused connection, a DNS failure, a timeout: no response, no
		# status, and nothing Google said. Reported as itself rather than as a
		# missing attribute on an exception that has no `.response`.
		frappe.log_error(
			title="Google Workspace request failed",
			message=frappe.get_traceback(),
		)
		frappe.throw(_("Could not reach Google: {0}").format(str(exception)), exc=GoogleWorkspaceError)


def _decode(response) -> Any:
	"""Google's answer, or its refusal raised with the status it refused with.

	Google reports what went wrong in a JSON body nested one level deeper than
	most -- `{"error": {"code": 409, "message": "Entity already exists."}}` --
	and that sentence is nearly always the useful one. It is preferred over the
	status code alone, and the status is kept on the exception for the callers
	that branch on it.

	A 403 gets a sentence added to it. It is the one refusal here whose message
	is reliably useless: "Not Authorized to access this resource/api" is what
	Google says both for a scope that was never granted in the delegation screen
	and for an administrator who cannot manage users, and it names neither. Both
	are one screen away from being fixed by anyone who is told which screen.
	"""
	if response.status_code >= 400:
		detail = ""
		try:
			body = response.json()
		except ValueError:
			body = None

		if isinstance(body, dict):
			error = body.get("error")
			if isinstance(error, dict):
				detail = error.get("message") or ""
			elif isinstance(error, str):
				# The token endpoint's shape, which is flatter than the API's.
				detail = body.get("error_description") or error
		if not detail:
			detail = (response.text or "").strip()[:200]

		message = _("Google refused the request ({0}). {1}").format(response.status_code, detail).strip()
		if response.status_code == 403:
			message += " " + _(
				"If this is the first call to fail this way, check the scopes granted to the"
				" service account in the Admin console's domain-wide delegation screen, and"
				" that the administrator in {0} can manage users."
			).format(_(SETTINGS))

		# The instance rather than the class, because the status has to survive
		# onto the exception `throw` raises -- `msgprint` re-arms an instance
		# with the message and raises it as it was given, attributes and all.
		frappe.throw(message, exc=GoogleWorkspaceError(message, status=response.status_code))

	if not response.content:
		return None
	try:
		return response.json()
	except ValueError:
		return None
