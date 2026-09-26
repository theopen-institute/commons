# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""What the SPA's user menu lists beyond its own entries.

The desk sidebar's user badge opens a menu of the account and maintenance entries
that used to sit in its header menu (`commons/public/js/user_menu.js`). The SPA's
sidebar has the same menu, and two parts of it come from site configuration
rather than code:

- Session Defaults: the Link fields Session Default Settings lists, each with this
  user's current value. The desk gets them on `frappe.boot.session_defaults`.
- Help, and the rows under it: Navbar Settings' "help_dropdown" and
  "settings_dropdown" tables.

Navbar rows are written for the desk. A Route row is a URL and travels as one. An
Action row is desk JavaScript (`frappe.ui.toolbar.show_about()`), and so is a
row's Condition; the SPA has neither `frappe.ui` nor `frappe.boot` to run them
against. The one Action that is really a URL -- `new_window('/app/...')`, which
is how System Console is added -- is turned into one. Every other Action row,
and every row with a Condition, is left out rather than drawn as an entry that
does nothing, or shown to people the desk would hide it from.
"""

import json
import re

import frappe

# `frappe.ui.toolbar.new_window('/app/system-console')`, quoted either way.
NEW_WINDOW = re.compile(r"""^\s*frappe\.ui\.toolbar\.new_window\(\s*(['"])(?P<url>[^'"]+)\1\s*\)\s*;?\s*$""")


@frappe.whitelist()
def get_user_menu() -> dict:
	"""The site-configured parts of the SPA's user menu.

	Whitelisted as well as read into the page's boot data, for the Vite dev
	server, which serves `index.html` without the Jinja pass. Nothing here is
	more than the desk already hands the same user on boot.
	"""
	navbar = frappe.get_cached_doc("Navbar Settings")
	return {
		"session_defaults": get_session_defaults(),
		"session_defaults_settings": bool(frappe.has_permission("Session Default Settings", "read")),
		"help": [row for row in map(to_menu_item, navbar.help_dropdown) if row],
		"settings": [row for row in map(to_menu_item, navbar.settings_dropdown) if row],
	}


def get_session_defaults() -> list[dict]:
	from frappe.core.doctype.session_default_settings.session_default_settings import (
		get_session_default_values,
	)

	return [
		{
			"fieldname": field["fieldname"],
			"doctype": field["options"],
			"label": field["label"],
			"value": field.get("default") or None,
		}
		for field in json.loads(get_session_default_values())
	]


def to_menu_item(row) -> dict | None:
	"""A Navbar Item as `{label, url, new_tab}`, or None where the SPA cannot honour it."""
	if row.hidden or row.condition:
		return None

	if row.item_type == "Route" and row.route:
		# The desk's menu opens a URL off the site in a new tab and a path on it
		# in place.
		return {"label": row.item_label, "url": row.route, "new_tab": not row.route.startswith("/")}

	if row.item_type == "Action" and (match := NEW_WINDOW.match(row.action or "")):
		return {"label": row.item_label, "url": match["url"], "new_tab": True}

	return None
