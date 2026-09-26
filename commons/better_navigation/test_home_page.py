"""The Commons Settings switch in front of the home page rule, without a site."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.better_navigation import home_page


class TestSwitch(TestCase):
	def flag(self, enabled):
		local = SimpleNamespace(session=SimpleNamespace(user="employee@example.com"), flags=frappe._dict())
		with (
			patch.object(home_page.frappe, "local", local),
			patch.object(home_page.settings, "feature_enabled", return_value=enabled),
			patch.object(home_page, "resolve", return_value="staff"),
		):
			home_page.set_home_page_flag()
		return local.flags.home_page

	def test_switched_on_the_priority_decides(self):
		self.assertEqual(self.flag(True), "staff")

	def test_switched_off_core_decides(self):
		"""Nothing set, so `get_home_page` runs its own first-role-found loop."""
		self.assertIsNone(self.flag(False))


class TestLogin(TestCase):
	"""At `POST /login` the session is Guest's when `before_request` runs."""

	def login(self, enabled, already=None):
		local = SimpleNamespace(flags=frappe._dict(home_page=already))
		with (
			patch.object(home_page.frappe, "local", local),
			patch.object(home_page.settings, "feature_enabled", return_value=enabled),
			patch.object(home_page, "resolve", side_effect=lambda user: f"home-of-{user}"),
		):
			home_page.set_home_page_on_login(SimpleNamespace(user="employee@example.com"))
		return local.flags.home_page

	def test_the_user_logging_in_gets_their_priority(self):
		self.assertEqual(self.login(True), "home-of-employee@example.com")

	def test_switched_off_core_decides(self):
		self.assertIsNone(self.login(False))

	def test_something_upstream_that_decided_is_left_alone(self):
		self.assertEqual(self.login(True, already="elsewhere"), "elsewhere")


class TestCandidates(TestCase):
	def test_administrator_is_left_to_core(self):
		"""`get_roles` gives Administrator every role; no order over those means anything."""
		with patch.object(home_page.frappe, "cache", SimpleNamespace(hget=lambda *a: self.fail("resolved"))):
			self.assertEqual(home_page.resolve("Administrator"), "")

	def test_a_disabled_role_decides_nothing(self):
		asked = {}
		database = SimpleNamespace(has_column=lambda *a: True)
		with (
			patch.object(home_page.frappe, "db", database),
			patch.object(home_page.frappe, "get_roles", return_value=["Employee"]),
			patch.object(home_page.frappe, "get_all", side_effect=lambda *a, **kw: asked.update(kw) or []),
		):
			home_page.candidates("employee@example.com")
		self.assertEqual(asked["filters"]["disabled"], 0)


class TestCacheClearing(TestCase):
	def test_cleared_now_and_again_once_the_save_settles(self):
		"""A read between the clear and the commit would otherwise cache the old answer for good."""
		deleted = []
		committed, rolled_back = [], []
		db = SimpleNamespace(
			after_commit=SimpleNamespace(add=committed.append),
			after_rollback=SimpleNamespace(add=rolled_back.append),
		)
		with (
			patch.object(home_page.frappe, "local", SimpleNamespace(db=db)),
			patch.object(home_page.frappe, "cache", SimpleNamespace(delete_value=deleted.append)),
		):
			home_page.clear_cache()
			self.assertEqual(deleted, [home_page.CACHE_KEY])
			committed[0]()
			rolled_back[0]()
		self.assertEqual(deleted, [home_page.CACHE_KEY] * 3)
