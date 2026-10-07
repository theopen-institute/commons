"""Is every lending voucher's GL on the date the voucher is for, is what keeps
it there in place, and the repair when it is not.

Lending dates its documents and their GL on the day they are saved, whatever
date was entered. Loan Repayment's `validate` sets `posting_date` to now, and
its GL is dated from `posting_date`. Loan Write Off does the same, and Loan
Disbursement sets `posting_date` to today. The date the user entered survives
in another field: `value_date` on a repayment or write-off, and
`disbursement_date` on a disbursement. That is the business date these checks
hold the GL to.

Lending then makes it worse after a backdated repayment. It submits a Loan
Repayment Repost, which cancels and re-books the GL of every repayment from
that date on, and `LoanRepayment.get_gl_map` dates it
`getdate() if self.flags.from_repost`. So the repost moves repayments that were
right to the day it ran: one repayment entered late for an earlier month takes
every later one with it.

Commons Settings' "Enable Loan Vouchers on Their Own Dates" keeps all three on
their own dates, reposts included (`commons.banking.loan_own_dates`).

`find_discrepancies` asks whether the books agree with the documents, whatever
keeps them there, so it also judges anything a site does on its own.
`setting_warning` says, when the setting is off, that nothing in this app keeps
new vouchers on their dates.

The repair touches Loan Repayments only. It cancels the repayment's live GL
and books it again from the document, as a repost does with the setting on,
and refuses when the document's own `posting_date` is not its value date,
because lending would book it on the wrong day again. Write-offs and disbursements are only
reported. Their `posting_date` is the day they were saved, so booking them
again would change nothing.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from commons.banking.ledger_audit import check_can_repair
from commons.commons_core import apps

# The most repayments one bulk request re-books. Each is its own savepoint.
MAX_BULK = 200

# Per voucher type: the field holding the date it is for, and its loan field.
VOUCHERS = {
	"Loan Repayment": ("value_date", "against_loan"),
	"Loan Write Off": ("value_date", "loan"),
	"Loan Disbursement": ("disbursement_date", "against_loan"),
}

GL_DATE = "GL not on the voucher's date"
DOC_DATE = "Posting date is not the value date"


def _gl_dates(voucher_type: str, names: list[str]) -> dict:
	"""{voucher_no: {date: debit}} from each voucher's live GL."""
	if not names:
		return {}
	out = {}
	for r in frappe.db.sql(
		"""
		select voucher_no, posting_date, sum(debit) as debit
		from `tabGL Entry`
		where voucher_type = %s and voucher_no in %s and is_cancelled = 0
		group by voucher_no, posting_date
		""",
		(voucher_type, tuple(names)),
		as_dict=True,
	):
		out.setdefault(r.voucher_no, {})[getdate(r.posting_date)] = flt(r.debit)
	return out


def issues_for(voucher_type: str, doc, gl: dict) -> list[tuple[str, str]]:
	"""The (issue, detail) pairs for one voucher. `gl` is {date: debit}."""
	date = getdate(doc.date)
	found = []
	wrong = sorted(d for d in gl if d != date)
	if wrong:
		found.append((GL_DATE, ", ".join(str(d) for d in wrong)))
	if voucher_type == "Loan Repayment" and getdate(doc.posting_date) != date:
		found.append((DOC_DATE, str(getdate(doc.posting_date))))
	return found


def find_discrepancies(filters) -> list[dict]:
	"""Every submitted lending voucher whose ledger dates disagree with it."""
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Company is required"))
	rows = []
	for voucher_type, (date_field, loan_field) in VOUCHERS.items():
		if not apps.has_doctype(voucher_type):
			continue
		if filters.voucher_type and filters.voucher_type != voucher_type:
			continue
		conditions = {"docstatus": 1, "company": filters.company}
		if filters.loan:
			conditions[loan_field] = filters.loan
		if filters.from_date and filters.to_date:
			conditions[date_field] = ("between", [filters.from_date, filters.to_date])
		elif filters.from_date:
			conditions[date_field] = (">=", filters.from_date)
		elif filters.to_date:
			conditions[date_field] = ("<=", filters.to_date)
		docs = frappe.get_all(
			voucher_type,
			filters=conditions,
			fields=["name", f"{date_field} as date", "posting_date", f"{loan_field} as loan"],
			order_by=f"{date_field}, name",
		)
		names = [d.name for d in docs]
		gl = _gl_dates(voucher_type, names)
		for doc in docs:
			entries = gl.get(doc.name, {})
			for issue, detail in issues_for(voucher_type, doc, entries):
				rows.append(
					frappe._dict(
						issue=issue,
						date=getdate(doc.date),
						voucher_type=voucher_type,
						voucher_no=doc.name,
						loan=doc.loan,
						posting_date=getdate(doc.posting_date),
						found=detail,
						amount=sum(entries.values()),
					)
				)
	return rows


