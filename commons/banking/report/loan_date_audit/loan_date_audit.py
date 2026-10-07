"""Where a lending voucher's GL is not on the date the voucher is for. The
check and the repair are in `commons.banking.loan_dates`.

When Commons Settings' "Enable Loan Vouchers on Their Own Dates" is off, the
report says so above its rows: nothing in this app then keeps new vouchers on
their dates.
"""

import frappe
from frappe import _

from commons.banking import loan_dates
from commons.commons_core import apps

WRONG = "Wrong date"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not apps.installed("lending"):
		return [], [], _("Lending is not installed on this site.")
	rows = [frappe._dict(r, status=WRONG, detail=r.found) for r in loan_dates.find_discrepancies(filters)]
	return _columns(), rows, loan_dates.setting_warning(), None, _summary(rows)


def _columns():
	return [
		{"fieldname": "action", "label": _("Action"), "fieldtype": "Data", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Data", "width": 300},
		{"fieldname": "date", "label": _("Voucher Date"), "fieldtype": "Date", "width": 110},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 130,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{"fieldname": "loan", "label": _("Loan"), "fieldtype": "Link", "options": "Loan", "width": 170},
		{"fieldname": "detail", "label": _("Detail"), "fieldtype": "Data", "width": 320},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "amount", "label": _("GL Debit"), "fieldtype": "Float", "precision": 2, "width": 110},
	]


def _summary(rows):
	"""How many vouchers are on the wrong date, green when none."""
	count = len(rows)
	return [
		{
			"value": count or _("None"),
			"label": _("Vouchers on the wrong date"),
			"indicator": "Red" if count else "Green",
			"datatype": "Int" if count else "Data",
		}
	]
