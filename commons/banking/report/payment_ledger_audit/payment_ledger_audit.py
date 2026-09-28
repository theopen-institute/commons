"""Where the payment ledger (and so Accounts Receivable/Payable) disagrees with
the general ledger, where an invoice's outstanding amount disagrees with the
payment ledger, and where Payment Reconciliation offers a journal entry line as
a payment although its own entry already netted it. The checks and the fixes
are in `commons.banking.ledger_audit` and `commons.banking.netted_payments`.
"""

from collections import Counter

import frappe
from frappe import _

from commons.banking import ledger_audit, netted_payments

LEDGER = "Payment ledger vs GL"
OUTSTANDING = "Invoice outstanding vs payment ledger"
NETTED = "Reconciliation: refunds counted twice"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.get("view") == OUTSTANDING:
		rows = ledger_audit.find_outstanding_discrepancies(filters)
		return _outstanding_columns(), rows, None, None, _outstanding_summary(rows)
	if filters.get("view") == NETTED:
		rows = netted_payments.for_display(netted_payments.find_netted_payments(filters))
		return _netted_columns(), rows, None, None, _netted_summary(rows)
	rows = ledger_audit.find_discrepancies(filters)
	return _ledger_columns(), rows, None, None, _ledger_summary(rows)


def _action_column():
	return {"fieldname": "action", "label": _("Action"), "fieldtype": "Data", "width": 90}


def _ledger_columns():
	return [
		_action_column(),
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Data", "width": 260},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 120,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 170,
		},
		{"fieldname": "voucher_status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 240,
		},
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 160,
		},
		{"fieldname": "gl_amount", "label": _("GL"), "fieldtype": "Float", "precision": 2, "width": 110},
		{
			"fieldname": "ple_amount",
			"label": _("Payment Ledger"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{
			"fieldname": "difference",
			"label": _("Difference"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
	]


def _outstanding_columns():
	return [
		_action_column(),
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 130,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Invoice"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 180,
		},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 200,
		},
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 180,
		},
		{
			"fieldname": "recorded",
			"label": _("Outstanding on Invoice"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 160,
		},
		{
			"fieldname": "ledger",
			"label": _("Per Payment Ledger"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 150,
		},
		{
			"fieldname": "difference",
			"label": _("Difference"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
	]


def _netted_columns():
	return [
		_action_column(),
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Data", "width": 260},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "voucher_no",
			"label": _("Journal Entry"),
			"fieldtype": "Link",
			"options": "Journal Entry",
			"width": 170,
		},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 240,
		},
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 160,
		},
		{"fieldname": "rows", "label": _("Lines"), "fieldtype": "Data", "width": 70},
		{
			"fieldname": "charged",
			"label": _("Charged in Entry"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
		{
			"fieldname": "offered",
			"label": _("Offered as Payment"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
	]


def _netted_summary(rows):
	if not rows:
		return [{"value": _("None"), "label": _("Refund lines"), "indicator": "Green", "datatype": "Data"}]
	return [
		{"value": len(rows), "label": _("Refund lines"), "indicator": "Orange", "datatype": "Int"},
		{
			"value": len({r["voucher_no"] for r in rows}),
			"label": _("Journal Entries"),
			"indicator": "Orange",
			"datatype": "Int",
		},
		{
			"value": sum(r["offered"] for r in rows),
			"label": _("Offered twice"),
			"indicator": "Orange",
			"datatype": "Float",
		},
	]


def _ledger_summary(rows):
	if not rows:
		return [{"value": _("None"), "label": _("Discrepancies"), "indicator": "Green", "datatype": "Data"}]
	counts = Counter(r.issue for r in rows)
	summary = [
		{"value": len(rows), "label": _("Discrepancies"), "indicator": "Red", "datatype": "Int"},
		{
			"value": len({(r.voucher_type, r.voucher_no) for r in rows}),
			"label": _("Vouchers"),
			"indicator": "Red",
			"datatype": "Int",
		},
	]
	summary += [
		{"value": n, "label": issue, "indicator": "Orange", "datatype": "Int"}
		for issue, n in counts.most_common()
	]
	return summary


def _outstanding_summary(rows):
	return [
		{
			"value": len(rows) if rows else _("None"),
			"label": _("Invoices"),
			"indicator": "Red" if rows else "Green",
			"datatype": "Int" if rows else "Data",
		}
	]
