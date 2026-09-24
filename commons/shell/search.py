"""Search, in both directions: this app's pages in the desk's bar, and the desk's
doctypes in this app's.

`awesomebar_results` is the outward half and `desk_doctypes` the inward one. They
are in one module because they are one idea -- a person who works in both places
should not have to remember which search box they are standing in front of -- and
because the argument for each is the mirror of the argument for the other.

The hook `frappe.desk.search.awesomebar_search` collects the first, and the reason
it is worth filling in is that the desk's bar is the one search box a person who
works in both places already has their hands on. Everything this app offers lives
under `/commons`, which the bar cannot reach on its own: its built-in results
are built from `frappe.boot` -- doctypes, reports, workspaces -- and a page that
is none of those is invisible to it. Type "leave" in the desk and you get the
Leave Application list; this module is what also offers the leave page a person
actually raises leave on.

Two things are settled here, and both are settled the way the sidebar settles
them.

*Which rows exist* is the site's, read from the same `Commons Workspace`
documents the sidebar is drawn from (`shell.workspaces`), so a site that renamed
a row or moved it to another workspace gets the renamed row here too, and a row
nobody configured is offered nowhere.

*Whether this user may open one* is this module's, and it is the half the
sidebar leaves to the browser -- see `shell/workspaces.py` on why. A search
result is not a sidebar row: it is offered to somebody who is not looking at the
page and cannot see that it would be empty, so the permission answer has to be
in before the row is sent rather than after.

What is deliberately not here, on the outward side: documents. The bar already
searches every doctype this user can read, and the desk's Global Search already
finds an individual leave application. Offering the same documents again under a
`/commons` route would be two answers to one question, and the second one would
be worse -- a self-service page shows you *your* record, not the one you
searched for.

The inward side is `desk_doctypes`, and it exists because the SPA has no boot.
The desk builds "Employee List" and "New ToDo" in the browser out of
`frappe.boot.user.can_read`, `can_search` and `can_create`, which are four
arrays a page outside `/app` never receives. This sends the same four, so that
bar can build the same rows.

Why this is part of the shell
-----------------------------
It was at the app root, on the grounds that a hook Frappe calls is not any one
section's. But what it searches is the navigation: every row it offers comes
from `workspaces.py` and `pages.py`, and what it may offer comes from
`PAGE_ACCESS` beside them. A search box is a second way into the sidebar rather
than a thing of its own, so it belongs with the sidebar -- and the dependency
already ran this way round, with `pages.py` naming `_page_row` as its one
caller and nothing under `shell/` importing back into here.
"""

import unicodedata

import frappe
from frappe.boot import get_tree_view_doctypes

from commons.commons_core import settings
from commons.self_service import registry
from commons.shell import pages as page_list
from commons.shell import workspaces
from commons.shell.pages import PAGE_ACCESS, PAGE_DOCTYPES, PAGES

# Where each shipped page lives, under `hooks.app_home`. The frontend's router
# is the authority on these (`frontend/src/router.ts`) and this is a second copy
# of its paths, which is the price of the bar being a desk feature: the
# hook runs on the server, and the routes it has to name are in a bundle the
# server never loads. Kept to the shipped pages, and kept next to the keys they
# belong to, so a route that moves is one line here rather than a search.
#
# `expense` is `/expenses` -- the page is plural and the key is not. That is the
# kind of thing this map exists to get right.
PAGE_PATHS: dict[str, str] = {
	"announcements": "/commons/announcements",
	"statement": "/commons/account",
	"leave": "/commons/requests/leave",
	"expense": "/commons/requests/expenses",
	"procurement": "/commons/requests/procurement",
	"attendance": "/commons/attendance",
	"reconciliation": "/commons/banking",
}

# What a page is called when the workspace row carrying it typed no override.
# `PAGES` maps the wording a System Manager picks in the desk to the key the
# frontend resolves, and inverted it is exactly that wording back again -- which
# is the right label here even though the sidebar's default label lives in the
# frontend (see `shell/pages.py`). A person searching the desk is searching for
# the row they chose in the desk.
PAGE_LABELS: dict[str, str] = {key: label for label, key in PAGES.items()}


