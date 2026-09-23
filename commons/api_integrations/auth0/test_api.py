"""The role gate, and what the whitelisted surface does and does not offer.

These endpoints take an address or an id and no document, so there is nothing to
check a per-record permission against -- whoever can call them can make an
account for any address on the tenant. That makes the gate the whole of the
security of this module's HTTP surface, and worth its own tests.
"""

import inspect
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.api_integrations.auth0 import api


def throw(message, exc=Exception, **kwargs):
	if isinstance(exc, Exception):
		raise exc
	raise exc(message)


class Gate(TestCase):
	def call(self, endpoint, roles, **kwargs):
		with (
			patch.object(api.frappe, "get_roles", lambda *args: roles),
			patch.object(api.frappe, "throw", throw),
			patch.object(api, "_", lambda text: text),
			patch.object(api, "users", Recorded()),
			patch.object(api.client, "available", lambda: True),
		):
			return endpoint(**kwargs)

	def test_a_system_manager_may_make_an_account(self):
		self.assertEqual(self.call(api.ensure_user, [api.ROLE], email="a@b.c"), "auth0|ensured")

	def test_anybody_else_may_not(self):
		with self.assertRaises(frappe.PermissionError):
			self.call(api.ensure_user, ["Employee"], email="a@b.c")

	def test_reading_an_account_is_gated_too(self):
		"""It is the most revealing thing here -- `app_metadata` included."""
		with self.assertRaises(frappe.PermissionError):
			self.call(api.get_user, ["Employee"], user_id="auth0|65f")

	def test_a_password_link_is_gated(self):
		"""It is a credential for as long as it lives."""
		with self.assertRaises(frappe.PermissionError):
			self.call(api.password_change_ticket, ["Employee"], user_id="auth0|65f")

	def test_whether_the_site_has_auth0_is_not_gated(self):
		"""So a page can leave the button out without needing the role to ask."""
		self.assertTrue(self.call(api.configured, ["Employee"]))


class Recorded:
	"""`commons.api_integrations.auth0.users`, answering rather than calling Auth0."""

	def ensure(self, email, **fields):
		return "auth0|ensured"

	def find(self, email):
		return "auth0|found"

	def get(self, user_id):
		return {"user_id": user_id}

	def password_change_ticket(self, user_id, result_url=None):
		return "https://example/t/abc"

	def send_verification_email(self, user_id):
		return {"id": "job_1"}


class Surface(TestCase):
	"""What is exposed, and the one thing that must never be."""

	def whitelisted(self):
		"""Every endpoint in `api`, read off Frappe's own register.

		`frappe.whitelisted` is a set of the function objects the decorator
		registered, not a flag on each function -- a test that looked for an
		attribute would find none and pass whatever this module contained.
		"""
		found = [
			name
			for name, member in vars(api).items()
			if inspect.isfunction(member) and member in frappe.whitelisted
		]
		# The register is the point of these tests, so an empty one is a failure
		# rather than a clean run.
		self.assertTrue(found)
		return found

	def test_nothing_hands_out_a_management_token(self):
		"""The shape this integration replaced. See the module docstring on why.

		Named rather than inspected: a check against the returned value would
		pass for an endpoint that had not been written yet, and this is a rule
		about what may be added.
		"""
		for name in self.whitelisted():
			self.assertNotIn("token", name.lower())

	def test_every_gated_endpoint_checks_before_it_acts(self):
		"""An endpoint added without the check is the one way this stops working."""
		ungated = {"configured"}
		for name in self.whitelisted():
			if name in ungated:
				continue
			source = inspect.getsource(getattr(api, name))
			self.assertIn("_permitted()", source, f"{name} does not check the role")

	def test_every_endpoint_is_annotated(self):
		"""`require_type_annotated_api_methods` is on for this app -- see hooks.py."""
		for name in self.whitelisted():
			signature = inspect.signature(getattr(api, name))
			self.assertIsNot(signature.return_annotation, inspect.Signature.empty, name)
			for parameter in signature.parameters.values():
				self.assertIsNot(parameter.annotation, inspect.Parameter.empty, f"{name}.{parameter.name}")
