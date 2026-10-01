"""Lending vouchers booked on their own dates, not on the day they are saved.

Lending overwrites the posting date of three vouchers with the day they are
saved, and dates their GL from it. A payment, write-off or disbursement entered
after the fact then sits in the books on the wrong day, and the bank balance
on the day it happened is off by its amount.

- Loan Repayment: `validate` sets `posting_date` to now. The posting date as
  entered is put back afterwards, as a pair of site server scripts would.
- Loan Repayment, reposted: a backdated repayment makes lending repost every
  repayment after it, and `get_gl_map` dates their GL
  `getdate() if self.flags.from_repost`. `get_gl_dict` is given the
  repayment's own date instead, before ERPNext picks the fiscal year from it.
  A site script re-booking them after the repost would fix them afterwards;
  this books them right the first time.
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

from frappe.utils import get_datetime, getdate

from commons.commons_core.settings import ENABLE_LOAN_OWN_DATES, feature_enabled


class OwnDateLoanRepaymentMixin:
	def validate(self):
		entered = self.posting_date
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