def awesomebar_results(txt: str) -> list[dict]:
	"""Rows for the desk's Awesome Bar: this app's pages, scored against `txt`.

	Ranked on the bar's own scale -- see `score` -- so a commons page and a
	doctype the bar found itself sort against each other rather than by which
	list they came from.
	"""
	keywords = (txt or "").strip()
	if not keywords:
		return []

	suffix = settings.title()
	found = []
	for row in _rows():
		matched = score(keywords, row["label"])
		if matched:
			found.append(
				{
					"label": row["label"],
					"description": suffix,
					"route": row["path"],
					"index": matched,
				}
			)
	return found


def _rows() -> list[dict]:
	"""Every page of this app the session user can open, as label and path.

	Walked out of the workspaces rather than out of `PAGE_PATHS`, because a page
	is only offered where a site has put it: a workspace row is what makes a
	page part of this app's navigation, and a site that removed one has said it
	does not want it.

	Deduplicated on the path. A page may only sit in one workspace
	(`CommonsWorkspace.validate_rows`), so in practice this only catches a
	self-service record type reached under two names -- but the bar
	deduplicates on route anyway, and doing it here means the row that survives
	is the first one configured rather than the first one scored.
	"""
	rows: list[dict] = []
	seen: set[str] = set()
	for workspace in workspaces.workspaces():
		for item in workspace["items"]:
			row = _page_row(item) if item["kind"] == "page" else _record_row(item)
			if not row or row["path"] in seen:
				continue
			seen.add(row["path"])
			rows.append(row)
	return rows


def _page_row(item: dict) -> dict | None:
	"""One shipped page, or None if this user has no business being offered it."""
	path = PAGE_PATHS.get(item["key"])
	if not path:
		return None

	# `workspaces` has already dropped the rows whose doctype is not on this
	# site, so in practice this only guards a caller that built an item some
	# other way -- but `has_permission` reads the doctype's meta, and asking it
	# about a doctype that does not exist is how that becomes a 500 rather than
	# a missing row.
	if not page_list.available(item["key"]):
		return None

	doctype = PAGE_DOCTYPES.get(item["key"])
	if doctype and not frappe.has_permission(doctype, "read"):
		return None

	# And the pages whose offer is not a read permission over a doctype. One so
	# far, and the bar has to agree with the sidebar about it: a student who is
	# not offered the attendance register in the navigation must not find it by
	# typing three letters into the desk. See `PAGE_ACCESS`.
	access = PAGE_ACCESS.get(item["key"])
	if access and not access():
		return None

	return {"label": item["label"] or PAGE_LABELS.get(item["key"], item["key"]), "path": path}


def _record_row(item: dict) -> dict | None:
	"""One self-service page.

	Offered whatever this user's permissions say, which is the one place this
	module parts company with the rule above -- and it is the same call
	`data/shell.ts` makes for the same reason: the page explains an account with
	no record of its own, or one it may not read, far better than a missing row
	does. The record itself is read by the page through the ordinary document
	API, so nothing is disclosed by offering the address of it.
	"""
	if not item["slug"]:
		return None
	return {"label": item["label"] or item["key"], "path": f"/commons/profile/{item['slug']}"}


@frappe.whitelist()
def desk_doctypes() -> dict:
	"""The doctypes this user may open in the desk, as the SPA's search bar needs them.

	`frappe.boot.get_user` hands the desk four lists and the desk's
	`search_utils.get_doctypes` walks them: everything readable, which of those
	has a list view, which may be created, and which are Singles or trees. The
	SPA has no boot, so this is that answer as an endpoint.

	The shape is the answer rather than the ingredients. The desk receives
	`can_read` and intersects it in the browser; this intersects here, where the
	sets already are, and sends four lists a caller can use without knowing how
	Frappe layers a permission. `search` is the master list -- a doctype with no
	list view is not somewhere you can be sent -- and `singles` are the ones that
	are a document rather than a list.

	Refused to anyone whose roles do not open the desk, and refused rather than
	filtered: every row built from this is a `/app` route, so for that person the
	whole answer is dead ends. It is also the honest reading of a whitelisted
	endpoint that would otherwise enumerate a site's schema for a website user
	who can reach none of it.
	"""
	if not _has_desk_access():
		return {"search": [], "create": [], "singles": [], "trees": []}

	user = frappe.get_user()
	# Builds the permission lists if they have not been built for this request;
	# reading the other three attributes directly would find them empty.
	can_read = set(user.get_can_read())
	can_search = set(user.can_search)
	can_create = set(user.can_create)

	singles = set(frappe.get_all("DocType", {"issingle": 1}, pluck="name"))
	trees = set(get_tree_view_doctypes())

	return {
		"search": sorted(can_search),
		"create": sorted(can_create),
		"singles": sorted(singles & can_read),
		"trees": sorted(trees & can_search),
	}


