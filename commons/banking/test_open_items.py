"""Open Receivables / Open Payables: which vouchers are open, and where a
ledger row counts. Site-less.

That the outstanding of every voucher agrees with ERPNext's Accounts
Receivable and Accounts Payable (run with a report date far in the future) was
checked against register.localhost on 2026-09-29: every company, both reports,
no voucher different. So was the date: at 2025-06-30 Accounts Payable found 97
payables open for Kula; this report 95, the two others having been paid since.
"""

from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import open_items as oi


def ple(voucher, against=None, amount=100.0, party="C1", on=date(2026, 1, 10), **kw):
	vtype, vno = voucher
	atype, ano = against or voucher
	return frappe._dict(
		account="Debtors",
		account_currency="NPR",
		party_type="Customer",
		party=party,
		voucher_type=vtype,
		voucher_no=vno,
		against_voucher_type=atype,
		against_voucher_no=ano,
		amount=amount,
		amount_in_account_currency=amount,
		posting_date=on,
		due_date=kw.pop("due_date", None),
		**kw,
	)


SI = ("Sales Invoice", "SI-1")
CN = ("Sales Invoice", "CN-1")
PE = ("Payment Entry", "PE-1")


def open_(rows, returns=None):
	with patch.object(oi, "dimension_fields", return_value=["cost_center"]):
		found = oi.open_vouchers(oi.balance(rows, returns or {}), 2)
	return {v.voucher_no: v for v in found}


class TestWhatIsOpen(TestCase):
	def test_a_payment_after_any_date_closes_the_invoice(self):
		rows = [ple(SI), ple(PE, SI, -100, on=date(2026, 9, 1))]
		self.assertEqual(open_(rows), {})

	def test_a_part_payment_leaves_the_rest_open(self):
		v = open_([ple(SI), ple(PE, SI, -40)])["SI-1"]
		self.assertEqual((v.amount, v.outstanding), (100, 60))

	def test_the_unallocated_part_of_a_payment_stays_with_the_payment(self):
		feb = date(2026, 2, 1)
		found = open_([ple(SI), ple(PE, SI, -100, on=feb), ple(PE, PE, -30, on=feb)])
		self.assertEqual(list(found), ["PE-1"])
		self.assertEqual((found["PE-1"].amount, found["PE-1"].outstanding), (-130, -30))
		self.assertEqual(found["PE-1"].posting_date, date(2026, 2, 1))

	def test_payment_against_a_credit_note_counts_against_its_invoice(self):
		# The credit note settles SI-1; a refund paid against the credit note
		# reopens SI-1, not the note (as Accounts Receivable does it).
		rows = [ple(SI), ple(CN, SI, -100), ple(PE, CN, 25)]
		found = open_(rows, {"CN-1": "SI-1"})
		self.assertEqual(list(found), ["SI-1"])
		self.assertEqual(found["SI-1"].outstanding, 25)

	def test_against_a_voucher_with_no_rows_of_its_own_stays_with_itself(self):
		# An advance against a Sales Order: the order has no ledger rows.
		found = open_([ple(PE, ("Sales Order", "SO-1"), -50)])
		self.assertEqual(list(found), ["PE-1"])

	def test_same_voucher_on_two_parties_is_two_vouchers(self):
		found = oi.open_vouchers(oi.balance([ple(SI, party="C1"), ple(SI, party="C2", amount=5)], {}), 2)
		self.assertEqual(sorted(v.party for v in found), ["C1", "C2"])

	def test_rounding_remainders_are_not_open(self):
		self.assertEqual(open_([ple(SI), ple(PE, SI, -99.999)]), {})


class TestDimensions(TestCase):
	def test_the_invoice_s_own_cost_center_decides_not_the_payment_s(self):
		v = open_([ple(SI, cost_center="A"), ple(PE, SI, -40, cost_center="B")])["SI-1"]
		self.assertTrue(oi.matches_dimensions(v, {"cost_center": {"A"}}))
		self.assertFalse(oi.matches_dimensions(v, {"cost_center": {"B"}}))

	def test_every_filtered_dimension_has_to_match(self):
		v = frappe._dict(dimensions={"cost_center": {"A"}, "project": {"P"}})
		self.assertTrue(oi.matches_dimensions(v, {}))
		self.assertTrue(oi.matches_dimensions(v, {"cost_center": {"A", "Z"}, "project": {"P"}}))
		self.assertFalse(oi.matches_dimensions(v, {"cost_center": {"A"}, "project": {"Q"}}))


class TestTree(TestCase):
	def vouchers(self):
		found = open_(
			[
				ple(SI, party="C2", due_date=date(2026, 1, 20)),
				ple(("Sales Invoice", "SI-2"), party="C1", amount=50, on=date(2026, 3, 1)),
				ple(PE, PE, -30, party="C1"),
			]
		)
		for v in found.values():
			v.party_name, v.reference, v.cost_center = v.party, None, ""
		return list(found.values())

	def test_account_then_party_then_voucher_with_totals(self):
		data = oi.tree(self.vouchers(), date(2026, 2, 1), False)
		self.assertEqual(
			[(r.indent, r.label) for r in data],
			[(0, "Debtors"), (1, "C1"), (2, "PE-1"), (2, "SI-2"), (1, "C2"), (2, "SI-1"), (0, "Total")],
		)
		account, c1 = data[0], data[1]
		self.assertEqual((account.outstanding, account.vouchers, account.parties), (120, 3, 2))
		self.assertEqual(c1.outstanding, 20)
		# Only SI-1 is past due on 2026-02-01; the payment is never overdue.
		self.assertEqual(account.overdue, 100)
		self.assertEqual(data[5].days_overdue, 12)

	def test_party_at_the_top_puts_its_accounts_under_it(self):
		vouchers = self.vouchers()
		next(v for v in vouchers if v.voucher_no == "SI-1").account = "Other Debtors"
		data = oi.tree(vouchers, date(2026, 2, 1), False, "Party")
		self.assertEqual(
			[(r.indent, r.row_type, r.label) for r in data],
			[
				(0, "party", "C1"),
				(1, "account", "Debtors"),
				(2, "voucher", "PE-1"),
				(2, "voucher", "SI-2"),
				(0, "party", "C2"),
				(1, "account", "Other Debtors"),
				(2, "voucher", "SI-1"),
				(0, "total", "Total"),
			],
		)
		self.assertEqual((data[0].accounts, data[0].outstanding), (1, 20))
		self.assertNotIn("parties", data[1])
