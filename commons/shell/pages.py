"""The pages this app ships, as a workspace is allowed to name them.

A workspace row is one of two things: a `Self Service Record`, which is
configuration and says its own name, or one of the pages below, which is code.
This module is the list of the second kind.

The values are the keys the API sends and `frontend/src/data/shell.ts` resolves
-- into a route, into whether this user may open it at all, and, for the three
request sections, into the badge an approver reads. The two halves have to agree
on this set, the way `hooks.py` and the old frontend app registry had to agree
on theirs.

The dictionary keys are what a System Manager picks in the desk, and they are
worded as the sidebar words the row rather than as the code spells it -- the
person choosing is choosing a row they have seen. They are stored values, so
`commons_workspace_item.json` lists exactly these as the Select's options
and `CommonsWorkspaceItem.validate` refuses anything else; a rename here is a
rename there and a patch for anything already saved.

Deliberately not here: the label and the icon each page is drawn with. Those
live in the frontend, because a Tailwind build can only compile an icon class it
can see written down in the source it scans -- see `self_service/icons.py`,
which is the same problem solved the same way for the icons that *are*
configuration. A workspace row may still override either, and an override is
held to the icon palette for exactly that reason.
"""

from commons.requests.expense import EXPENSES
from commons.requests.leave import LEAVE
from commons.requests.procurement import PROCUREMENT
from commons.statement import ledger

PAGES: dict[str, str] = {
	"Announcements": "announcements",
	"Account Balance": "statement",
	"Leave Request": "leave",
	"Expense Claim": "expense",
	"Procurement": "procurement",
}

# What the default workspace holds when a site has configured no workspace of
# its own, in sidebar order: the ungated page first as a bare row, then
# everything self-service under one heading, then the three things a person
# raises under another. This is the sidebar this app hard-coded before
# workspaces were documents, and reproducing it exactly is the point.
DEFAULT_REQUEST_PAGES: tuple[str, ...] = ("leave", "expense", "procurement")


# The request section behind each page, for the pages that have one. The section
# already knows both things the navigation needs to ask -- what doctype the page
# stands on, and whether this site has what the section needs at all -- so this
# points at it rather than restating either.
#
# Announcements has no entry: the page is ungated and reads nothing, which is
# why it is also where bare `/commons` lands.
PAGE_SECTIONS = {
	"leave": LEAVE,
	"expense": EXPENSES,
	"procurement": PROCUREMENT,
}

# The same question for a page that is not a request section. `statement` is the
# only one so far and it is not an oversight that it has no `RequestType`: there
# is nothing to raise and nobody to approve it, so the shape the three request
# pages share has nothing to lend it -- what it has in common with them is only
# that it can be absent, and that is this line rather than a base class.
PAGE_AVAILABILITY = {
	"statement": ledger.available,
}

# The doctype whose read permission decides whether a page is worth offering to
# *this user*, which is a different question from whether the site has it at all
# -- see `search._page_row`, the one caller.
#
# `statement` is deliberately absent, and the absence is the point rather than an
# omission. The doctype behind it is `GL Entry`, whose read permission is an
# accountant's: gating the row on it would take the page away from every student,
# member and supplier it was written for and leave it to the only people who were
# never going to read their own balance on it. Who may see what is settled inside
# the page instead -- the reader's own parties, and nothing else exists for them
# to be offered.
PAGE_DOCTYPES: dict[str, str] = {key: section.doctype for key, section in PAGE_SECTIONS.items()}


def available(key: str) -> bool:
	"""Whether this site has what the page behind this row needs.

	The same answer the endpoints behind the page give -- literally the same
	call, `approvals.RequestType.available` -- asked again here because the two
	fail differently and both have to be right: an endpoint throws, and a row in
	the navigation would instead offer somewhere that cannot load. Leave and
	expenses are absent without HRMS and procurement without ERPNext; neither is
	spelled out here, because the section says.

	A page with neither a section nor an availability test is always available.
	Announcements is the only one, and it reads nothing.
	"""
	section = PAGE_SECTIONS.get(key)
	if section is not None:
		return section.available()
	check = PAGE_AVAILABILITY.get(key)
	return check is None or check()
