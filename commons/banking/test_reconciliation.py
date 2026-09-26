"""The reconciliation page's two navigation answers, and the refusals its one
write makes before it writes anything.

Site-less, like `education_extensions.test_attendance`. What is pinned here is
the part that fails quietly: a split of a deposit that the server accepts and
ERPNext then rejects halfway through (after the repayments were submitted), or a
loan from another company booked against this bank's statement.

What a repayment actually posts, and that the match lands, is lending's and
ERPNext's to get right. It was checked by hand against register.localhost's
data (see `reconciliation.py`), and is not restated with mocks here.
"""

import datetime
import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import reconciliation

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


class TestWhetherTheSiteKeepsStatements(TestCase):
	def present(self, *doctypes: str):
		return patch.object(
			reconciliation.apps, "has_doctype", side_effect=lambda doctype: doctype in doctypes
		)

	def test_lines_and_accounts_is_a_page(self):
		with self.present("Bank Transaction", "Bank Account"):
			self.assertTrue(reconciliation.available())

	def test_either_missing_is_not(self):
		for present in (("Bank Transaction",), ("Bank Account",), ()):
			with self.subTest(present=present), self.present(*present):
				self.assertFalse(reconciliation.available())

	def test_lending_is_not_asked_about(self):
		"""The page matches payments and journal entries without it."""
		with self.present("Bank Transaction", "Bank Account"):
			self.assertTrue(reconciliation.available())


class TestWhoReconciles(TestCase):
	def test_is_write_on_bank_transaction(self):
		with patch.object(reconciliation.frappe, "has_permission", return_value=True) as asked:
			self.assertTrue(reconciliation.can_reconcile())
		asked.assert_called_once_with("Bank Transaction", "write")

	def test_read_alone_is_not_enough(self):
		with patch.object(
			reconciliation.frappe, "has_permission", side_effect=lambda doctype, perm: perm == "read"
		):
			self.assertFalse(reconciliation.can_reconcile())


def _raise(message, *args, **kwargs):
	raise ValueError(message)


def _flt(value, precision=None):
	number = float(value or 0)
	return round(number, precision) if precision is not None else number


def line(**overrides):
	values = {
		"docstatus": 1,
		"deposit": 5000,
		"withdrawal": 0,
		"unallocated_amount": 5000,
		"company": "Open Institute (Nepal)",
		"currency": "NPR",
	}
	values.update(overrides)
	return SimpleNamespace(precision=lambda field: 2, **values)


class TestTheSplitIsCheckedFirst(TestCase):
	"""`_validated_lines`, which runs before any repayment is inserted."""

	def setUp(self):
		companies = {
			"LOAN-A": "Open Institute (Nepal)",
			"LOAN-B": "Open Institute (Nepal)",
			"LOAN-KC": "Kula",
		}
		db = SimpleNamespace(get_value=lambda doctype, name, field: companies.get(name))
		self.enterContext(patch.object(reconciliation.frappe, "db", db))
		self.enterContext(
			patch.object(
				reconciliation.frappe,
				"get_doc",
				return_value=SimpleNamespace(check_permission=lambda perm: None),
			)
		)
		self.enterContext(
			patch.object(reconciliation.frappe, "format_value", side_effect=lambda value, df: str(value))
		)
		# `frappe.throw` reaches for request-local state a site-less run does not
		# have; see `better_navigation.test_shell`, which stands it in the same way.
		self.enterContext(patch.object(reconciliation.frappe, "throw", side_effect=_raise))
		# And `flt` with a precision asks System Settings how to round; site-less
		# that fails, and `flt` swallows the failure and answers 0.
		self.enterContext(patch.object(reconciliation, "flt", side_effect=_flt))

	def refused(self, transaction, rows, says):
		with self.assertRaises(ValueError) as refusal:
			reconciliation._validated_lines(transaction, rows)
		self.assertIn(says, str(refusal.exception))

	def test_a_split_that_fits_is_accepted(self):
		self.assertEqual(
			reconciliation._validated_lines(
				line(), [{"loan": "LOAN-A", "amount": 3000}, {"loan": "LOAN-B", "amount": "2000"}]
			),
			[{"loan": "LOAN-A", "amount": 3000.0}, {"loan": "LOAN-B", "amount": 2000.0}],
		)

	def test_more_than_is_left_on_the_line_is_refused(self):
		"""ERPNext would refuse it too, but after the submits, and with a message
		that itself raises `IndexError` on this version."""
		self.refused(line(unallocated_amount=4000), [{"loan": "LOAN-A", "amount": 5000}], "only 4000")

	def test_a_withdrawal_is_refused(self):
		self.refused(line(deposit=0, withdrawal=5000), [{"loan": "LOAN-A", "amount": 5000}], "deposit")

	def test_a_draft_line_is_refused(self):
		self.refused(line(docstatus=0), [{"loan": "LOAN-A", "amount": 5000}], "submitted")

	def test_another_companys_loan_is_refused(self):
		self.refused(line(), [{"loan": "LOAN-KC", "amount": 5000}], "belongs to Kula")

	def test_a_loan_that_does_not_exist_is_refused(self):
		self.refused(line(), [{"loan": "LOAN-GONE", "amount": 5000}], "does not exist")

	def test_the_same_loan_twice_is_refused(self):
		self.refused(
			line(), [{"loan": "LOAN-A", "amount": 2000}, {"loan": "LOAN-A", "amount": 3000}], "appears twice"
		)

	def test_nothing_and_zero_are_refused(self):
		self.refused(line(), [], "at least one loan")
		self.refused(line(), [{"loan": "LOAN-A", "amount": 0}], "has no amount")
		self.refused(line(), [{"amount": 100}], "names a loan")


