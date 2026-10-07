# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Every name in Frappe that Better Navigation hangs on, still there.

Five kinds: the sidebar classes the rail patches and reads, the arrangement
editor `js/arrange.js` extends, the classes `scss/navigation_rail.scss` styles,
the order of calls the home page priority (`home_page.py`) slips into, and the
sidebar method and desktop page the Desk To Do widget
(`public/js/desk_todos/`) mounts on.

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
			# Desk To Do wraps the first and calls the other two.
			"add_standard_items",
			"make_sidebar_item",
		],
		"properties": [
			"$items_container",
			"current_module",
			"sidebar_expanded",
			"sidebar_header",
			"dock",
			# Desk To Do reads the guard around the wrapped call, and the band it adds to.
			"standard_items_setup",
			"$standard_items_band",
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
		"strings": [
			"frappe.ui.sidebar_item.TypeButton =",
			"TypeSpacer",
			"section-break",
			"standard-sidebar-item",
		],
	},
	("ui", "sidebar", "sidebar_item.html"): {
		"strings": ["sidebar-item-container", "item-anchor", "sidebar-item-label"],
	},
	("ui", "sidebar", "sidebar_panel.js"): {
		"strings": ["frappe.ui.SidebarPanel =", "frappe.ui.sidebar_panels =", "toggle(name)"],
	},
	# `js/arrange.js` subclasses it: the methods it overrides or calls, and the fields it reads.
	("ui", "sidebar", "arrangement_editor.js"): {
		"methods": [
			"layers",
			"prepare",
			"title",
			"save_args",
			"can_add",
			"add",
			"apply",
			"copy",
			"reset",
			"is_own_add",
			"item_extras",
			"item_classes",
			"decorate_item",
			"entry_icon",
			"preview_item",
			"visibility_button",
			"hide_tooltip",
			"arranged_rows",
			"arrange",
			"render_panes",
		],
		"properties": ["entries", "order", "hidden", "can_curate_site", "layer_config", "loaded", "dialog"],
		"strings": ["frappe.ui.ArrangementEditor ="],
	},
	("ui", "components", "dropdown.js"): {"strings": ["frappe.ui.Dropdown ="]},
	("utils", "utils.js"): {"methods": ["app_logo", "desktop_icon", "sidebar_for_module"]},
}

# The rail's drawers open over the sidebar, one above its z-index.
SCSS_SEAMS = {("desk", "sidebar.scss"): ["z-index: 1020"]}

# The desktop page Desk To Do puts its navbar icon on: the event it listens for, and the
# bell it is placed beside. Outside `public/js`, so listed apart from SEAMS.
DESKTOP_SEAMS = {
	("desk", "page", "desktop", "desktop.js"): [
		'$(document).trigger("desktop_screen"',
		'$(".desktop-notifications")',
	],
	("desk", "page", "desktop", "desktop.html"): ['class="desktop-notifications"'],
}

# Where Frappe's own classes may be defined or drawn: its stylesheets and the sidebar's scripts
# and templates.
CLASS_SOURCES = [("public", "scss"), ("public", "js", "frappe", "ui", "sidebar")]

# What the server half calls in `frappe.boot`, and the boot keys the desk half reads.
BOOT_FUNCTIONS = ["get_module_sidebars", "get_app_data", "get_app_rail_host_map", "get_boot_module_app"]
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

	def test_boot_still_offers_what_the_rail_reads(self):
		import frappe.boot

		for name in BOOT_FUNCTIONS:
			with self.subTest(function=name):
				self.assertTrue(callable(getattr(frappe.boot, name, None)))
		source = _source("boot.py")
		for key in BOOT_KEYS:
			with self.subTest(key=key):
				self.assertIn(f"bootinfo.{key} =", source)

	def test_app_data_is_in_the_boot_before_extend_bootinfo_runs(self):
		"""The rail reads this user's `app_data` from the boot it extends (`navigation_apps.py`)."""
		# `get_bootinfo` builds it (`load_desktop_data`), then the session runs the hooks.
		self.assertIn("load_desktop_data(bootinfo", _source("boot.py"))
		sessions = _source("sessions.py")
		self.assertLess(
			sessions.index("bootinfo = get_bootinfo()"), sessions.index('get_hooks("extend_bootinfo")')
		)

	def test_every_frappe_class_the_rail_styles_is_still_frappes(self):
		"""A renamed class throws nothing: the rail only looks wrong. So each is looked for here."""
		with open(frappe.get_app_path("commons", "better_navigation", "scss", "navigation_rail.scss")) as f:
			stylesheet = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", f.read())
		classes = {
			name for name in re.findall(r"\.([a-z][\w-]*)", stylesheet) if not name.startswith("commons-")
		}
		self.assertTrue(classes, "read no classes from navigation_rail.scss")

		frappe_source = []
		for parts in CLASS_SOURCES:
			for root, _dirs, files in os.walk(frappe.get_app_path("frappe", *parts)):
				for name in files:
					if name.endswith((".scss", ".js", ".html")):
						with open(os.path.join(root, name), encoding="utf-8") as f:
							frappe_source.append(f.read())
		frappe_source = "\n".join(frappe_source)

		for name in sorted(classes):
			with self.subTest(css_class=name):
				found = re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", frappe_source)
				self.assertTrue(found, f".{name} is styled by navigation_rail.scss but is not in Frappe")
		for parts, texts in SCSS_SEAMS.items():
			source = _source("public", "scss", *parts)
			for text in texts:
				with self.subTest(path=os.path.join(*parts), string=text):
					self.assertTrue(text in source, f"{text!r} is not in {os.path.join(*parts)}")

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
