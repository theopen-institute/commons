"""The Desktop's icons, drawn from the rail instead of from Desktop Icon records.

Core's Desktop (/desk) shows every Desktop Icon a site has: one per app, one per
workspace its sidebars came from, folders, and whatever a site added since. With
"Enable Desktop from Navigation Apps" on, the boot's `desktop_icons` is replaced
by a list built from what `navigation_apps.resolve` gives the user:

    a Navigation App bound to nothing   its frontend and its modules, each an icon
                                         of its own on the Desktop
    an installed app (bound or not),    one App icon, opening a modal of its
    and Other                            frontend and modules

A Navigation App's "Desktop" field (`desktop_display`) overrides that default
either way: Separate Icons spreads even a bound app over the Desktop, and One
Icon gathers one of the site's own into a single icon. An app with no record
of its own -- an installed app nobody configured, or Other -- has the default.

Every other icon is left out, so a site's Desktop is the rail laid flat: the
same apps, in the same order, under the same titles, hidden and restricted the
same way.

Nothing is written. A module's picture is the Desktop Image on its Navigation
App row, if set. Desktop Icon records are only read, for how an icon looks
otherwise (an app's logo, a sidebar's colour), so the records apps ship and migrate keeps
re-importing are untouched, and switching this off brings core's Desktop back
as it was. The one place a list built here is kept is a Desktop Layout, which
core saves when a user rearranges their Desktop and prefers to the boot from
then on; "Reset to default" in the Desktop's menu returns them to this list.

Labels are what the Desktop finds an icon by -- a sidebar icon opens the sidebar
named by its label, and a modal holds the icons whose `parent_icon` is its
label -- so a sidebar's icon is always labelled with the sidebar's name, and no
two icons may share a label. An app whose only destination is one module or its
frontend gets that, not a modal of one.
"""

import frappe
from frappe import _

from commons.better_navigation import navigation_apps

APP_KEY = "app:"
OTHER = navigation_apps.OTHER

# A Navigation App's `desktop_display`; anything else is the default.
SEPARATE = "Separate Icons"
ONE = "One Icon"

