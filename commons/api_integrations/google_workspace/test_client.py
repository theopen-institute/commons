"""The settings, the token cache, and what a refusal turns into.

Site-less. `frappe.throw` logs its message through `frappe.local`, which only a
request or a site has, so it is replaced with a plain raise wherever a decision
rather than a message is what is under test -- the same technique
`commons.api_integrations.auth0.test_client` uses and for the same reason.

Nothing here talks to Google and nothing here signs an assertion. `_issue` is
the boundary: everything above it is this app's, everything below it is
`google-auth` doing what it is tested for, so `_issue` is stubbed and what is
checked is the cache, the key, the lifetime arithmetic and the error
translation.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.api_integrations.google_workspace import client

KEY = {
	"type": "service_account",
	"client_email": "commons@example-project.iam.gserviceaccount.com",
	"private_key": "-----BEGIN PRIVATE KEY-----\nnot a real one\n-----END PRIVATE KEY-----\n",
	"token_uri": "https://oauth2.googleapis.com/token",
}

# Two scopes this app does not ask for, for the `extra_scopes` tests. Real ones,
# so the test exercises the same prefix check a site's paste would.
EXTRA = (
	"https://www.googleapis.com/auth/admin.directory.group",
	"https://www.googleapis.com/auth/admin.directory.orgunit",
)

DOMAIN = {
	"admin_email": "directory-bot@example.org",
	"service_account_key": json.dumps(KEY),
	"customer_id": "",
	"org_unit_path": "",
	"extra_scopes": "",
}


def throw(message, exc=Exception, **kwargs):
	"""`frappe.throw` without the message log, raising a class or an instance.

	The instance branch is the one that matters: `client._decode` passes a
	`GoogleWorkspaceError` it has already built so the status survives onto the
	exception, and a stub that only handled classes would silently lose it --
	which is the thing half of these tests are checking.
	"""
	if isinstance(exc, Exception):
		raise exc
	raise exc(message)


def _format(text):
	"""`frappe._` without a site: `.format` is what the callers go on to call."""
	return text


class Response:
	"""Just enough of `requests.Response` for `_decode`."""

	def __init__(self, status_code=200, body=None, text=""):
		self.status_code = status_code
		self._body = body
		self.text = text
		self.content = b"x" if (body is not None or text) else b""

	def json(self):
		if self._body is None:
			raise ValueError("not json")
		return self._body


class Settings(TestCase):
	def held(self, **overrides):
		with (
			patch.object(client, "settings", return_value={**DOMAIN, **overrides}),
			patch.object(client.frappe, "throw", throw),
			patch.object(client, "_", _format),
		):
			return client.credentials()

	def test_the_key_is_parsed_from_the_field(self):
		self.assertEqual(self.held().service_account_email, KEY["client_email"])

	def test_a_blank_customer_means_whoever_the_administrator_belongs_to(self):
		self.assertEqual(self.held().customer_id, client.DEFAULT_CUSTOMER)

	def test_a_blank_org_unit_means_the_root(self):
		self.assertEqual(self.held().org_unit_path, client.DEFAULT_ORG_UNIT_PATH)

	def test_a_site_that_has_set_one_is_honoured(self):
		self.assertEqual(self.held(org_unit_path="/Staff").org_unit_path, "/Staff")

	def test_a_missing_administrator_is_named_rather_than_raised_over(self):
		with self.assertRaises(Exception) as raised:
			self.held(admin_email="")
		self.assertIn("admin_email", str(raised.exception))

	def test_a_key_that_is_not_json_says_so(self):
		with self.assertRaises(Exception) as raised:
			self.held(service_account_key="-----BEGIN PRIVATE KEY-----")
		self.assertIn("not valid JSON", str(raised.exception))

	def test_an_oauth_client_secret_file_is_recognised_and_named(self):
		"""The commonest wrong paste: valid JSON, wrong file entirely."""
		wrong = json.dumps({"installed": {"client_id": "1.apps.googleusercontent.com"}})
		with self.assertRaises(Exception) as raised:
			self.held(service_account_key=wrong)
		self.assertIn("OAuth client secret", str(raised.exception))

	def test_a_key_missing_its_private_key_is_named(self):
		partial = json.dumps({"client_email": "a@b.iam.gserviceaccount.com"})
		with self.assertRaises(Exception) as raised:
			self.held(service_account_key=partial)
		self.assertIn("private_key", str(raised.exception))


class Scopes(TestCase):
	def test_the_two_this_app_needs_are_always_asked_for(self):
		with (
			patch.object(client, "settings", return_value=DOMAIN),
			patch.object(client.frappe, "throw", throw),
			patch.object(client, "_", _format),
		):
			self.assertEqual(client.credentials().scopes, client.SCOPES)

	def test_extra_scopes_can_be_pasted_comma_separated(self):
		"""Which is how the Admin console's own field spells them."""
		self.assertEqual(len(client.extra_scopes(",".join(EXTRA))), 2)

	def test_extra_scopes_can_be_pasted_one_per_line(self):
		"""Which is how the documentation lists them."""
		self.assertEqual(len(client.extra_scopes("\n".join(EXTRA) + "\n")), 2)

	def test_a_stray_line_is_not_turned_into_a_scope(self):
		"""One bad entry otherwise gets the whole token request refused."""
		self.assertEqual(client.extra_scopes("admin.directory.group\n# a note"), ())

	def test_a_scope_pasted_twice_is_asked_for_once(self):
		one = "https://www.googleapis.com/auth/admin.directory.group"
		self.assertEqual(client.extra_scopes(f"{one},{one}"), (one,))


