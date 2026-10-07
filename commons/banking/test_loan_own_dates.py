"""Lending vouchers on their own dates, site-less.

Each extension is put on top of a stand-in for lending's class that overwrites
the date the way lending does, so what is pinned is the order: lending's
overwrite first, the voucher's own date after it, and nothing when the setting
is off.

That the real classes do this through lending's own submit and repost was
checked against a real site inside rolled-back transactions: a
backdated repayment, write-off and disbursement, and a repost of one
loan's repayments, each on its own date with the setting on and on the day
of the test with it off.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import loan_own_dates as lod

TODAY = "2026-09-30"


class LendingRepayment:
	def __init__(self, posting_date, from_repost=False, value_date=None, new=False):
		self.posting_date = posting_date
		self.value_date = value_date
		self.flags = frappe._dict(from_repost=from_repost)
		self.new = new

	def is_new(self):
		return self.new

	def validate(self):
		self.posting_date = f"{TODAY} 16:01:30"

	def get_gl_dict(self, args, account_currency=None, item=None):
		return dict(args)


class LendingWriteOff:
	def __init__(self, value_date):
		self.value_date = value_date

	def set_missing_values(self):
		self.posting_date = TODAY


class LendingDisbursement:
	def __init__(self, disbursement_date):
		self.disbursement_date = disbursement_date

	def set_missing_values(self):
		self.posting_date = TODAY


class Repayment(lod.OwnDateLoanRepaymentMixin, LendingRepayment):
	pass


class WriteOff(lod.OwnDateLoanWriteOffMixin, LendingWriteOff):
	pass


class Disbursement(lod.OwnDateLoanDisbursementMixin, LendingDisbursement):
	pass


def setting(on):
	return patch.object(lod, "feature_enabled", return_value=on)


def called_as(cmd):
	return patch.object(lod.frappe, "form_dict", frappe._dict(cmd=cmd))


def from_the_bank_reconciliation_tool():
	# As lending's create_loan_repayment_bts makes it: entered now, valued on
	# the bank transaction's date.
	return Repayment(f"{TODAY} 16:01:29", value_date="2026-04-13 00:00:00", new=True)


class TestOn(TestCase):
	def test_a_repayment_keeps_the_date_entered(self):
		doc = Repayment("2026-04-13 00:00:00")
		with setting(True):
			doc.validate()
		self.assertEqual(str(doc.posting_date), "2026-04-13 00:00:00")

	def test_a_repayment_from_a_bank_transaction_on_its_date(self):
		doc = from_the_bank_reconciliation_tool()
		with setting(True), called_as(lod.FROM_BANK_TRANSACTION):
			doc.validate()
			doc.new = False  # and again on submit
			doc.validate()
		self.assertEqual(str(doc.posting_date), "2026-04-13 00:00:00")

	def test_a_repayment_saved_any_other_way_keeps_the_date_entered(self):
		doc = from_the_bank_reconciliation_tool()
		with setting(True), called_as("frappe.desk.form.save.savedocs"):
			doc.validate()
		self.assertEqual(str(doc.posting_date), f"{TODAY} 16:01:29")

	def test_a_reposted_repayment_books_on_its_own_date(self):
		doc = Repayment("2026-04-13 00:00:00", from_repost=True)
		with setting(True):
			gl = doc.get_gl_dict({"posting_date": TODAY, "debit": 3000})
		self.assertEqual(str(gl["posting_date"]), "2026-04-13")
		self.assertEqual(gl["debit"], 3000)

	def test_a_repayment_saved_normally_is_left_to_its_own_gl_map(self):
		doc = Repayment("2026-04-13 00:00:00")
		with setting(True):
			gl = doc.get_gl_dict({"posting_date": "2026-04-13"})
		self.assertEqual(gl["posting_date"], "2026-04-13")

	def test_a_write_off_on_its_value_date(self):
		doc = WriteOff("2026-08-01")
		with setting(True):
			doc.set_missing_values()
		self.assertEqual(str(doc.posting_date), "2026-08-01")

	def test_a_disbursement_on_its_disbursement_date(self):
		doc = Disbursement("2026-08-01")
		with setting(True):
			doc.set_missing_values()
		self.assertEqual(str(doc.posting_date), "2026-08-01")


class TestOff(TestCase):
	def test_lending_is_left_alone(self):
		repayment, write_off, disbursement = (
			Repayment("2026-04-13 00:00:00"),
			WriteOff("2026-08-01"),
			Disbursement("2026-08-01"),
		)
		reposted = Repayment("2026-04-13 00:00:00", from_repost=True)
		from_bank = from_the_bank_reconciliation_tool()
		with setting(False), called_as(lod.FROM_BANK_TRANSACTION):
			repayment.validate()
			from_bank.validate()
			write_off.set_missing_values()
			disbursement.set_missing_values()
			gl = reposted.get_gl_dict({"posting_date": TODAY})
		self.assertTrue(str(repayment.posting_date).startswith(TODAY))
		self.assertEqual(from_bank.posting_date, f"{TODAY} 16:01:30")
		self.assertEqual(write_off.posting_date, TODAY)
		self.assertEqual(disbursement.posting_date, TODAY)
		self.assertEqual(gl["posting_date"], TODAY)
