"""The way in to Auth0: the credentials, the management token, and one call.

Everything this integration does to Auth0 goes through `management` below, and
`management` is public for exactly that reason. The Management API has a few
hundred endpoints; `users` wraps the handful this app has needed so far, and
anything else is one line at the call site rather than a change to this file::

	client.management("GET", "roles")
	client.management("POST", f"users/{user_id}/roles", json_body={"roles": [...]})

What the single way in settles, once:

*The secret is read, never returned.* `credentials` is not whitelisted and
nothing that is whitelisted returns what it reads. `Auth0Error` carries a status
code and Auth0's own message; it never carries the request body, because the
request body for a token is the client secret and an error message is the one
place a secret reliably ends up in front of somebody.

*The token is cached.* A Management API token is good for 24 hours and Auth0
meters how many are issued. Fetching one per call is both slow -- a round trip
before the one that was actually wanted -- and, on a tenant with a monthly
quota, a bill. It is held in Redis with an expiry a little shorter than Auth0's
own, so it is dropped before it stops working rather than after.

Redis rather than a field on the Single beside the credentials. A field means a
live, tenant-wide, create-and-delete-anybody token sitting in the database and
in every backup, for a day at a time; a cache entry is in neither, and it
expires on its own. The cost is that a bench restart or a Redis flush throws the
token away and the next call fetches another -- a round trip, not a failure.

*A rejected token is retried once.* A cached token can stop working before its
expiry: the application's secret is rotated, its grant is revoked, or a scope is
taken away. That arrives as a 401 on some unrelated call, hours later. Once,
immediately, with a fresh token, is the difference between "somebody rotated the
secret last week" and an error nobody can place. If the second is refused too
the error stands, so a genuinely revoked grant fails on the second call rather
than looping.
"""

from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _
from frappe.utils import get_request_session

SETTINGS = "Auth0 Settings"

# The database Auth0 puts new accounts in. A tenant may have several; this is
# the name of the default username-and-password one, and the only reason it is
# configurable at all is that a tenant which renamed it would otherwise be
# stuck.
DEFAULT_CONNECTION = "Username-Password-Authentication"

# Dropped from the cache this many seconds before Auth0 says it expires, so a
# call that starts just under the wire still has a token that is good when it
# lands.
EXPIRY_MARGIN = 300

# What a token is kept for when Auth0 does not say. It always says; this is so
# that an unexpected response shape shortens the cache rather than caching
# something until the next deploy.
FALLBACK_TTL = 3600

# Long enough for Auth0 under load, short enough that a wedged call does not
# hold a worker, or somebody's save, for minutes.
TIMEOUT = 30


class Auth0Error(frappe.ValidationError):
	"""A call Auth0 refused, with the status it refused it with.

	A `ValidationError` so the message reaches whoever pressed the button rather
	than becoming a 500 with a traceback -- what went wrong is nearly always
	something a person can act on (the address is taken, the grant is missing a
	scope) rather than a bug.

	`status` is on it because callers need to tell refusals apart:
	`users.ensure` treats 409 as "it already exists, go and find it", and
	`users.delete` treats 404 as "already gone". Reading a status off an
	exception is otherwise a guess -- `requests` raises an `HTTPError` that has
	`.response`, but a DNS failure or a timeout raises one that does not, and
	code reaching for `e.response.status_code` to report the real problem fails
	with an `AttributeError` about the reporting instead.
	"""

	def __init__(self, message: str, status: int | None = None):
		super().__init__(message)
		self.status = status


@dataclass(frozen=True)
class Credentials:
	"""What `Auth0 Settings` holds, cleaned up and with the blanks filled in."""

	domain: str
	client_id: str
	client_secret: str
	connection: str
	audience: str


