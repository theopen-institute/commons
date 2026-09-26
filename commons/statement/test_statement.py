"""What the statement has to get right, and what would fail quietly if it did not.

Site-less, like `better_navigation.test_shell` and `self_service.test_self_service_api`: what
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
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from pypika import Table

from commons.statement import api, ledger, parties
from commons.statement.parties import Party, party_condition

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. See `better_navigation.test_shell`.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


def _raise(message, exc=frappe.ValidationError, **kwargs):
	"""`frappe.throw` without a site behind it, keeping the exception class."""
	raise exc(message)


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

	def account(self, balance, currency="NPR", account_type="Receivable"):
		# `direction` as the server puts it there, not as a literal: these
		# assertions are about the headline agreeing with the accounts under it,
		# and a hand-written direction would let the two drift in the fixture.
		return {
			"balance": balance,
			"currency": currency,
			"account_type": account_type,
			"direction": ledger.direction(balance, account_type),
		}

	def test_a_payable_balance_is_turned_round_before_it_is_added(self):
		"""The bug this exists to stop. A customer owing 500 and an employee
		owed 500 are +500 and +500 in their own conventions, and the two
		conventions run opposite ways -- so added as they stand they come to
		1,000 when the reader's net position is nought."""
		totals = api._totals(
			[self.account(500), self.account(500, account_type="Payable")], []
		)
		self.assertEqual(totals[0]["account"], 0.0)

	def loan(self, outstanding, currency="NPR"):
		return {"outstanding": outstanding, "currency": currency}

	def test_the_two_balances_stay_two_numbers(self):
		totals = api._totals([self.account(1200)], [self.loan(50000)])
		self.assertEqual(totals[0]["account"], 1200.0)
		self.assertEqual(totals[0]["loans"], 50000.0)
		# Nothing offers their sum. If a key ever appears that does, this is
		# where it should have to be argued for.
		self.assertNotIn(1200.0 + 50000.0, totals[0].values())

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
			[(row["currency"], row["account"], row["loans"]) for row in totals],
			[("GBP", 0.0, 50000.0), ("NPR", 1200.0, 0.0)],
		)

	def test_a_company_with_no_currency_is_kept_apart_rather_than_merged(self):
		"""A broken setup rather than a case to model -- but it must not collapse
		two real currencies into one bucket on the way to being noticed."""
		totals = api._totals([self.account(1200), self.account(5, None)], [])
		self.assertEqual(len(totals), 2)

	def test_a_reader_with_nothing_has_no_rows_at_all(self):
		self.assertEqual(api._totals([], []), [])