class Available(TestCase):
	def available(self, **overrides):
		with patch.object(client, "settings", return_value={**DOMAIN, **overrides}):
			return client.available()

	def test_a_site_with_a_key_and_an_administrator_has_workspace(self):
		self.assertTrue(self.available())

	def test_an_administrator_without_a_key_is_not_a_configured_site(self):
		self.assertFalse(self.available(service_account_key=""))

	def test_a_site_that_has_never_been_set_up_has_no_workspace(self):
		with patch.object(client, "settings", return_value={}):
			self.assertFalse(client.available())

	def test_a_key_that_does_not_parse_still_reads_as_configured(self):
		"""So `credentials` gets to name the problem instead of a button vanishing."""
		self.assertTrue(self.available(service_account_key="{oops"))


class CacheKey(TestCase):
	def key(self, **overrides):
		with (
			patch.object(client, "settings", return_value={**DOMAIN, **overrides}),
			patch.object(client.frappe, "throw", throw),
			patch.object(client, "_", _format),
		):
			return client.cache_key(client.credentials())

	def test_two_administrators_do_not_share_a_token(self):
		"""A token is issued to the pair, and is useless to any other."""
		self.assertNotEqual(self.key(), self.key(admin_email="someone-else@example.org"))

	def test_two_service_accounts_do_not_share_a_token(self):
		other = json.dumps({**KEY, "client_email": "other@example-project.iam.gserviceaccount.com"})
		self.assertNotEqual(self.key(), self.key(service_account_key=other))

	def test_the_private_key_is_not_in_the_key(self):
		"""Keys are readable in Redis and turn up in monitoring."""
		self.assertNotIn("BEGIN PRIVATE KEY", self.key())

	def test_rotating_only_the_key_material_leaves_the_cache_key_alone(self):
		"""Which is the whole reason `forget_token` exists."""
		rotated = json.dumps({**KEY, "private_key": "a different one"})
		self.assertEqual(self.key(), self.key(service_account_key=rotated))

	def test_adding_a_scope_leaves_the_cache_key_alone(self):
		"""The other thing `forget_token` is for, and the more confusing one."""
		extra = "https://www.googleapis.com/auth/admin.directory.group"
		self.assertEqual(self.key(), self.key(extra_scopes=extra))


