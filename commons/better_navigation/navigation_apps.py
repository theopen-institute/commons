"""The rail: which apps it lists, and which sidebars each one offers.

Three levels, in this app's terms rather than Frappe's:

    Navigation App   an entry on the rail
      Sidebar        a module, picked from the app's top menu (a `Workspace Sidebar`)
        Item         a row in the sidebar (a `Workspace Sidebar Item`)

Only the top level is new. The bottom two are v16's own Workspace Sidebar and its
items, which already render, filter by permission and have an editor; this adds
the grouping above them that Frappe has no document for. (Upstream's v17 draws
the same three levels as Dock, Sidebar and Sidebar Item, so a `Navigation App`
maps onto a Dock when that arrives.)

"App" here is not an installed app. A `Navigation App` is whatever grouping a
site wants on its rail -- "Finance" holding sidebars from ERPNext and from this
app, say -- and a site may add as many as it likes.

The fallback is the installed apps
----------------------------------
A site that has configured nothing still gets a rail: one entry per installed
app, holding the sidebars that belong to it. And a site that has configured some
apps loses nothing it did not mention -- every sidebar no `Navigation App`
claims is still grouped under its installed app, after the configured ones. So
installing an app puts it on the rail without anybody touching this, and
configuring is only ever a matter of claiming what should move.

Which installed app a sidebar belongs to is not one field. A standard sidebar
names its app; one made on the site usually does not (the form only offers the
field for standard ones). So it is asked in turn: the sidebar's own `app`, then
the app of its `module`, then the app of a Desktop Icon of the same name. A
sidebar none of those place is grouped under "Other", which is the honest answer
and a hint that it wants claiming.

Two rules
---------
*A sidebar is in one app.* The header has to say which app and module the page
you are on belongs to, and a sidebar in two apps has no answer. Enforced when a
`Navigation App` is saved; here the first to claim one keeps it, so a conflict
that got past the form still resolves the same way every time.

*A role-restricted app still claims its sidebars.* Otherwise somebody without
the role would find the same sidebars back under their installed app, and the
restriction would only have moved them. Roles decide who sees the app on the
rail; they are not permission, and a sidebar a person cannot open is filtered
by the browser against what the boot already allows them, the same split
`workspaces.py` makes for the frontend's rows.

Personal sidebars (`for_user`) are left out of the fallback for everyone but
their owner, and cannot be claimed at all: a rail shared by a site is no place
for one person's sidebar.
"""

import frappe

APP = "Navigation App"
APP_SIDEBAR = "Navigation App Sidebar"
SIDEBAR = "Workspace Sidebar"

# Where a sidebar goes when nothing says which app it belongs to.
OTHER = "Other"


