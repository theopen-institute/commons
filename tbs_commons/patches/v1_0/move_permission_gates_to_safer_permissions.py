# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Repoint the gate doctypes at `Safer Permissions` before the sync sees them.

Moving a doctype between modules moves its files, and migrate reads the module
from the file it finds while `remove_orphan_doctypes` reads it from the
database. A site that installed these two under `TBS Commons` therefore has
them deleted -- table and all -- on the first migrate after the move, and
recreated empty on the second. Rewriting the column first makes the two agree,
so the move costs nothing.

Runs pre_model_sync, which is the only point early enough to matter.
"""

import frappe

DOCTYPES = ("Permission Gate Settings", "Permission Gate Rule")
MODULE = "Safer Permissions"


def execute() -> None:
	for doctype in DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.get_value("DocType", doctype, "module") == MODULE:
			continue

		# The module's own `Module Def` is created by `before_migrate`, which
		# has already run by the time patches do.
		frappe.db.set_value("DocType", doctype, "module", MODULE, update_modified=False)
