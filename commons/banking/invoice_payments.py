"""Book a deposit as payments of Sales Invoices, and reconcile them, in one request.

The invoice counterpart of `reconciliation.create_loan_repayments`, and like it
it adds no capability. Each Payment Entry is the one ERPNext's own "Create >
Payment" on an invoice makes (`get_payment_entry`): the invoice's customer,
receivable account, accounting dimensions and payment-term rows. Then it is
dated the day the money arrived, posted to this statement's bank, cut down to
the amount paid, submitted and matched to the deposit as `Matched`.

One deposit can pay several invoices: a student paying two terms, or a parent
paying for two children. The invoices are grouped into as few Payment Entries
as ERPNext allows -- one per customer, receivable account and set of
accounting dimensions -- because a Payment Entry has one party, one party
account and one value for each dimension.

One request is one transaction, for the reasons `create_loan_repayments` gives:
a refused match takes the payments with it, and two bookkeepers on the same
deposit cannot both allocate it.

Who hears about it is not this module's business. A Notification on Payment
Entry's Submit sends the receipt, as one on Loan Repayment does for repayments,
so a payment booked in the desk sends the same email.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from commons.banking.reconciliation import (
	BANK_ACCOUNT,
	BANK_TRANSACTION,
	_require_fully_matched,
)

SALES_INVOICE = "Sales Invoice"
PAYMENT_ENTRY = "Payment Entry"

# `Payment Entry.reference_no` is a Data field.
REFERENCE_LENGTH = 140

# The fields of a reference row that describe the invoice, copied from the
# rows `get_payment_entry` proposes. `allocated_amount` is set here, and
# `payment_request` by ERPNext's own `allocate_open_payment_requests_to_references`.
REFERENCE_FIELDS = (
	"reference_doctype",
	"reference_name",
	"bill_no",
	"due_date",
	"total_amount",
	"outstanding_amount",
	"payment_term",
	"payment_term_outstanding",
)


@frappe.whitelist(methods=["POST"])
def create_invoice_payments(
	bank_transaction: str,
	payments: list[dict] | str,
	reference_number: str | None = None,
	draft: bool = False,
) -> dict:
	"""Book one deposit as payments of one or more Sales Invoices, and reconcile them.

	`payments` is `[{"invoice": ..., "amount": ...}]`. With `draft`, the
	Payment Entries are inserted, with every check below, and left as drafts:
	not submitted and not matched, so the line stays open and the drafts wait
	on the board under "Include drafts", as the loan tab's do.

	The permission checks are the documents' own: `get_payment_entry` asks for
	create on Payment Entry and read on the invoice, inserting and submitting
	ask for create and submit, and reconciling saves the Bank Transaction.
	"""
	draft = frappe.parse_json(draft) if isinstance(draft, str) else bool(draft)
	transaction = frappe.get_doc(BANK_TRANSACTION, bank_transaction, for_update=True)
	transaction.check_permission("write")
	lines = _validated_lines(transaction, payments)

	gl_account = frappe.db.get_value(BANK_ACCOUNT, transaction.bank_account, "account")
	if not gl_account:
		frappe.throw(
			_("Bank Account {0} has no GL account to post payments to.").format(transaction.bank_account)
		)
	reference = _reference(reference_number, transaction)

	created: dict[str, float] = {}
	for group in _grouped(lines):
		entry = _payment_entry(transaction, gl_account, group, reference)
		entry.insert()
		if not draft:
			entry.submit()
		created[entry.name] = flt(sum(line["amount"] for line in group))

	if draft:
		return {
			"transaction": transaction.name,
			"status": transaction.status,
			"unallocated_amount": transaction.unallocated_amount,
			"payment_entries": list(created),
			"draft": True,
		}

	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import (
		reconcile_vouchers,
	)

	# `Matched`, as `create_loan_repayments` explains.
	reconciled = reconcile_vouchers(
		transaction.name,
		json.dumps([{"payment_doctype": PAYMENT_ENTRY, "payment_name": name} for name in created]),
	)
	_require_fully_matched(reconciled, PAYMENT_ENTRY, created)
	return {
		"transaction": reconciled.name,
		"status": reconciled.status,
		"unallocated_amount": reconciled.unallocated_amount,
		"payment_entries": list(created),
	}


def _validated_lines(transaction, payments) -> list[dict]:
	"""The lines, with their invoices read, checked before anything is written.

	ERPNext would refuse most of these itself, but halfway through and in
	words about Payment Entry rows rather than about the deposit.
	"""
	if transaction.docstatus != 1:
		frappe.throw(_("Only a submitted bank transaction can be reconciled."))
	if flt(transaction.deposit) <= 0:
		frappe.throw(_("An invoice payment can only be booked against a deposit."))

	rows = frappe.parse_json(payments) if isinstance(payments, str) else payments
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("Name at least one invoice."))

	precision = transaction.precision("unallocated_amount")
	company_currency = frappe.get_cached_value("Company", transaction.company, "default_currency")
	bank_currency = frappe.get_cached_value(
		"Account",
		frappe.db.get_value(BANK_ACCOUNT, transaction.bank_account, "account"),
		"account_currency",
	)
	dimensions = _dimension_fields()

	lines, seen = [], set()
	for row in rows:
		if not isinstance(row, dict):
			frappe.throw(_("Each payment names an invoice and an amount."))
		name, amount = row.get("invoice"), flt(row.get("amount"), precision)
		if not name:
			frappe.throw(_("Each payment names an invoice."))
		if name in seen:
			frappe.throw(_("Invoice {0} appears twice. Combine the amounts into one line.").format(name))
		seen.add(name)
		if amount <= 0:
			frappe.throw(_("The payment of {0} has no amount.").format(name))

		invoice = frappe.db.get_value(
			SALES_INVOICE,
			name,
			[
				"name",
				"docstatus",
				"company",
				"customer",
				"debit_to",
				"is_return",
				"outstanding_amount",
				"party_account_currency",
				*dimensions,
			],
			as_dict=True,
		)
		if not invoice:
			frappe.throw(_("Sales Invoice {0} does not exist.").format(name))
		if invoice.docstatus != 1:
			frappe.throw(_("Sales Invoice {0} is not submitted.").format(name))
		if invoice.is_return:
			frappe.throw(
				_("{0} is a credit note; refunds are booked from the Payment entry tab.").format(name)
			)
		if invoice.company != transaction.company:
			frappe.throw(
				_("Sales Invoice {0} belongs to {1}, and this bank account to {2}.").format(
					name, invoice.company, transaction.company
				)
			)
		# A payment in another currency has an exchange rate and a gain or loss
		# to settle, which the desk's form is for.
		if (invoice.party_account_currency or company_currency) != company_currency or (
			bank_currency and bank_currency != company_currency
		):
			frappe.throw(
				_("{0} is not in {1}. Book a payment in another currency from the desk.").format(
					name, company_currency
				)
			)
		outstanding = flt(invoice.outstanding_amount, precision)
		if outstanding <= 0:
			frappe.throw(_("Sales Invoice {0} has nothing outstanding.").format(name))
		if amount > outstanding:
			frappe.throw(
				_(
					"{0} has {1} outstanding, less than the {2} entered. Book the excess as an advance "
					"from the Payment entry tab."
				).format(name, outstanding, amount)
			)
		frappe.get_doc(SALES_INVOICE, name).check_permission("read")
		lines.append(
			{
				"invoice": name,
				"amount": amount,
				"group": (
					invoice.customer,
					invoice.debit_to,
					tuple(invoice.get(fieldname) for fieldname in dimensions),
				),
			}
		)

	total = flt(sum(line["amount"] for line in lines), precision)
	if total > flt(transaction.unallocated_amount, precision):
		currency = {"fieldtype": "Currency", "options": transaction.currency}
		frappe.throw(
			_("The payments come to {0}, but only {1} of this deposit is unallocated.").format(
				frappe.format_value(total, currency),
				frappe.format_value(transaction.unallocated_amount, currency),
			)
		)
	return lines


def _dimension_fields() -> list[str]:
	"""The accounting dimensions' fieldnames, which a Payment Entry holds one value of each."""
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		get_accounting_dimensions,
	)

	return list(get_accounting_dimensions())


