"""The ways into a statement: the page, the print format, and the PDF.

Three entry points and one answer. `_statement` is the whole of what a statement
is; everything above it only settles *whose* statement is being asked for, and
that is the only thing the three differ on:

* `get_statement` -- the session's own parties. The page. Nothing is accepted
  from the caller, because every argument would be a way of asking about
  somebody else.
* `party_statement` -- one party, by name, permission-checked. What a print
  format calls, and what makes the PDF and the page one interpretation rather
  than two implementations that agree for now. Exposed to Jinja through the
  `jinja` hook in `hooks.py`.
* `download_statement` -- the same print format, rendered to PDF for a reader
  who cannot open the desk.

What is deliberately *not* here is a second set of rules for the printed
version. No date range, no wider window, no different rounding: the PDF folds
older entries into a brought-forward balance exactly as the page does, because a
printed statement that disagreed with the screen it was printed from would be
worse than either.

The one thing that legitimately differs between them is wording. "You owe" and
"Owed to you" are English, and the page says it one way and the print format
another. Which of the two applies is not wording, and is decided once, on the
way out of here -- see `ledger.direction`.
"""

import frappe
from frappe import _
from frappe.utils import flt

from commons.statement import ledger, loans, parties, print_format_name


@frappe.whitelist()
def get_statement() -> dict:
	"""Everything the page draws, for whoever is asking.

	The shape is the same for a reader with nothing on their account as for one
	with three: empty lists rather than an error, so the page has one way of
	rendering itself and an empty state rather than a failure to explain.
	"""
	return _statement(parties.session_parties())


@frappe.whitelist()
def party_statement(party_type: str, party: str) -> dict:
	"""The statement of one named party -- the print format's data source.

	Whitelisted and exposed to Jinja, which are two ways of reaching the same
	function on purpose. A print format calls it with the document it is
	printing; the desk and anything else calls it over HTTP; both get the
	figures the page gets, from the code the page uses.

	Who may ask is `parties.named`, which throws rather than answering thinly.
	"""
	return _statement([parties.named(party_type, party)])


def _statement(mine: list[parties.Party]) -> dict:
	"""One statement, for whichever parties the caller was entitled to.

	`ledger` and `lending` are the two things a renderer cannot work out for
	itself -- whether this site keeps a ledger at all, and whether it lends --
	and they are the difference between "you have no balance" and "there is no
	such thing here", which are different sentences to put on an empty page.
	"""
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
		# So a renderer can say what "the last 50" means rather than hard-coding
		# a number the server owns.
		"page_length": ledger.PAGE_LENGTH,
	}


# A currency whose accounts do not agree on which way their balances run. Not a
# fourth direction so much as the absence of one: somebody who is both a
# customer and an employee is owed by one book and owes the other, and their sum
# is a figure with no sentence attached to it. Every renderer says so rather
# than picking one of the two readings and being wrong for half of what it
# covers.
MIXED = "mixed"


def _totals(accounts: list[dict], borrowings: list[dict]) -> list[dict]:
	"""The two headline figures, per currency.

	Per currency because adding two currencies together is not an answer, and
	this app already refuses to guess an exchange rate anywhere a document does
	not carry one. A reader with one company -- which is nearly all of them --
	sees one row and never learns that this is a list.

	The two figures stay separate all the way out to the renderer. They are not
	netted, they are not summed, and nothing here offers a total of the two:
	money owed on a loan and money owed on an invoice are settled differently,
	to different schedules, and a single number combining them is one nobody
	could act on. That is the whole argument for this section having two
	balances rather than one, and it is honoured by never adding them.
	"""
	rows: dict[str, dict] = {}

	def row(currency: str | None) -> dict:
		# A company with no default currency is a broken setup rather than a
		# case to model, but it must not collapse two real currencies into one
		# bucket on the way to being noticed.
		key = currency or ""
		return rows.setdefault(
			key, {"currency": currency, "account": 0.0, "loans": 0.0, "directions": set()}
		)

	for account in accounts:
		current = row(account["currency"])
		current["account"] += _owed_by_party(account)
		current["directions"].add(account["direction"])
	for loan in borrowings:
		row(loan["currency"])["loans"] += flt(loan["outstanding"])

	for values in rows.values():
		values["account"] = flt(values["account"])
		values["loans"] = flt(values["loans"])
		values["direction"] = _headline_direction(values.pop("directions"), values["account"])
	return sorted(rows.values(), key=lambda values: values["currency"] or "")