# The setting


def setting_warning() -> str | None:
	"""A warning when Commons Settings' "Enable Loan Vouchers on Their Own Dates"
	is off, else None.

	With it off, lending dates every voucher saved from now on, and every
	repayment a repost re-books, on the day it happens. A site may keep the
	dates some other way; the GL dates check shows whether it does.
	"""
	from commons.commons_core.settings import ENABLE_LOAN_OWN_DATES, feature_enabled

	if feature_enabled(ENABLE_LOAN_OWN_DATES):
		return None
	return _(
		"Commons Settings' Enable Loan Vouchers on Their Own Dates is off, so lending books "
		"repayments, write-offs and disbursements saved or reposted from now on on the day "
		"that happens, not on their own dates."
	)


# Repair


def _plan(voucher_no: str) -> frappe._dict:
	doc = frappe.db.get_value(
		"Loan Repayment",
		voucher_no,
		["name", "docstatus", "value_date as date", "posting_date", "company"],
		as_dict=True,
	)
	if not doc:
		frappe.throw(_("Loan Repayment {0} not found").format(voucher_no))
	gl = frappe.get_all(
		"GL Entry",
		filters={"voucher_type": "Loan Repayment", "voucher_no": voucher_no, "is_cancelled": 0},
		fields=["posting_date", "account", "debit", "credit"],
		order_by="creation, name",
	)
	date = getdate(doc.date)
	plan = frappe._dict(
		voucher_no=voucher_no,
		date=date,
		posting_date=getdate(doc.posting_date),
		gl=gl,
		needed=any(getdate(g.posting_date) != date for g in gl),
		refused=None,
	)
	if doc.docstatus != 1:
		plan.refused = _("{0} is not submitted.").format(voucher_no)
	elif not gl:
		plan.refused = _("{0} has no GL to re-book.").format(voucher_no)
	elif plan.posting_date != date:
		plan.refused = _(
			"{0}'s posting date is {1} but its value date is {2}. Lending would book it on {1} again, so this needs a person."
		).format(voucher_no, plan.posting_date, date)
	return plan


@frappe.whitelist()
def preview_repair(voucher_no: str) -> dict:
	"""What re-booking a repayment would do, without doing it."""
	check_can_repair()
	return _plan(voucher_no)


def _repair(voucher_no: str) -> dict:
	plan = _plan(voucher_no)
	if not plan.needed:
		return {"voucher_no": voucher_no, "status": "nothing to repair"}
	if plan.refused:
		frappe.throw(plan.refused)

	doc = frappe.get_doc("Loan Repayment", voucher_no)
	doc.make_gl_entries(cancel=1)
	doc.make_gl_entries()

	after = frappe.get_all(
		"GL Entry",
		filters={"voucher_type": "Loan Repayment", "voucher_no": voucher_no, "is_cancelled": 0},
		pluck="posting_date",
	)
	if not after or any(getdate(d) != plan.date for d in after):
		frappe.throw(_("{0} did not re-book on {1}").format(voucher_no, plan.date))

	moved = sorted({str(getdate(g.posting_date)) for g in plan.gl if getdate(g.posting_date) != plan.date})
	doc.add_comment(
		"Info",
		_("GL re-booked on the repayment's date {0}; it was dated {1}.").format(plan.date, ", ".join(moved)),
	)
	return {"voucher_no": voucher_no, "status": "re-booked", "date": str(plan.date)}


@frappe.whitelist(methods=["POST"])
def repair_repayment(voucher_no: str) -> dict:
	"""Re-book one repayment's GL on its own date."""
	check_can_repair()
	return _repair(voucher_no)


@frappe.whitelist(methods=["POST"])
def repair_repayments(vouchers: list | str) -> list[dict]:
	"""`repair_repayment` for several, each alone: a refusal skips only that one."""
	check_can_repair()
	vouchers = frappe.parse_json(vouchers)
	if len(vouchers) > MAX_BULK:
		frappe.throw(_("At most {0} repayments at a time").format(MAX_BULK))
	results = []
	for name in vouchers:
		frappe.db.savepoint("loan_date_repair")
		try:
			results.append(_repair(name))
		except Exception as e:
			frappe.db.rollback(save_point="loan_date_repair")
			frappe.clear_last_message()
			results.append({"voucher_no": name, "status": "failed", "error": str(e)})
	return results
