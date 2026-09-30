"""Is every lending voucher's GL on the date the voucher is for, is what keeps
it there in place, and the repair when it is not.

Lending dates its documents and their GL on the day they are saved, whatever
date was entered. Loan Repayment's `validate` sets `posting_date` to now, and
its GL is dated from `posting_date`. Loan Write Off does the same, and Loan
Disbursement sets `posting_date` to today. The date the user entered survives
in another field: `value_date` on a repayment or write-off, and
`disbursement_date` on a disbursement. That is the business date these checks
hold the GL to.

Two site Server Scripts keep a repayment's `posting_date` as entered ("Loan
Repayment - Remember Posting Date" stashes it in Before Validate, "Loan
Repayment - Keep Posting Date" puts it back in Before Save). That covers
submit, but not what follows a backdated repayment. Lending then submits a
Loan Repayment Repost, which cancels and re-books the GL of every repayment
from that date on, and `LoanRepayment.get_gl_map` dates it
`getdate() if self.flags.from_repost`. So the repost moves repayments that were
right to the day it ran. On 2026-09-27, LM-REP-0140 was entered for April and
took LM-REP-0118 and LM-REP-0124 with it. A third script on the repost, After
Submit, books them again on their own dates.

`find_discrepancies` asks whether the books agree with the documents, whatever
the scripts say. `safeguards` asks whether the scripts are there and working.
It runs the two repayment scripts on an unsaved document inside a savepoint
that is rolled back, so it tests what they do rather than what they are called.

The repair touches Loan Repayments only. It cancels the repayment's live GL
and books it again from the document, as the repost script does, and refuses
when the document's own `posting_date` is not its value date, because lending
would book it on the wrong day again. Write-offs and disbursements are only
reported. Their `posting_date` is always the day they were saved, so booking
them again would change nothing.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime

from commons.commons_core import apps

# Who may run the repair. It re-books GL, so it is for the people who may
# already fix the books by hand.
REPAIR_ROLES = ("Accounts Manager", "System Manager")

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
GFL_DATE = "GFL income entry not on the repayment's date"

# What the repost script must do, found in its text. Whitespace is ignored.
REBOOK_CALLS = ("make_gl_entries(cancel=1)", "make_gl_entries()")

OK = "OK"
MISSING = "Missing"
NOT_COVERED = "Not covered"


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


def _gfl_dates(names: list[str]) -> dict:
	"""{repayment: (journal entry, its date)} for the site's GFL income entries."""
	if not names or not frappe.get_meta("Loan Repayment").has_field("custom_gfl_income_voucher"):
		return {}
	rows = frappe.get_all(
		"Loan Repayment",
		filters={"name": ("in", names), "custom_gfl_income_voucher": ("is", "set")},
		fields=["name", "custom_gfl_income_voucher"],
	)
	je_dates = dict(
		frappe.get_all(
			"Journal Entry",
			filters={"name": ("in", [r.custom_gfl_income_voucher for r in rows]), "docstatus": 1},
			fields=["name", "posting_date"],
			as_list=True,
		)
	)
	return {
		r.name: (r.custom_gfl_income_voucher, getdate(je_dates[r.custom_gfl_income_voucher]))
		for r in rows
		if r.custom_gfl_income_voucher in je_dates
	}


def issues_for(voucher_type: str, doc, gl: dict, gfl: tuple | None) -> list[tuple[str, str]]:
	"""The (issue, detail) pairs for one voucher. `gl` is {date: debit}."""
	date = getdate(doc.date)
	found = []
	wrong = sorted(d for d in gl if d != date)
	if wrong:
		found.append((GL_DATE, ", ".join(str(d) for d in wrong)))
	if voucher_type == "Loan Repayment" and getdate(doc.posting_date) != date:
		found.append((DOC_DATE, str(getdate(doc.posting_date))))
	if gfl and gfl[1] != date:
		found.append((GFL_DATE, f"{gfl[0]} on {gfl[1]}"))
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
		gfl = _gfl_dates(names) if voucher_type == "Loan Repayment" else {}
		for doc in docs:
			entries = gl.get(doc.name, {})
			for issue, detail in issues_for(voucher_type, doc, entries, gfl.get(doc.name)):
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


# Safeguards