def _grouped(lines: list[dict]) -> list[list[dict]]:
	"""The lines in the order given, gathered into one list per Payment Entry."""
	groups: dict[tuple, list[dict]] = {}
	for line in lines:
		groups.setdefault(line["group"], []).append(line)
	return list(groups.values())


def _reference(typed: str | None, transaction) -> str:
	"""The entry's reference: what was typed, else the statement's own, else the line's description.

	A Payment Entry to a bank account must carry one. The line's name is the
	last resort, so that a bare statement line can still be booked.
	"""
	for value in (typed, transaction.reference_number, transaction.description, transaction.name):
		value = (value or "").strip()
		if value and not set(value) <= set("-\u2013\u2014. 0"):
			return value[:REFERENCE_LENGTH]
	return transaction.name


def _payment_entry(transaction, gl_account: str, group: list[dict], reference: str):
	"""One Payment Entry for a group of invoices of one customer, as ERPNext builds it."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import (
		allocate_open_payment_requests_to_references,
		get_payment_entry,
	)

	date = getdate(transaction.date)
	entry = None
	references = []
	for line in group:
		proposed = get_payment_entry(
			SALES_INVOICE, line["invoice"], bank_account=gl_account, reference_date=date
		)
		entry = entry or proposed
		# Term by term, as ERPNext proposes them, until the amount paid runs out.
		left = line["amount"]
		for row in proposed.references:
			take = min(flt(row.allocated_amount), left)
			if take <= 0:
				continue
			references.append(
				{**{field: row.get(field) for field in REFERENCE_FIELDS}, "allocated_amount": take}
			)
			left = flt(left - take, entry.precision("paid_amount"))

	total = flt(sum(line["amount"] for line in group), entry.precision("paid_amount"))
	entry.set("references", [])
	for row in references:
		entry.append("references", row)
	allocate_open_payment_requests_to_references(entry.references, entry.precision("paid_amount"))

	entry.posting_date = date
	entry.reference_date = date
	entry.reference_no = reference
	entry.bank_account = transaction.bank_account
	entry.paid_amount = entry.received_amount = total
	entry.set_amounts()
	return entry