class TestSubmittingADraftToMatchIt(TestCase):
	"""`submit_and_reconcile` refuses before it submits anything."""

	def setUp(self):
		self.enterContext(patch.object(reconciliation.frappe, "throw", side_effect=_raise))
		self.enterContext(patch.object(reconciliation, "flt", side_effect=_flt))
		self.submitted = []
		self.fetched = []
		self.docs = {
			("Bank Transaction", "BT-OPEN"): SimpleNamespace(
				name="BT-OPEN", docstatus=1, unallocated_amount=5000, check_permission=lambda perm: None
			),
			("Bank Transaction", "BT-DONE"): SimpleNamespace(
				name="BT-DONE", docstatus=1, unallocated_amount=0, check_permission=lambda perm: None
			),
			("Payment Entry", "PE-SUBMITTED"): SimpleNamespace(
				name="PE-SUBMITTED", docstatus=1, submit=lambda: self.submitted.append("PE-SUBMITTED")
			),
		}
		self.enterContext(
			patch.object(
				reconciliation.frappe,
				"get_doc",
				side_effect=lambda doctype, name, **kwargs: self.fetched.append((doctype, kwargs))
				or self.docs[(doctype, name)],
			)
		)

	def refused(self, says, *args):
		with self.assertRaises(ValueError) as refusal:
			reconciliation.submit_and_reconcile(*args)
		self.assertIn(says, str(refusal.exception))
		self.assertEqual(self.submitted, [])

	def test_a_voucher_type_reconciliation_cannot_match_is_refused(self):
		self.refused("cannot be matched", "BT-OPEN", "Expense Claim", "HR-EXP-1")

	def test_a_fully_reconciled_line_is_refused(self):
		self.refused("already fully reconciled", "BT-DONE", "Payment Entry", "PE-SUBMITTED")

	def test_a_voucher_that_is_not_a_draft_is_refused(self):
		self.refused("is not a draft", "BT-OPEN", "Payment Entry", "PE-SUBMITTED")

	def test_the_line_is_locked_before_it_is_read(self):
		"""Two bookkeepers on one line would otherwise both pass the unallocated check."""
		self.refused("is not a draft", "BT-OPEN", "Payment Entry", "PE-SUBMITTED")
		self.assertEqual(self.fetched[0], ("Bank Transaction", {"for_update": True}))


class TestBookingRepaymentsLocksTheLine(TestCase):
	def test_the_line_is_locked_before_the_split_is_checked(self):
		fetched = []
		transaction = SimpleNamespace(check_permission=lambda perm: None)

		def get_doc(doctype, name, **kwargs):
			fetched.append((doctype, kwargs))
			return transaction

		with (
			patch.object(reconciliation.frappe, "get_doc", side_effect=get_doc),
			patch.object(reconciliation, "_validated_lines", side_effect=ValueError("checked")),
			self.assertRaises(ValueError),
		):
			reconciliation.create_loan_repayments("BT-1", [{"loan": "LOAN-A", "amount": 100}])
		self.assertEqual(fetched[0], ("Bank Transaction", {"for_update": True}))