class TestWhichWayTheHeadlineRuns(TestCase):
	"""The one word every renderer reads instead of deriving it again.

	The sign of a balance says which way it runs only once you also know which
	side of the books the party sits on. The page said that in TypeScript and a
	print format would have said it again in Jinja -- so it is said here, once,
	and both of them only choose the English for it.
	"""

	def account(self, balance, account_type="Receivable", currency="NPR"):
		return {
			"balance": balance,
			"currency": currency,
			"account_type": account_type,
			"direction": ledger.direction(balance, account_type),
		}

	def test_a_customer_in_debt_owes(self):
		self.assertEqual(ledger.direction(500, "Receivable"), ledger.OWED_BY_PARTY)

	def test_a_customer_in_credit_is_owed(self):
		self.assertEqual(ledger.direction(-500, "Receivable"), ledger.OWED_TO_PARTY)

	def test_an_employee_with_a_positive_balance_is_owed(self):
		"""The same sign, the opposite sentence. This is the whole reason the
		derivation is not left to whoever is drawing the number."""
		self.assertEqual(ledger.direction(500, "Payable"), ledger.OWED_TO_PARTY)

	def test_an_employee_overpaid_owes_it_back(self):
		self.assertEqual(ledger.direction(-500, "Payable"), ledger.OWED_BY_PARTY)

	def test_nothing_outstanding_runs_neither_way(self):
		self.assertEqual(ledger.direction(0, "Receivable"), ledger.SETTLED)
		self.assertEqual(ledger.direction(0, "Payable"), ledger.SETTLED)

	def test_the_headline_follows_its_accounts(self):
		totals = api._totals([self.account(500), self.account(300)], [])
		self.assertEqual(totals[0]["direction"], ledger.OWED_BY_PARTY)

	def test_accounts_that_disagree_are_mixed_rather_than_guessed(self):
		"""Somebody who is both a customer and an employee. Their sum is a
		figure with no sentence attached to it, and saying so beats picking one
		of the two readings and being wrong for half of what it covers."""
		totals = api._totals(
			[self.account(500), self.account(200, "Payable")],
			[],
		)
		self.assertEqual(totals[0]["direction"], api.MIXED)

	def test_a_settled_account_does_not_make_the_headline_mixed(self):
		"""Nothing outstanding is not a third opinion."""
		totals = api._totals([self.account(500), self.account(0)], [])
		self.assertEqual(totals[0]["direction"], ledger.OWED_BY_PARTY)

	def test_accounts_that_cancel_out_net_to_nothing_and_still_say_mixed(self):
		"""Two companies, one currency, owed one way and owing the other.

		The net is genuinely nought and the page may print it. What it may not
		do is call the reader settled: they have a debt in one company and a
		credit in another, and both have to be dealt with. `MIXED` is what stops
		a correct number becoming a wrong sentence.
		"""
		totals = api._totals([self.account(500), self.account(-500)], [])
		self.assertEqual(totals[0]["account"], 0.0)
		self.assertEqual(totals[0]["direction"], api.MIXED)

	def test_a_headline_of_nothing_says_settled(self):
		totals = api._totals([self.account(0)], [])
		self.assertEqual(totals[0]["direction"], ledger.SETTLED)


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


class TestWhoMayReadSomebodyElsesStatement(TestCase):
	"""`parties.named`, which is the only place a party arrives from outside.

	Everywhere else in this section the parties come from the session and cannot
	be anybody else's. A print format is handed a document, so the party comes
	off that -- and this is the check standing between "print my statement" and
	"print theirs". It is worth its own tests for the same reason the sign rule
	is: it is four lines, and being wrong looks exactly like being right.
	"""

	def setUp(self):
		# `frappe.throw` reaches for `frappe.flags`, which a site-less run has no
		# binding for -- the same stand-in `better_navigation.test_shell` makes, except that
		# this one keeps the exception class, because which refusal is given is
		# half of what these tests are about.
		self.enterContext(patch.object(parties.frappe, "throw", side_effect=_raise))
		self.mine = party(party_type="Student", name="me@example.com")
		self.theirs = party(party_type="Student", name="them@example.com")
		self.enterContext(
			patch.object(parties, "_party", side_effect=lambda doctype, name: Party(
				party_type=doctype, name=name, title="Someone", account_type="Receivable"
			))
		)
		self.enterContext(patch.object(parties, "session_parties", return_value=[self.mine]))

	def permissions(self, **granted):
		"""Stand in for the site's permissions. Nothing is granted by default."""
		self.enterContext(
			patch.object(
				parties.frappe,
				"has_permission",
				side_effect=lambda doctype, *args, **kwargs: granted.get(doctype, False),
			)
		)

	def test_your_own_statement_needs_no_permission_at_all(self):
		"""The whole feature. A student has no `GL Entry` right and never will,
		and the page exists so that they can read their own balance anyway."""
		self.permissions()
		found = parties.named("Student", "me@example.com")
		self.assertEqual(found.name, "me@example.com")

	def test_somebody_elses_is_refused_outright(self):
		self.permissions()
		with self.assertRaises(frappe.PermissionError):
			parties.named("Student", "them@example.com")

	def test_accounts_may_read_anybody_they_can_read_the_ledger_for(self):
		"""The desk's case: printing a statement for a customer."""
		self.permissions(Student=True, **{"GL Entry": True})
		found = parties.named("Student", "them@example.com")
		self.assertEqual(found.name, "them@example.com")

	def test_reading_the_party_alone_is_not_enough(self):
		"""An HR user can read `Employee`. That is not the same as being
		entitled to read an employee's salary history, and a rule asking only
		about the party doctype would hand every one of them everybody's."""
		self.permissions(Student=True)
		with self.assertRaises(frappe.PermissionError):
			parties.named("Student", "them@example.com")

	def test_reading_the_ledger_alone_is_not_enough(self):
		self.permissions(**{"GL Entry": True})
		with self.assertRaises(frappe.PermissionError):
			parties.named("Student", "them@example.com")

	def test_a_name_that_is_not_a_party_is_refused_rather_than_answered_empty(self):
		"""An empty statement under a real person's name reads as "you owe
		nothing", which is a worse answer than a refusal."""
		self.permissions(Student=True, **{"GL Entry": True})
		with patch.object(parties, "_party", return_value=None):
			with self.assertRaises(frappe.DoesNotExistError):
				parties.named("Student", "nobody@example.com")


