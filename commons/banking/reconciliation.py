"""What the navigation asks about the reconciliation page, and the one write it
makes in a single step.

The questions are the same two the attendance register answers: does this site
have the page at all, and is this reader somebody it is for.

The write is `create_loan_repayments`, and it adds no capability. It books a
repayment the way lending's own `create_loan_repayment_bts` does: naming the
statement's Bank Account and its GL account as the repayment's `bank_account`
and `payment_account`, which `LoanRepayment.set_repayment_account` then keeps.
The repayment is then matched to the deposit, as a `Matched` row.

The endpoint does those same two steps, making the same documents, in one
request. There are two reasons for that:

* One request is one transaction in Frappe. If the match is refused, the
  repayment goes too, rather than staying submitted with nothing on the
  statement to account for it.
* The page cannot do the matching step through ERPNext's own candidate search.
  Lending's contribution to it, `get_lr_matching_query`, selects its rank
  without naming it `rank` and its amount without naming it `paid_amount`. So
  `check_matching`'s sort raises `KeyError` whenever an uncleared repayment
  exists. The page reads uncleared repayments through the document API instead.

Every repayment type Bank Reconciliation Settings allows is one lending books
from a statement (`BANK_RECONCILIATION_REPAYMENT_TYPES`), and each of those
posts to the repayment's own `payment_account`, so the repayment posts to this
statement's bank. A Bank Account with no GL account is refused up front,
because lending would then fall back to the Loan Product's account.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate

from commons.banking.doctype.bank_reconciliation_settings import bank_reconciliation_settings as settings
from commons.commons_core import apps

BANK_TRANSACTION = "Bank Transaction"
BANK_ACCOUNT = "Bank Account"
LOAN = "Loan"
LOAN_REPAYMENT = "Loan Repayment"

# `Loan Repayment.reference_number` is a Data field.
REFERENCE_LENGTH = 140


def available() -> bool:
	"""Whether this site keeps bank statements at all.

	`Bank Transaction` and `Bank Account` are what the page is made of: the lines
	and the account they belong to. Lending is optional. Without it, the page
	still matches and creates payment and journal entries, and the loan tab
	takes itself away.
	"""
	return apps.has_doctype(BANK_TRANSACTION) and apps.has_doctype(BANK_ACCOUNT)


def can_reconcile() -> bool:
	"""Whether this reader reconciles, which is the whole of who the page is for.

	The test is write on `Bank Transaction`, because every reconciliation saves
	one. It also matters for a second reason. ERPNext's candidate search,
	`get_linked_payments`, reads vouchers without asking permission, so the page
	must not be offered to somebody who could not keep a bank account's books in
	the desk. Accounts User and Accounts Manager hold this right; nobody else
	does on a stock site.
	"""
	return bool(frappe.has_permission(BANK_TRANSACTION, "write"))


@frappe.whitelist(methods=["POST"])
def create_loan_repayments(
	bank_transaction: str,
	repayments: list[dict],
	reference_number: str | None = None,
	draft: bool = False,
) -> dict:
	"""Book one deposit as repayments of one or more loans, and reconcile them.

	With `draft`, the repayments are inserted, with every check below, and left
	as drafts: not submitted, so nothing is posted, and not matched to the line.
	For a bookkeeper who wants someone else to look before anything reaches the
	ledger. The line stays open, and the drafts appear on the page's board
	under "Include drafts", where "Submit and match" finishes the job and still
	posts on the day the money arrived.

	`repayments` is `[{"loan": ..., "amount": ...}]`. There is more than one
	when a borrower pays two loans with one transfer, or somebody pays for a
	sibling. Each becomes a repayment of the type Bank Reconciliation Settings
	names (`Normal Repayment` unless a site says otherwise), dated
	(`value_date`) when the money arrived, and is then submitted and matched to
	the deposit -- or, with `draft`, left as a draft as above.

	The permission checks are the documents' own. Inserting and submitting a
	repayment checks `create` and `submit` on `Loan Repayment`, and
	reconciling saves the `Bank Transaction`, which checks `write`. The explicit
	`check_permission` calls below come first only so that a refusal is reported
	before anything is attempted, rather than halfway through.
	"""
	# Locked for the rest of the request. Two bookkeepers booking against the
	# same deposit at once would otherwise both pass the unallocated check below,
	# and ERPNext's allocation would then quietly match only what the first left
	# of the second -- a repayment submitted in full, posted to the loan, and
	# never cleared.
	transaction = frappe.get_doc(BANK_TRANSACTION, bank_transaction, for_update=True)
	transaction.check_permission("write")
	lines = _validated_lines(transaction, repayments)

	gl_account = frappe.db.get_value(BANK_ACCOUNT, transaction.bank_account, "account")
	if not gl_account:
		frappe.throw(
			_("Bank Account {0} has no GL account to post repayments to.").format(transaction.bank_account)
		)
	reference = (reference_number or "").strip()[:REFERENCE_LENGTH]
	repayment_type = settings.default_repayment_type()

	created = []
	for line in lines:
		# The loan, the amount, the date the money arrived, a reference if one
		# was typed, and the statement's bank, as lending's own
		# `create_loan_repayment_bts` names it.
		repayment = frappe.get_doc(
			{
				"doctype": LOAN_REPAYMENT,
				"against_loan": line["loan"],
				"repayment_type": repayment_type,
				"amount_paid": line["amount"],
				"bank_account": transaction.bank_account,
				"payment_account": gl_account,
				# Both dates are the day the money arrived. Lending's `validate`
				# replaces `posting_date` with the current time on every save;
				# Commons Settings' "Enable Loan Vouchers on Their Own Dates"
				# puts it back, so the ledger entries are dated as sent here.
				# Without it, lending posts on the day of booking, which
				# `_require_statement_date` refuses.
				"posting_date": get_datetime(transaction.date),
				"value_date": get_datetime(transaction.date),
				"reference_number": reference or None,
				"reference_date": getdate(transaction.date) if reference else None,
			}
		)
		repayment.insert()
		_require_statement_date(repayment, transaction)
		if not draft:
			repayment.submit()
			_require_statement_date(repayment, transaction)
		created.append(repayment.name)

	if draft:
		return {
			"transaction": transaction.name,
			"status": transaction.status,
			"unallocated_amount": transaction.unallocated_amount,
			"repayments": created,
			"draft": True,
		}

	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
		reconcile_vouchers,
	)

	# `Matched`, not `Voucher Created`, like every repayment matched by hand.
	# The difference is what ERPNext's `unreconcile_transaction` does later: it
	# cancels vouchers marked as created, and only unlinks matched ones.
	reconciled = reconcile_vouchers(
		transaction.name,
		json.dumps([{"payment_doctype": LOAN_REPAYMENT, "payment_name": name} for name in created]),
	)
	_require_fully_matched(
		reconciled, LOAN_REPAYMENT, {name: line["amount"] for name, line in zip(created, lines, strict=True)}
	)
	return {
		"transaction": reconciled.name,
		"status": reconciled.status,
		"unallocated_amount": reconciled.unallocated_amount,
		"repayments": created,
	}


# The voucher types a draft on the board can be, which are the ones ERPNext's
# reconciliation can match (`bank_reconciliation_doctypes`, with lending's two).
DRAFT_VOUCHERS = (
	"Payment Entry",
	"Journal Entry",
	"Purchase Invoice",
	"Sales Invoice",
	"Loan Repayment",
	"Loan Disbursement",
)


@frappe.whitelist(methods=["POST"])
def submit_and_reconcile(bank_transaction: str, voucher_type: str, voucher: str) -> dict:
	"""Submit a draft voucher and match it to a statement line, in one transaction.

	What the board offers when a statement line is paired with a draft: the
	payment somebody started and never submitted, which the bank has since
	shown. ERPNext can only match a submitted voucher (a draft has no GL
	entries to clear), so the two steps are needed. They are one request for the
	reason `create_loan_repayments` is: if the match is refused, the submit
	goes too, rather than leaving the voucher posted with no statement line
	accounting for it.

	The voucher is submitted as it stands in the database, not as the page last
	read it, and goes through its full submit: validation, `submit` permission
	and any server scripts the site has. It is matched as `Matched`, not
	`Voucher Created`, because it existed before the statement line was dealt
	with; ERPNext's `unreconcile_transaction` would otherwise cancel it later.
	"""
	if voucher_type not in DRAFT_VOUCHERS:
		frappe.throw(_("{0} cannot be matched to a statement line.").format(voucher_type))

	# Locked, for the reason `create_loan_repayments` gives.
	transaction = frappe.get_doc(BANK_TRANSACTION, bank_transaction, for_update=True)
	transaction.check_permission("write")
	if transaction.docstatus != 1:
		frappe.throw(_("Only a submitted bank transaction can be reconciled."))
	if flt(transaction.unallocated_amount) <= 0:
		frappe.throw(_("Bank transaction {0} is already fully reconciled.").format(transaction.name))

	document = frappe.get_doc(voucher_type, voucher)
	if document.docstatus != 0:
		frappe.throw(_("{0} {1} is not a draft.").format(voucher_type, voucher))
	dated = document.get("posting_date")
	document.submit()
	if voucher_type == LOAN_REPAYMENT:
		# Lending re-dates on submit too; the draft's own date is what stands.
		_require_date_kept(document, dated)
	_require_same_direction(transaction, voucher_type, document.name)

	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
		reconcile_vouchers,
	)

	reconciled = reconcile_vouchers(
		transaction.name,
		json.dumps([{"payment_doctype": voucher_type, "payment_name": document.name}]),
	)
	return {
		"transaction": reconciled.name,
		"status": reconciled.status,
		"unallocated_amount": reconciled.unallocated_amount,
		"voucher": document.name,
	}


@frappe.whitelist()
def accounting_dimensions(company: str) -> list[dict]:
	"""The company's accounting dimensions, and which accounts must carry them.

	What `GLEntry.validate_dimensions_for_pl_and_bs` enforces at submit: a
	dimension marked mandatory for Profit and Loss or Balance Sheet accounts
	must be set on every GL entry against that kind of account, and a missing
	one refuses the whole voucher. The page asks first, so a Payment Entry or a
	Journal Entry made from a statement line carries them from the start.

	An endpoint because `Accounting Dimension` is readable only by System
	Managers and Accounts Managers, and an Accounts User, who is exactly who
	books these entries, is refused it. What comes back is configuration: the
	dimension's field and label, the company's default value, and the two
	flags. Which values exist is still read through Frappe's own link search,
	under the reader's permissions.
	"""
	if not can_reconcile():
		frappe.throw(_("You are not allowed to reconcile bank transactions."), frappe.PermissionError)
	if not apps.has_doctype("Accounting Dimension"):
		return []
	dimension = frappe.qb.DocType("Accounting Dimension")
	detail = frappe.qb.DocType("Accounting Dimension Detail")
	rows = (
		frappe.qb.from_(dimension)
		.left_join(detail)
		.on((detail.parent == dimension.name) & (detail.company == company))
		.select(
			dimension.fieldname,
			dimension.label,
			dimension.document_type,
			detail.default_dimension,
			detail.mandatory_for_pl,
			detail.mandatory_for_bs,
		)
		.where(dimension.disabled == 0)
		.run(as_dict=True)
	)
	return [
		{
			"fieldname": row.fieldname,
			"label": row.label or row.document_type,
			"document_type": row.document_type,
			"default": row.default_dimension,
			"mandatory_for_pl": bool(row.mandatory_for_pl),
			"mandatory_for_bs": bool(row.mandatory_for_bs),
		}
		for row in rows
	]


@frappe.whitelist()
def loan_matching_settings() -> dict[str, int]:
	"""The weights and thresholds the page's loan suggestions are scored with.

	Bank Reconciliation Settings is readable only by System Managers, and the
	bookkeeper the suggestions are for is usually an Accounts User, so the page
	reads it here. Tuning, not data: the same answer for everybody who may use
	the page, each value falling back to its default as `loan_matching` explains.
	"""
	if not can_reconcile():
		frappe.throw(_("You are not allowed to reconcile bank transactions."), frappe.PermissionError)
	return settings.loan_matching()


# The most names one `applicant_titles` request reads, which is the page's own
# cap on loans.
MAX_TITLES = 2000


@frappe.whitelist()
def applicant_titles(doctype: str, names: list | str) -> dict[str, str]:
	"""{name: title} for these records of one loan applicant doctype.

	The title is the doctype's own title field, from its meta, so a site that
	lends to a doctype of its own (Lending's applicant type is a Select a site
	may extend) gets its borrowers' names without the page knowing the field.

	Read with `get_list`, under the reader's permissions. A doctype this reader
	may not read, or one with no title field, answers with nothing, and the
	page names those borrowers by id.
	"""
	names = frappe.parse_json(names) if isinstance(names, str) else names
	if not isinstance(names, list) or len(names) > MAX_TITLES:
		frappe.throw(_("At most {0} names at a time").format(MAX_TITLES))
	if not names or not apps.has_doctype(doctype) or not frappe.has_permission(doctype, "read"):
		return {}
	title_field = frappe.get_meta(doctype).get_title_field()
	if title_field == "name":
		return {}
	rows = frappe.get_list(
		doctype,
		filters={"name": ["in", list(set(names))]},
		fields=["name", title_field],
		limit_page_length=len(names),
	)
	return {row.name: row.get(title_field) for row in rows if row.get(title_field)}


def _validated_lines(transaction, repayments) -> list[dict]:
	"""The lines, checked against the deposit before anything is written.

	ERPNext would refuse most of these problems itself, but late and in its own
	words. Over-allocating fails deep inside `allocate_payment_entries`, and on
	this ERPNext version the message there is itself broken: two placeholders
	and one argument, so it raises `IndexError`. Only after that would the
	submitted repayments be rolled back.
	"""
	if transaction.docstatus != 1:
		frappe.throw(_("Only a submitted bank transaction can be reconciled."))
	if flt(transaction.deposit) <= 0:
		frappe.throw(_("A loan repayment can only be booked against a deposit."))

	rows = frappe.parse_json(repayments) if isinstance(repayments, str) else repayments
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("Name at least one loan to repay."))

	precision = transaction.precision("unallocated_amount")
	company = transaction.company
	lines, seen = [], set()
	for row in rows:
		if not isinstance(row, dict):
			frappe.throw(_("Each repayment names a loan and an amount."))
		loan, amount = row.get("loan"), flt(row.get("amount"), precision)
		if not loan:
			frappe.throw(_("Each repayment names a loan."))
		if loan in seen:
			frappe.throw(_("Loan {0} appears twice. Combine the amounts into one line.").format(loan))
		seen.add(loan)
		if amount <= 0:
			frappe.throw(_("The repayment of {0} has no amount.").format(loan))
		loan_company = frappe.db.get_value(LOAN, loan, "company")
		if loan_company is None:
			frappe.throw(_("Loan {0} does not exist.").format(loan))
		if loan_company != company:
			frappe.throw(
				_("Loan {0} belongs to {1}, and this bank account to {2}.").format(
					loan, loan_company, company
				)
			)
		frappe.get_doc(LOAN, loan).check_permission("read")
		lines.append({"loan": loan, "amount": amount})

	total = flt(sum(line["amount"] for line in lines), precision)
	if total > flt(transaction.unallocated_amount, precision):
		frappe.throw(
			_("The repayments come to {0}, but only {1} of this deposit is unallocated.").format(
				frappe.format_value(total, {"fieldtype": "Currency", "options": transaction.currency}),
				frappe.format_value(
					transaction.unallocated_amount, {"fieldtype": "Currency", "options": transaction.currency}
				),
			)
		)
	return lines


def _require_date_kept(repayment, dated) -> None:
	"""Refuse a submit that moved a draft repayment off the date it was saved with. See below."""
	if getdate(repayment.posting_date) != getdate(dated):
		frappe.throw(_date_moved_message(repayment, dated))


def _require_statement_date(repayment, transaction) -> None:
	"""Refuse a repayment that lending has dated other than the day the money arrived.

	Lending's `validate` sets `posting_date` to the current time on every save.
	Commons Settings' "Enable Loan Vouchers on Their Own Dates" puts the
	statement's date back, or a site may do it its own way. When nothing does --
	the setting off, or the site's own way not running -- the repayment would
	post to the ledger on the day it was booked, with nothing on screen to say
	so. Refused instead, which rolls back everything this request has written.
	"""
	if getdate(repayment.posting_date) != getdate(transaction.date):
		frappe.throw(_date_moved_message(repayment, transaction.date))


def _date_moved_message(repayment, meant) -> str:
	return _(
		"Lending dated {0} {1} instead of {2}. Nothing kept the repayment's posting date: turn on "
		"Enable Loan Vouchers on Their Own Dates in Commons Settings, or book it from the desk."
	).format(repayment.name or _("the repayment"), getdate(repayment.posting_date), getdate(meant))


def _require_fully_matched(transaction, voucher_type: str, amounts: dict[str, float]) -> None:
	"""Refuse a match that left part of a voucher unallocated.

	ERPNext's `allocate_payment_entries` allocates the smaller of a voucher and
	what is left on the line, and says nothing when that is less than the
	voucher. For a repayment made from this line, less means somebody else got
	to the line first; the whole request is rolled back rather than leaving a
	repayment posted in full and matched in part.
	"""
	precision = transaction.precision("unallocated_amount")
	allocated: dict[str, float] = {}
	for row in transaction.payment_entries:
		if row.payment_document == voucher_type:
			allocated[row.payment_entry] = allocated.get(row.payment_entry, 0) + flt(row.allocated_amount)
	for name, amount in amounts.items():
		if flt(allocated.get(name), precision) < flt(amount, precision):
			frappe.throw(
				_(
					"Only {0} of {1} could be matched to {2}. Someone else may have matched this line "
					"meanwhile; reload the page and try again."
				).format(flt(allocated.get(name), precision), name, transaction.name)
			)


def _require_same_direction(transaction, voucher_type: str, voucher: str) -> None:
	"""Refuse a voucher that moves this statement's bank account the other way, or not at all.

	The board only pairs a deposit with money in and a withdrawal with money out,
	but that is the browser's check. ERPNext's match compares amounts without
	signs, so a payment out matched to a deposit would be accepted and clear the
	line. Read off the voucher's own ledger entries, now it has been submitted:
	a deposit debits the bank's account, a withdrawal credits it.
	"""
	account = frappe.db.get_value(BANK_ACCOUNT, transaction.bank_account, "account")
	net = _net_on_account(voucher_type, voucher, account)
	if not net:
		frappe.throw(
			_("{0} {1} does not post to {2}, the account this statement is for.").format(
				voucher_type, voucher, account
			)
		)
	if (net > 0) != (flt(transaction.deposit) > 0):
		frappe.throw(
			_("{0} {1} is money {2} this account, and the statement line is money {3}.").format(
				voucher_type,
				voucher,
				_("into") if net > 0 else _("out of"),
				_("in") if flt(transaction.deposit) > 0 else _("out"),
			)
		)


def _net_on_account(voucher_type: str, voucher: str, account: str) -> float:
	"""What `voucher` does to `account`, in its own currency: debits less credits."""
	from frappe.query_builder.functions import Sum

	gle = frappe.qb.DocType("GL Entry")
	return flt(
		frappe.qb.from_(gle)
		.select(Sum(gle.debit_in_account_currency - gle.credit_in_account_currency))
		.where(
			(gle.voucher_type == voucher_type)
			& (gle.voucher_no == voucher)
			& (gle.account == account)
			& (gle.is_cancelled == 0)
		)
		.run()[0][0]
	)
