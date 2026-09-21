"""Which parties the session user is, so a statement can be drawn for them.

A login is not a party. `Customer`, `Supplier`, `Employee` and `Student` are
four doctypes that each name a user in their own way, and one person can be
several of them at once -- a member of staff who is also a student pays fees as
one and is reimbursed as the other, and the two have separate balances because
they are separate accounts.

This is the only module in the section that reads `frappe.session`. Everything
downstream is handed the parties it is to report on and never asks who is
asking, which is what keeps the scoping in one readable place: if a party is
not in the list this module returns, no query in this section can reach its
rows.

Why the links are a table rather than a rule
--------------------------------------------

It is tempting to look for a Link-to-User field on each party doctype and use
whatever turns up. That would cover `Student.user` and `Employee.user_id`
today, and it would be a guess -- a field called `user` on a doctype nobody
here has seen is as likely to be "who created this" as "whose this is", and
guessing wrong hands somebody another person's ledger. So each link is written
down, next to the app that owns it, and a party type with no entry is reported
on for nobody.

That is also why `Member` is absent, and worth saying out loud since this app
ships it. `commons.community.Member` is not a `Party Type`: nothing posts a
ledger entry against a member, and the fees a member owes are posted against
whatever they are underneath -- a `Student`, usually -- which is the row this
module resolves. A member with a balance has it as one of the four below.

`Party Type` is the site's own document, not a list here. It says which of
these are party types at all, and whether each one's balance is a receivable or
a payable -- which is the difference between "you owe this" and "you are owed
this", and not something to hard-code for `Employee` when a site is free to
have said otherwise.
"""

from dataclasses import dataclass

import frappe

from commons.api import session_employee_filters
from commons.commons_core import apps

PARTY_TYPE = "Party Type"

# The child table ERPNext links a portal login to a Customer or a Supplier
# through. A person can be on several, which is why this is a read rather than
# a single value.
PORTAL_USER = "Portal User"

# How each party doctype names the user behind it.
#
# `None` means the link is a `Portal User` row rather than a field -- ERPNext's
# own portal mechanism, and the one `website_list_for_contact` reads to decide
# whose orders a logged-in customer may see.
#
# `Employee` is filtered as well as matched: an employee who has left keeps
# their `user_id`, and `session_employee_filters` is the one definition of what
# makes an Employee row this session's own. Stated there rather than repeated
# here, so a statement and a leave request agree on which record is yours.
#
# `Student` names two fields and needs both. Education ships a `user` link and
# barely fills it in; what it actually reads to answer "whose portal is this" is
# the email -- `education.utils.get_current_student` matches
# `student_email_id` against the session and nothing else, and a site whose
# students have fees but no `user` link is the ordinary case rather than a
# broken one. Matching either is what makes this agree with the app that raised
# the fees.
USER_LINKS: dict[str, tuple[str, ...] | None] = {
	"Customer": None,
	"Supplier": None,
	"Employee": ("user_id",),
	"Student": ("user", "student_email_id"),
}


@dataclass(frozen=True)
class Party:
	"""One party the session user is, as the rest of the section needs it."""

	party_type: str
	name: str
	title: str
	#: `Receivable` or `Payable`, from this site's own `Party Type` document.
	#: Which way round a balance reads depends on it -- see `ledger.balance_of`.
	account_type: str


def session_parties() -> list[Party]:
	"""Every party the session user is, in a stable order.

	Empty for a site with no ERPNext, where `Party Type` is not a doctype and
	nothing posts a ledger entry at all -- the same shape as "you are nobody's
	party here", which is the honest answer in both cases and is what the page
	renders as its empty state.
	"""
	if not apps.has_doctype(PARTY_TYPE):
		return []

	found: list[Party] = []
	for row in frappe.get_all(PARTY_TYPE, fields=["name", "account_type"], order_by="name asc"):
		if row.name not in USER_LINKS or not apps.has_doctype(row.name):
			continue
		for name, title in _records(row.name):
			found.append(
				Party(
					party_type=row.name,
					name=name,
					title=title,
					# A `Party Type` saved before the field was mandatory, or one
					# a site added by hand. Receivable is the shape of every
					# party type ERPNext ships except the two payables, and it is
					# the reading that errs towards "this is yours to settle".
					account_type=row.account_type or "Receivable",
				)
			)
	return found


