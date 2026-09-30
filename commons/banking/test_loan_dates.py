"""The loan date audit's judgements, site-less.

What is pinned here is what would mislead quietly if it drifted: which dates
count as wrong, that the repost safeguard is recognised by what it does, and
that the repair refuses a repayment lending would book on the wrong day again.

That the whole thing finds and repairs real damage was checked against
register.localhost inside a rolled-back transaction: LM-REP-0118, 0124 and 0140
found, re-booked on 2026-05-05, 2026-06-12 and 2026-04-13, none left.
"""

from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import loan_dates as ld


def doc(value="2026-04-13", posting="2026-04-13 00:00:00"):
	return frappe._dict(date=value, posting_date=posting)


class TestWhichIssue(TestCase):
	def test_gl_on_the_voucher_date_is_fine(self):
		self.assertEqual(ld.issues_for("Loan Repayment", doc(), {date(2026, 4, 13): 3000}, None), [])

	def test_gl_on_another_day_is_named(self):
		found = ld.issues_for("Loan Repayment", doc(), {date(2026, 9, 27): 3000}, None)
		self.assertEqual(found, [(ld.GL_DATE, "2026-09-27")])

	def test_a_repayment_whose_posting_date_drifted(self):
		found = ld.issues_for(
			"Loan Repayment", doc(posting="2026-09-27 16:01:30"), {date(2026, 4, 13): 3000}, None
		)
		self.assertEqual(found, [(ld.DOC_DATE, "2026-09-27")])

	def test_write_offs_are_not_held_to_their_posting_date(self):
		# Lending always sets a write-off's posting date to the save day; only the GL matters.
		found = ld.issues_for("Loan Write Off", doc(posting="2026-09-27"), {date(2026, 4, 13): 10}, None)
		self.assertEqual(found, [])

	def test_gfl_income_on_another_day(self):
		found = ld.issues_for(
			"Loan Repayment", doc(), {date(2026, 4, 13): 3000}, ("ACC-JV-1", date(2026, 9, 27))
		)
		self.assertEqual(found, [(ld.GFL_DATE, "ACC-JV-1 on 2026-09-27")])


class TestRepostSafeguard(TestCase):
	def test_recognised_by_what_it_calls(self):
		self.assertTrue(ld.rebooks("x.make_gl_entries( cancel=1 )\nx.make_gl_entries()"))

	def test_a_script_that_only_cancels_is_not_enough(self):
		self.assertFalse(ld.rebooks("x.make_gl_entries(cancel=1)"))
		self.assertFalse(ld.rebooks(None))


class TestRepairRefuses(TestCase):
	def plan(self, posting):
		row = frappe._dict(name="LM-REP-1", docstatus=1, date="2026-04-13", posting_date=posting, company="C")
		gl = [frappe._dict(posting_date="2026-09-27", account="Bank", debit=3000, credit=0)]
		with (
			patch.object(ld.frappe, "db", SimpleNamespace(get_value=lambda *a, **k: row)),
			patch.object(ld.frappe, "get_all", return_value=gl),
		):
			return ld._plan("LM-REP-1")

	def test_a_repayment_on_its_own_posting_date_is_re_booked(self):
		plan = self.plan("2026-04-13 00:00:00")
		self.assertTrue(plan.needed)
		self.assertIsNone(plan.refused)

	def test_a_drifted_posting_date_is_refused(self):
		plan = self.plan("2026-09-27 16:01:30")
		self.assertTrue(plan.needed)
		self.assertIn("needs a person", plan.refused)
