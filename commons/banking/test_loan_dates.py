"""The loan date audit's judgements, site-less.

What is pinned here is what would mislead quietly if it drifted: which dates
count as wrong, that the safeguards are the app's setting and nothing else,
who may repair, and that the repair refuses a repayment lending would book on
the wrong day again.

That the whole thing finds and repairs real damage was checked against a site
inside a rolled-back transaction: three repayments moved by one repost were
found, re-booked on their own dates, and none left.
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
		self.assertEqual(ld.issues_for("Loan Repayment", doc(), {date(2026, 4, 13): 3000}), [])

	def test_gl_on_another_day_is_named(self):
		found = ld.issues_for("Loan Repayment", doc(), {date(2026, 9, 27): 3000})
		self.assertEqual(found, [(ld.GL_DATE, "2026-09-27")])

	def test_a_repayment_whose_posting_date_drifted(self):
		found = ld.issues_for("Loan Repayment", doc(posting="2026-09-27 16:01:30"), {date(2026, 4, 13): 3000})
		self.assertEqual(found, [(ld.DOC_DATE, "2026-09-27")])

	def test_write_offs_are_not_held_to_their_posting_date(self):
		# Lending always sets a write-off's posting date to the save day; only the GL matters.
		found = ld.issues_for("Loan Write Off", doc(posting="2026-09-27"), {date(2026, 4, 13): 10})
		self.assertEqual(found, [])


class TestSafeguards(TestCase):
	"""The app's setting is the only safeguard looked for."""

	def safeguards(self, on, extended=True):
		with (
			patch("commons.commons_core.settings.feature_enabled", return_value=on),
			patch.object(ld.apps, "has_doctype", return_value=True),
			patch.object(ld, "_extended", return_value=extended),
			patch.object(ld.frappe, "get_all", side_effect=AssertionError("no server script probe")),
		):
			return ld.safeguards()

	def test_setting_on_and_classes_extended(self):
		rows = self.safeguards(on=True)
		self.assertEqual(len(rows), 4)
		self.assertEqual({r.status for r in rows}, {ld.OK})

	def test_setting_on_but_a_class_not_extended(self):
		rows = self.safeguards(on=True, extended=False)
		self.assertEqual({r.status for r in rows}, {ld.MISSING})
		self.assertIn("Restart the bench", rows[0].detail)

	def test_setting_off_is_missing_everywhere(self):
		rows = self.safeguards(on=False)
		self.assertEqual({r.status for r in rows}, {ld.MISSING})
		self.assertTrue(all("Enable Loan Vouchers on Their Own Dates" in r.detail for r in rows))


def _raise(msg, exc=frappe.ValidationError, *a, **k):
	raise exc(msg)


class TestWhoMayRepair(TestCase):
	def test_needs_write_on_period_closing_voucher(self):
		with (
			patch.object(ld.frappe, "has_permission", return_value=False) as asked,
			patch.object(ld.frappe, "throw", side_effect=_raise),
		):
			with self.assertRaises(frappe.PermissionError):
				ld.repair_repayment("LOAN-REP-1")
		asked.assert_called_with("Period Closing Voucher", "write")

	def test_permitted_reaches_the_repair(self):
		with (
			patch.object(ld.frappe, "has_permission", return_value=True),
			patch.object(ld, "_repair", return_value={"status": "ok"}),
		):
			self.assertEqual(ld.repair_repayment("LOAN-REP-1"), {"status": "ok"})


class TestRepairRefuses(TestCase):
	def plan(self, posting):
		row = frappe._dict(
			name="LOAN-REP-1", docstatus=1, date="2026-04-13", posting_date=posting, company="C"
		)
		gl = [frappe._dict(posting_date="2026-09-27", account="Bank", debit=3000, credit=0)]
		with (
			patch.object(ld.frappe, "db", SimpleNamespace(get_value=lambda *a, **k: row)),
			patch.object(ld.frappe, "get_all", return_value=gl),
		):
			return ld._plan("LOAN-REP-1")

	def test_a_repayment_on_its_own_posting_date_is_re_booked(self):
		plan = self.plan("2026-04-13 00:00:00")
		self.assertTrue(plan.needed)
		self.assertIsNone(plan.refused)

	def test_a_drifted_posting_date_is_refused(self):
		plan = self.plan("2026-09-27 16:01:30")
		self.assertTrue(plan.needed)
		self.assertIn("needs a person", plan.refused)