def _repayment_scripts() -> list[str]:
	return frappe.get_all(
		"Server Script",
		filters={
			"script_type": "DocType Event",
			"reference_doctype": "Loan Repayment",
			"doctype_event": ("in", ["Before Validate", "Before Save"]),
			"disabled": 0,
		},
		pluck="name",
		order_by="name",
	)


def probe_repayment_date() -> tuple[bool, str]:
	"""Whether a Loan Repayment keeps the posting date it was given.

	Runs the site's Before Validate scripts, overwrites the date as lending's
	`validate` does, then runs its Before Save scripts, all on an unsaved
	document inside a savepoint that is rolled back.
	"""
	from frappe.core.doctype.server_script.server_script_utils import run_server_script_for_doc_event

	entered = get_datetime("2001-02-03 04:05:06")
	doc = frappe.new_doc("Loan Repayment")
	doc.posting_date = entered
	frappe.db.savepoint("loan_date_probe")
	try:
		run_server_script_for_doc_event(doc, "before_validate")
		doc.posting_date = now_datetime()
		run_server_script_for_doc_event(doc, "validate")
		kept = get_datetime(doc.posting_date) == entered
		return kept, "" if kept else _("posting date became {0}").format(doc.posting_date)
	except Exception as e:
		return False, str(e)
	finally:
		frappe.db.rollback(save_point="loan_date_probe")
		frappe.clear_last_message()


def rebooks(script: str) -> bool:
	"""Whether a repost script's text cancels and re-books GL."""
	text = "".join((script or "").split())
	return all(call in text for call in REBOOK_CALLS)


def _repost_scripts() -> list[str]:
	return [
		s.name
		for s in frappe.get_all(
			"Server Script",
			filters={
				"script_type": "DocType Event",
				"reference_doctype": "Loan Repayment Repost",
				"doctype_event": "After Submit",
				"disabled": 0,
			},
			fields=["name", "script"],
			order_by="name",
		)
		if rebooks(s.script)
	]


def safeguards() -> list[dict]:
	"""What keeps lending's GL on the voucher's date, and whether it is in place."""
	from frappe.utils.safe_exec import is_safe_exec_enabled

	rows = []

	def add(check, ok, detail, status=None):
		rows.append(frappe._dict(check=check, status=status or (OK if ok else MISSING), detail=detail))

	enabled = is_safe_exec_enabled()
	add(
		_("Server scripts can run"),
		enabled,
		_("server_script_enabled is set in common_site_config.json")
		if enabled
		else _("Set server_script_enabled in common_site_config.json; site_config is not read for it"),
	)

	if apps.has_doctype("Loan Repayment"):
		kept, why = probe_repayment_date() if enabled else (False, _("server scripts cannot run"))
		scripts = ", ".join(_repayment_scripts()) or _("none enabled")
		add(
			_("Loan Repayment keeps the posting date entered"),
			kept,
			_("Tested now, rolled back. Scripts: {0}").format(scripts)
			if kept
			else _("{0}. Scripts: {1}").format(why, scripts),
		)

	if apps.has_doctype("Loan Repayment Repost"):
		found = _repost_scripts()
		add(
			_("Repost books repayments on their own dates"),
			bool(found) and enabled,
			", ".join(found)
			if found
			else _(
				"No enabled After Submit script on Loan Repayment Repost calls make_gl_entries(cancel=1) and make_gl_entries()"
			),
		)

	for voucher_type, date_field in (
		("Loan Write Off", "Value Date"),
		("Loan Disbursement", "Disbursement Date"),
	):
		if apps.has_doctype(voucher_type):
			add(
				_("{0}: GL on the {1}").format(voucher_type, date_field),
				False,
				_(
					"Nothing keeps it there: lending dates a {0}'s GL on the day it is submitted. A backdated one shows under GL dates."
				).format(voucher_type),
				status=NOT_COVERED,
			)
	return rows


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
	frappe.only_for(REPAIR_ROLES)
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
	frappe.only_for(REPAIR_ROLES)
	return _repair(voucher_no)


@frappe.whitelist(methods=["POST"])
def repair_repayments(vouchers: list | str) -> list[dict]:
	"""`repair_repayment` for several, each alone: a refusal skips only that one."""
	frappe.only_for(REPAIR_ROLES)
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
