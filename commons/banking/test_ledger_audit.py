"""The payment ledger audit's judgements, site-less.

What is pinned here is what would do damage quietly if it drifted: which issue a
discrepancy is filed under, that a repair leaves rows that are already right
alone, and that a repair refuses when the rebuilt rows would not add up to the
GL (the case where writing anything would be a guess).

That the whole thing finds and repairs real damage was checked against
a real site inside a rolled-back transaction: 31 discrepancies across
two companies, all 26 vouchers repaired, none left, the ledger unchanged after
the rollback (see `ledger_audit.py` for what they were).
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import ledger_audit as la


def ple(account="Creditors", party="S1", against="PINV-1", amount=-100.0, name=None, **kw):
	return frappe._dict(
		name=name,
		voucher_type="Journal Entry",
		voucher_no="JV-1",
		account=account,
		party_type="Supplier",
		party=party,
		against_voucher_type="Purchase Invoice",
		against_voucher_no=against,
		amount=amount,
		**kw,
	)


class TestWhichIssue(TestCase):
	def test_live_rows_on_a_cancelled_voucher_come_first(self):
		# Even on an account that is no longer payable: the cancel is the story.
		self.assertEqual(la._issue(2, False, 0, 750), la.CANCELLED)

	def test_an_account_that_is_no_longer_payable(self):
		self.assertEqual(la._issue(1, False, 0, 750), la.NOT_RP)

	def test_missing_extra_and_differing(self):
		self.assertEqual(la._issue(1, True, -4500, 0), la.MISSING)
		self.assertEqual(la._issue(1, True, 0, -35), la.EXTRA)
		self.assertEqual(la._issue(1, True, -6743.48, -6440.22), la.DIFFERS)


class TestOnlyWhatDiffersIsTouched(TestCase):
	def test_identical_rows_are_left_alone(self):
		live = [ple(name="a", against="PINV-1"), ple(name="b", against="PINV-2")]
		rebuilt = [ple(against="PINV-2"), ple(against="PINV-1"), ple(against="JV-1", amount=-303.26)]
		delink, add = la._differing(live, rebuilt)
		self.assertEqual(delink, [])
		self.assertEqual([r.against_voucher_no for r in add], ["JV-1"])

	def test_a_changed_amount_is_replaced(self):
		delink, add = la._differing([ple(name="a", amount=-100)], [ple(amount=-90)])
		self.assertEqual([r.name for r in delink], ["a"])
		self.assertEqual([r.amount for r in add], [-90])

	def test_duplicates_are_matched_one_for_one(self):
		# Two identical live rows and one rebuilt: one of them has to go.
		delink, add = la._differing([ple(name="a"), ple(name="b")], [ple()])
		self.assertEqual(len(delink), 1)
		self.assertEqual(add, [])


class TestThePlan(TestCase):
	def plan(self, status, live, rebuilt, gl_amount):
		issue = frappe._dict(
			voucher_type="Journal Entry",
			voucher_no="JV-1",
			account="Creditors",
			party_type="Supplier",
			party="S1",
			gl_amount=gl_amount,
			voucher_status=status,
		)
		with (
			patch.object(la.frappe, "db", SimpleNamespace(get_value=lambda *a, **k: "Co")),
			patch.object(la.frappe, "format", side_effect=lambda v, *a: str(v)),
			patch.object(la, "_", side_effect=lambda text, *a, **k: text),
			patch.object(la, "find_discrepancies", return_value=[issue]),
			patch.object(la.frappe, "get_all", return_value=live),
			patch.object(la.frappe, "get_doc", return_value=object()),
			patch.object(la, "_rebuilt_entries", return_value=rebuilt),
		):
			return la._plan("Journal Entry", "JV-1")

	def test_a_cancelled_voucher_is_only_delinked(self):
		plan = self.plan("Cancelled", [ple(name="a", amount=750)], [ple(amount=1)], 0)
		self.assertEqual([r.name for r in plan.delink], ["a"])
		self.assertEqual(plan.add, [])
		self.assertIsNone(plan.refused)

	def test_a_rebuild_that_matches_the_gl_goes_ahead(self):
		plan = self.plan("Submitted", [], [ple(amount=-60), ple(against="PINV-2", amount=-40)], -100)
		self.assertIsNone(plan.refused)
		self.assertEqual(len(plan.add), 2)

	def test_a_rebuild_that_does_not_match_the_gl_is_refused(self):
		plan = self.plan("Submitted", [], [ple(amount=-60)], -100)
		self.assertIsNotNone(plan.refused)

	def test_a_doctype_with_no_rebuild_is_refused(self):
		plan = self.plan("Submitted", [], None, -100)
		self.assertIsNotNone(plan.refused)
