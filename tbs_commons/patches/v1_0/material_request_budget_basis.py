"""Retain old ledger history; require review before activating the new MR basis."""

import frappe


def execute():
	for budget in frappe.get_all("Department Budget", pluck="name"):
		frappe.db.set_value("Department Budget", budget, "ready", 0)
		frappe.get_doc("Department Budget", budget).add_comment(
			"Info",
			"Budget basis changed to submitted Purchase/Material Issue requests. "
			"Previous procurement/order/invoice entries are retained as history and excluded from totals. "
			"Finance must reconcile submitted Material Requests before reactivating the budget.",
		)
