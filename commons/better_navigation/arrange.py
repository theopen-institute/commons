# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The rail's two editors: which apps it lists, and which modules each app offers.

The desk draws both in Frappe's own arrangement editor (`frappe.ui.ArrangementEditor`,
the one behind Manage Dock and Edit Sidebar) -- see `js/arrange.js`. This is what they
read and write. Everything is stored where it already was, on `Navigation App`
records, so the form and the editors are two ways into the same data:

- Manage Rail orders and hides apps (`rail_after` and `hidden`), and adds new ones: a
  Navigation App of its own, with a title and an icon, which then needs modules before
  the rail shows it.
- Manage Modules orders, adds and takes modules off one app's list, with
  Category and Spacer rows between them: the record's modules table. Taking one of an
  installed app's own modules off its list switches the record to Replace, which is
  what sends a module to Other; with none taken off it stays in Add, so a module the
  app gains later still turns up.

Only the site's arrangement is edited ("For everyone"). There is no per-user layer:
Navigation Apps are site records.

The rail order is the whole rail's, whichever editor wrote. Every app sits at its
default place unless its record anchors it after another (see `navigation_apps`), so
a save writes an anchor only onto the apps that left the default order, and a record
is made only for an app that needs one to hold a position or to be hidden. A record
an editor made that no longer holds anything (`_is_placeholder`) is deleted again.
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
				"module_mode": nav.ADD,
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

	As few apps as possible are anchored; see `anchors_for`.
	"""
	from frappe.boot import get_app_data

	by_key = {app["key"]: app for app in rail}
	defaults = [f"app:{name}" for name in [*frappe.get_installed_apps(), nav.OTHER]]
	anchors = anchors_for(keys, defaults, {key for key in keys if by_key[key].get("record")})
	meta = nav.apps_from_app_data(get_app_data())[0]

	for key in keys:
		app = by_key[key]
		anchor = anchors[key]
		is_hidden = 1 if key in hidden else 0
		if not app.get("record") and not anchor and not is_hidden:
			continue
		doc = _record_for(app)
		changed = doc.is_new() or (doc.rail_after or None) != anchor or int(doc.hidden or 0) != is_hidden
		doc.rail_after = anchor
		doc.hidden = is_hidden
		target = doc.installed_app
		if _is_placeholder(doc, nav.OTHER if target == nav.OTHER else (meta.get(target) or {}).get("title")):
			if not doc.is_new():
				frappe.delete_doc(APP, doc.name)
		elif changed:
			doc.save()


def anchors_for(keys: list[str], defaults: list[str], with_record: set[str]) -> dict[str, str | None]:
	"""What each app in `keys` follows on the rail so that it reads `keys`: None for its default place.

	The longest run of apps still in their default order stays unanchored
	(`_unmoved`), and each of the rest follows the app before it in `keys`, or the
	top. `navigation_apps.rail_sequence` turns this back into `keys`.
	"""
	stay = _unmoved(keys, defaults, with_record)
	return {
		key: None if key in stay else (keys[index - 1] if index else nav.TOP)
		for index, key in enumerate(keys)
	}


def _unmoved(keys: list[str], defaults: list[str], with_record: set[str]) -> set[str]:
	"""The apps of `keys` that can stay unanchored: a run in default order, chosen to anchor as few as it can.

	The heaviest increasing subsequence by default position. An app without a record
	weighs far more than one with, since anchoring it means making a record for it.
	"""
	rank = {key: i for i, key in enumerate(defaults)}
	candidates = [key for key in keys if key in rank]
	weight = [1 if key in with_record else 1000 for key in candidates]
	best = list(weight)
	previous: list[int | None] = [None] * len(candidates)
	for i, key in enumerate(candidates):
		for j in range(i):
			if rank[candidates[j]] < rank[key] and best[j] + weight[i] > best[i]:
				best[i], previous[i] = best[j] + weight[i], j
	stay: set[str] = set()
	at = max(range(len(candidates)), key=best.__getitem__, default=None)
	while at is not None:
		stay.add(candidates[at])
		at = previous[at]
	return stay


def _is_placeholder(doc, default_title: str | None) -> bool:
	"""Whether a record stands for an installed app and says nothing about it but that.

	What `_record_for` makes for an app that only needed a position: bound, enabled,
	under the app's own title, in Add mode, with no position, modules, roles, mark or
	frontend of its own, and not hidden.
	"""
	return bool(
		doc.installed_app
		and doc.enabled
		and not doc.hidden
		and not doc.rail_after
		and (doc.module_mode or nav.ADD) == nav.ADD
		and not doc.modules
		and not doc.roles
		and not (doc.icon or doc.logo or doc.frontend_url or doc.frontend_label)
		and (doc.apps_screen or "One Icon") == "One Icon"
		and doc.title == (default_title or doc.installed_app)
	)


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
			"module_mode": nav.ADD,
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
	A module row names its Module Def and what the rail calls it, which is its
	sidebar's label: the editor renames Categories, not modules.
	"""
	_check()
	from frappe.boot import get_module_sidebars

	module_sidebars = get_module_sidebars()
	rail = _rail(module_sidebars)
	app = next((a for a in rail if a["key"] == key), None)
	if not app:
		frappe.throw(_("{0} is not on the rail.").format(frappe.bold(key)))

	rows, listed = [], set()
	for entry in app["modules"]:
		if entry.get("category"):
			rows.append({"kind": "category", "label": entry["category"]})
		elif entry.get("space_before"):
			rows.append({"kind": "spacer"})
		module = (module_sidebars.get(entry["shell"]) or {}).get("module") or entry["shell"]
		if module in listed:
			continue
		listed.add(module)
		rows.append(
			{
				"kind": "module",
				"module": module,
				"label": entry["label"],
				"icon": entry.get("icon"),
			}
		)

	# An installed app's (or Other's) own modules it does not list: taken off by Replace, or
	# hidden by the app's Dock.
	target = app.get("installed_app")
	if target:
		# Modules another app lists are that app's to give up, not this one's to take back.
		holders = {m["shell"] for other in rail if other is not app for m in other["modules"]}
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
	Replace, which sends it to Other -- unless its Dock hides it, which already keeps
	it off the rail. Putting such a module back lists it. Other has nowhere further to send a module, so its
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
	old_rows = frappe.get_doc(APP, app["record"]).modules if app.get("record") else []
	dock_hidden = set((nav.shipped_docks().get(target) or {}).get("hidden") or ())
	dock_hidden = {
		sidebar.get("module") or shell for shell, sidebar in module_sidebars.items() if shell in dock_hidden
	}
	images = {row.module: row.desktop_image for row in old_rows if row.module and row.get("desktop_image")}

	rows, taken_off = [], False
	for item in items:
		kind = item.get("kind")
		hidden = item.get("hidden") and target != nav.OTHER
		if hidden:
			module = item.get("module")
			if kind == "module" and target and owner(module) == target and module not in dock_hidden:
				taken_off = True
			continue
		if kind == "module" and item.get("module"):
			rows.append(
				{
					"type": nav.MODULE,
					"module": item["module"],
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
		doc.module_mode = nav.REPLACE if taken_off else nav.ADD
	doc.set("modules", rows)
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
