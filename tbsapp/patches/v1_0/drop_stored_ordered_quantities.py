# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Drop the columns that used to cache how much of a request had been ordered.

`Procurement Request Item.ordered_qty` and `Procurement Request.per_ordered` are
virtual now -- counted from the submitted Material Requests on every read. The
columns behind them hold whatever the old hook last wrote, which nothing reads
and nothing keeps true, so they go. Nothing is lost: every value they held is
recomputed from the Material Requests themselves.
"""

import frappe

COLUMNS = (
	("Procurement Request Item", "ordered_qty"),
	("Procurement Request", "per_ordered"),
)


def execute() -> None:
	for doctype, column in COLUMNS:
		table = f"tab{doctype}"
		if not frappe.db.table_exists(doctype):
			continue

		if column in frappe.db.get_table_columns(doctype):
			frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")