class Lifetime(TestCase):
	def test_an_aware_expiry_is_measured(self):
		ahead = datetime.now(timezone.utc) + timedelta(seconds=3600)
		self.assertAlmostEqual(client._lifetime(ahead), 3600, delta=5)

	def test_a_naive_expiry_is_read_as_utc_rather_than_raising(self):
		"""Which version of google-auth is installed decides which of these arrives."""
		ahead = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=3600)
		self.assertAlmostEqual(client._lifetime(ahead), 3600, delta=5)

	def test_no_expiry_falls_back_rather_than_caching_forever(self):
		self.assertEqual(client._lifetime(None), client.FALLBACK_TTL)

	def test_an_expiry_already_past_has_no_life_left(self):
		"""A skewed clock should re-mint, not serve a dead token for an hour."""
		behind = datetime.now(timezone.utc) - timedelta(seconds=120)
		self.assertEqual(client._lifetime(behind), 0)


class Decode(TestCase):
	def decode(self, response):
		with patch.object(client.frappe, "throw", throw), patch.object(client, "_", _format):
			return client._decode(response)

	def test_a_body_is_parsed(self):
		self.assertEqual(self.decode(Response(body={"id": "114"})), {"id": "114"})

	def test_an_empty_204_is_not_an_error(self):
		"""What a successful DELETE answers with."""
		self.assertIsNone(self.decode(Response(status_code=204)))

	def test_a_refusal_carries_its_status(self):
		nested = {"error": {"code": 409, "message": "Entity already exists."}}
		with self.assertRaises(client.GoogleWorkspaceError) as raised:
			self.decode(Response(status_code=409, body=nested))
		self.assertEqual(raised.exception.status, 409)

	def test_a_refusal_carries_what_google_said_from_one_level_down(self):
		"""Google nests its message deeper than most, which is easy to miss."""
		nested = {"error": {"code": 409, "message": "Entity already exists."}}
		with self.assertRaises(client.GoogleWorkspaceError) as raised:
			self.decode(Response(status_code=409, body=nested))
		self.assertIn("Entity already exists.", str(raised.exception))

	def test_a_403_is_told_where_to_go_and_look(self):
		"""Google's own words for this name neither of the two things that cause it."""
		nested = {"error": {"code": 403, "message": "Not Authorized to access this resource/api"}}
		with self.assertRaises(client.GoogleWorkspaceError) as raised:
			self.decode(Response(status_code=403, body=nested))
		self.assertIn("domain-wide delegation", str(raised.exception))

	def test_a_flat_oauth_style_error_is_read_too(self):
		flat = {"error": "unauthorized_client", "error_description": "Client is unauthorized"}
		with self.assertRaises(client.GoogleWorkspaceError) as raised:
			self.decode(Response(status_code=400, body=flat))
		self.assertIn("Client is unauthorized", str(raised.exception))

	def test_a_refusal_that_is_not_json_still_has_its_status(self):
		"""A proxy between here and Google answering in HTML."""
		with self.assertRaises(client.GoogleWorkspaceError) as raised:
			self.decode(Response(status_code=502, text="<html>bad gateway</html>"))
		self.assertEqual(raised.exception.status, 502)


