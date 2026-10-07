# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Every name in Frappe that Better Navigation hangs on, still there.

The desk half (`js/navigation_rail.js`, `js/user_menu.js`, `js/arrange.js`,
`js/boot_arrangement.js`, `public/js/user_menu_rows.js`) patches Frappe's
sidebar classes and reads their properties, markup and menu rows. In the
browser, a missing method switches the rail off and a changed one makes it give
up (`patch` in the rail), so a Frappe upgrade costs the rail, not the desk --
but quietly. This reads Frappe's own source instead, so the run after
`bench update` says which name moved, before anyone opens the desk.

A failure here is not a broken desk. It is the list of what to look at in
Frappe's diff before shipping the upgrade.
"""

import os
import re
from unittest import TestCase

import frappe

JS = ("public", "js", "frappe")

# Per file: methods defined there, `this.<property>` it sets, and strings (classes,
# row names, globals) it carries.
SEAMS = {
	("ui", "sidebar", "sidebar.js"): {
		"methods": [
			"dock_enabled",
			"open_module",
			"setup",
			"set_workspace_sidebar",
			"add_item",
			"empty",
			"open",
			"refresh_header",
			"refresh_dock",
			"create_user_menu",
		],
		"properties": [
			"$items_container",
			"current_module",
			"sidebar_expanded",
			"sidebar_header",
			"dock",
		],
		"strings": [
			"workspace-selector",
			"navbar-modal-search-mobile",
			"sidebar-notification",
			"notification-count",
			"standard-items-band",
			"frappe.get_module_icon =",
			'frappe.router.on("change"',
		],
	},
	("ui", "sidebar", "dock.js"): {
		"methods": ["make", "render_entries", "render_logo", "name_tile", "close", "refresh"],
		"properties": [
			"$dock",
			"$items",
			"tooltips",
			"$header",
			"$header_logo",
			"$header_title",
			"is_pinned",
			"enabled",
			"rendered",
			"header_tooltip",
		],
		"strings": [
			"frappe.ui.Dock =",
			"static pointer_can_reveal()",
			"dock-user",
			"dock-item",
			"dock-item-icon",
			"dock-item-label",
			"es-tooltip--plain",
		],
	},
	("ui", "sidebar", "sidebar_header.js"): {
		"methods": [
			"menu_items",
			"all_apps_item",
			"system_items",
			"navbar_items",
			"get_help_siblings",
			"refresh",
		],
		"properties": ["wrapper", "$header_title", "$header_logo", "$drop_icon", "sidebar"],
		"strings": ["frappe.ui.SidebarHeader =", "switch-module", "switch-app", "all-apps"],
	},
	("ui", "sidebar", "sidebar_header.html"): {"strings": ["title-container"]},
	("ui", "sidebar", "sidebar_item.js"): {
		"strings": ["TypeButton", "TypeSpacer", "section-break", "standard-sidebar-item"],
	},
	("ui", "sidebar", "sidebar_item.html"): {
		"strings": ["sidebar-item-container", "item-anchor", "sidebar-item-label"],
	},
	("ui", "sidebar", "sidebar_panel.js"): {
		"strings": ["frappe.ui.SidebarPanel =", "frappe.ui.sidebar_panels =", "toggle(name)"],
	},
	("ui", "sidebar", "arrangement_editor.js"): {"strings": ["frappe.ui.ArrangementEditor ="]},
	("ui", "components", "dropdown.js"): {"strings": ["frappe.ui.Dropdown ="]},
	("utils", "utils.js"): {"methods": ["app_logo", "desktop_icon"]},
}

# What the server half calls in `frappe.boot`, and the boot keys the desk half reads.
BOOT_FUNCTIONS = ["get_module_sidebars", "get_app_data", "get_app_rail_host_map"]
BOOT_KEYS = ["module_sidebars", "app_data"]


def _source(*parts: str) -> str:
	with open(frappe.get_app_path("frappe", *parts), encoding="utf-8") as f:
		return f.read()


class TestFrappeSeams(TestCase):
	def test_desk_names_are_still_in_frappe(self):
		for parts, seams in SEAMS.items():
			path = os.path.join(*parts)
			source = _source(*JS, *parts)
			# Asserted as booleans: a failure names the seam, not the whole file.
			for method in seams.get("methods", ()):
				with self.subTest(path=path, method=method):
					pattern = rf"(?m)^\s*(static\s+)?{re.escape(method)}\s*\(.*\)\s*\{{\s*$"
					self.assertTrue(re.search(pattern, source), f"{method}() is not defined in {path}")
			for prop in seams.get("properties", ()):
				with self.subTest(path=path, property=prop):
					found = re.search(rf"this\.{re.escape(prop)}\b", source)
					self.assertTrue(found, f"this.{prop} is not in {path}")
			for text in seams.get("strings", ()):
				with self.subTest(path=path, string=text):
					self.assertTrue(text in source, f"{text!r} is not in {path}")

	def test_boot_still_offers_what_the_rail_reads(self):
		import frappe.boot

		for name in BOOT_FUNCTIONS:
			with self.subTest(function=name):
				self.assertTrue(callable(getattr(frappe.boot, name, None)))
		source = _source("boot.py")
		for key in BOOT_KEYS:
			with self.subTest(key=key):
				self.assertIn(f"bootinfo.{key} =", source)