def named(party_type: str, name: str) -> Party:
	"""One party the caller has asked for by name, or a refusal.

	The other way into this module. `session_parties` answers "who am I", which
	is how the page reaches a statement; this answers "may I see theirs", which
	is how a print format does -- the party comes off the document being
	printed, not off the session, so it is the one place in this section where
	a name arrives from outside and has to be checked rather than trusted.

	Two ways to be allowed, and they are different people:

	* it is one of your own parties, which is the page's case and needs nothing
	  else -- the whole feature is that a reader may see their own balance
	  whatever their `GL Entry` permission says;
	* or you may read both the party's own doctype *and* `GL Entry`, which is
	  the desk's case: somebody in Accounts printing a statement for a customer.

	`GL Entry` is asked for as well as the party doctype, deliberately. An HR
	user can read `Employee`; that is not the same as being entitled to read an
	employee's ledger, and a rule that asked only about the party doctype would
	hand every one of them everybody's salary history.

	Throws rather than returning `None`. Every caller needs the party, and a
	print format that got a `None` would render an empty statement under a real
	person's name -- which reads as "you owe nothing" rather than as a refusal.
	"""
	party = _party(party_type, name)
	if not party:
		frappe.throw(
			frappe._("{0} {1} is not a party here.").format(frappe._(party_type), name),
			frappe.DoesNotExistError,
		)

	if any(mine.party_type == party_type and mine.name == name for mine in session_parties()):
		return party

	if frappe.has_permission(party_type, "read", doc=name) and frappe.has_permission("GL Entry", "read"):
		return party

	frappe.throw(
		frappe._("You are not permitted to see the account of {0}.").format(party.title),
		frappe.PermissionError,
	)


def _party(party_type: str, name: str) -> Party | None:
	"""The party record behind a name, or None if this site has no such party.

	"No such party" covers three things a caller does not need to tell apart: a
	doctype that is not a `Party Type` here, one that is not on the site at all,
	and a name no record answers to. None of the three is a statement, and the
	one caller refuses all three the same way.
	"""
	if not apps.has_doctype(PARTY_TYPE) or not apps.has_doctype(party_type):
		return None
	account_type = frappe.db.get_value(PARTY_TYPE, party_type, "account_type")
	if account_type is None and not frappe.db.exists(PARTY_TYPE, party_type):
		return None

	title_field = frappe.get_meta(party_type).get_title_field()
	title = frappe.db.get_value(party_type, name, title_field)
	if title is None and not frappe.db.exists(party_type, name):
		return None

	return Party(
		party_type=party_type,
		name=name,
		title=title or name,
		account_type=account_type or "Receivable",
	)


def _records(party_type: str) -> list[tuple[str, str]]:
	"""The rows of one party doctype this user is, as (name, how it reads).

	A raw read, and the reason is the same one `registry.owner_of` gives: this
	answers "which of these am I", returns an id and a name and no balance, and
	grants nothing on its own. A permission-checked read would make the answer
	depend on whether the caller may browse the customer list, which is a
	different question and one almost every reader of this page answers no to.

	The name a party reads by is the doctype's own title field rather than a
	fourth column in `USER_LINKS`: every one of these has one, and a site that
	renames a customer's title field gets that here without an edit.
	"""
	meta = frappe.get_meta(party_type)
	title_field = meta.get_title_field()
	fields = ["name"] + ([title_field] if title_field != "name" else [])

	links = USER_LINKS[party_type]
	filters: dict = {}
	or_filters: dict = {}

	if links is None:
		names = frappe.get_all(
			PORTAL_USER,
			filters={"parenttype": party_type, "user": frappe.session.user},
			pluck="parent",
			parent_doctype=party_type,
		)
		if not names:
			return []
		filters = {"name": ["in", sorted(set(names))]}
	else:
		# A field this site's doctype does not have is dropped rather than asked
		# for: a missing column fails the whole read, where the honest answer is
		# that this is not one of the ways a login is named here. The same
		# filtering `registry.display_fields` does, for the same reason.
		present = [link for link in links if meta.has_field(link)]
		if not present:
			return []
		or_filters = dict.fromkeys(present, frappe.session.user)
		if party_type == "Employee":
			filters = session_employee_filters()
			# The login is already the `or_filters`; leaving it in `filters` too
			# would AND a condition that is also being ORed, which is how an
			# employee with a `user_id` and no `status` would slip through.
			filters.pop("user_id", None)

	rows = frappe.get_all(
		party_type,
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="name asc",
	)
	return [(row.name, row.get(title_field) or row.name) for row in rows]


def party_condition(table, type_field: str, name_field: str, parties: list[Party]):
	"""A `where` matching any of these parties, as pairs rather than as two lists.

	Written once because getting it wrong is silent. `party` is a Dynamic Link,
	so the doctype it points at is a separate column, and filtering on
	`party_type in (...) and party in (...)` matches the cross product: a
	Student whose id happens to equal an Employee id would collect the other
	person's ledger. The pair has to be matched as a pair, and every caller in
	this section goes through here so that only one of them has to remember.

	Returns `None` for no parties at all, which every caller reads as "there is
	nothing to look for" rather than issuing an unfiltered query.
	"""
	condition = None
	for party in parties:
		pair = (table[type_field] == party.party_type) & (table[name_field] == party.name)
		condition = pair if condition is None else (condition | pair)
	return condition
