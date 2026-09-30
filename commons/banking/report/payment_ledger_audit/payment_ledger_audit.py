"""Where the payment ledger (and so Accounts Receivable/Payable) disagrees with
the general ledger, where an invoice's outstanding amount disagrees with the
payment ledger, and where Payment Reconciliation offers a journal entry line as
a payment although its own entry already netted it. The checks and the fixes
are in `commons.banking.ledger_audit` and `commons.banking.netted_payments`.

Every check runs by default and their problems share one list, so a clean
report means all three are clean. Each row says which check found it, in the
same columns: what the amount should be, what it is, and the difference.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money

from commons.banking import ledger_audit, netted_payments

ALL = "All"
LEDGER = "Payment ledger vs GL"
OUTSTANDING = "Invoice outstanding vs payment ledger"
NETTED = "Reconciliation: refunds counted twice"
# In the order to fix them: an outstanding amount is only right once the
# payment ledger under it is.
CHECKS = (LEDGER, OUTSTANDING, NETTED)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	chosen = filters.get("view")
	checks = [chosen] if chosen in CHECKS else list(CHECKS)
	rows = []
	for check in checks:
		rows += FINDERS[check](filters)
	return _columns(), rows, None, None, _summary(checks, rows)


def _ledger_rows(filters):
	return [
		frappe._dict(
			r,
			check=LEDGER,
			detail=r.voucher_status,
			expected=r.gl_amount,
			found=r.ple_amount,
		)
		for r in ledger_audit.find_discrepancies(filters)
	]


def _outstanding_rows(filters):
	return [
		frappe._dict(
			r,
			check=OUTSTANDING,
			issue=_("Outstanding on invoice differs"),
			expected=r.ledger,
			found=r.recorded,
		)
		for r in ledger_audit.find_outstanding_discrepancies(filters)
	]


def _netted_rows(filters):
	return [
		frappe._dict(
			r,
			check=NETTED,
			detail=_("Lines {0}; the entry charges {1}").format(r["rows"], fmt_money(r["charged"])),
			expected=0,
			found=r["offered"],
			difference=flt(r["offered"], 2),
		)
		for r in netted_payments.for_display(netted_payments.find_netted_payments(filters))
	]


FINDERS = {LEDGER: _ledger_rows, OUTSTANDING: _outstanding_rows, NETTED: _netted_rows}


def _columns():
	return [
		{"fieldname": "action", "label": _("Action"), "fieldtype": "Data", "width": 90},
		{"fieldname": "check", "label": _("Check"), "fieldtype": "Data", "width": 190},
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
		{"fieldname": "detail", "label": _("Detail"), "fieldtype": "Data", "width": 160},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 220,
		},
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 160,
		},
		{
			"fieldname": "expected",
			"label": _("Should Be"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{"fieldname": "found", "label": _("Is"), "fieldtype": "Float", "precision": 2, "width": 110},
		{
			"fieldname": "difference",
			"label": _("Difference"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
	]


def _summary(checks, rows):
	"""One figure per check run, green when it found nothing."""
	summary = []
	for check in checks:
		n = sum(r.check == check for r in rows)
		summary.append(
			{
				"value": n or _("None"),
				"label": check,
				"indicator": "Red" if n else "Green",
				"datatype": "Int" if n else "Data",
			}
		)
	return summary