def _has_desk_access() -> bool:
	"""Whether any of the session user's roles opens the desk.

	The same question `commons/www/commons.py` puts on the page's boot data for
	the frontend to gate on. Asked again here rather than trusted from there: a
	whitelisted endpoint is reachable without the page that boots it.
	"""
	if frappe.session.user == "Guest":
		return False
	return bool(frappe.get_cached_doc("User", frappe.session.user).has_desk_access())


# The bar's own scoring constants, from
# frappe/public/js/frappe/ui/toolbar/fuzzy_match.js. Copied rather than
# approximated because the number this module returns as `index` is sorted
# directly against the numbers that file produces for every built-in row: a
# scale of its own would put this app's pages either always above the desk's
# results or always below them, whatever the person actually typed.
SEQUENTIAL_BONUS = 25
SEPARATOR_BONUS = 30
CAMEL_BONUS = 30
FIRST_LETTER_BONUS = 15

LEADING_LETTER_PENALTY = -5
MAX_LEADING_LETTER_PENALTY = -15
UNMATCHED_LETTER_PENALTY = -1


def score(pattern: str, text: str) -> int:
	"""How well `text` matches `pattern`, on the Awesome Bar's scale. 0 for no match.

	A subsequence match with the bar's bonuses: adjacency, a match after a
	separator, a capital following a lowercase, and the first letter; against
	penalties for leading unmatched letters and for length that went unmatched.

	One deliberate difference from the JavaScript. `fuzzy_match` recurses to find
	the *best* placement of the pattern when a letter occurs more than once --
	matching "ae" in "leave" at positions 3,4 rather than at 1,4 -- and this
	takes the first placement it finds, left to right. The two agree except when
	a later placement would have scored higher, and what is being matched here
	is a handful of two- and three-word page names where they do not diverge in
	practice. The alternative was carrying a port of a recursive search that has
	to stay in step with a file in another app; this is the part of it that
	earns its keep.
	"""
	if not pattern or not text:
		return 0

	matches: list[int] = []
	index = 0
	for position, char in enumerate(text):
		if index >= len(pattern):
			break
		if _fold(pattern[index]) == _fold(char):
			matches.append(position)
			index += 1

	if index < len(pattern):
		return 0

	total = 100
	total += max(LEADING_LETTER_PENALTY * matches[0], MAX_LEADING_LETTER_PENALTY)
	total += UNMATCHED_LETTER_PENALTY * (len(text) - len(matches))

	for order, position in enumerate(matches):
		if order > 0 and position == matches[order - 1] + 1:
			total += SEQUENTIAL_BONUS
		if position == 0:
			total += FIRST_LETTER_BONUS
			continue
		neighbour = text[position - 1]
		if neighbour != neighbour.upper() and text[position] != text[position].lower():
			total += CAMEL_BONUS
		if neighbour in ("_", " "):
			total += SEPARATOR_BONUS

	return total


def _fold(char: str) -> str:
	"""One character as the matcher compares it: accents dropped, lowercased.

	The same normalisation `fuzzy_match` does per character, so "Genève" is
	found by typing "geneve" here exactly as it is in the desk.
	"""
	stripped = "".join(
		part for part in unicodedata.normalize("NFD", char) if not unicodedata.combining(part)
	)
	return stripped.lower()
