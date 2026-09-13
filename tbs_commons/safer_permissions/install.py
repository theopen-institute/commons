# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Registering the gate checkbox with core, once per gateable doctype."""

import frappe

from tbs_commons.safer_permissions.permissions import GATE, SETTINGS


def sync_permission_gates() -> None:
	"""Register the gate checkbox for every doctype listed in the settings.

	A `Permission Type` record is what puts a `Require User Permission` box on
	each of a doctype's rows in the Role Permission Manager: core creates the
	Custom Field on `DocPerm`, `Custom DocPerm` and `DocShare` and draws it.
	Writing one is restricted to install, migrate or developer mode, which is
	why this runs here rather than when an administrator saves the settings.

	The box an administrator ticks lands on `Custom DocPerm`, not `DocPerm`, so
	it survives the app that owns the doctype shipping new permissions.

	Records are created and never removed. Deleting one drops the Custom Field
	and with it the column, so every role that had the box ticked is silently
	ungated -- the exact failure this app exists to prevent. Retiring a gate is
	deliberate work: untick the roles first, then delete the `Permission Type`
	by hand.
	"""
	from frappe.core.doctype.permission_type.permission_type import get_doctype_ptype_map

	if not frappe.db.exists("DocType", SETTINGS):
		return

	wanted = {rule.document_type for rule in frappe.get_single(SETTINGS).rules if rule.document_type}
	existing = set(
		frappe.get_all("Permission Type", filters={"perm_type": GATE}, pluck="doc_type", limit=0)
	)

	created = False
	for doctype in sorted(wanted - existing):
		# A rule may name a doctype from an app that has since been removed.
		if not frappe.db.exists("DocType", doctype):
			continue

		frappe.get_doc({"doctype": "Permission Type", "perm_type": GATE, "doc_type": doctype}).insert(
			ignore_permissions=True
		)
		created = True

	if created:
		get_doctype_ptype_map.clear_cache()
		frappe.db.commit()
