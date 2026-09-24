"""What the navigation asks about the reconciliation page, and the one write it
makes in a single step.

The questions are the same two the attendance register answers: does this site
have the page at all, and is this reader somebody it is for.

The write is `create_loan_repayments`, and it adds no capability. On this
site a repayment made the ordinary way is already reconcilable: nothing names an
account on it, so `LoanRepayment.set_repayment_account` falls back to the Loan
Product's `payment_account`, which is the GL account of the bank the borrowers
pay into. The repayment is then matched to the deposit. Every reconciled
repayment on register.localhost was booked this way, and all of them are
`Matched` rows.

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

The repayment is refused before submit if it would not post to this
statement's bank account. That happens for a deposit into an account the Loan
Product does not name, and ERPNext would reject the match anyway, but only
after the repayment had been submitted.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate

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
) -> dict:
	"""Book one deposit as repayments of one or more loans, and reconcile them.

	`repayments` is `[{"loan": ..., "amount": ...}]`. There is more than one
	when a borrower pays two loans with one transfer, or somebody pays for a
	sibling. Each becomes a submitted `Normal Repayment` dated (`value_date`)
	when the money arrived, and is then matched to the deposit.

	The permission checks are the documents' own. Inserting and submitting a
	repayment checks `create` and `submit` on `Loan Repayment`, and
	reconciling saves the `Bank Transaction`, which checks `write`. The explicit
	`check_permission` calls below come first only so that a refusal is reported
	before anything is attempted, rather than halfway through.
	"""
	transaction = frappe.get_doc(BANK_TRANSACTION, bank_transaction)
	transaction.check_permission("write")
	lines = _validated_lines(transaction, repayments)

	gl_account = frappe.db.get_value(BANK_ACCOUNT, transaction.bank_account, "account")
	reference = (reference_number or "").strip()[:REFERENCE_LENGTH]

	created = []
	for line in lines:
		# Only what a person fills in by hand: the loan, the amount, the date
		# the money arrived and, if they typed one, a reference. The account
		# is left to the Loan Product, exactly as it is when the form is used.
		repayment = frappe.get_doc(
			{
				"doctype": LOAN_REPAYMENT,
				"against_loan": line["loan"],
				"repayment_type": "Normal Repayment",
				"amount_paid": line["amount"],
				# No `posting_date`: `LoanRepayment.validate` overwrites it with
				# the current time whatever is sent.
				"value_date": get_datetime(transaction.date),
				"reference_number": reference or None,
				"reference_date": getdate(transaction.date) if reference else None,
			}
		)
		repayment.insert()
		if repayment.payment_account != gl_account:
			frappe.throw(
				_(
					"{0} would post to {1}, but this statement is for {2} ({3}). "
					"Set the Loan Product's repayment account, or book it from the desk."
				).format(line["loan"], repayment.payment_account, transaction.bank_account, gl_account)
			)
		repayment.submit()
		created.append(repayment.name)

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
	return {
		"transaction": reconciled.name,
		"status": reconciled.status,
		"unallocated_amount": reconciled.unallocated_amount,
		"repayments": created,
	}


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
				_("Loan {0} belongs to {1}, and this bank account to {2}.").format(loan, loan_company, company)
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
