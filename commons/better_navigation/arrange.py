# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The rail's two editors: which apps it lists, and which modules each app offers.

The desk draws both in Frappe's own arrangement editor (`frappe.ui.ArrangementEditor`,
the one behind Manage Dock and Edit Sidebar) -- see `js/arrange.js`. This is what they
read and write. Everything is stored where it already was, on `Navigation App`
records, so the form and the editors are two ways into the same data:

- Manage Rail orders and hides apps (`rail_order` and `hidden`), and adds new ones: a
  Navigation App of its own, with a title and an icon, which then needs modules before
  the rail shows it.
- Manage Modules orders, adds, relabels and takes modules off one app's list, with
  Category and Spacer rows between them: the record's modules table. Taking one of an
  installed app's own modules off its list switches the record to Replace, which is
  what sends a module to Other; with none taken off it stays in Add, so a module the
  app gains later still turns up.

Only the site's arrangement is edited ("For everyone"). There is no per-user layer:
Navigation Apps are site records.

The rail order is the whole rail's, whichever editor wrote. The resolver lists apps
with a record before apps without one, so giving one app a record (the first edit of
ERPNext's modules, say) would otherwise move it to the top. Each save therefore
writes the order the rail had, or the one the editor asked for, onto records -- and
only onto the apps that need one to hold their place: an app still where Frappe's
default would put it, among the apps nobody has configured, is left without a record.
"""

import json

import frappe
from frappe import _

from commons.better_navigation import navigation_apps as nav

APP = nav.APP


def _check():
	"""Both editors write Navigation App records, so both need the right to."""
	frappe.has_permission(APP, "write", throw=True)
	frappe.has_permission(APP, "create", throw=True)


def _rail(module_sidebars: dict | None = None) -> list[dict]:
	"""Every app the rail could list, hidden ones included, in rail order."""
	return nav.navigation_apps(module_sidebars=module_sidebars, everything=True)


def _parse(items) -> list[dict]:
	return json.loads(items) if isinstance(items, str) else list(items or [])


# ------------------------------------------------------------------------------------
# Manage Rail
# ------------------------------------------------------------------------------------


@frappe.whitelist()
def get_rail() -> list[dict]:
	"""The apps, in rail order, as the rail editor lists them."""
	_check()
	return [
		{
			"key": app["key"],
			"title": app["title"],
			"icon": app.get("icon"),
			"logo": app.get("logo"),
			"hidden": bool(app.get("hidden")),
			"roles": app.get("roles") or [],
			"configured": bool(app.get("configured")),
		}
		for app in _rail()
	]


@frappe.whitelist(methods=["POST"])
def save_rail(items) -> dict:
	"""Store the rail's order and which apps are off it. `items` is every app, in order.

	An item marked `new` is an app the editor added: it is made here, as a Navigation App of
	its own, and stands in the order where the editor put it. Their keys come back under
	`created`, so the editor can go on to give them modules.
	"""
	_check()
	items = _parse(items)
	from frappe.boot import get_module_sidebars

	# Built once for the whole save: it is Frappe's, and nothing saved here changes it.
	module_sidebars = get_module_sidebars()
	created = []
	for item in items:
		if not item.get("new"):
			continue
		title = (item.get("title") or "").strip()
		if not title:
			frappe.throw(_("A new app needs a title."))
		if frappe.db.exists(APP, title):
			frappe.throw(_("There is already a Navigation App called {0}.").format(frappe.bold(title)))
		doc = frappe.get_doc(
			{
				"doctype": APP,
				"title": title,
				"icon": item.get("icon") or None,
				"enabled": 1,
				"sidebar_mode": nav.ADD,
			}
		).insert()
		item["key"] = f"navigation-app:{doc.name}"
		created.append(item["key"])

	rail = _rail(module_sidebars)
	known = {app["key"] for app in rail}
	keys = [item["key"] for item in items if item.get("key") in known]
	# An app the editor did not list (installed since it opened) keeps its place at the end.
	keys += [app["key"] for app in rail if app["key"] not in keys]
	hidden = {item["key"] for item in items if item.get("hidden")}
	_store_order(rail, keys, hidden)
	return {**payload(module_sidebars), "created": created}


def _store_order(rail: list[dict], keys: list[str], hidden: set[str]) -> None:
	"""Write `keys` as the rail order, and `hidden` as the apps off it, onto records.

	The apps at the end that nobody configured, still in Frappe's default order and
	not hidden, are left as they are: the resolver already lists them there. Every app
	before them gets a record holding its place, made for it if it has none.
	"""
	by_key = {app["key"]: app for app in rail}
	default = [app["key"] for app in rail if not app.get("configured")]

	# The longest tail of plain apps in the default order.
	tail: list[str] = []
	for key in reversed(keys):
		app = by_key[key]
		if app.get("configured") or key in hidden:
			break
		if tail and default.index(key) > default.index(tail[0]):
			break
		tail.insert(0, key)

	for position, key in enumerate(keys[: len(keys) - len(tail)], start=1):
		doc = _record_for(by_key[key])
		doc.rail_order = position * 10
		doc.hidden = 1 if key in hidden else 0
		doc.save()


def _record_for(app: dict):
	"""The Navigation App behind a rail app, made bound to its installed app if it has none.

	Records are named by their title, and the app's title may already be taken -- by a
	disabled record kept for later, say -- so a new one takes the first free variant
	("ERPNext (erpnext)", then numbered).
	"""
	if app.get("record"):
		return frappe.get_doc(APP, app["record"])
	return frappe.get_doc(
		{
			"doctype": APP,
			"title": _free_title(app["title"], app["installed_app"]),
			"installed_app": app["installed_app"],
			"enabled": 1,
			"sidebar_mode": nav.ADD,
		}
	)


def _free_title(title: str, installed_app: str | None) -> str:
	if not frappe.db.exists(APP, title):
		return title
	base = f"{title} ({installed_app})" if installed_app and installed_app != title else title
	candidate, n = base, 2
	while frappe.db.exists(APP, candidate):
		candidate, n = f"{base} {n}", n + 1
	return candidate


# ------------------------------------------------------------------------------------
# Manage Modules
# ------------------------------------------------------------------------------------


@frappe.whitelist()
def get_app_modules(key: str) -> dict:
	"""One app's module list as its editor shows it.

	`rows` is the list as the rail draws it -- each Category and Spacer a row of its
	own -- and then, taken off, the installed app's own modules it no longer lists.
	A module row names its Module Def, what the rail calls it, the label the
	record gives it (`own_label`), if any, and whether it has more than one
	sidebar on the site (`several_sidebars`), where that label is not used.
	"""
	_check()
	from frappe.boot import get_module_sidebars

	module_sidebars = get_module_sidebars()
	rail = _rail(module_sidebars)
	app = next((a for a in rail if a["key"] == key), None)
	if not app:
		frappe.throw(_("{0} is not on the rail.").format(frappe.bold(key)))

	several = nav.multi_shell_modules()
	own_labels = {}
	if app.get("record"):
		for row in frappe.get_doc(APP, app["record"]).sidebars:
			if nav.row_type(row) == nav.MODULE and row.module and row.label:
				own_labels[row.module] = row.label

	rows, listed = [], set()
	for entry in app["sidebars"]:
		if entry.get("category"):
			rows.append({"kind": "category", "label": entry["category"]})
		elif entry.get("space_before"):
			rows.append({"kind": "spacer"})
		module = (module_sidebars.get(entry["sidebar"]) or {}).get("module") or entry["sidebar"]
		if module in listed:
			continue
		listed.add(module)
		rows.append(
			{
				"kind": "module",
				"module": module,
				"label": entry["label"],
				"own_label": own_labels.get(module),
				"icon": entry.get("icon"),
				"several_sidebars": module in several,
			}
		)

	# An installed app's (or Other's) own modules it does not list: taken off by Replace.
	target = app.get("installed_app")
	if target:
		# Modules another app lists are that app's to give up, not this one's to take back.
		holders = {m["sidebar"] for other in rail if other is not app for m in other["sidebars"]}
		owner = _owner_of(module_sidebars)
		for shell, sidebar in module_sidebars.items():
			module = sidebar.get("module") or shell
			if module in listed or shell in holders or owner(module) != target:
				continue
			listed.add(module)
			rows.append(
				{
					"kind": "module",
					"module": module,
					"label": sidebar.get("label") or shell,
					"icon": sidebar.get("header_icon"),
					"hidden": True,
					"several_sidebars": module in several,
				}
			)

	return {"title": app["title"], "installed_app": target, "rows": rows}


@frappe.whitelist(methods=["POST"])
def save_app_modules(key: str, items) -> dict:
	"""Store one app's module list. `items` is every row, in order, each marked if taken off.

	What the editor was not shown is kept: a row naming a module the person editing cannot
	open (or one whose app is not installed just now) stays where it was, and so does each
	row's Apps Screen Image, which the editor does not carry.

	Taking one of an installed app's own modules off its list switches the record to
	Replace, which sends it to Other. Other has nowhere further to send a module, so its
	list is only ever ordered and labelled: nothing is taken off it. A module that came
	from another app is simply released, back to that app, without changing the mode.
	"""
	_check()
	items = _parse(items)
	from frappe.boot import get_module_sidebars

	module_sidebars = get_module_sidebars()
	rail = _rail(module_sidebars)
	app = next((a for a in rail if a["key"] == key), None)
	if not app:
		frappe.throw(_("{0} is not on the rail.").format(frappe.bold(key)))
	target = app.get("installed_app")

	# The order the rail has now, held before a new record could move this app.
	order = [a["key"] for a in rail]
	hidden_apps = {a["key"] for a in rail if a.get("hidden")}

	visible = {sidebar.get("module") or shell for shell, sidebar in module_sidebars.items()}
	owner = _owner_of(module_sidebars)
	old_rows = frappe.get_doc(APP, app["record"]).sidebars if app.get("record") else []
	images = {row.module: row.desktop_image for row in old_rows if row.module and row.get("desktop_image")}

	rows, taken_off = [], False
	for item in items:
		kind = item.get("kind")
		hidden = item.get("hidden") and target != nav.OTHER
		if hidden:
			if kind == "module" and target and owner(item.get("module")) == target:
				taken_off = True
			continue
		if kind == "module" and item.get("module"):
			rows.append(
				{
					"type": nav.MODULE,
					"module": item["module"],
					"label": item.get("own_label") or None,
					"desktop_image": images.get(item["module"]),
				}
			)
		elif kind == "category" and (item.get("label") or "").strip():
			rows.append({"type": nav.CATEGORY, "label": item["label"].strip()})
		elif kind == "spacer":
			rows.append({"type": nav.SPACER})

	rows = _keep_unseen(rows, old_rows, visible)

	doc = _record_for(app)
	if target:
		doc.sidebar_mode = nav.REPLACE if taken_off else nav.ADD
	doc.set("sidebars", rows)
	doc.save()

	_store_order(_rail(module_sidebars), order, hidden_apps)
	return payload(module_sidebars)


def _owner_of(module_sidebars: dict):
	"""A function from a module to the installed app it belongs to by default, or Other."""
	module_apps = nav.module_apps()
	installed = set(frappe.get_installed_apps())
	hosts = nav.app_hosts()
	app_by_module = {}
	for shell, sidebar in module_sidebars.items():
		module = sidebar.get("module") or shell
		app_by_module.setdefault(module, sidebar.get("app"))

	def owner(module: str | None) -> str | None:
		if not module:
			return None
		return nav.default_app_of(app_by_module.get(module), module, module_apps, hosts, installed)

	return owner


def _keep_unseen(rows: list[dict], old_rows: list, visible: set[str]) -> list[dict]:
	"""Put back each old row for a module the editor did not show, after the row it followed."""
	result = list(rows)
	previous = None
	for row in old_rows:
		if row.module and row.module not in visible:
			kept = {
				"type": nav.MODULE,
				"module": row.module,
				"label": row.label or None,
				"desktop_image": row.get("desktop_image"),
			}
			at = next(
				(i + 1 for i, r in enumerate(result) if previous and r.get("module") == previous),
				0 if previous is None else len(result),
			)
			result.insert(at, kept)
		if row.module:
			previous = row.module
	return result


# ------------------------------------------------------------------------------------
# What the desk redraws from
# ------------------------------------------------------------------------------------


def payload(module_sidebars: dict | None = None) -> dict:
	"""The rail and the Apps screen, as the boot would carry them now.

	So an editor's save is redrawn in place: `navigation_apps`, and `app_data` as the
	Apps screen arranges it. The browser places each module in its rail app from the
	rail itself (`js/boot_arrangement.js`).
	"""
	from frappe.boot import get_app_data, get_module_sidebars

	from commons.better_navigation import apps_screen
	from commons.commons_core import settings

	if module_sidebars is None:
		module_sidebars = get_module_sidebars()
	app_data = get_app_data()
	# Read before the Apps screen rewrites `app_data`, as in the boot.
	rail = nav.navigation_apps(module_sidebars=module_sidebars, app_data=app_data)
	# The Apps screen as the boot would arrange it, or the desk's copy would be Frappe's.
	if settings.feature_enabled(settings.ENABLE_DESKTOP_FROM_NAVIGATION_APPS):
		apps_screen.arrange(app_data, rail)
	return {"navigation_apps": rail, "app_data": app_data}
