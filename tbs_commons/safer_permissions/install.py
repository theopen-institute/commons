# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The gate checkbox: one column on the tables core keeps permissions in."""

import frappe

from tbs_commons.safer_permissions.permissions import GATE

# Where core stores permission flags. `DocShare` is included because core's own
# permission types are: a share must not hand out what a gate withholds.
GATE_FIELD_TARGETS = ("Custom DocPerm", "DocPerm", "DocShare")


def sync_gate_field() -> None:
	"""Create the gate column on install and migrate. Safe to run repeatedly.

	Deliberately not a `Permission Type`. That core extension point registers one
	record per doctype, can only be written during install, migrate or developer
	mode, and draws its checkbox among the rights. The gate applies to every
	doctype and belongs beside "Only if Creator", so a plain column plus
	`public/js/permission_manager_gate.js` is both simpler and closer to the truth.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	_bust_permission_manager_cache()

	for target in GATE_FIELD_TARGETS:
		if existing := frappe.db.exists("Custom Field", {"dt": target, "fieldname": GATE}):
			# An earlier version scoped this field to the doctypes a settings
			# document listed. It applies everywhere now, so drop the leftover
			# condition rather than leave the checkbox hidden.
			frappe.db.set_value("Custom Field", existing, "depends_on", "")
			continue

		create_custom_field(
			target,
			{
				"fieldname": GATE,
				"label": frappe.unscrub(GATE),
				"fieldtype": "Check",
				"insert_after": "append",
			},
		)


def _bust_permission_manager_cache() -> None:
	"""Make every desk drop its cached copy of the Role Permission Manager.

	`page_js` is appended to that page's script, and the desk caches the whole
	script in `localStorage` under `_page:permission-manager` with no version
	check at all -- `pageview.js` uses the key if it merely exists. The one thing
	that does invalidate it is `sync_pages()` at desk boot, which deletes the key
	when the Page's `modified` differs from the copy it cached alongside it.

	So touching the record is how a change to the gate checkbox actually reaches
	anyone who has opened this page before. Done on every migrate rather than only
	when something changed: the cost is one re-fetch of a 20KB script per user,
	and the alternative is an admin UI that is silently a version behind.
	"""
	if not frappe.db.exists("Page", "permission-manager"):
		return
	frappe.db.set_value(
		"Page", "permission-manager", "modified", frappe.utils.now(), update_modified=False
	)
