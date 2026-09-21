"""What the statement has to get right, and what would fail quietly if it did not.

Site-less, like `shell.test_shell` and `self_service.test_self_service_api`: what
stands between this section and a database is `frappe.get_all` and a query
builder, so the parts pinned here are the ones that are arithmetic and wording
rather than SQL. That is not a compromise. Every bug this section can have that
a reader would not immediately see is in this file's subject matter:

* a balance that reads the wrong way round for a payable party, which looks
  exactly like a balance that reads the right way round;
* a running balance that is right on screen and wrong against the total,
  because the two were computed separately;
* two currencies added together, or a loan balance netted off an invoice
  balance, either of which produces a number rather than an error;
* a dynamic link matched as two lists instead of as a pair, which shows one
  person another person's ledger only when their ids happen to collide.
"""

import logging
from unittest import TestCase
from unittest.mock import patch

from pypika import Table

from commons.statement import api, ledger
from commons.statement.parties import Party, party_condition

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. See `shell.test_shell`.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


def party(account_type="Receivable", party_type="Customer", name="CUST-0001"):
	return Party(party_type=party_type, name=name, title="A Person", account_type=account_type)


def entry(debit=0.0, credit=0.0, **extra):
	"""One `GL Entry` as the read hands it over."""
	import frappe

	return frappe._dict(
		{
			"name": extra.get("name", "GL-0001"),
			"posting_date": extra.get("posting_date", "2026-01-01"),
			"account": extra.get("account", "Debtors - X"),
			"voucher_type": extra.get("voucher_type", "Sales Invoice"),
			"voucher_no": extra.get("voucher_no", "SINV-0001"),
			"remarks": extra.get("remarks"),
			"is_opening": extra.get("is_opening", "No"),
			"debit": debit,
			"credit": credit,
		}
	)


class TestWhichWayRoundABalanceReads(TestCase):
	"""The sign rule, which is the one thing on this page nobody can check by eye.

	A receivable party owes the organisation; a payable party is owed by it.
	Both read as "what is outstanding on your account", so the same positive
	number means opposite things and the only way to be sure it is the right one
	is to say so here. The answer comes from the site's own `Party Type`, never
	from a guess about what an `Employee` is.
	"""

	def test_a_customer_owes_what_they_were_invoiced(self):
		self.assertEqual(ledger._movement(party(), debit=500, credit=0), 500)

	def test_a_customer_who_has_paid_owes_nothing(self):
		self.assertEqual(ledger._movement(party(), debit=500, credit=500), 0)

	def test_a_customer_who_has_overpaid_is_in_credit(self):
		self.assertEqual(ledger._movement(party(), debit=500, credit=800), -300)

	def test_an_employee_is_owed_what_was_credited_to_them(self):
		"""The same two columns, the other way round.

		An expense claim credits the employee's payable account, and a positive
		balance there means the organisation owes them -- so the subtraction has
		to run the other way or a reimbursement would read as a debt.
		"""
		self.assertEqual(ledger._movement(party("Payable"), debit=0, credit=500), 500)

	def test_an_employee_who_has_been_paid_is_owed_nothing(self):
		self.assertEqual(ledger._movement(party("Payable"), debit=500, credit=500), 0)


class TestWhatALineSays(TestCase):
	"""Charged and settled, rather than debit and credit.

	The book's words read backwards to half the people on this page: a payment
	from a customer is a credit and a payment to a supplier is a debit, and both
	make the balance smaller. What a statement has is one column that puts the
	balance up and one that brings it down, whichever way the bookkeeping ran.
	"""

	def test_a_receivable_line_charges_on_the_debit(self):
		line = ledger._line(party(), entry(debit=250))
		self.assertEqual((line["charged"], line["paid"]), (250, 0))

	def test_a_receivable_line_settles_on_the_credit(self):
		line = ledger._line(party(), entry(credit=250))
		self.assertEqual((line["charged"], line["paid"]), (0, 250))

	def test_a_payable_line_charges_on_the_credit(self):
		line = ledger._line(party("Payable"), entry(credit=250))
		self.assertEqual((line["charged"], line["paid"]), (250, 0))

	def test_a_payable_line_settles_on_the_debit(self):
		line = ledger._line(party("Payable"), entry(debit=250))
		self.assertEqual((line["charged"], line["paid"]), (0, 250))

	def test_a_blank_remark_is_absent_rather_than_empty(self):
		"""The page draws a remark when there is one; `""` is not one."""
		self.assertIsNone(ledger._line(party(), entry(debit=1, remarks="   "))["remarks"])

	def test_a_remark_keeps_its_words(self):
		line = ledger._line(party(), entry(debit=1, remarks=" Term 2 fees "))
		self.assertEqual(line["remarks"], "Term 2 fees")

	def test_a_line_says_which_account_it_was_posted_to(self):
		"""Carried on every line so the page can decide.

		A student's ledger is one account and the label would be noise; a member
		of staff has payroll, income tax withheld and social security posted
		against them, and a statement netting the three without saying which is
		which is a figure they cannot check. Which of the two this is, is the
		page's call -- but it can only make it if the account is here.
		"""
		line = ledger._line(party(), entry(debit=1, account="Payroll Payable - X"))
		self.assertEqual(line["account"], "Payroll Payable - X")


