# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Frappe's Apps screen, arranged from the Navigation Apps.

Frappe 16.50's Apps screen (`/desk`, with Desktop Settings on "Apps") draws one tile per
entry in `frappe.boot.app_data` that is `on_apps_screen`, ordered by `sequence_id`, and
sends each to its landing route: the entry's `app_route`, else the first row of its
`dock`, else its first module (`Sidebar.app_landing_route`). So the screen is arranged
here, in the boot, and Frappe draws it -- nothing in the browser is patched.

Each app on the rail, in rail order, as its Navigation App's Apps Screen setting says:

- One Icon (and every app with no record): its own tile, under its rail title and logo.
- Icon per Module: a tile for each of its modules, in its order -- and one for its
  frontend, first, if it has one -- each opening that module. A module's picture is its
  row's Apps Screen Image, else the letter Frappe draws.
- Hidden: no tile; it stays on the rail.

An app taken off the rail is off the Apps screen too, and every other entry is turned off.

A module tile is an `app_data` entry of its own, named `commons-module:<shell>`, whose
`dock` is that one module: Frappe's landing ladder then opens the module the way a rail
tile would. Such entries are only ever on the Apps screen; the module still belongs to
its rail app everywhere else.

Off unless Commons Settings' "Enable Apps Screen from Navigation Apps" is ticked.
"""

import frappe

from commons.better_navigation import navigation_apps as nav

ONE_ICON = "One Icon"
PER_MODULE = "Icon per Module"
HIDDEN = "Hidden"


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Arrange the Apps screen, when Commons Settings says so. Runs after the rail's hook."""
	from commons.commons_core import settings

	if not settings.feature_enabled(settings.ENABLE_DESKTOP_FROM_NAVIGATION_APPS):
		return
	if bootinfo.get("module_sidebars") is None or bootinfo.get("app_data") is None:
		return
	try:
		rail = bootinfo.get("navigation_apps")
		if rail is None:
			rail = nav.navigation_apps(module_sidebars=bootinfo.module_sidebars, app_data=bootinfo.app_data)
		arrange(bootinfo.app_data, rail)
	except Exception:
		# The boot is read on a GET; a broken arrangement leaves Frappe's own screen.
		frappe.log_error(title="Apps screen from Navigation Apps: kept Frappe's", defer_insert=True)


def arrange(app_data: list[dict], rail: list[dict]) -> None:
	"""Rewrite `app_data` in place so the Apps screen shows `rail` as its settings say."""
	by_name = {entry.get("app_name"): entry for entry in app_data}
	for entry in app_data:
		entry["on_apps_screen"] = False

	sequence = 0
	for app in rail:
		mode = app.get("apps_screen") or ONE_ICON
		if mode == HIDDEN:
			continue

		if mode == PER_MODULE:
			if app.get("frontend"):
				sequence += 1
				app_data.append(
					_tile(
						f"commons-frontend:{app['key']}",
						app["frontend"]["label"],
						app.get("logo"),
						sequence,
						route=app["frontend"]["url"],
					)
				)
			for module in app["sidebars"]:
				sequence += 1
				app_data.append(
					_tile(
						f"commons-module:{module['sidebar']}",
						module["label"],
						module.get("desktop_image"),
						sequence,
						dock=[{"link_type": "Sidebar", "link_to": module["sidebar"]}],
					)
				)
			continue

		sequence += 1
		entry = by_name.get(app["app_name"])
		if entry is None:
			entry = _tile(app["app_name"], app["title"], app.get("logo"), sequence)
			app_data.append(entry)
			by_name[app["app_name"]] = entry
		entry.update(on_apps_screen=True, sequence_id=sequence, app_title=app["title"])
		if app.get("logo"):
			entry["app_logo_url"] = app["logo"]
		# An app Frappe does not know has no dock of its own; its modules lead into it, so the
		# tile opens its first one even where the rail has not placed them.
		if not entry.get("dock") and not entry.get("app_route"):
			entry["dock"] = [{"link_type": "Sidebar", "link_to": m["sidebar"]} for m in app["sidebars"]]


def _tile(
	app_name: str,
	title: str,
	logo: str | None,
	sequence: int,
	route: str = "",
	dock: list[dict] | None = None,
) -> dict:
	return {
		"app_name": app_name,
		"app_title": title,
		"app_logo_url": logo or None,
		"app_route": route,
		"desk_route": "",
		"on_apps_screen": True,
		"sequence_id": sequence,
		"dock": dock or [],
	}