def _owed_by_party(account: dict) -> float:
	"""One account's balance, restated so that positive always means "they owe".

	Without this the sum above is not arithmetic. `balance` is in the party's
	own convention -- positive means a customer owes the organisation, and
	positive means the organisation owes an employee -- which is the right way
	to read a *statement*, because both say "what is outstanding on your
	account". It is the wrong thing to add up: a customer balance of +500 and an
	employee balance of -500 both mean "owes 500", and adding them as they stand
	produces nought.

	So the two conventions are collapsed into one here, and only here. `balance`
	itself is left alone, because the statement it heads is read in the party's
	convention and restating it there would mean an employee's reimbursement
	arriving as a negative number.
	"""
	balance = flt(account["balance"])
	return balance if account["account_type"] == "Receivable" else -balance


def _headline_direction(directions: set[str], balance: float) -> str:
	"""Which way the headline figure for one currency runs.

	Taken from the accounts behind it rather than from the sign of their sum.
	The two agree once the sum is arithmetic -- see `_owed_by_party` -- but the
	accounts carry one thing the sum cannot: whether they agreed in the first
	place. A reader who owes fees and is owed a reimbursement has a net that is
	perfectly correct and a sentence that is not, and `MIXED` is how a renderer
	is told to stop claiming one and point down the page instead.

	A settled account is not a third opinion, and does not make a headline
	mixed.
	"""
	meaningful = directions - {ledger.SETTLED}
	if not meaningful:
		return ledger.SETTLED
	if len(meaningful) > 1:
		return MIXED
	return meaningful.pop()


@frappe.whitelist()
def download_statement(party_type: str, party: str) -> None:
	"""The same statement, as a PDF, through the same print format.

	For a reader who cannot open the desk, which is most of the people this
	section was written for: a student or a supplier has no `/app`, so the
	desk's own print view is not a route they have. This is that route.

	`ignore_print_permissions` is set deliberately and is narrower than it
	sounds. Print permission is a permission over the *party document* -- the
	Customer, the Student -- and a reader almost never has it over their own;
	`parties.named` has already settled whether this statement is theirs to see,
	which is the question that matters, and the page behind it would be
	pointless if the answer here were "only if you may also open your own
	customer record in the desk".

	Nothing of the document itself is rendered. The print format draws the
	statement and nothing else -- see `print/statement.html`.

	The print format is a site's to add by hand (`frontend/README.md` has the
	two lines), so it may not be there -- and it is refused rather than printed
	without it. `frappe.get_print` given a print format that does not exist
	falls back to "Standard" without a word, and "Standard" draws every field
	of the party document; with print permissions set aside above, that would
	hand a student their whole Student record, or an employee their Employee
	record, in place of a statement.
	"""
	resolved = parties.named(party_type, party)

	name = print_format_name(resolved.party_type)
	if not frappe.db.exists("Print Format", {"name": name, "doc_type": resolved.party_type, "disabled": 0}):
		frappe.throw(
			_("Statements cannot be downloaded yet: the print format {0} has not been set up.").format(
				frappe.bold(name)
			),
			frappe.DoesNotExistError,
		)

	# Put back as it was found rather than to False: a caller that had set it
	# for its own reasons -- a batch print, a test -- would otherwise have it
	# cleared from under it by a statement it happened to render on the way.
	previous = frappe.flags.ignore_print_permissions
	frappe.flags.ignore_print_permissions = True
	try:
		pdf = frappe.get_print(resolved.party_type, resolved.name, name, as_pdf=True)
	finally:
		frappe.flags.ignore_print_permissions = previous

	frappe.local.response.filename = f"{_filename(resolved)}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


def _filename(party: parties.Party) -> str:
	"""What the saved file is called.

	The party's own name and the date, which is what somebody filing a statement
	wants to see in a downloads folder. Scrubbed of anything a filesystem or a
	`Content-Disposition` header would rather not carry -- a customer name is
	free text and has had slashes and quotes in it before now.
	"""
	stem = f"{party.title} statement {frappe.utils.today()}"
	return "".join(character if character.isalnum() or character in " -_" else "-" for character in stem)