class TestTheRunningBalance(TestCase):
	"""The column the page exists for, and the total it has to agree with.

	The total is a sum the database does over every entry there has ever been;
	the lines are the most recent fifty. Those are two different queries and they
	have to close on the same figure, which is why the opening is *derived* from
	the total rather than summed a second time.
	"""

	def lines(self, *pairs):
		return [{"charged": charged, "paid": paid} for charged, paid in pairs]

	def test_the_last_line_closes_on_the_balance(self):
		lines = self.lines((100, 0), (0, 40), (60, 0))
		opening = ledger._opening(500, lines)
		ledger._run_balance(lines, opening)
		self.assertEqual(lines[-1]["balance"], 500)

	def test_what_is_not_listed_is_the_opening(self):
		"""Three movements netting 120 against a balance of 500: the 380 before
		them is the history this page does not draw."""
		self.assertEqual(ledger._opening(500, self.lines((100, 0), (0, 40), (60, 0))), 380)

	def test_a_statement_showing_everything_opens_at_zero(self):
		lines = self.lines((100, 0), (0, 40))
		self.assertEqual(ledger._opening(60, lines), 0)

	def test_a_statement_with_nothing_on_it_opens_at_the_balance(self):
		"""Every entry this party has is on a loan account, so the ledger lists
		none -- and the opening is then the whole of it rather than zero."""
		self.assertEqual(ledger._opening(500, []), 500)

	def test_each_line_carries_the_balance_after_it(self):
		lines = self.lines((100, 0), (0, 40))
		ledger._run_balance(lines, 0)
		self.assertEqual([line["balance"] for line in lines], [100, 60])


class TestTheHeadlineFigures(TestCase):
	"""Two balances, per currency, never added to each other.

	This is the whole of what was asked for, expressed as a function: a loan
	balance and an account balance are settled differently, to different
	schedules, and one number combining them is one nobody could act on. The
	only way to be sure they stay apart is to assert that nothing adds them.
	"""

	def account(self, balance, currency="NPR"):
		return {"balance": balance, "currency": currency}

	def loan(self, outstanding, currency="NPR"):
		return {"outstanding": outstanding, "currency": currency}

	def test_the_two_balances_stay_two_numbers(self):
		totals = api._totals([self.account(1200)], [self.loan(50000)])
		self.assertEqual(totals, [{"currency": "NPR", "account": 1200.0, "loans": 50000.0}])

	def test_a_reader_with_no_loans_still_has_a_loan_line_of_zero(self):
		"""Zero rather than absent: "you owe nothing on loans" is an answer, and
		the page draws it as one."""
		totals = api._totals([self.account(1200)], [])
		self.assertEqual(totals[0]["loans"], 0.0)

	def test_accounts_of_one_currency_are_added(self):
		totals = api._totals([self.account(1200), self.account(300)], [])
		self.assertEqual(totals[0]["account"], 1500.0)

	def test_two_currencies_are_two_rows(self):
		"""Never one. There is no rate to convert at and this app refuses to
		invent one anywhere else either."""
		totals = api._totals([self.account(1200), self.account(90, "GBP")], [])
		self.assertEqual([row["currency"] for row in totals], ["GBP", "NPR"])
		self.assertEqual([row["account"] for row in totals], [90.0, 1200.0])

	def test_a_loan_in_another_currency_does_not_join_the_account_balance(self):
		totals = api._totals([self.account(1200)], [self.loan(50000, "GBP")])
		self.assertEqual(
			totals,
			[
				{"currency": "GBP", "account": 0.0, "loans": 50000.0},
				{"currency": "NPR", "account": 1200.0, "loans": 0.0},
			],
		)

	def test_a_company_with_no_currency_is_kept_apart_rather_than_merged(self):
		"""A broken setup rather than a case to model -- but it must not collapse
		two real currencies into one bucket on the way to being noticed."""
		totals = api._totals([self.account(1200), self.account(5, None)], [])
		self.assertEqual(len(totals), 2)

	def test_a_reader_with_nothing_has_no_rows_at_all(self):
		self.assertEqual(api._totals([], []), [])


class TestMatchingADynamicLink(TestCase):
	"""The pair, not the two lists.

	`party` is a Dynamic Link, so the doctype it points at is a separate column.
	Filtering on `party_type in (...) and party in (...)` matches the cross
	product, and a Student whose id equalled an Employee id would collect the
	other person's ledger. It would also never be noticed, because it is correct
	for everybody whose ids do not collide.
	"""

	table = Table("tabGL Entry")

	def condition(self, *parties):
		return party_condition(self.table, "party_type", "party", list(parties))

	def test_one_party_pins_both_columns(self):
		sql = str(self.condition(party()))
		self.assertIn('"party_type"=', sql)
		self.assertIn('"party"=', sql)

	def test_two_parties_are_two_pairs_rather_than_two_lists(self):
		"""The shape that matters: `(a AND b) OR (c AND d)`, never
		`a IN (..) AND b IN (..)`."""
		sql = str(self.condition(party(), party(party_type="Employee", name="HR-EMP-0001")))
		self.assertEqual(sql.count(" OR "), 1)
		self.assertEqual(sql.count(" AND "), 2)
		self.assertNotIn(" IN ", sql)

	def test_nobody_is_not_a_condition(self):
		"""`None` rather than something that matches everything: every caller
		reads it as "there is nothing to look for" and issues no query at all."""
		self.assertIsNone(self.condition())
