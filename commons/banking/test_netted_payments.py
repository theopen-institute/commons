"""Which journal entry lines the netted-refund check flags, site-less.

Pinned: a refund line sitting with a charge to the same party is flagged; a
plain payment is not (it is a real unallocated payment); a line already
referenced to its own entry is not offered, so not flagged; and an entry that
pays out more than it charges is flagged but refused, because marking it would
hide a real payment.

Against a real site, in a rolled-back transaction, every flagged line
was on Payment Reconciliation's payment side, the fix removed exactly those,
and the invoice side, the GL and the payment ledger did not change.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import netted_payments as npay


def line(idx, paying, voucher="JV-1", reference_type="", party="E1"):
	return frappe._dict(
		voucher_no=voucher,
		posting_date="2024-07-30",
		row_name=f"{voucher}-{idx}",
		idx=idx,
		account="TDS Payable",
		party_type="Employee",
		party=party,
		paying=paying,
		reference_type=reference_type,
	)


class TestWhatIsFlagged(TestCase):
	def find(self, lines):
		with patch.object(npay, "_lines", return_value=lines):
			return npay.find_netted_payments({"company": "Co"})

	def test_a_refund_beside_a_charge(self):
		(found,) = self.find([line(1, -750), line(2, 75)])
		self.assertEqual((found.charged, found.offered, found.rows), (750, 75, "2"))
		self.assertEqual(found.issue, npay.NETTED)

	def test_an_entry_that_nets_to_nothing(self):
		(found,) = self.find([line(1, 3000), line(2, -3000)])
		self.assertEqual(found.issue, npay.NETTED)

	def test_a_plain_payment_is_left_alone(self):
		self.assertEqual(self.find([line(1, 4500)]), [])

	def test_a_line_already_referenced_to_its_entry_is_not_offered(self):
		self.assertEqual(self.find([line(1, -5000), line(2, 500, reference_type="Journal Entry")]), [])

	def test_paying_out_more_than_charged_is_refused(self):
		(found,) = self.find([line(1, -100), line(2, 300)])
		self.assertEqual(found.issue, npay.EXCESS)

	def test_parties_are_kept_apart(self):
		self.assertEqual(self.find([line(1, -750, party="E1"), line(2, 75, party="E2")]), [])

	def test_other_voucher_types_are_not_asked(self):
		with patch.object(npay, "_lines") as lines:
			self.assertEqual(
				npay.find_netted_payments({"company": "Co", "voucher_type": "Payment Entry"}), []
			)
		lines.assert_not_called()