class TestWhatAMatchMustLeaveBehind(TestCase):
	"""The checks made after writing, whose refusal rolls the request back."""

	def setUp(self):
		self.enterContext(patch.object(reconciliation.frappe, "throw", side_effect=_raise))
		self.enterContext(patch.object(reconciliation, "flt", side_effect=_flt))

	def test_a_repayment_lending_redated_is_refused(self):
		"""Server scripts off: lending dates it the day it was booked, silently."""
		transaction = SimpleNamespace(date=datetime.date(2026, 9, 1))
		booked_today = SimpleNamespace(name="LR-1", posting_date=datetime.datetime(2026, 9, 26, 10, 0))
		with self.assertRaises(ValueError) as refusal:
			reconciliation._require_statement_date(booked_today, transaction)
		self.assertIn("server scripts", str(refusal.exception))

	def test_a_repayment_on_the_statement_date_passes(self):
		transaction = SimpleNamespace(date=datetime.date(2026, 9, 1))
		kept = SimpleNamespace(name="LR-1", posting_date=datetime.datetime(2026, 9, 1, 0, 0))
		reconciliation._require_statement_date(kept, transaction)

	def test_a_submit_that_moves_a_drafts_date_is_refused(self):
		moved = SimpleNamespace(name="LR-1", posting_date=datetime.datetime(2026, 9, 26, 10, 0))
		with self.assertRaises(ValueError):
			reconciliation._require_date_kept(moved, datetime.datetime(2026, 9, 1))

	def allocations(self, *rows):
		return SimpleNamespace(
			name="BT-1",
			precision=lambda field: 2,
			payment_entries=[
				SimpleNamespace(
					payment_document="Loan Repayment", payment_entry=name, allocated_amount=amount
				)
				for name, amount in rows
			],
		)

	def test_a_repayment_matched_in_part_is_refused(self):
		"""ERPNext allocates what is left of the line without a word."""
		with self.assertRaises(ValueError) as refusal:
			reconciliation._require_fully_matched(
				self.allocations(("LR-1", 3000), ("LR-2", 400)), "Loan Repayment", {"LR-1": 3000, "LR-2": 600}
			)
		self.assertIn("LR-2", str(refusal.exception))

	def test_repayments_matched_in_full_pass(self):
		reconciliation._require_fully_matched(
			self.allocations(("LR-1", 3000), ("LR-2", 600)), "Loan Repayment", {"LR-1": 3000, "LR-2": 600}
		)

	def direction(self, net, deposit):
		transaction = SimpleNamespace(bank_account="Bank A/c", deposit=deposit)
		db = SimpleNamespace(get_value=lambda *args, **kwargs: "1100 - Bank - OI")
		with (
			patch.object(reconciliation.frappe, "db", db),
			patch.object(reconciliation, "_net_on_account", return_value=net),
		):
			reconciliation._require_same_direction(transaction, "Payment Entry", "PE-1")

	def test_money_out_matched_to_a_deposit_is_refused(self):
		with self.assertRaises(ValueError) as refusal:
			self.direction(net=-500, deposit=500)
		self.assertIn("out of", str(refusal.exception))

	def test_money_in_matched_to_a_withdrawal_is_refused(self):
		with self.assertRaises(ValueError):
			self.direction(net=500, deposit=0)

	def test_a_voucher_that_never_touches_the_account_is_refused(self):
		with self.assertRaises(ValueError) as refusal:
			self.direction(net=0, deposit=500)
		self.assertIn("does not post", str(refusal.exception))

	def test_the_same_direction_passes(self):
		self.direction(net=500, deposit=500)
		self.direction(net=-500, deposit=0)


class TestWhoMayReadTheDimensions(TestCase):
	def test_only_somebody_who_reconciles(self):
		with (
			patch.object(reconciliation, "can_reconcile", return_value=False),
			patch.object(reconciliation.frappe, "throw", side_effect=ValueError),
		):
			with self.assertRaises(ValueError):
				reconciliation.accounting_dimensions("Open Institute (Nepal)")
