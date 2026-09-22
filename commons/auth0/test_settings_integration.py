"""The settings against a real site: bench --site SITE execute commons.auth0.test_settings_integration.run

Rollback-only, and it never reaches Auth0. Every test here stops at the
credential layer -- what the Single holds, what the database holds underneath
it, and who is allowed to ask -- because that is the half of this section a
mocked test cannot check and the half a network test would check least
reliably. How the tenant answers is `test_client` and `test_users`, in full,
site-less.

What is worth pinning here is the claim the section is built on: that the
credential is not readable. `commons.auth0` says the secret is encrypted in
`__Auth`, absent from the document's own row, and unreadable once saved, and
that claim is the reason this is an app module rather than a Server Script. It
is a claim about Frappe's `Password` fieldtype rather than about any code here,
which is exactly the kind of thing that stops being true in a version bump
without anybody noticing.

The cache is the other reason. `forget_token` runs from `on_update` and writes
to Redis, which no savepoint rolls back -- so each test that touches it clears
its own key, and `tearDown` clears the document cache that `get_cached_doc`
would otherwise answer rolled-back values from.
"""

import unittest

import frappe

from commons import testing
from commons.auth0 import api, client

SECRET = "integration-test-secret"
DOMAIN = "integration-test.eu.auth0.com"

# Someone with a desk login and no business managing an identity provider.
ORDINARY_USER = "auth0-test-ordinary@example.com"


@testing.site_suite()
class TestAuth0Settings(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint("auth0_settings_test")
		self.addCleanup(self.restore)

	def restore(self):
		frappe.db.rollback(save_point="auth0_settings_test")
		# Neither Redis nor the document cache is in the transaction, and
		# `get_cached_doc` would go on answering with values the rollback has
		# taken back.
		frappe.clear_document_cache(client.SETTINGS)
		frappe.cache.delete_value(self.key())
		frappe.set_user("Administrator")

	def key(self) -> str:
		"""The cache key for the tenant these tests configure.

		Built by hand rather than through `client.credentials`, so it can be
		cleared in `restore` whether or not the settings were ever filled in.
		"""
		return f"auth0_management_token::{DOMAIN}::abc123"

	def configure(self, **overrides) -> "frappe.Document":
		document = frappe.get_single(client.SETTINGS)
		document.domain = overrides.get("domain", DOMAIN)
		document.client_id = overrides.get("client_id", "abc123")
		document.client_secret = overrides.get("client_secret", SECRET)
		document.connection = overrides.get("connection", "")
		document.audience = overrides.get("audience", "")
		document.save()
		frappe.clear_document_cache(client.SETTINGS)
		return document

	# What the site holds, and what it does not

	def test_a_site_with_nothing_filled_in_has_no_auth0(self):
		"""Not a broken site -- see `client.available`."""
		frappe.db.sql("DELETE FROM tabSingles WHERE doctype=%s", client.SETTINGS)
		frappe.clear_document_cache(client.SETTINGS)
		self.assertFalse(client.available())

	def test_filling_the_form_in_is_what_makes_auth0_available(self):
		self.configure()
		self.assertTrue(client.available())

	def test_the_secret_round_trips(self):
		"""Written through the form, read back by `client.settings`."""
		self.configure()
		self.assertEqual(client.credentials().client_secret, SECRET)

	def test_the_secret_is_not_in_the_doctype_s_own_row(self):
		"""The claim `commons.auth0` is built on: a `Password` field lives in `__Auth`.

		A masked `Data` field would put the secret here in plain text, where a
		report, a fixture export or anybody who can read the table would have
		it.
		"""
		self.configure()
		stored = frappe.db.sql(
			"SELECT value FROM tabSingles WHERE doctype=%s AND field='client_secret'",
			client.SETTINGS,
		)
		self.assertTrue(stored, "client_secret has no row at all")
		self.assertNotEqual(stored[0][0], SECRET)

	def test_reading_the_document_back_does_not_give_up_the_secret(self):
		"""What a System Manager opening the form sees, and what the REST API returns."""
		self.configure()
		frappe.clear_document_cache(client.SETTINGS)
		reloaded = frappe.get_doc(client.SETTINGS)
		self.assertNotEqual(reloaded.client_secret, SECRET)
		self.assertNotIn(SECRET, frappe.as_json(reloaded.as_dict()))

	# What `credentials` makes of what it is given

	def test_a_domain_pasted_with_its_scheme_is_cleaned_up(self):
		"""Site-less too, but this is the path a real save takes."""
		self.configure(domain=f"https://{DOMAIN}/")
		self.assertEqual(client.credentials().domain, DOMAIN)

	def test_a_blank_connection_becomes_auth0_s_default(self):
		self.configure()
		self.assertEqual(client.credentials().connection, client.DEFAULT_CONNECTION)

	def test_the_audience_is_derived_unless_the_form_says_otherwise(self):
		self.configure()
		self.assertEqual(client.credentials().audience, f"https://{DOMAIN}/api/v2/")

	# The cache, which no rollback reaches

	def test_saving_the_settings_drops_the_cached_token(self):
		"""A rotated secret leaves the cache key unchanged -- see `client.cache_key`."""
		document = self.configure()
		frappe.cache.set_value(self.key(), "stale-token", expires_in_sec=3600)

		document.reload()
		document.client_secret = "rotated-secret"
		document.save()

		self.assertIsNone(frappe.cache.get_value(self.key(), expires=True))

	def test_the_rotated_secret_is_what_is_read_afterwards(self):
		document = self.configure()
		document.reload()
		document.client_secret = "rotated-secret"
		document.save()
		frappe.clear_document_cache(client.SETTINGS)
		self.assertEqual(client.credentials().client_secret, "rotated-secret")

	# Who may ask

	def test_a_session_without_the_role_is_refused(self):
		"""The whole of the security of the HTTP surface -- see `commons.auth0.api`."""
		self.configure()
		frappe.set_user(self.ordinary_user())
		self.assertNotIn(api.ROLE, frappe.get_roles())
		with self.assertRaises(frappe.PermissionError):
			api.find_user("somebody@example.com")

	def test_guest_is_refused(self):
		self.configure()
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.find_user("somebody@example.com")

	def test_whether_the_site_has_auth0_is_askable_without_the_role(self):
		"""So a page can leave the button out without holding System Manager."""
		self.configure()
		frappe.set_user(self.ordinary_user())
		self.assertTrue(api.configured())

	def ordinary_user(self) -> str:
		"""A desk login with nothing granted to it. Rolled back with the rest."""
		if frappe.db.exists("User", ORDINARY_USER):
			return ORDINARY_USER

		user = frappe.new_doc("User")
		user.email = ORDINARY_USER
		user.first_name = "Auth0 Test"
		user.send_welcome_email = 0
		user.insert(ignore_permissions=True)
		return user.name


def run():
	"""Run this suite against a site by hand, verbosely.

	`bench --site SITE execute commons.auth0.test_settings_integration.run`
	"""
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		result = unittest.TextTestRunner(verbosity=2).run(
			unittest.defaultTestLoader.loadTestsFromTestCase(TestAuth0Settings)
		)
		if not result.wasSuccessful():
			raise RuntimeError("Auth0 settings integration tests failed")
		return {"tests": result.testsRun, "success": True}
	finally:
		frappe.set_user(original_user)
		frappe.db.rollback()
