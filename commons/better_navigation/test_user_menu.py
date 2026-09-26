# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Which Navbar Settings rows the SPA's user menu can carry, and as what.

The rows are written for the desk, so the translation is the whole contract: a
Route row is a URL, `new_window(...)` is a URL, and everything else that is desk
JavaScript -- an Action or a Condition -- is left out.
"""

from unittest import TestCase

import frappe

from commons.commons_core.user_menu import to_menu_item


def row(**fields):
	return frappe._dict({"item_label": "Row", "hidden": 0, "condition": None, **fields})


class TestToMenuItem(TestCase):
	def test_route_on_site_opens_in_place(self):
		self.assertEqual(
			to_menu_item(row(item_type="Route", route="/desk/system-health-report")),
			{"label": "Row", "url": "/desk/system-health-report", "new_tab": False},
		)

	def test_route_off_site_opens_in_new_tab(self):
		self.assertTrue(to_menu_item(row(item_type="Route", route="https://frappe.io/support"))["new_tab"])

	def test_new_window_action_becomes_its_url(self):
		for action in (
			"frappe.ui.toolbar.new_window('/app/system-console')",
			'frappe.ui.toolbar.new_window("/app/system-console");',
		):
			with self.subTest(action=action):
				self.assertEqual(
					to_menu_item(row(item_type="Action", action=action)),
					{"label": "Row", "url": "/app/system-console", "new_tab": True},
				)

	def test_other_actions_are_left_out(self):
		for action in ("frappe.ui.toolbar.show_about()", "frappe.ui.toolbar.new_window(x)", None):
			with self.subTest(action=action):
				self.assertIsNone(to_menu_item(row(item_type="Action", action=action)))

	def test_hidden_and_conditional_rows_are_left_out(self):
		self.assertIsNone(to_menu_item(row(item_type="Route", route="/app", hidden=1)))
		self.assertIsNone(
			to_menu_item(row(item_type="Route", route="/app", condition="eval: frappe.boot.developer_mode"))
		)
