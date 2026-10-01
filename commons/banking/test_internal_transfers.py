"""Which journal entries count as moving no money at the bank, site-less.

What is pinned here is what would do damage quietly if it drifted: an entry is
only cleared when every bank and cash account on it nets to nothing, an entry
that also pays out of another bank account is not, an entry with no bank line
at all is not, and one already cleared keeps its date.

The backfill was checked against a real site inside a rolled-back
transaction.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import internal_transfers as it

ACCOUNT_TYPES = {"Bank": "Bank", "Cash": "Cash", "Prime": "Bank", "Salary": None, "Income": None}


def line(account, debit=0, credit=0):
	return frappe._dict(account=account, debit_in_account_currency=debit, credit_in_account_currency=credit)


def account_type(doctype, name, field):
	return ACCOUNT_TYPES.get(name)


# Two departments' shares of one bank account, and the
# internal charge between them.
DEPARTMENT_MOVE = [
	line("Bank", credit=20000),
	line("Bank", debit=20000),
	line("Salary", debit=20000),
	line("Income", credit=20000),
]


@patch.object(it.frappe, "get_cached_value", side_effect=account_type)
class TestMovesNoMoney(TestCase):
	def test_a_move_between_departments_on_one_account(self, _):
		self.assertTrue(it.moves_no_money(DEPARTMENT_MOVE))

	def test_a_payment_out_of_the_bank(self, _):
		self.assertFalse(it.moves_no_money([line("Bank", credit=500), line("Salary", debit=500)]))

	def test_a_transfer_between_two_bank_accounts_moves_money(self, _):
		self.assertFalse(it.moves_no_money([line("Bank", credit=500), line("Prime", debit=500)]))

	def test_one_account_nets_to_nothing_but_another_does_not(self, _):
		lines = [*DEPARTMENT_MOVE, line("Prime", credit=100), line("Salary", debit=100)]
		self.assertFalse(it.moves_no_money(lines))

	def test_every_account_netting_to_nothing(self, _):
		lines = [*DEPARTMENT_MOVE, line("Cash", debit=5), line("Cash", credit=5)]
		self.assertTrue(it.moves_no_money(lines))

	def test_an_entry_with_no_bank_line(self, _):
		self.assertFalse(it.moves_no_money([line("Salary", debit=1), line("Income", credit=1)]))

	def test_rounding_below_a_paisa_nets_to_nothing(self, _):
		self.assertTrue(it.moves_no_money([line("Bank", debit=100.001), line("Bank", credit=100)]))
		self.assertFalse(it.moves_no_money([line("Bank", debit=100.01), line("Bank", credit=100)]))


class FakeEntry(frappe._dict):
	def db_set(self, field, value):
		self[field] = value


@patch.object(it.frappe, "get_cached_value", side_effect=account_type)
class TestClearOnSubmit(TestCase):
	def entry(self, **kw):
		return FakeEntry(accounts=DEPARTMENT_MOVE, posting_date="2025-09-30", clearance_date=None, **kw)

	def test_cleared_on_its_posting_date(self, _):
		doc = self.entry()
		with patch.object(it, "feature_enabled", return_value=True):
			it.clear_on_submit(doc)
		self.assertEqual(doc.clearance_date, "2025-09-30")

	def test_left_alone_with_the_setting_off(self, _):
		doc = self.entry()
		with patch.object(it, "feature_enabled", return_value=False):
			it.clear_on_submit(doc)
		self.assertIsNone(doc.clearance_date)

	def test_an_entry_already_cleared_keeps_its_date(self, _):
		doc = self.entry()
		doc.clearance_date = "2025-10-15"
		with patch.object(it, "feature_enabled", return_value=True):
			it.clear_on_submit(doc)
		self.assertEqual(doc.clearance_date, "2025-10-15")