class TestDownloadingWithoutThePrintFormat(TestCase):
	"""`api.download_statement` where the site has not set the print format up.

	The print formats are added by hand now, so a site without one is ordinary.
	`frappe.get_print` given a missing print format falls back to "Standard",
	which prints every field of the party document -- and the download sets
	print permissions aside -- so a missing format has to be a refusal, never a
	print.
	"""

	def setUp(self):
		self.enterContext(patch.object(api.frappe, "throw", side_effect=_raise))
		self.enterContext(patch.object(api.frappe, "bold", side_effect=lambda text: text))
		self.enterContext(
			patch.object(
				api.parties,
				"named",
				return_value=Party(party_type="Student", name="me@example.com", title="Me", account_type="Receivable"),
			)
		)
		self.printed = self.enterContext(patch.object(api.frappe, "get_print", return_value=b"%PDF"))

	def site_with(self, *formats):
		"""Stand in for the Print Format table: `formats` are (name, doc_type, disabled) rows."""

		def exists(doctype, filters):
			return any(
				(name, doc_type, disabled) == (filters["name"], filters["doc_type"], filters["disabled"])
				for name, doc_type, disabled in formats
			)

		self.enterContext(patch.object(api.frappe, "db", SimpleNamespace(exists=exists)))

	def test_a_missing_print_format_is_refused_rather_than_printed(self):
		self.site_with()
		with self.assertRaises(frappe.DoesNotExistError):
			api.download_statement("Student", "me@example.com")
		self.printed.assert_not_called()

	def test_a_disabled_print_format_is_refused(self):
		self.site_with(("Student Account Statement", "Student", 1))
		with self.assertRaises(frappe.DoesNotExistError):
			api.download_statement("Student", "me@example.com")
		self.printed.assert_not_called()

	def test_a_format_of_that_name_for_another_doctype_is_refused(self):
		self.site_with(("Student Account Statement", "Customer", 0))
		with self.assertRaises(frappe.DoesNotExistError):
			api.download_statement("Student", "me@example.com")
		self.printed.assert_not_called()

	def test_the_print_format_that_is_there_is_the_one_printed(self):
		self.site_with(("Student Account Statement", "Student", 0))
		response = SimpleNamespace()
		with (
			patch.object(api.frappe, "local", SimpleNamespace(response=response)),
			patch.object(api.frappe, "flags", SimpleNamespace()),
			patch.object(api, "_filename", return_value="Me statement"),
		):
			api.download_statement("Student", "me@example.com")
		self.assertEqual(self.printed.call_args.args[:3], ("Student", "me@example.com", "Student Account Statement"))
		self.assertEqual(response.type, "pdf")