# How each Desktop Icon looks, by label, and each installed app's own App icon.
CACHE_KEY = "commons_desktop_icon_looks"
LOOKS = ("app", "icon", "logo_url", "icon_image", "bg_color")


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Swap core's Desktop icons for the rail's, when the switch is on."""
	from commons.commons_core import settings

	if not settings.feature_enabled(settings.ENABLE_DESKTOP_FROM_NAVIGATION_APPS):
		return
	if frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User":
		return

	from frappe.desk.doctype.desktop_icon.desktop_icon import check_app_permission

	looks = _looks()
	bootinfo.desktop_icons = desktop_icons(
		navigation_apps.navigation_apps(),
		looks=looks["by_label"],
		app_looks=looks["by_app"],
		sidebar_items=bootinfo.get("workspace_sidebar_item") or {},
		artwork=_artwork(bootinfo.get("desktop_icon_urls") or {}),
		frontend_permitted=lambda app_name: bool(check_app_permission("", app_name)),
	)


def desktop_icons(
	rail: list[dict],
	*,
	looks: dict[str, dict],
	app_looks: dict[str, dict],
	sidebar_items: dict[str, dict],
	frontend_permitted=lambda app_name: True,
	artwork: dict[str, set[str]] | None = None,
) -> list[dict]:
	"""The Desktop's icons, from plain data.

	`rail` is `navigation_apps.resolve`'s output for the user. `looks` is how
	each existing Desktop Icon looks, by label, and `app_looks` each installed
	app's App icon (with its `label`), by app. `sidebar_items` is the boot's
	`workspace_sidebar_item`: a sidebar the user can open nothing in has no
	icon, as with core. `frontend_permitted` asks an installed app's
	`add_to_apps_screen` permission hook whether its frontend is offered.
	`artwork` is the Desktop artwork each installed app ships, by app, as the
	file names `_artwork` reads out of the boot.
	"""
	artwork = artwork or {}
	icons: list[dict] = []
	taken: set[str] = set()

	def add(icon: dict) -> None:
		icon = frappe._dict(icon, idx=len(icons))
		icons.append(icon)
		taken.add(icon["label"].casefold())

	for entry in rail:
		app_name = entry["key"][len(APP_KEY) :] if entry["key"].startswith(APP_KEY) else None
		installed = app_name if app_name and app_name != OTHER else None

		destinations: list[dict] = []
		frontend = entry.get("frontend")
		if frontend and (not installed or frontend_permitted(installed)):
			destinations.append(_frontend_icon(frontend, installed, entry))
		for module in entry["sidebars"]:
			if _routable(sidebar_items.get(module["sidebar"].lower())):
				destinations.append(_sidebar_icon(module, installed, looks, artwork))
		destinations = [d for d in destinations if d["label"].casefold() not in taken]
		destinations = list({d["label"].casefold(): d for d in destinations}.values())
		if not destinations:
			continue

		# Spread over the Desktop: by default a Navigation App of the site's own.
		if _spread(entry, bound=app_name is not None):
			for destination in destinations:
				add(destination)
			continue

		# An app with one place to go: that place, wearing the app's mark.
		if len(destinations) == 1:
			add({**destinations[0], **_app_look(entry, installed, app_looks), "icon_type": "App"})
			continue

		label = _app_label(
			entry, installed, app_looks, {*taken, *(d["label"].casefold() for d in destinations)}
		)
		add(
			_icon(
				label,
				icon_type="App",
				link_type="External",
				**_app_look(entry, installed, app_looks),
			)
		)
		for destination in destinations:
			add({**destination, "parent_icon": label})
	return icons


def _spread(entry: dict, bound: bool) -> bool:
	"""Whether an app's destinations are icons of their own, rather than one icon's window."""
	display = entry.get("desktop")
	if display in (SEPARATE, ONE):
		return display == SEPARATE
	return not bound


def _routable(sidebar: dict | None) -> bool:
	"""Whether the Desktop can open a sidebar: the user can see something in it, as core asks.

	And its first link is not a report the boot left without details -- one
	disabled since it was linked. Core's Desktop routes an icon to the first
	link and reads those details unguarded, and the error stops every icon after
	it from drawing.
	"""
	if not sidebar or not sidebar.get("items"):
		return False
	first = next((item for item in sidebar["items"] if item.get("type") == "Link"), None)
	return not (first and first.get("link_type") == "Report" and not first.get("report"))


def _app_label(entry: dict, installed: str | None, app_looks: dict, taken: set[str]) -> str:
	"""What an app's icon is called: a Navigation App's own title, else the app's own icon's.

	An installed app's App icon keeps the label it ships with ("Framework"), so
	the artwork core keys by label still finds it. Only when one of the app's
	own modules has that name (Helpdesk's "Helpdesk" sidebar) does the app take
	another, since the modal is found by it.
	"""
	own = (app_looks.get(installed) or {}).get("label") if installed else None
	label = own if own and not entry.get("configured") else entry["title"]
	if label.casefold() not in taken:
		return label
	return next(
		candidate
		for candidate in (_("{0} Modules").format(label), *(f"{label} ({n})" for n in range(2, 100)))
		if candidate.casefold() not in taken
	)


def _app_look(entry: dict, installed: str | None, app_looks: dict) -> dict:
	"""An app's mark: its own App icon's look, under a Navigation App's own logo if it has one."""
	look = {key: (app_looks.get(installed) or {}).get(key) for key in LOOKS} if installed else {}
	look["app"] = installed
	if entry.get("configured") and entry.get("logo"):
		look["logo_url"] = entry["logo"]
		look["icon_image"] = None
	elif not (look.get("logo_url") or look.get("icon_image")):
		look["logo_url"] = entry.get("logo")
	return look


def _sidebar_icon(module: dict, installed: str | None, looks: dict, artwork: dict[str, set[str]]) -> dict:
	"""A module's icon: the Navigation App row's Desktop Image, else as its own Desktop Icon looks.

	Failing that, as artwork an app ships for it. Core draws the file
	`<app>/public/icons/desktop_icons/<style>/<scrubbed label>.svg` for an icon
	whose `app` has one, in the user's Solid or Subtle style, so naming the app
	is all it takes: its own installed app's first, else any app's. A sidebar
	made on the site (Transactions) gets artwork by adding a file to this app,
	with no Desktop Icon record. An icon with a logo or image of its own keeps
	it.
	"""
	name = module["sidebar"]
	look = {key: (looks.get(name) or {}).get(key) for key in LOOKS}
	look["app"] = look.get("app") or installed
	look["icon"] = look.get("icon") or module.get("icon")
	if module.get("desktop_image"):
		# The Navigation App row's own picture comes first. No app, or core
		# would draw the app's artwork by that label in its place.
		look.update(app=None, logo_url=module["desktop_image"], icon_image=None)
		return _icon(name, icon_type="Link", link_type="Workspace Sidebar", link_to=name, **look)
	stem = frappe.scrub(name)
	has_own_art = stem in artwork.get(look["app"], ()) or look.get("logo_url") or look.get("icon_image")
	if not has_own_art:
		look["app"] = next(
			(app for app in (installed, *artwork) if app and stem in artwork.get(app, ())), look["app"]
		)
	return _icon(name, icon_type="Link", link_type="Workspace Sidebar", link_to=name, **look)


def _artwork(urls: dict[str, dict[str, list[str]]]) -> dict[str, set[str]]:
	"""The boot's `desktop_icon_urls`, as the file names each app has in either style."""
	return {
		app: {url.rsplit("/", 1)[-1].removesuffix(".svg") for paths in styles.values() for url in paths}
		for app, styles in urls.items()
	}


def _frontend_icon(frontend: dict, installed: str | None, entry: dict) -> dict:
	return _icon(
		frontend["label"],
		icon_type="Link",
		link_type="External",
		link=frontend["url"],
		app=installed,
		logo_url=entry.get("logo"),
	)


def _icon(label: str, **fields) -> dict:
	"""A row as core's `get_desktop_icons` returns one."""
	return frappe._dict(
		{
			"name": label,
			"label": label,
			"link": None,
			"link_to": None,
			"parent_icon": None,
			"icon": None,
			"logo_url": None,
			"icon_image": None,
			"app": None,
			# Standard, so the Desktop's edit mode offers no "Edit" for a record
			# that does not exist; removable, so a user may still hide one.
			"standard": 1,
			"hidden": 0,
			"restrict_removal": 0,
			**fields,
			"bg_color": fields.get("bg_color") or "gray",
		}
	)


def _looks() -> dict:
	"""How the site's Desktop Icons look, cached like the rail's own inputs."""

	def read():
		rows = frappe.get_all(
			"Desktop Icon",
			# The ones every user is shown: standard, or added for the site.
			or_filters={"standard": 1, "owner": "Administrator"},
			fields=["label", "icon_type", *LOOKS],
		)
		return {
			"by_label": {row.label: {key: row[key] for key in LOOKS} for row in rows},
			"by_app": {
				row.app: {"label": row.label, **{key: row[key] for key in LOOKS}}
				for row in rows
				if row.icon_type == "App" and row.app
			},
		}

	return frappe.client_cache.get_value(CACHE_KEY, generator=read)


def clear_cache(*args, **kwargs) -> None:
	"""Forget the icons' looks, now and when the transaction ends; a doc event."""
	frappe.client_cache.delete_value(CACHE_KEY)
	if db := getattr(frappe.local, "db", None):
		db.after_commit.add(_forget)
		db.after_rollback.add(_forget)


def _forget() -> None:
	frappe.client_cache.delete_value(CACHE_KEY)
