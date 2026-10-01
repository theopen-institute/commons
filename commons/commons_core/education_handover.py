"""Hand the `Education Extensions` module to the site that fills it, and take its workspaces off the rest.

TEMPORARY. Delete this file, and its entry in `before_migrate`, once every site
carrying this app -- register.theopen.institute, kulaculture.org, tbs, and the
local ones -- has migrated past the release that dropped `Education Extensions`
from `modules.txt`. Nothing else calls it.

The module never held any of this app's code. It is where the Open Institute's
register keeps twenty Custom DocTypes and the reports, print formats, web form,
scripts and fields around them, and this app claimed it only so that retiring
NepalERP would not delete them. It shipped the module's three workspaces as
files, so every site got them, tbs included, which has no Education at all.

Claimed by this app, the module is also this app's to delete: uninstalling it
would take the twenty doctypes and their rows with it. A custom `Module Def`
(`custom = 1`, no `app_name`) is the site's own and nobody's to uninstall.

What happens, per site
----------------------
* **Something of the site's lives in the module** (register): the `Module Def`
  becomes custom. The three workspaces stay, as site records -- with their
  `module` and `app` cleared, because the desk's workspace list asks the app of
  any workspace whose `app` is empty, and a custom module has none to give
  (`frappe.desk.desktop`, `get_module_app` raises), while one that names an app
  is deleted by migrate's `remove_orphan_entities` once its file is gone. Who
  may open them is their own roles, which stay. Their sidebars get
  `app = "commons"`, which is where the navigation rail has always put them: it
  groups a sidebar with no app by its module's app, and that was this one.
* **Nothing of the site's does** (tbs): the three workspaces are deleted, if
  they are still exactly as shipped. `remove_orphan_entities` would not do it --
  it only looks at workspaces that name an app, and these name none. The
  `Module Def`, then unused, is removed by `drop_stale_module_defs` after the
  migrate. A workspace a site has edited is kept, as on register.

And on every site, whatever became of the module:

* **The register's fields are named in Attendance Register Settings** where the site has
  them (register). This app used to ship `custom_late`, `custom_session_type`,
  `custom_session_details` and `custom_inactive` as fixtures, and the register
  read them by those names. The fixture file is gone and the register reads
  whichever fields the settings name; the four Custom Fields stay on the site,
  since removing a fixture deletes nothing. Naming them here, with a late
  arrival worth half a session as it always was there, is what keeps that
  register as it was with nobody opening the form. Only on a site whose four
  settings are all blank, so one that has turned a feature off since is not
  turned back on; a site with none of the fields is left blank, and its
  register goes without.

Why `before_migrate`: the same reason as `community_handover` -- after the
files are gone and before anything in the migrate acts on their absence. The
settings step does not need it, but it does not mind it: Commons Settings is a
Single, so its values are rows in `tabSingles` and can be written before the
doctype sync has added the fields that will read them.
"""

import frappe

MODULE = "Education Extensions"
APP = "commons"

# The three workspaces as this app shipped them, by the `modified` in each file.
# A workspace still at its shipped `modified` is one no site has touched.
SHIPPED = {
	"Admissions": "2023-01-20 12:59:04.062176",
	"Assesssments": "2022-12-06 09:42:05.683580",
	"Course Grades": "2022-11-28 06:35:30.812136",
}


SETTINGS = "Attendance Register Settings"

# Where an earlier copy of this step wrote the same settings, before the
# register had a settings page of its own; moved from there when present.
OLD_SETTINGS = "Commons Settings"
OLD_PREFIX = "attendance_"

# The register's fields as one school's register named them, and the
# settings field that names each now.
REGISTER_FIELDS = {
	"late_field": ("Student Attendance", "custom_late"),
	"session_type_field": ("Course Schedule", "custom_session_type"),
	"session_details_field": ("Course Schedule", "custom_session_details"),
	"inactive_term_field": ("Academic Term", "custom_inactive"),
}

# What a late arrival earned under the register's own rule, before it was a setting.
LATE_CREDIT = ("late_credit", 0.5)


def run() -> None:
	hand_over_module()
	name_register_fields()


