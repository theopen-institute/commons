"""Lending vouchers booked on their own dates, not on the day they are saved.

Lending overwrites the posting date of three vouchers with the day they are
saved, and dates their GL from it. A payment, write-off or disbursement entered
after the fact then sits in the books on the wrong day, and the bank balance
on the day it happened is off by its amount.

- Loan Repayment: `validate` sets `posting_date` to now. The posting date as
  entered is put back afterwards.
- Loan Repayment, from the desk Bank Reconciliation Tool: lending's
  `create_loan_repayment_bts` enters `posting_date` as now and the bank
  transaction's date (or the date picked in its dialog) as `value_date`, and
  leaves nothing on the repayment that names the transaction. A new repayment
  saved by that call is put on its value date. Edit in Full Page hands the
  form back unsaved, so there the posting date is whatever is entered on it.
- Loan Repayment, reposted: a backdated repayment makes lending repost every
  repayment after it, and `get_gl_map` dates their GL
  `getdate() if self.flags.from_repost`. `get_gl_dict` is given the
  repayment's own date instead, before ERPNext picks the fiscal year from it,
  so they are booked right the first time.
- Loan Write Off: `set_missing_values` sets `posting_date` to today. It is set
  to the value date.
- Loan Disbursement: `set_missing_values` sets `posting_date` to today. It is
  set to the disbursement date. Lending also starts a monthly schedule's first
  repayment from `posting_date` when none is given, so with this on, that
  counts from the disbursement date as well. Charges invoiced on disbursement
  stay dated the day they are made.

Only the GL date moves. What lending calls the value date, which drives
interest and demands, is left as it was. Vouchers already booked are not
touched: the Loan Date Audit lists them, and re-books repayments.
"""

import frappe
from frappe.utils import get_datetime, getdate

from commons.commons_core.settings import ENABLE_LOAN_OWN_DATES, feature_enabled

# Lending's whitelisted method behind the desk Bank Reconciliation Tool's
# "Loan Repayment" voucher. /commons/banking makes its own repayments, already
# entered on the transaction's date, and does not come through here.
FROM_BANK_TRANSACTION = (
	"lending.loan_management.doctype.loan_repayment.loan_repayment.create_loan_repayment_bts"
)


def from_bank_transaction(doc):
	return doc.is_new() and frappe.form_dict.get("cmd") == FROM_BANK_TRANSACTION


class OwnDateLoanRepaymentMixin:
	def validate(self):
		entered = self.posting_date
		if self.value_date and from_bank_transaction(self):
			entered = self.value_date
		super().validate()
		if entered and feature_enabled(ENABLE_LOAN_OWN_DATES):
			self.posting_date = get_datetime(entered)

	def get_gl_dict(self, args, account_currency=None, item=None):
		if self.flags.from_repost and feature_enabled(ENABLE_LOAN_OWN_DATES):
			args = {**args, "posting_date": getdate(self.posting_date)}
		return super().get_gl_dict(args, account_currency, item)


class OwnDateLoanWriteOffMixin:
	def set_missing_values(self):
		super().set_missing_values()
		if self.value_date and feature_enabled(ENABLE_LOAN_OWN_DATES):
			self.posting_date = getdate(self.value_date)


class OwnDateLoanDisbursementMixin:
	def set_missing_values(self):
		super().set_missing_values()
		if self.disbursement_date and feature_enabled(ENABLE_LOAN_OWN_DATES):
			self.posting_date = getdate(self.disbursement_date)


# Which class extends which doctype, for the Loan Date Audit to check.
MIXINS = {
	"Loan Repayment": OwnDateLoanRepaymentMixin,
	"Loan Write Off": OwnDateLoanWriteOffMixin,
	"Loan Disbursement": OwnDateLoanDisbursementMixin,
}
