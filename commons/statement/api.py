"""The one endpoint behind the Account Balance page.

One call, not three. The page has no permission preamble to run first -- there
is no approving to be done here and nothing to create -- so the only question
it asks is "what is on my account", and splitting that into a ledger call and a
loans call would mean two round trips before a single figure could be drawn,
plus a moment where the trade balance was on screen and the loan balance was
not. On a statement those two are read together or they mislead.

Nothing is accepted from the caller. There is no party argument, no company
argument and no date range, because every one of those would be a way of asking
about somebody else and would have to be proved not to be. The parties come
from the session and the scope follows from them; see `parties.session_parties`
and the package docstring on why the reads beneath this ignore permissions.
"""

import frappe
from frappe.utils import flt

from commons.statement import ledger, loans, parties


@frappe.whitelist()
def get_statement() -> dict:
	"""Everything the page draws, for whoever is asking.

	The shape is the same for a reader with nothing on their account as for one
	with three: empty lists rather than an error, so the page has one way of
	rendering itself and an empty state rather than a failure to explain.

	`ledger` and `lending` are the two things the page cannot work out for
	itself -- whether this site keeps a ledger at all, and whether it lends --
	and they are the difference between "you have no balance" and "there is no
	such thing here", which are different sentences to put on an empty page.
	"""
	mine = parties.session_parties()
	accounts = ledger.statements(mine)
	borrowings = loans.balances(mine)
	return {
		"ledger": ledger.available(),
		"lending": loans.available(),
		"parties": [
			{
				"party_type": party.party_type,
				"party": party.name,
				"party_name": party.title,
				"account_type": party.account_type,
			}
			for party in mine
		],
		"accounts": accounts,
		"loans": borrowings,
		"totals": _totals(accounts, borrowings),
		# So the page can say what "the last 50" means rather than hard-coding
		# a number the server owns.
		"page_length": ledger.PAGE_LENGTH,
	}


def _totals(accounts: list[dict], borrowings: list[dict]) -> list[dict]:
	"""The two headline figures, per currency.

	Per currency because adding two currencies together is not an answer, and
	this app already refuses to guess an exchange rate anywhere a document does
	not carry one. A reader with one company -- which is nearly all of them --
	sees one row and never learns that this is a list.

	The two figures stay separate all the way out to the page. They are not
	netted, they are not summed, and nothing here offers a total of the two:
	money you owe on a loan and money you owe on an invoice are settled
	differently, to different schedules, and a single number combining them is
	one nobody could act on. That is the whole argument for this section having
	two balances rather than one, and it is honoured by never adding them.
	"""
	rows: dict[str, dict] = {}

	def row(currency: str | None) -> dict:
		# A company with no default currency is a broken setup rather than a
		# case to model, but it must not collapse two real currencies into one
		# bucket on the way to being noticed.
		key = currency or ""
		return rows.setdefault(key, {"currency": currency, "account": 0.0, "loans": 0.0})

	for account in accounts:
		row(account["currency"])["account"] += flt(account["balance"])
	for loan in borrowings:
		row(loan["currency"])["loans"] += flt(loan["outstanding"])

	for values in rows.values():
		values["account"] = flt(values["account"])
		values["loans"] = flt(values["loans"])
	return sorted(rows.values(), key=lambda values: values["currency"] or "")
