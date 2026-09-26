"""The statement itself: what the general ledger says about these parties.

Fees, sales invoices, credit notes, payment entries and journal entries are
five doctypes and one answer. Every one of them posts a `GL Entry` against the
party it concerns, so the ledger is the statement and nothing in this module
names any of them -- which is why a site that installs Education gets its
`Fees` on this page without a line changing here, and why one that never does
is not carrying code for a doctype it does not have.

Three decisions are worth reading before the code.

*Company currency, and no conversion.* `debit` and `credit` are in the
company's currency always, whatever currency the account or the invoice was
in. They are therefore the only pair of columns on this table that can be added
up without an exchange rate, and a statement whose running balance is a sum has
to add something addable. An account kept in another currency shows its
movements converted, which is what the company's own books say they were worth.

*One statement per party per company.* Balances across companies are separate
books and do not add; balances across party types are separate accounts and do
not either -- a person who is both a Customer and an Employee is owed by one
and owes the other, and one net figure across the two would be a number nobody
could act on.

*Old entries become an opening balance rather than a scroll.* The total is a
sum over every row, computed by the database and always exact. What is listed
is the most recent `PAGE_LENGTH` of them, with everything before folded into
the opening balance the way a paper statement folds the previous quarter. That
keeps a twenty-year customer's page the same size as a new one's, and the two
figures always agree because the opening is derived from the exact total rather
than from a second, shorter sum.
"""

import frappe
from frappe.query_builder.functions import Coalesce, Count, Sum
from frappe.utils import flt

from commons.commons_core import apps
from commons.statement import company_currency, loans
from commons.statement.parties import Party, party_condition

GL_ENTRY = "GL Entry"

# How many movements a statement lists. Everything older is real and counted --
# it is in the opening balance -- but it is not drawn.
PAGE_LENGTH = 50

# What one movement carries. Deliberately short: a statement line says when,
# what it was, and how much, and nothing here opens the document behind it.
#
# `account` is the exception to that shortness and it earns its place on real
# data. A party's ledger is not always one account: a student's fees are all on
# Debtors and read perfectly without it, but a member of staff has payroll,
# income tax withheld and social security all posted against them, and a
# statement netting the three without saying which is which is a number they
# cannot check. The page prints it only where a statement actually spans more
# than one, so the common case stays as clean as it reads now.
ENTRY_FIELDS = (
	"name",
	"posting_date",
	"company",
	"account",
	"party_type",
	"party",
	"voucher_type",
	"voucher_no",
	"remarks",
	"debit",
	"credit",
	"is_opening",
)


def available() -> bool:
	"""Whether this site keeps a ledger at all.

	`GL Entry` rather than "is ERPNext installed", for the reason
	`commons_core.apps` gives: this module touches one doctype and reads
	nothing else of ERPNext's, so that doctype is the question it is actually
	asking.
	"""
	return apps.has_doctype(GL_ENTRY)


def statements(parties: list[Party]) -> list[dict]:
	"""One statement per party per company, in a stable order.

	A raw read. The package docstring is the argument for it; what matters here
	is that `parties` is resolved from the session by `parties.session_parties`
	and is never accepted from a request, and that `party_condition` matches the
	dynamic link as a pair -- so the widest this query can reach is the rows of
	the people the caller already is.
	"""
	if not available() or not parties:
		return []

	by_party = {(party.party_type, party.name): party for party in parties}
	excluded = loans.ledger_exclusion(parties)

	found = []
	for (party_type, name, company), totals in _totals(parties, excluded).items():
		party = by_party[(party_type, name)]
		lines, listed = _lines(party, company, excluded)
		balance = _movement(party, totals["debit"], totals["credit"])
		opening = _opening(balance, lines)
		_run_balance(lines, opening)
		found.append(
			{
				"party_type": party_type,
				"party": name,
				"party_name": party.title,
				"account_type": party.account_type,
				"company": company,
				"currency": company_currency(company),
				"balance": balance,
				"direction": direction(balance, party.account_type),
				"opening": opening,
				"entries": totals["count"],
				"lines": lines,
				# Whether anything was folded into the opening, so the page can
				# say so rather than let a statement look as though it started
				# there.
				"truncated": totals["count"] > listed,
			}
		)

	found.sort(key=lambda row: (row["company"], row["party_type"], row["party"]))
	return found


def _opening(balance: float, lines: list[dict]) -> float:
	"""What the balance stood at before the first listed line.

	The whole of the history this page does not draw, as one figure. Derived by
	taking the listed movements back off the exact total rather than summed a
	second time from the older rows -- so the opening plus what is on screen is
	the closing balance by construction, and not by two queries agreeing.

	Which matters most in the case that would otherwise be hardest to notice: a
	statement showing every entry there has ever been opens at zero, and it does
	so because the movements cancel the total exactly, rather than because
	anything here special-cased a short history.
	"""
	return flt(balance - sum(line["charged"] - line["paid"] for line in lines))


def _run_balance(lines: list[dict], opening: float) -> None:
	"""Lay the running balance along the lines, in reading order.

	Here rather than in the browser because it is the column the page is for,
	and because it has to start from the opening figure -- a balance computed
	from what is on screen would be right only for a party whose history fits on
	it.
	"""
	balance = opening
	for line in lines:
		balance = flt(balance + line["charged"] - line["paid"])
		line["balance"] = balance


