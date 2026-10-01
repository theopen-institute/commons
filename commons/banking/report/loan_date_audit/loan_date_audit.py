"""Where a lending voucher's GL is not on the date the voucher is for, and
whether what keeps it there is in place. The checks and the repair are in
`commons.banking.loan_dates`.

Both checks run by default and their problems share one list: vouchers on the
wrong date, and safeguards that are missing. A clean report
means both are clean. Choosing Safeguards lists every safeguard, the ones in
place too, as the record of what was checked.
"""

import frappe
from frappe import _

from commons.banking import loan_dates
from commons.commons_core import apps

ALL = "All"
DATES = "GL dates"
SAFEGUARDS = "Safeguards"
CHECKS = (DATES, SAFEGUARDS)

WRONG = "Wrong date"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not apps.installed("lending"):
		return [], [], _("Lending is not installed on this site.")
	chosen = filters.get("view")
	checks = [chosen] if chosen in CHECKS else list(CHECKS)
	rows = []
	if DATES in checks:
		rows += [
			frappe._dict(r, check=DATES, status=WRONG, detail=r.found)
			for r in loan_dates.find_discrepancies(filters)
		]
	if SAFEGUARDS in checks:
		rows += [
			frappe._dict(check=SAFEGUARDS, status=s.status, issue=s.check, detail=s.detail)
			for s in loan_dates.safeguards()
			# Only problems in the combined list; all of them when asked for.
			if chosen == SAFEGUARDS or s.status != loan_dates.OK
		]
	return _columns(), rows, None, None, _summary(checks, rows)


def _columns():
	return [
		{"fieldname": "action", "label": _("Action"), "fieldtype": "Data", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "check", "label": _("Check"), "fieldtype": "Data", "width": 100},
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


def _figure(value, label, indicator):
	return {
		"value": value or _("None"),
		"label": label,
		"indicator": indicator if value else "Green",
		"datatype": "Int" if value else "Data",
	}


def _summary(checks, rows):
	"""One figure per check, green when it found nothing wrong."""
	summary = []
	if DATES in checks:
		summary.append(_figure(sum(r.check == DATES for r in rows), _("Vouchers on the wrong date"), "Red"))
	if SAFEGUARDS in checks:
		summary.append(
			_figure(sum(r.status == loan_dates.MISSING for r in rows), _("Safeguards missing"), "Red")
		)
	return summary
