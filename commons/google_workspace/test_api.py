"""The role check, the field allowlist, and the one endpoint that returns a secret.

Site-less. `users` is the boundary -- what each operation sends is tested in
`test_users` -- so it is stubbed here and what is checked is what this layer adds:
who is refused, which arguments become which Google fields, and whether a
password that was never applied to anything can escape.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.google_workspace import api, client

ALLOWED = ["System Manager", "Employee"]
NOT_ALLOWED = ["Employee"]


def throw(message, exc=Exception, **kwargs):
	if isinstance(exc, Exception):
		raise exc
	raise exc(message)


def _format(text):
	return text


def refused(status):
	return client.GoogleWorkspaceError(f"refused {status}", status=status)


def _endpoints():
	"""Every whitelisted function in `api`, by name.

	`frappe.whitelist` records the function in a module-level set rather than
	setting an attribute on it, so membership of `frappe.whitelisted` is the
	only way to ask this -- and asking it the obvious wrong way gives an empty
	list, which is a sweep that passes by finding nothing. `Endpoints` below
	exists to make that failure impossible to miss.
	"""
	return [
		(name, function)
		for name, function in vars(api).items()
		if callable(function) and function in frappe.whitelisted
	]


class Endpoints(TestCase):
	def test_the_sweeps_below_have_something_to_sweep(self):
		"""Both sweeps pass trivially if this finds nothing, so it is asserted once."""
		self.assertGreater(len(_endpoints()), 10)


class Permitted(TestCase):
	def roles(self, held):
		return patch.object(api.frappe, "get_roles", lambda *a, **kw: held)

	def test_the_role_is_required(self):
		with (
			self.roles(NOT_ALLOWED),
			patch.object(api.frappe, "throw", throw),
			patch.object(api, "_", _format),
		):
			with self.assertRaises(Exception):
				api._permitted()

	def test_the_role_is_enough(self):
		with self.roles(ALLOWED):
			self.assertIsNone(api._permitted())

	def test_every_endpoint_but_configured_checks_it(self):
		"""Adding an unchecked one should have to be done on purpose."""
		import inspect

		unchecked = [
			name
			for name, function in _endpoints()
			if name != "configured" and "_permitted()" not in inspect.getsource(function)
		]
		self.assertEqual(unchecked, [])

	def test_configured_answers_without_a_role(self):
		"""Otherwise a button exists on every site and explains itself only when pressed."""
		with self.roles(NOT_ALLOWED), patch.object(api.client, "available", lambda: False):
			self.assertFalse(api.configured())


class Phone(TestCase):
	def phone(self, number):
		with patch.object(api.frappe, "throw", throw), patch.object(api, "_", _format):
			return api._phone(number)

	def test_an_international_number_passes(self):
		self.assertEqual(self.phone("+254712345678"), "+254712345678")

	def test_the_spacing_people_write_is_cleaned_up(self):
		self.assertEqual(self.phone("+254 (0)712 345 678"), "+2540712345678")

	def test_a_local_number_is_asked_about_rather_than_guessed_at(self):
		"""Prefixing a country code would be inventing data."""
		with self.assertRaises(Exception) as raised:
			self.phone("0712345678")
		self.assertIn("+254712345678", str(raised.exception))

	def test_something_that_is_not_a_number_is_refused(self):
		with self.assertRaises(Exception):
			self.phone("ask reception")


class Profile(TestCase):
	def profile(self, **kwargs):
		with patch.object(api.frappe, "throw", throw), patch.object(api, "_", _format):
			return api._profile(**kwargs)

	def test_nothing_given_writes_nothing(self):
		"""An omitted argument must not become an erased field."""
		self.assertEqual(self.profile(), {})

	def test_a_phone_becomes_googles_list_valued_field(self):
		built = self.profile(phone="+254712345678")
		self.assertEqual(built["phones"][0]["value"], "+254712345678")
		self.assertTrue(built["phones"][0]["primary"])

	def test_a_recovery_address_is_the_scalar_field(self):
		self.assertEqual(self.profile(recovery_email="ann@example.net")["recoveryEmail"], "ann@example.net")

	def test_a_recovery_number_is_checked_before_it_is_sent(self):
		with self.assertRaises(Exception):
			self.profile(recovery_phone="0712345678")

	def test_a_title_and_a_department_are_one_organisation_entry(self):
		built = self.profile(job_title="Registrar", department="Admissions")
		self.assertEqual(len(built["organizations"]), 1)
		self.assertEqual(built["organizations"][0]["title"], "Registrar")

	def test_a_title_alone_is_still_an_organisation(self):
		self.assertEqual(self.profile(job_title="Registrar")["organizations"][0]["title"], "Registrar")

	def test_an_employee_id_is_an_external_id(self):
		self.assertEqual(self.profile(employee_id="EMP-0041")["externalIds"][0]["value"], "EMP-0041")

	def test_nothing_outside_the_signature_can_be_reached(self):
		"""The allowlist is the signature -- see the module docstring."""
		built = self.profile(phone="+254712345678", recovery_email="ann@example.net")
		self.assertEqual(set(built), {"phones", "recoveryEmail"})


class EnsureUser(TestCase):
	def ensure(self, create, find=None, **kwargs):
		"""`create` is what `users.create` does: a value, or an exception to raise."""
		self.created = []

		def create_user(email, given_name, family_name, password=None, **fields):
			self.created.append({"email": email, "password": password, "fields": fields})
			if isinstance(create, Exception):
				raise create
			return create

		with (
			patch.object(api.frappe, "get_roles", lambda *a, **kw: ALLOWED),
			patch.object(api.frappe, "throw", throw),
			patch.object(api, "_", _format),
			patch.object(api.users, "create", create_user),
			patch.object(api.users, "recover_existing", lambda email: find),
		):
			return api.ensure_user("ann@example.org", "Ann", "Wanjiru", **kwargs)

	def test_a_new_account_comes_back_with_a_way_to_sign_in(self):
		answer = self.ensure("114")
		self.assertEqual(answer["id"], "114")
		self.assertTrue(answer["created"])
		self.assertTrue(answer["password"])

	def test_the_password_returned_is_the_one_that_was_set(self):
		answer = self.ensure("114")
		self.assertEqual(answer["password"], self.created[0]["password"])

	def test_an_account_that_already_existed_gets_no_password(self):
		"""The generated one was never applied, so returning it would be a lie."""
		answer = self.ensure(refused(409), find="114")
		self.assertEqual(answer["id"], "114")
		self.assertFalse(answer["created"])
		self.assertIsNone(answer["password"])

	def test_created_is_which_branch_google_sent_it_down(self):
		"""Not a lookup beforehand, which a request arriving in between would spoil."""
		self.assertTrue(self.ensure("114")["created"])
		self.assertFalse(self.ensure(refused(409), find="114")["created"])

	def test_any_other_refusal_is_not_treated_as_an_existing_account(self):
		with self.assertRaises(client.GoogleWorkspaceError):
			self.ensure(refused(403))

	def test_the_named_fields_reach_the_account(self):
		self.ensure("114", phone="+254712345678", recovery_email="ann@example.net")
		self.assertEqual(self.created[0]["fields"]["recoveryEmail"], "ann@example.net")

	def test_a_caller_without_the_role_reaches_nothing(self):
		with (
			patch.object(api.frappe, "get_roles", lambda *a, **kw: NOT_ALLOWED),
			patch.object(api.frappe, "throw", throw),
			patch.object(api, "_", _format),
		):
			with self.assertRaises(Exception):
				api.ensure_user("ann@example.org", "Ann", "Wanjiru")


class UpdateUser(TestCase):
	def update(self, **kwargs):
		self.sent = {}

		def update_user(user_key, **fields):
			self.sent = fields
			return {"id": user_key}

		with (
			patch.object(api.frappe, "get_roles", lambda *a, **kw: ALLOWED),
			patch.object(api.frappe, "throw", throw),
			patch.object(api, "_", _format),
			patch.object(api.users, "update", update_user),
		):
			return api.update_user("114", **kwargs)

	def test_only_what_was_passed_is_sent(self):
		self.update(recovery_email="ann@example.net")
		self.assertEqual(self.sent, {"recoveryEmail": "ann@example.net"})

	def test_a_given_name_alone_does_not_take_the_family_name_with_it(self):
		self.update(given_name="Ann")
		self.assertEqual(self.sent["name"], {"givenName": "Ann"})

	def test_both_names_go_together(self):
		self.update(given_name="Ann", family_name="Wanjiru")
		self.assertEqual(self.sent["name"], {"givenName": "Ann", "familyName": "Wanjiru"})

	def test_an_update_that_changes_nothing_says_so(self):
		"""Rather than a PATCH with an empty body, which Google accepts and ignores."""
		with self.assertRaises(Exception):
			self.update()

	def test_the_primary_address_is_not_reachable_here(self):
		"""Changing it renames the account, which is a migration and not an edit."""
		import inspect

		signature = inspect.signature(api.update_user)
		self.assertNotIn("email", signature.parameters)


class SetUserPassword(TestCase):
	def test_it_returns_what_was_set(self):
		with (
			patch.object(api.frappe, "get_roles", lambda *a, **kw: ALLOWED),
			patch.object(api.users, "set_password", lambda key, change_at_next_login=True: "xK4"),
		):
			self.assertEqual(api.set_user_password("114"), "xK4")

	def test_the_caller_cannot_choose_the_password(self):
		"""One chosen elsewhere travels through a body, a script and their logs."""
		import inspect

		self.assertNotIn("password", inspect.signature(api.set_user_password).parameters)


class NothingDeletes(TestCase):
	def test_no_endpoint_removes_an_account(self):
		"""Deleting takes a mailbox with it; `suspend_user` is what offboarding wants."""
		self.assertFalse(hasattr(api, "delete_user"))

	def test_the_library_still_can(self):
		from commons.google_workspace import users

		self.assertTrue(callable(users.delete))


class Annotations(TestCase):
	def test_every_endpoint_is_annotated(self):
		"""`require_type_annotated_api_methods` is on for this app -- see hooks.py."""
		import inspect

		bare = []
		for name, function in _endpoints():
			signature = inspect.signature(function)
			if signature.return_annotation is inspect.Signature.empty:
				bare.append(name)
			bare += [
				f"{name}.{parameter}"
				for parameter, detail in signature.parameters.items()
				if detail.annotation is inspect.Parameter.empty
			]
		self.assertEqual(bare, [])


class Errors(TestCase):
	def test_a_refusal_reaches_whoever_pressed_the_button(self):
		self.assertIsInstance(client.GoogleWorkspaceError("nope"), frappe.ValidationError)
