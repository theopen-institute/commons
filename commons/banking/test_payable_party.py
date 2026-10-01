"""Which payment lines get the payment's party, site-less.

What is pinned here is what would do damage quietly if it drifted: only
party-less lines on Payable accounts are touched, a line that already names a
party keeps it, and with the setting off the ledger lines are ERPNext's own.

That it fixes the cancel was checked against a real site inside a
rolled-back transaction: a payment with a TDS deduction, submitted and
cancelled with the site's own server scripts for this disabled,
left no live payment ledger rows, and the ledger preview named the supplier
on the TDS line.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import payable_party as pp

ACCOUNT_TYPES = {"Creditors": "Payable", "TDS": "Payable", "Bank": "Bank", "Travel": None}


def line(account, party_type=None, party=None):
	return frappe._dict(account=account, party_type=party_type, party=party, debit=1)


def account_type(doctype, name, field):
	return ACCOUNT_TYPES.get(name)


@patch.object(pp.frappe, "get_cached_value", side_effect=account_type)
class TestFillPayableParty(TestCase):
	def test_party_less_payable_lines_get_the_payment_party(self, _):
		entries = [line("TDS"), line("Bank"), line("Travel")]
		pp.fill_payable_party(entries, "Supplier", "S1")
		self.assertEqual((entries[0].party_type, entries[0].party), ("Supplier", "S1"))
		self.assertIsNone(entries[1].party)
		self.assertIsNone(entries[2].party)

	def test_a_line_that_names_a_party_keeps_it(self, _):
		entries = [line("Creditors", "Employee", "E1")]
		pp.fill_payable_party(entries, "Supplier", "S1")
		self.assertEqual((entries[0].party_type, entries[0].party), ("Employee", "E1"))

	def test_a_payment_without_a_party_changes_nothing(self, _):
		entries = [line("TDS")]
		pp.fill_payable_party(entries, None, None)
		self.assertIsNone(entries[0].party)


class Base:
	party_type = "Supplier"
	party = "S1"

	def build_gl_map(self):
		return [line("TDS"), line("Bank")]


class Payment(pp.PayablePartyPaymentEntryMixin, Base):
	pass


@patch.object(pp.frappe, "get_cached_value", side_effect=account_type)
class TestBehindTheSetting(TestCase):
	def test_off_leaves_erpnexts_lines_alone(self, _):
		with patch.object(pp, "feature_enabled", return_value=False):
			self.assertIsNone(Payment().build_gl_map()[0].party)

	def test_on_fills_the_party(self, _):
		with patch.object(pp, "feature_enabled", return_value=True) as enabled:
			self.assertEqual(Payment().build_gl_map()[0].party, "S1")
		enabled.assert_called_with(pp.ENABLE_PAYABLE_PARTY)