def _totals(parties: list[Party], excluded: loans.LedgerExclusion) -> dict[tuple[str, str, str], dict]:
	"""Every party-and-company pair these parties have a ledger in, and its sums.

	Grouped by the database rather than by counting rows in Python: the sum has
	to be over every entry that has ever been posted, and the page lists a
	window of them.
	"""
	table = frappe.qb.DocType(GL_ENTRY)
	query = (
		frappe.qb.from_(table)
		.select(
			table.party_type,
			table.party,
			table.company,
			Sum(table.debit).as_("debit"),
			Sum(table.credit).as_("credit"),
			Count(table.name).as_("count"),
		)
		.where(_scope(table, parties, excluded))
		.groupby(table.party_type, table.party, table.company)
	)
	return {
		(row.party_type, row.party, row.company): {
			"debit": flt(row.debit),
			"credit": flt(row.credit),
			"count": int(row.count or 0),
		}
		for row in query.run(as_dict=True)
	}


def _lines(party: Party, company: str, excluded: loans.LedgerExclusion) -> tuple[list[dict], int]:
	"""The most recent movements on one party's ledger, oldest first.

	Fetched newest-first and turned round, which is the only way to take the
	*last* fifty rows of an unbounded history in one query. The running balance
	is then laid on in reading order by the caller's opening figure -- see
	`statements`, where the two are reconciled.
	"""
	table = frappe.qb.DocType(GL_ENTRY)
	rows = frappe.get_all(
		GL_ENTRY,
		filters=_scope(table, [party], excluded) & (table.company == company),
		fields=list(ENTRY_FIELDS),
		order_by="posting_date desc, creation desc",
		limit_page_length=PAGE_LENGTH,
	)
	rows.reverse()
	return [_line(party, row) for row in rows], len(rows)


def _line(party: Party, row: frappe._dict) -> dict:
	"""One movement, in the two columns a statement actually has.

	Not debit and credit. Those are the book's words and they read backwards to
	half the people on this page: a payment from a customer is a credit, and a
	payment to a supplier is a debit, and both of them make the balance smaller.
	What a statement says is what was charged and what was settled, which is the
	same pair of numbers the other way round for a payable party -- hence
	`_movement`, which is where the one sign rule in this module lives.
	"""
	debit = flt(row.debit)
	credit = flt(row.credit)
	charged = debit if party.account_type == "Receivable" else credit
	paid = credit if party.account_type == "Receivable" else debit
	return {
		"name": row.name,
		"date": row.posting_date,
		"account": row.account,
		"voucher_type": row.voucher_type,
		"voucher_no": row.voucher_no,
		# The ledger's own note. Frappe writes these as plain text, and the page
		# renders them as text -- nothing on this page renders markup it was
		# handed, which is the same rule `get_expense_claim_lines` follows.
		"remarks": (row.remarks or "").strip() or None,
		"is_opening": row.is_opening == "Yes",
		"charged": charged,
		"paid": paid,
	}


# The three ways a balance can run, as the one word every renderer reads.
#
# Here rather than in each of them, and it is the whole of what "one source of
# interpretation" means for this section. The sign of `balance` says which way
# round it runs only once you also know whether this party sits on the
# receivable or the payable side, and that is a derivation -- a small one, and
# small derivations written down twice are the ones that drift. The page and the
# print format each word this differently, because "You owe" and "Owed to you"
# are wording; which of the two applies is not.
SETTLED = "settled"
OWED_BY_PARTY = "owed_by_party"
OWED_TO_PARTY = "owed_to_party"


def direction(balance: float, account_type: str) -> str:
	"""Which way round a balance runs, said once for everything that draws it."""
	if not balance:
		return SETTLED
	owed_by_party = balance > 0 if account_type == "Receivable" else balance < 0
	return OWED_BY_PARTY if owed_by_party else OWED_TO_PARTY


def _movement(party: Party, debit: float, credit: float) -> float:
	"""Which way round this party's balance reads.

	A receivable balance is positive when the party owes the organisation, and a
	payable one when the organisation owes the party. Both are "what is
	outstanding on your account", which is the only reading a person has for the
	number, and the sign is taken from the site's own `Party Type` rather than
	from a guess about what an Employee is -- see `parties.Party.account_type`.
	"""
	return flt(debit - credit if party.account_type == "Receivable" else credit - debit)


def _scope(table, parties: list[Party], excluded: loans.LedgerExclusion):
	"""The where every read in this module starts from.

	Three things, and each of them is load-bearing:

	* the parties, matched as pairs (`party_condition`) -- and, for a party
	  reached through the desk, within the companies the reader may see;
	* cancelled entries left out, or a reversed invoice would be counted twice;
	* the lending module's entries left out, which is `loans.ledger_exclusion`
	  and the reason that module exists -- a loan's principal is posted against
	  the borrower and would otherwise be added to what they owe on invoices.

	The last comes in two parts, and `loans.LedgerExclusion` is the argument
	for them: an account only lending posts through is left out whole, and one
	trade shares loses only the entries lending posted against a loan. The
	`Coalesce` is not decoration. Most entries have no `against_voucher_type`,
	`NULL = 'Loan'` is `NULL` rather than false, and `NOT (... AND NULL)` would
	then drop every trade entry on a shared account -- the very rows the split
	exists to keep.
	"""
	condition = party_condition(table, "party_type", "party", parties) & (table.is_cancelled == 0)
	if excluded.dedicated:
		condition = condition & table.account.notin(sorted(excluded.dedicated))
	if excluded.shared:
		lending_owned = Coalesce(table.against_voucher_type, "") == loans.LOAN
		if excluded.voucher_types:
			lending_owned = lending_owned | table.voucher_type.isin(list(excluded.voucher_types))
		condition = condition & ~(table.account.isin(sorted(excluded.shared)) & lending_owned)
	return condition