@frappe.whitelist()
def get_navigation_apps() -> list[dict]:
	"""The rail, for the session user."""
	return navigation_apps()


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Hand the desk its rail, when the rail is switched on.

	On the boot rather than behind a call, so the rail draws with the sidebar
	instead of after it. Left off entirely while the switch is off: the rail's
	script checks the same flag and installs nothing.
	"""
	from commons.commons_core import settings

	if settings.feature_enabled(settings.ENABLE_NAVIGATION_RAIL):
		bootinfo.navigation_apps = navigation_apps()


def navigation_apps(user: str | None = None) -> list[dict]:
	"""The rail for `user` (the session user by default), read from the site."""
	user = user or frappe.session.user
	return resolve(
		configured=_configured(),
		sidebars=_sidebars(),
		installed_apps=frappe.get_installed_apps(),
		app_meta=_app_meta(),
		module_apps=dict(frappe.get_all("Module Def", fields=["name", "app_name"], as_list=True)),
		icon_apps=_icon_apps(),
		user=user,
		user_roles=set(frappe.get_roles(user)),
	)


def resolve(
	*,
	configured: list[dict],
	sidebars: list[dict],
	installed_apps: list[str],
	app_meta: dict[str, dict],
	module_apps: dict[str, str],
	icon_apps: dict[str, str],
	user: str,
	user_roles: set[str],
) -> list[dict]:
	"""The rail, from plain data: configured apps first, then the installed ones.

	`configured` is the enabled Navigation Apps in rail order, each with its
	`sidebars` rows (`sidebar`, `label`) and `roles`. `sidebars` is every
	Workspace Sidebar (`name`, `header_icon`, `app`, `module`, `for_user`).
	The rest say what an installed app is called and which app a module or a
	Desktop Icon belongs to.
	"""
	by_name = {sidebar["name"]: sidebar for sidebar in sidebars}
	claimed: set[str] = set()
	rail: list[dict] = []

	for app in configured:
		entries = []
		for row in app["sidebars"]:
			sidebar = by_name.get(row["sidebar"])
			# Deleted since, personal, or already claimed by an earlier app.
			if not sidebar or sidebar.get("for_user") or sidebar["name"] in claimed:
				continue
			claimed.add(sidebar["name"])
			entries.append(_entry(sidebar, row.get("label")))

		roles = set(app.get("roles") or ())
		if roles and not roles & user_roles:
			continue
		if entries:
			entries.sort(key=_by_label)
			rail.append(
				{
					"key": f"navigation-app:{app['name']}",
					"title": app["title"],
					"icon": app.get("icon") or None,
					"logo": app.get("logo") or None,
					"configured": True,
					"sidebars": entries,
				}
			)

	grouped: dict[str, list[dict]] = {}
	for sidebar in sidebars:
		if sidebar["name"] in claimed:
			continue
		if sidebar.get("for_user") and sidebar["for_user"] != user:
			continue
		owner = installed_app_of(sidebar, module_apps, icon_apps)
		if owner not in installed_apps:
			owner = OTHER
		grouped.setdefault(owner, []).append(_entry(sidebar))

	for app_name in [*installed_apps, OTHER]:
		entries = grouped.get(app_name)
		if not entries:
			continue
		meta = app_meta.get(app_name) or {}
		rail.append(
			{
				"key": f"app:{app_name}",
				"title": meta.get("title") or (OTHER if app_name == OTHER else app_name),
				"icon": None,
				"logo": meta.get("logo") or None,
				"configured": False,
				"sidebars": sorted(entries, key=_by_label),
			}
		)
	return rail


def installed_app_of(sidebar: dict, module_apps: dict[str, str], icon_apps: dict[str, str]) -> str | None:
	"""Which installed app a sidebar belongs to, asked in the order the module docstring gives."""
	if sidebar.get("app"):
		return sidebar["app"]
	module = (sidebar.get("module") or "").strip()
	if module in module_apps:
		return module_apps[module]
	return icon_apps.get(sidebar["name"])


def _by_label(entry: dict) -> str:
	"""Modules are always listed alphabetically, by what the menus call them."""
	return entry["label"].casefold()


def _entry(sidebar: dict, label: str | None = None) -> dict:
	return {
		"sidebar": sidebar["name"],
		"label": (label or "").strip() or sidebar["name"],
		"icon": sidebar.get("header_icon") or None,
	}


def installed() -> bool:
	"""Whether `Navigation App` is on this site yet.

	The same deploy window `workspaces.installed` guards: code lands before
	migrate creates the doctype. Until then the rail is the installed apps alone.
	"""
	return bool(frappe.db.exists("DocType", APP, cache=True))


def _configured() -> list[dict]:
	if not installed():
		return []

	apps = frappe.get_all(
		APP,
		filters={"enabled": 1},
		fields=["name", "title", "icon", "logo"],
		order_by="rail_order asc, title asc",
	)
	if not apps:
		return []

	names = [app.name for app in apps]
	rows = frappe.get_all(
		APP_SIDEBAR,
		filters={"parent": ["in", names], "parenttype": APP},
		fields=["parent", "sidebar", "label"],
		order_by="parent asc, idx asc",
		parent_doctype=APP,
	)
	roles = frappe.get_all(
		"Has Role",
		filters={"parent": ["in", names], "parenttype": APP},
		fields=["parent", "role"],
		parent_doctype=APP,
	)

	for app in apps:
		app["sidebars"] = [row for row in rows if row.parent == app.name]
		app["roles"] = [row.role for row in roles if row.parent == app.name]
	return apps


def _sidebars() -> list[dict]:
	return frappe.get_all(SIDEBAR, fields=["name", "header_icon", "app", "module", "for_user"])


def _icon_apps() -> dict[str, str]:
	"""A Desktop Icon's app, by label, for the icons that open a sidebar."""
	return dict(
		frappe.get_all(
			"Desktop Icon",
			filters={"link_type": "Workspace Sidebar", "app": ["is", "set"]},
			fields=["label", "app"],
			as_list=True,
		)
	)


def _app_meta() -> dict[str, dict]:
	"""What each installed app is called and its logo, the way the desk's boot works it out."""
	meta = {}
	for app_name in frappe.get_installed_apps():
		screen = (frappe.get_hooks("add_to_apps_screen", app_name=app_name) or [{}])[0]
		title = screen.get("title") or next(iter(frappe.get_hooks("app_title", app_name=app_name)), None)
		logo = screen.get("logo") or next(iter(frappe.get_hooks("app_logo_url", app_name=app_name)), None)
		meta[app_name] = {"title": title or app_name, "logo": logo}
	return meta
