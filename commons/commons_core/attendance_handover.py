"""Carry the attendance register's settings into Commons Settings.

TEMPORARY. Delete this file, and its entry in `before_migrate`, once every site
carrying this app -- register.theopen.institute and the local ones -- has
migrated past the release that dropped `Attendance Register Settings`. Nothing
else calls it.

The register's settings were a Single of their own, `Attendance Register
Settings`, and are now the Attendance tab of `Commons Settings`, each field
under its old name with `attendance_` in front (see
`commons.attendance_register.register`). With the doctype's files gone,
migrate's `remove_orphan_doctypes` deletes it, but not its values, which would
be left in `tabSingles` with nothing to read them. This copies them across first.

Only onto a site whose Commons Settings holds no `attendance_` value yet, so a
second migrate, or a site where somebody has already filled the new tab, is left
as it is. The old rows are deleted either way.

Why `before_migrate`: after the files are gone and before anything in the
migrate acts on their absence. Both are Singles, so their values are rows in
`tabSingles` and can be written before the doctype sync has added the fields
that will read them.
"""

import frappe

OLD = "Attendance Register Settings"
NEW = "Commons Settings"
PREFIX = "attendance_"


def run() -> None:
	old = frappe.db.sql("select field, value from tabSingles where doctype = %s", OLD, as_dict=True)
	old = [row for row in old if row.field not in ("name", "modified", "modified_by", "owner", "creation")]
	if not old:
		return
	if not frappe.db.sql(
		"select 1 from tabSingles where doctype = %s and field like %s limit 1", (NEW, PREFIX + "%")
	):
		print(f"Attendance handover: {len(old)} setting(s) moved to {NEW}")
		for row in old:
			frappe.db.sql(
				"insert into tabSingles (doctype, field, value) values (%s, %s, %s)",
				(NEW, PREFIX + row.field, row.value),
			)
	# Deleting the orphaned doctype leaves its Single's rows behind.
	frappe.db.sql("delete from tabSingles where doctype = %s", OLD)
	frappe.db.commit()
	frappe.clear_document_cache(NEW, NEW)
