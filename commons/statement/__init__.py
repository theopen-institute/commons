"""What a person owes the organisation, and what it owes them.

The one section of this app that is not about a request. Everything else here
is something a member of staff raises and waits on an approver for; this is a
statement -- read-only, historical, and about money that has already moved.

It is one page and three questions, and the three are separate on purpose.

*Which parties am I?* A login is not a party. It is linked to one by whatever
each party doctype uses to name a user -- a `Portal User` row on a Customer, a
`user_id` on an Employee, a `user` on a Student -- and a person can be more
than one at once. `parties.py` is that resolution, and it is the only thing in
this module that consults the session: everything downstream is handed parties
and never asks who is asking.

*What is on my account?* Fees, invoices, payments, credit notes and journal
entries are not four questions. Every one of them posts a `GL Entry` against
the party, so the ledger is the statement and nothing here has to know that
`Fees` exists -- which is the reason a site that installs Education gets its
fees on this page without a line being changed. `ledger.py`.

*What do I owe on loans?* Separately, and not as a matter of taste. `lending`
posts its GL entries with the applicant as the party, so a loan's principal
sits in the same table as the invoices and would be summed with them by
anything that merely filtered on the party -- a disbursement reading as though
the borrower had been invoiced for it. `loans.py` takes those accounts out of
the ledger above and answers for them itself, from the Loan documents, so the
two balances are two numbers that never touch.

On permissions, because this is money and the answer is deliberate
---------------------------------------------------------------

The ledger read ignores permissions, and is scoped to the caller's own parties
before it is issued. That is the same bounded disclosure `registry.owner_of`
and `registry.record_exists` make and it is argued the same way: the rows are
the caller's own, the party is resolved from the session and never accepted
from the request, and nothing here returns a row belonging to anybody else.

The alternative was `frappe.get_list`, and it does not work for what this page
is for. `GL Entry` read is an accountant's permission; a student, a member or a
supplier has none of it and never will. A statement gated on it would be a page
that only Accounts could open, about everybody else's money. Either the reader
may see their own balance or the section does not exist, and the requirement --
anybody with a balance here can see it -- is the first of those.

What that does *not* extend to is anything beyond the balance. No voucher is
opened, no attachment is served, no other party is named, and the line's
description is the ledger's own remark rather than the document behind it.
"""


import frappe


def company_currency(company: str) -> str | None:
	"""The currency every figure in this section is expressed in.

	Here, at the top of the package, because it is the one fact all three
	modules share and neither of the two that need it may import the other --
	`ledger` reads `loans` to know which accounts to leave out, so the
	dependency only runs one way.

	The company's own currency, and not the account's or the document's. A
	ledger entry's `debit` and `credit` are in it whatever currency the invoice
	was raised in, and a loan's amounts are declared in it on the doctype
	itself, so it is the one unit in which a trade balance and a loan balance
	are both stated -- which is what makes the two headline figures on the page
	comparable rather than merely adjacent.
	"""
	return frappe.get_cached_value("Company", company, "default_currency")


def print_format_name(party_type: str) -> str:
	"""What the statement print format for one party doctype is called.

	A print format is attached to exactly one doctype, so there is one of these
	per party type -- four of them where a site has all four. They are four
	records and one template: each holds a two-line stub that fetches the
	statement and includes `print/statement.html`, which is where the printed
	statement actually lives.

	Named here rather than in either of the two modules that need it.
	`install.py` creates them under this name and `api.download_statement` asks
	for one by it, and a name spelled in both places is a name that can be
	changed in one.
	"""
	return f"{party_type} Account Statement"