def settings() -> dict:
	"""What the `Auth0 Settings` Single holds, secret included.

	Guarded by the doctype's existence for the window
	`commons.commons_core.settings` describes: code lands before the migrate
	that creates its doctype, and for that one window there is no Single to read
	at all. That reads as unconfigured rather than as an error.

	`get_password` rather than the attribute: a `Password` field's value lives
	encrypted in `__Auth`, and the document's own attribute holds a placeholder.
	`raise_exception=False` because a site part-way through being set up has no
	secret yet, and `available` is the thing entitled to have an opinion about
	that.
	"""
	if not frappe.db.exists("DocType", SETTINGS, cache=True):
		return {}

	document = frappe.get_cached_doc(SETTINGS)
	return {
		"domain": (document.domain or "").strip(),
		"client_id": (document.client_id or "").strip(),
		"client_secret": document.get_password("client_secret", raise_exception=False) or "",
		"connection": (document.connection or "").strip(),
		"audience": (document.audience or "").strip(),
	}


def available() -> bool:
	"""Whether this site has an Auth0 tenant to talk to at all.

	The three credentials, because a site with a domain and no secret cannot
	make a single call and should be told so here rather than at the token
	request. Asked the way the rest of this app asks it -- see
	`commons.statement.ledger.available` -- so a page or a button can leave
	itself out instead of offering something that only explains itself after
	being pressed.
	"""
	held = settings()
	return all(held.get(key) for key in ("domain", "client_id", "client_secret"))


def credentials() -> Credentials:
	"""The tenant's credentials, or a refusal naming what is missing.

	Named, because the failure this replaces is a `KeyError` in a log and the
	fix is one field somebody has to be told to fill in.

	The domain is cleaned rather than trusted. Pasting it with its scheme, or
	with a trailing slash, is the commonest way to spend an afternoon on a 404,
	and both are unambiguous to undo.

	The audience is derived unless the form says otherwise: Auth0 names it after
	the tenant domain, and a token issued for anything else is rejected by every
	call below, so it is not really a choice. The exception is a tenant on a
	custom domain, where the audience stays the canonical `*.auth0.com` one even
	though the API is reached on the custom name -- which is the whole reason
	that field exists.
	"""
	held = settings()
	missing = [key for key in ("domain", "client_id", "client_secret") if not held.get(key)]
	if missing:
		frappe.throw(
			_("Auth0 is not configured on this site. Missing: {0}. Set them in {1}.").format(
				", ".join(missing), _(SETTINGS)
			),
			title=_("Auth0 Not Configured"),
		)

	domain = held["domain"].removeprefix("https://").removeprefix("http://").rstrip("/")
	return Credentials(
		domain=domain,
		client_id=held["client_id"],
		client_secret=held["client_secret"],
		connection=held.get("connection") or DEFAULT_CONNECTION,
		audience=held.get("audience") or f"https://{domain}/api/v2/",
	)


def cache_key(creds: Credentials) -> str:
	"""Where this tenant's token is kept.

	Keyed by domain and client id, so that pointing the site at another tenant
	or another application does not keep serving the token belonging to the old
	one until it happens to expire. The secret is not in the key: cache keys are
	readable in Redis and turn up in monitoring. Rotating only the secret leaves
	the key unchanged, which is what `forget_token` is for.
	"""
	return f"auth0_management_token::{creds.domain}::{creds.client_id}"


def forget_token() -> None:
	"""Drop the cached token, so the next call fetches a new one.

	Called when the settings are saved. A rotated secret does not change the
	cache key -- the old application's token would otherwise go on working, or
	go on failing, for up to a day after somebody thought they had changed it.

	Silent on a site with nothing configured, because saving a half-filled form
	is how a site gets configured and it must not fail on the way.
	"""
	if not available():
		return
	frappe.cache.delete_value(cache_key(credentials()))


