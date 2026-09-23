"""The credentials, the token cache, and what a refusal turns into.

Site-less. `frappe.throw` logs its message through `frappe.local`, which only a
request or a site has, so it is replaced with a plain raise wherever a decision
rather than a message is what is under test -- the same technique
`commons.safer_permissions.test_permission_gate` uses and for the same reason.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.api_integrations.auth0 import client

TENANT = {
	"domain": "example.eu.auth0.com",
	"client_id": "abc123",
	"client_secret": "shhh",
	"connection": "",
	"audience": "",
}


def throw(message, exc=Exception, **kwargs):
	"""`frappe.throw` without the message log, raising a class or an instance.

	The instance branch is the one that matters: `client._decode` passes an
	`Auth0Error` it has already built so the status survives onto the exception,
	and a stub that only handled classes would silently lose it -- which is the
	thing half of these tests are checking.
	"""
	if isinstance(exc, Exception):
		raise exc
	raise exc(message)


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
		with patch.object(client, "settings", return_value={**TENANT, **overrides}):
			return client.credentials()

	def test_a_domain_pasted_with_its_scheme_is_cleaned_up(self):
		self.assertEqual(self.held(domain="https://example.eu.auth0.com/").domain, "example.eu.auth0.com")

	def test_the_audience_is_derived_from_the_domain(self):
		self.assertEqual(self.held().audience, "https://example.eu.auth0.com/api/v2/")

	def test_a_custom_domain_tenant_can_name_its_own_audience(self):
		"""The one case where the derived answer is wrong -- see `credentials`."""
		held = self.held(domain="login.example.org", audience="https://example.eu.auth0.com/api/v2/")
		self.assertEqual(held.audience, "https://example.eu.auth0.com/api/v2/")

	def test_a_blank_connection_falls_back_to_auth0_s_default(self):
		self.assertEqual(self.held().connection, client.DEFAULT_CONNECTION)

	def test_a_tenant_that_renamed_its_connection_is_honoured(self):
		self.assertEqual(self.held(connection="Staff").connection, "Staff")

	def test_a_missing_secret_is_named_rather_than_raised_over(self):
		with patch.object(client.frappe, "throw", throw), patch.object(client, "_", lambda text: text):
			with self.assertRaises(Exception) as raised:
				self.held(client_secret="")
		self.assertIn("client_secret", str(raised.exception))


class Available(TestCase):
	def available(self, **overrides):
		with patch.object(client, "settings", return_value={**TENANT, **overrides}):
			return client.available()

	def test_a_site_with_all_three_credentials_has_auth0(self):
		self.assertTrue(self.available())

	def test_a_domain_without_a_secret_is_not_a_configured_site(self):
		"""It cannot make one call, and should be told here rather than at the token."""
		self.assertFalse(self.available(client_secret=""))

	def test_a_site_that_has_never_been_set_up_has_no_auth0(self):
		with patch.object(client, "settings", return_value={}):
			self.assertFalse(client.available())


class CacheKey(TestCase):
	def key(self, **overrides):
		with patch.object(client, "settings", return_value={**TENANT, **overrides}):
			return client.cache_key(client.credentials())

	def test_two_tenants_do_not_share_a_token(self):
		self.assertNotEqual(self.key(), self.key(domain="other.eu.auth0.com"))

	def test_two_applications_on_one_tenant_do_not_share_a_token(self):
		self.assertNotEqual(self.key(), self.key(client_id="def456"))

	def test_the_secret_is_not_in_the_key(self):
		"""Keys are readable in Redis and turn up in monitoring."""
		self.assertNotIn(TENANT["client_secret"], self.key())

	def test_rotating_only_the_secret_leaves_the_key_alone(self):
		"""Which is the whole reason `forget_token` exists."""
		self.assertEqual(self.key(), self.key(client_secret="rotated"))


class Decode(TestCase):
	def decode(self, response):
		with patch.object(client.frappe, "throw", throw), patch.object(client, "_", _format):
			return client._decode(response)

	def test_a_body_is_parsed(self):
		self.assertEqual(self.decode(Response(body={"user_id": "auth0|1"})), {"user_id": "auth0|1"})

	def test_an_empty_204_is_not_an_error(self):
		"""What a successful DELETE answers with."""
		self.assertIsNone(self.decode(Response(status_code=204)))

	def test_a_refusal_carries_its_status(self):
		with self.assertRaises(client.Auth0Error) as raised:
			self.decode(Response(status_code=409, body={"message": "The user already exists."}))
		self.assertEqual(raised.exception.status, 409)

	def test_a_refusal_carries_what_auth0_said(self):
		with self.assertRaises(client.Auth0Error) as raised:
			self.decode(Response(status_code=403, body={"message": "Insufficient scope"}))
		self.assertIn("Insufficient scope", str(raised.exception))

	def test_a_refusal_that_is_not_json_still_has_its_status(self):
		"""A gateway between here and Auth0 answering in HTML."""
		with self.assertRaises(client.Auth0Error) as raised:
			self.decode(Response(status_code=502, text="<html>bad gateway</html>"))
		self.assertEqual(raised.exception.status, 502)


def _format(text):
	"""`frappe._` without a site: `.format` is what the callers go on to call."""
	return text


class Token(TestCase):
	"""The cache, and the one retry."""

	def setUp(self):
		self.issued = []

	def cache(self, cached=None):
		store = {"value": cached}

		def get_value(key, expires=False, **kwargs):
			return store["value"]

		def set_value(key, value, expires_in_sec=None, **kwargs):
			store["value"] = value
			store["ttl"] = expires_in_sec

		self.store = store
		return SimpleNamespace(get_value=get_value, set_value=set_value, delete_value=lambda key: None)

	def token(self, cached=None, refresh=False, expires_in=86400):
		def send(method, url, bearer, json_body, params):
			self.issued.append(url)
			return Response(body={"access_token": "issued-token", "expires_in": expires_in})

		with (
			patch.object(client, "settings", return_value=TENANT),
			patch.object(client.frappe, "cache", self.cache(cached)),
			patch.object(client, "_send", send),
		):
			return client.token(refresh=refresh)

	def test_a_cached_token_is_used_without_asking_auth0(self):
		self.assertEqual(self.token(cached="cached-token"), "cached-token")
		self.assertEqual(self.issued, [])

	def test_a_cold_cache_fetches_and_stores_one(self):
		self.assertEqual(self.token(), "issued-token")
		self.assertEqual(self.store["value"], "issued-token")

	def test_the_stored_token_expires_before_auth0_says_it_does(self):
		"""So a call starting just under the wire still has a good token."""
		self.token(expires_in=86400)
		self.assertEqual(self.store["ttl"], 86400 - client.EXPIRY_MARGIN)

	def test_a_short_lived_token_is_never_cached_for_a_negative_time(self):
		self.token(expires_in=60)
		self.assertGreaterEqual(self.store["ttl"], 60)

	def test_a_refresh_ignores_the_cache(self):
		self.assertEqual(self.token(cached="cached-token", refresh=True), "issued-token")
		self.assertEqual(len(self.issued), 1)


class Management(TestCase):
	"""The path, the header, and the 401 retried exactly once."""

	def call(self, statuses):
		"""`statuses` is what Auth0 answers, in order."""
		self.sent = []
		answers = list(statuses)

		def send(method, url, bearer, json_body, params):
			self.sent.append((method, url, bearer))
			return Response(status_code=answers.pop(0), body={"ok": True})

		tokens = iter(["stale-token", "fresh-token"])
		with (
			patch.object(client, "settings", return_value=TENANT),
			patch.object(client, "token", lambda refresh=False: next(tokens)),
			patch.object(client, "_send", send),
			patch.object(client.frappe, "throw", throw),
			patch.object(client, "_", _format),
		):
			return client.management("GET", "users-by-email", params={"email": "a@b.c"})

	def test_the_path_is_relative_to_the_api_version(self):
		self.call([200])
		self.assertEqual(self.sent[0][1], "https://example.eu.auth0.com/api/v2/users-by-email")

	def test_a_401_is_retried_once_with_a_fresh_token(self):
		"""A secret rotated since the token was cached -- see the module docstring."""
		self.assertEqual(self.call([401, 200]), {"ok": True})
		self.assertEqual([bearer for _, _, bearer in self.sent], ["stale-token", "fresh-token"])

	def test_a_second_401_stands_rather_than_looping(self):
		with self.assertRaises(client.Auth0Error) as raised:
			self.call([401, 401])
		self.assertEqual(raised.exception.status, 401)
		self.assertEqual(len(self.sent), 2)

	def test_a_403_is_not_retried(self):
		"""A missing scope is not fixed by a new token, and asking again is noise."""
		with self.assertRaises(client.Auth0Error):
			self.call([403])
		self.assertEqual(len(self.sent), 1)


class Errors(TestCase):
	def test_an_auth0_error_is_a_validation_error(self):
		"""So the message reaches whoever pressed the button, not a 500 log."""
		self.assertIsInstance(client.Auth0Error("nope", status=400), frappe.ValidationError)

	def test_a_status_is_optional(self):
		"""A failure with no response at all -- a timeout, a DNS failure."""
		self.assertIsNone(client.Auth0Error("could not reach Auth0").status)