class Token(TestCase):
	"""The cache, and the one retry."""

	def setUp(self):
		self.issued = 0

	def cache(self, cached=None):
		store = {"value": cached}

		def get_value(key, expires=False, **kwargs):
			return store["value"]

		def set_value(key, value, expires_in_sec=None, **kwargs):
			store["value"] = value
			store["ttl"] = expires_in_sec

		self.store = store
		return SimpleNamespace(get_value=get_value, set_value=set_value, delete_value=lambda key: None)

	def token(self, cached=None, refresh=False, lifetime=3600):
		def issue(creds):
			self.issued += 1
			return "issued-token", lifetime

		with (
			patch.object(client, "settings", return_value=DOMAIN),
			patch.object(client.frappe, "cache", self.cache(cached)),
			patch.object(client.frappe, "throw", throw),
			patch.object(client, "_", _format),
			patch.object(client, "_issue", issue),
		):
			return client.token(refresh=refresh)

	def test_a_cached_token_is_used_without_signing_anything(self):
		self.assertEqual(self.token(cached="cached-token"), "cached-token")
		self.assertEqual(self.issued, 0)

	def test_a_cold_cache_mints_one_and_stores_it(self):
		self.assertEqual(self.token(), "issued-token")
		self.assertEqual(self.store["value"], "issued-token")

	def test_the_stored_token_expires_before_google_says_it_does(self):
		"""So a call starting just under the wire still has a good token."""
		self.token(lifetime=3600)
		self.assertEqual(self.store["ttl"], 3600 - client.EXPIRY_MARGIN)

	def test_a_token_with_no_life_left_is_never_cached_for_a_negative_time(self):
		self.token(lifetime=0)
		self.assertGreaterEqual(self.store["ttl"], 60)

	def test_a_refresh_ignores_the_cache(self):
		self.assertEqual(self.token(cached="cached-token", refresh=True), "issued-token")
		self.assertEqual(self.issued, 1)


class Directory(TestCase):
	"""The path, the header, and the 401 retried exactly once."""

	def call(self, statuses):
		"""`statuses` is what Google answers, in order."""
		self.sent = []
		answers = list(statuses)

		def send(method, url, bearer, json_body, params):
			self.sent.append((method, url, bearer))
			return Response(status_code=answers.pop(0), body={"ok": True})

		tokens = iter(["stale-token", "fresh-token"])
		with (
			patch.object(client, "settings", return_value=DOMAIN),
			patch.object(client, "token", lambda refresh=False: next(tokens)),
			patch.object(client, "_send", send),
			patch.object(client.frappe, "throw", throw),
			patch.object(client, "_", _format),
		):
			return client.directory("GET", "users/114", params={"projection": "full"})

	def test_the_path_is_relative_to_the_api(self):
		self.call([200])
		self.assertEqual(self.sent[0][1], "https://admin.googleapis.com/admin/directory/v1/users/114")

	def test_a_401_is_retried_once_with_a_fresh_token(self):
		"""A key rotated since the token was cached -- see the module docstring."""
		self.assertEqual(self.call([401, 200]), {"ok": True})
		self.assertEqual([bearer for _, _, bearer in self.sent], ["stale-token", "fresh-token"])

	def test_a_second_401_stands_rather_than_looping(self):
		with self.assertRaises(client.GoogleWorkspaceError) as raised:
			self.call([401, 401])
		self.assertEqual(raised.exception.status, 401)
		self.assertEqual(len(self.sent), 2)

	def test_a_403_is_not_retried(self):
		"""A missing scope is not fixed by a new token, and asking again is noise."""
		with self.assertRaises(client.GoogleWorkspaceError):
			self.call([403])
		self.assertEqual(len(self.sent), 1)

	def test_a_429_is_not_retried(self):
		"""Google's rate limiter, and retrying it at once is the worst answer."""
		with self.assertRaises(client.GoogleWorkspaceError):
			self.call([429])
		self.assertEqual(len(self.sent), 1)


class Errors(TestCase):
	def test_a_workspace_error_is_a_validation_error(self):
		"""So the message reaches whoever pressed the button, not a 500 log."""
		self.assertIsInstance(client.GoogleWorkspaceError("nope", status=400), frappe.ValidationError)

	def test_a_status_is_optional(self):
		"""A failure with no response at all -- a timeout, a DNS failure."""
		self.assertIsNone(client.GoogleWorkspaceError("could not reach Google").status)