def token(refresh: bool = False) -> str:
	"""A Management API token for this tenant, from the cache where possible.

	`refresh` is for the one caller below that has just been told by Auth0 that
	the cached one is no good.

	No lock around the fetch. Two requests arriving on a cold cache both ask for
	a token and both get one, and the second overwrites the first in Redis --
	which costs one extra issuance and breaks nothing, because Auth0 issues
	independent tokens and both stay valid. A lock would cost a round trip on
	every call to avoid that.
	"""
	creds = credentials()
	key = cache_key(creds)

	if not refresh:
		# `expires=True` keeps this out of the per-request local cache, which
		# has no notion of the TTL that is the whole point of the entry.
		cached = frappe.cache.get_value(key, expires=True)
		if cached:
			return cached

	issued = _decode(
		_send(
			"POST",
			f"https://{creds.domain}/oauth/token",
			None,
			{
				"grant_type": "client_credentials",
				"client_id": creds.client_id,
				"client_secret": creds.client_secret,
				"audience": creds.audience,
			},
			None,
		)
	)

	access = (issued or {}).get("access_token")
	if not access:
		# Reached only if Auth0 answers 200 with something unexpected, which is
		# worth saying out loud rather than caching an empty string.
		frappe.throw(_("Auth0 issued no access token."), exc=Auth0Error)

	lifetime = issued.get("expires_in") or FALLBACK_TTL
	# Never negative, and never so short that the entry is gone before the call
	# it was fetched for.
	frappe.cache.set_value(key, access, expires_in_sec=max(int(lifetime) - EXPIRY_MARGIN, 60))
	return access


def management(
	method: str,
	path: str,
	json_body: dict | None = None,
	params: dict | None = None,
) -> Any:
	"""One Management API call, with the token on it and the 401 retried.

	`path` is relative to `/api/v2/` -- `users`, `users-by-email`,
	`users/{id}/roles` -- so nothing repeats the tenant domain or the API
	version, and nothing else in this app has to know how a token is obtained.

	The retry is for a token that stopped working before its cached expiry; the
	module docstring says when that happens. It is deliberately not a retry of
	anything else: a 429 is Auth0's rate limiter and retrying it immediately is
	the worst available response, and a 5xx is already retried by the session
	`get_request_session` builds.
	"""
	creds = credentials()
	url = f"https://{creds.domain}/api/v2/{path.lstrip('/')}"

	response = _send(method, url, token(), json_body, params)
	if response.status_code == 401:
		response = _send(method, url, token(refresh=True), json_body, params)

	return _decode(response)


def _send(method: str, url: str, bearer: str | None, json_body: dict | None, params: dict | None):
	"""The HTTP call itself, returning the response whatever its status.

	`requests` through `get_request_session`, rather than
	`frappe.make_post_request`, for two reasons that both matter here. That
	helper calls `raise_for_status` and hands back an `HTTPError` whose status
	the caller then has to dig for -- and `users.ensure` is built entirely
	around telling one status from the others. It also calls `frappe.log_error`
	on every exception, so the 409 this integration treats as an ordinary outcome
	would file an Error Log every time an account already existed.

	The session is still Frappe's, so the bench's retry behaviour on 5xx and any
	site-level request configuration are unchanged.
	"""
	session = get_request_session()
	headers = {"Content-Type": "application/json"}
	if bearer:
		headers["Authorization"] = f"Bearer {bearer}"

	try:
		return session.request(method, url, headers=headers, json=json_body, params=params, timeout=TIMEOUT)
	except Exception as exception:
		# A refused connection, a DNS failure, a timeout: no response, no
		# status, and nothing Auth0 said. Reported as itself rather than as a
		# missing attribute on an exception that has no `.response`.
		frappe.log_error(title="Auth0 request failed")
		frappe.throw(_("Could not reach Auth0: {0}").format(str(exception)), exc=Auth0Error)


def _decode(response) -> Any:
	"""Auth0's answer, or its refusal raised with the status it refused with.

	Auth0 reports what went wrong in a JSON body with `message` in it, and that
	sentence is nearly always the useful one -- "The user already exists",
	"Insufficient scope". It is preferred over the status code alone, and the
	status is kept on the exception for the callers that branch on it.
	"""
	if response.status_code >= 400:
		try:
			body = response.json()
			detail = body.get("message") or body.get("error_description") or ""
		except ValueError:
			detail = (response.text or "").strip()[:200]

		# The instance rather than the class, because the status has to survive
		# onto the exception `throw` raises -- `msgprint` re-arms an instance
		# with the message and raises it as it was given, attributes and all.
		message = _("Auth0 refused the request ({0}). {1}").format(response.status_code, detail).strip()
		frappe.throw(message, exc=Auth0Error(message, status=response.status_code))

	if not response.content:
		return None
	try:
		return response.json()
	except ValueError:
		return None
