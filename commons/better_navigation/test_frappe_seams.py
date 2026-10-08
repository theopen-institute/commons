# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Every name in Frappe that this app's desk additions hang on, still there.

Three kinds: the sidebar method, panel and desktop page the Desk To Do widget
(`public/js/desk_todos/`) mounts on; the user menu call `public/js/user_menu_rows.js`
passes rows through; and the order of calls the home page priority (`home_page.py`)
slips into. The rail and the rest of the desk's navigation are Open Desk's, which
checks its own.

In the browser a missing name makes each of these quietly not appear, so a Frappe
upgrade costs the feature, not the desk -- but quietly. This reads Frappe's own
source instead, so the run after `bench update` says which name moved, before anyone
opens the desk.

A failure here is not a broken desk. It is the list of what to look at in Frappe's
diff before shipping the upgrade.
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
		# Desk To Do wraps the first and calls the next two; the user menu's rows pass
		# through the last.
		"methods": ["add_standard_items", "add_item", "make_sidebar_item", "create_user_menu"],
		# Desk To Do reads the guard around the wrapped call, and the band it adds to.
		"properties": ["standard_items_setup", "$standard_items_band"],
		"strings": ["standard-items-band"],
	},
	("ui", "sidebar", "sidebar_item.js"): {"strings": ["frappe.ui.sidebar_item.TypeButton ="]},
	("ui", "sidebar", "sidebar_panel.js"): {
		"strings": ["frappe.ui.SidebarPanel =", "frappe.ui.sidebar_panels =", "toggle(name)"],
	},
	("ui", "components", "dropdown.js"): {"strings": ["frappe.ui.Dropdown ="]},
}

# The desktop page Desk To Do puts its navbar icon on: the event it listens for, and the
# bell it is placed beside. Outside `public/js`, so listed apart from SEAMS.
DESKTOP_SEAMS = {
	("desk", "page", "desktop", "desktop.js"): [
		'$(document).trigger("desktop_screen"',
		'$(".desktop-notifications")',
	],
	("desk", "page", "desktop", "desktop.html"): ['class="desktop-notifications"'],
}


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
					pattern = rf"(?m)^\s*(static\s+|get\s+)?{re.escape(method)}\s*\(.*\)\s*\{{\s*\}}?\s*$"
					self.assertTrue(re.search(pattern, source), f"{method}() is not defined in {path}")
			for prop in seams.get("properties", ()):
				with self.subTest(path=path, property=prop):
					found = re.search(rf"this\.{re.escape(prop)}\b", source)
					self.assertTrue(found, f"this.{prop} is not in {path}")
			for text in seams.get("strings", ()):
				with self.subTest(path=path, string=text):
					self.assertTrue(text in source, f"{text!r} is not in {path}")

	def test_desktop_page_still_offers_what_desk_todos_reads(self):
		for parts, texts in DESKTOP_SEAMS.items():
			path = os.path.join(*parts)
			source = _source(*parts)
			for text in texts:
				with self.subTest(path=path, string=text):
					self.assertTrue(text in source, f"{text!r} is not in {path}")

	def test_the_home_page_flag_still_comes_first(self):
		"""`home_page.py` sets `frappe.local.flags.home_page`; Frappe has to read it, and in time.

		`get_home_page` returns the flag before looking at any Role, and at login the
		`on_login` hooks run before the response's home page is asked for.
		"""
		import inspect

		from frappe.auth import LoginManager
		from frappe.website.utils import get_home_page

		self.assertTrue(
			re.search(
				r"if frappe\.local\.flags\.home_page\b[^\n]*:\s*\n\s*return frappe\.local\.flags\.home_page",
				inspect.getsource(get_home_page),
			),
			"get_home_page no longer returns frappe.local.flags.home_page first",
		)
		post_login = inspect.getsource(LoginManager.post_login)
		trigger, info = post_login.find('run_trigger("on_login")'), post_login.find("set_user_info(")
		self.assertTrue(0 <= trigger < info, "on_login no longer runs before set_user_info")
		self.assertIn("get_home_page()", inspect.getsource(LoginManager.set_user_info))
		self.assertIn('get_hooks("before_request")', _source("app.py"))
