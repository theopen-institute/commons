"""The Commons Settings switch in front of the home page rule, without a site."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.commons_core import home_page


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