def hand_over_module() -> None:
	module = frappe.db.get_value("Module Def", MODULE, ("custom", "app_name"), as_dict=True)
	if not module or module.custom or module.app_name != APP:
		return

	workspaces = frappe.get_all(
		"Workspace", filters={"module": MODULE}, fields=["name", "modified"], order_by="name"
	)
	if not users(exclude_workspaces=[w.name for w in workspaces]):
		for workspace in workspaces:
			if workspace.name in SHIPPED and str(workspace.modified) == SHIPPED[workspace.name]:
				delete_workspace(workspace.name)
				print(
					f"Education handover: removed the {workspace.name} workspace, which this site never used."
				)
		if not users():
			return

	frappe.db.set_value("Module Def", MODULE, {"custom": 1, "app_name": None}, update_modified=False)
	for name in frappe.get_all("Workspace", filters={"module": MODULE}, pluck="name"):
		frappe.db.set_value("Workspace", name, {"module": None, "app": None}, update_modified=False)
	for name in frappe.get_all(
		"Workspace Sidebar", filters={"module": MODULE, "app": ("is", "not set")}, pluck="name"
	):
		frappe.db.set_value("Workspace Sidebar", name, "app", APP, update_modified=False)

	frappe.cache.delete_key("bootinfo")
	from commons.better_navigation.navigation_apps import clear_cache

	clear_cache()
	print(f"Education handover: {MODULE} is this site's own module now.")


def users(exclude_workspaces: list[str] | None = None) -> int:
	"""How many records name the module, through any Link to Module Def."""
	link = {"fieldtype": "Link", "options": "Module Def"}
	links = [
		(row.parent, row.fieldname)
		for row in frappe.get_all("DocField", filters=link, fields=["parent", "fieldname"])
	] + [
		(row.dt, row.fieldname)
		for row in frappe.get_all("Custom Field", filters=link, fields=["dt", "fieldname"])
	]
	count = 0
	for doctype, fieldname in links:
		try:
			meta = frappe.get_meta(doctype)
		except frappe.DoesNotExistError:
			continue
		if meta.issingle or meta.is_virtual or not frappe.db.table_exists(doctype):
			continue
		filters = {fieldname: MODULE}
		if doctype == "Workspace" and exclude_workspaces:
			filters["name"] = ("not in", exclude_workspaces)
		count += frappe.db.count(doctype, filters)
	return count


def delete_workspace(name: str) -> None:
	"""The row and its child rows, without `Workspace.after_delete`.

	In developer mode that deletes the workspace's folder under its module's
	path, and the module is no longer any app's to have one.
	"""
	for table in frappe.get_meta("Workspace").get_table_fields():
		frappe.db.delete(table.options, {"parent": name, "parenttype": "Workspace"})
	frappe.db.delete("Workspace", name)
	frappe.cache.delete_key("bootinfo")


def name_register_fields() -> None:
	"""Name the register's old fields in its settings, where the site has them and has named none.

	Read from `tabSingles` raw rather than through the document: before this
	migrate's doctype sync the settings doctype does not exist yet, and the
	document would not be there to read. Written with `set_single_value` for
	the same reason, which writes the rows and asks the doctype nothing.
	"""
	settings = [*REGISTER_FIELDS, LATE_CREDIT[0]]
	old = frappe.db.get_singles_dict(OLD_SETTINGS)
	moved = {
		setting: old.get(OLD_PREFIX + setting)
		for setting in settings
		if old.get(OLD_PREFIX + setting) not in (None, "")
	}
	if any(OLD_PREFIX + setting in old for setting in settings):
		frappe.db.delete(
			"Singles", {"doctype": OLD_SETTINGS, "field": ("in", [OLD_PREFIX + s for s in settings])}
		)

	stored = frappe.db.get_singles_dict(SETTINGS)
	if any((stored.get(setting) or "").strip() for setting in REGISTER_FIELDS):
		return

	values = moved or {
		setting: fieldname
		for setting, (doctype, fieldname) in REGISTER_FIELDS.items()
		if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
	}
	if not values:
		return
	if "late_field" in values and LATE_CREDIT[0] not in values:
		values[LATE_CREDIT[0]] = LATE_CREDIT[1]

	frappe.db.set_single_value(SETTINGS, values, update_modified=False)
	named = ", ".join(str(fieldname) for setting, fieldname in values.items() if setting in REGISTER_FIELDS)
	print(f"Education handover: Attendance Register Settings names the register's fields, {named}.")
