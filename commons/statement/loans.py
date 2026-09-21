"""What is owed on loans, kept apart from everything else that is owed.

Separate because the accounting says so, not because it reads better. `lending`
posts its GL entries with the borrower as the party whenever the account is a
receivable or a payable one -- see `Loan.add_opening_gl_entry` and
`LoanDisbursement.make_gl_entries` -- so a loan's principal sits in the very
same table as the fees and the invoices. Anything that merely filtered
`GL Entry` on the party would add the two together and show a disbursement as
though the borrower had been invoiced for the money they were lent.

So this module does two jobs, and the first is the one that is easy to miss:

* `ledger_accounts` names the accounts the statement must leave out, so the
  balance on the other page is trade only.
* `balances` answers for those accounts itself, from the Loan documents, where
  a loan's own arithmetic lives.

The number, and what it is not
------------------------------

What is reported is **outstanding principal** -- `lending`'s own
`get_pending_principal_amount`, imported rather than restated so that the
figure on this page is the figure the lender's own forms compute. It is what
is still borrowed. It is deliberately not a settlement quote: interest accrued
since the last demand, penalties and charges are `calculate_amounts`, which is
several queries, may write as it goes, and opens with a `Loan` read permission
check that every borrower reading their own statement would fail. A page that
promised a payoff figure and delivered a principal balance would be worse than
one that says which it is, so the page says.

Absent entirely on a site without `lending`, which is most of them. The section
above works exactly as well without this one; it simply has no second balance
to draw.
"""

import frappe
from frappe.utils import flt

from commons.commons_core import apps
from commons.statement import company_currency
from commons.statement.parties import Party, party_condition

LOAN = "Loan"
LOAN_PRODUCT = "Loan Product"

# A loan that is closed is not a balance. `get_total_loan_amount` draws the
# same line for the same reason -- there is nothing left to owe -- and a
# borrower who wants the history of a settled loan is asking for a statement of
# it rather than for a balance.
CLOSED = "Closed"

# What a loan row carries. The first block is what the page draws; the second is
# exactly what `get_pending_principal_amount` reads, listed here because passing
# it a row with a field missing gets an answer rather than an error.
LOAN_FIELDS = (
	"name",
	"applicant_type",
	"applicant",
	"company",
	"loan_product",
	"status",
	"posting_date",
	"disbursement_date",
	"rate_of_interest",
	"loan_amount",
	"total_amount_paid",
	"repayment_schedule_type",
	"total_payment",
	"disbursed_amount",
	"debit_adjustment_amount",
	"credit_adjustment_amount",
	"total_principal_paid",
	"total_interest_payable",
	"written_off_amount",
)


def available() -> bool:
	"""Whether this site lends at all."""
	return apps.has_doctype(LOAN)


def ledger_accounts(parties: list[Party]) -> set[str]:
	"""Every account the lending module posts through, for the ledger to skip.

	Read off the meta rather than listed. `Loan Product` names twenty-five
	accounts and has gained several over the versions this app has run against;
	a list here would be a list to keep in step, and the one that fell behind
	would not fail -- it would quietly put a loan account back into somebody's
	trade balance, which is the exact bug this function exists to prevent. So
	the fields are whatever the doctype says are links to an `Account`, and a
	version that adds a twenty-sixth is covered the day it lands.

	Products are read whole because there are a handful of them and their
	accounts are the site's, whoever borrowed. Loans are read for these parties
	only: a loan names its own accounts, and the only ones that can turn up in
	*this* reader's ledger are the ones on *their* loans.
	"""
	if not available():
		return set()

	accounts = _accounts_named_by(LOAN_PRODUCT, filters=None)
	condition = party_condition(frappe.qb.DocType(LOAN), "applicant_type", "applicant", parties)
	if condition is not None:
		accounts |= _accounts_named_by(LOAN, filters=condition)
	return accounts


def _accounts_named_by(doctype: str, filters) -> set[str]:
	"""The distinct accounts named by every row of `doctype` this filter selects."""
	fields = [
		field.fieldname
		for field in frappe.get_meta(doctype).get_link_fields()
		if field.options == "Account"
	]
	if not fields:
		return set()

	table = frappe.qb.DocType(doctype)
	query = frappe.qb.from_(table).select(*[table[field] for field in fields])
	if filters is not None:
		query = query.where(filters)
	return {value for row in query.run() for value in row if value}


def balances(parties: list[Party]) -> list[dict]:
	"""Every loan these parties still owe on, oldest first.

	Submitted only -- a draft loan is a proposal -- and not the closed ones.

	A raw read, for the reason the package docstring gives: the rows are the
	caller's own, and `Loan` read is a lender's permission that no borrower has.
	Only the loan's own figures come back; the repayment schedule, the security
	behind it and every other party's loans do not.
	"""
	if not available() or not parties:
		return []

	table = frappe.qb.DocType(LOAN)
	condition = party_condition(table, "applicant_type", "applicant", parties)
	# One condition rather than a list of them: a `filters` list holding a
	# Criterion beside a plain `[field, op, value]` row is parsed by a branch
	# that also has to recognise nested `[cond, "or", cond]` lists, and which of
	# the two it decides a list is depends on what the first element happens to
	# be. Handing it a single Criterion leaves nothing to decide.
	rows = frappe.get_all(
		LOAN,
		filters=condition & (table.docstatus == 1) & (table.status != CLOSED),
		fields=list(LOAN_FIELDS),
		order_by="posting_date asc, name asc",
	)
	return [_loan(row) for row in rows]


def _loan(row: frappe._dict) -> dict:
	"""One loan, as the page draws it.

	`outstanding` is `lending`'s own arithmetic over the row this read already
	has -- the import is deferred because the app is optional, and the module
	behind it is large enough that a site which never lends should not pay for
	loading it.
	"""
	from lending.loan_management.doctype.loan_repayment.loan_repayment import (
		get_pending_principal_amount,
	)

	return {
		"loan": row.name,
		"party_type": row.applicant_type,
		"party": row.applicant,
		"company": row.company,
		"currency": company_currency(row.company),
		"product": row.loan_product,
		"status": row.status,
		"posting_date": row.posting_date,
		"disbursement_date": row.disbursement_date,
		"rate_of_interest": flt(row.rate_of_interest),
		# What was sanctioned, and what has actually been handed over. The two
		# differ for as long as a loan is partially disbursed, and a borrower
		# reading a balance smaller than the loan they signed for wants to see
		# which of the two it is measured against.
		"sanctioned": flt(row.loan_amount),
		"disbursed": flt(row.disbursed_amount),
		"repaid": flt(row.total_amount_paid),
		"written_off": flt(row.written_off_amount),
		"outstanding": flt(get_pending_principal_amount(row)),
	}
