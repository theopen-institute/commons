# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Desk islands on v16: the registry, the boot list, and how each steps aside.

The registry is a copy of frappe develop's, so its tests are the questions
develop's own `test_island.py` asks of it. The boot tests are about this app's
two additions: the switch in Commons Settings, and yielding to a Frappe that
fills the list itself.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.pseudo_islands import boot, registry

ASSETS = {
	"commons.banking.island.js": "/assets/commons/dist/island/commons.banking.island.A.js",
	"commons.banking.island.css": "/assets/commons/dist/island/commons.island.B.css",
	"elsewhere.chart.island.js": "/assets/elsewhere/dist/island/elsewhere.chart.island.C.js",
	"commons.page.sales.island.js": "/assets/frappe/dist/page-island/commons.page.sales.island.D.js",
	"commons.bundle.js": "/assets/commons/dist/js/commons.bundle.E.js",
}


class TestRegistry(TestCase):
	def test_an_island_is_its_asset_key_without_the_suffix(self):
		self.assertEqual(registry.island_name("commons.banking.island.js"), "commons.banking")
		self.assertIsNone(registry.island_name("commons.banking.island.css"))
		self.assertIsNone(registry.island_name("commons.bundle.js"))

	def test_an_island_belongs_to_the_app_that_serves_it(self):
		self.assertEqual(
			registry.island_app("commons.banking", ASSETS["commons.banking.island.js"]), "commons"
		)

	def test_a_page_island_belongs_to_the_app_in_its_name(self):
		self.assertEqual(
			registry.island_app("commons.page.sales", ASSETS["commons.page.sales.island.js"]), "commons"
		)

	def test_only_the_islands_of_installed_apps_are_on_the_site(self):
		with (
			patch.object(registry, "get_assets_json", return_value=ASSETS),
			patch.object(frappe, "get_installed_apps", return_value=["frappe", "commons"]),
		):
			self.assertEqual(registry.get_ui_islands(), ["commons.banking", "commons.page.sales"])


class TestBoot(TestCase):
	def test_switched_off_sends_nothing(self):
		bootinfo = frappe._dict()
		with patch.object(boot, "enabled", return_value=False):
			boot.extend_bootinfo(bootinfo)
		self.assertNotIn("ui_islands", bootinfo)

	def test_switched_on_sends_the_registry(self):
		bootinfo = frappe._dict()
		with (
			patch.object(boot, "enabled", return_value=True),
			patch.object(registry, "get_ui_islands", return_value=["commons.banking"]),
		):
			boot.extend_bootinfo(bootinfo)
		self.assertEqual(bootinfo.ui_islands, ["commons.banking"])

	def test_a_frappe_with_its_own_list_keeps_it(self):
		"""v17 fills `ui_islands` before app hooks run; this must not overwrite it."""
		bootinfo = frappe._dict(ui_islands=["frappe.own"])
		with (
			patch.object(boot, "enabled", return_value=True),
			patch.object(registry, "get_ui_islands", return_value=["commons.banking"]),
		):
			boot.extend_bootinfo(bootinfo)
		self.assertEqual(bootinfo.ui_islands, ["frappe.own"])


class TestAssetsEndpoint(TestCase):
	def test_the_v17_method_name_reaches_this_module(self):
		from commons import hooks

		self.assertEqual(
			hooks.override_whitelisted_methods["frappe.utils.island.get_island_assets"],
			"commons.pseudo_islands.registry.get_island_assets",
		)

	def test_switched_off_the_endpoint_refuses(self):
		with patch.object(boot, "enabled", return_value=False), self.assertRaises(frappe.ValidationError):
			registry.get_island_assets("commons.banking")
