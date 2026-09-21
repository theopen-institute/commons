# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Which Role decides the home page when someone holds several.

`frappe.website.utils.get_home_page` takes the *first* of the user's roles that
names a home page and stops::

	for role in frappe.get_roles():
		home_page = frappe.db.get_value("Role", role, "home_page")
		if home_page:
			break

and `frappe.permissions.get_roles` has no `ORDER BY` in either branch -- a normal
user's roles come back in whatever order the `Has Role` child rows are stored in
(which reshuffles when the User is re-saved), and Administrator gets
`frappe.get_all("Role")`, every role on the site, unordered. So "first" means
"whatever the database happened to return first". Employee beat System Manager
here by accident, not by rule.

That loop cannot be sorted from outside, and the one hook core offers for this
(`get_website_user_home_page`) is consulted *after* it -- only when no role named
a home page at all. So this module preempts instead: `get_home_page` returns
`frappe.local.flags.home_page` untouched when it is set, and `before_request`
runs early enough (`frappe.app.init_request`, with the session already up) to set
it. Role.home_page stays exactly what it has always been; this only decides which
one of them is read.

Two things core does are deliberately left alone. A user's personal
`default_workspace` outranks every role rule -- core applies it last -- so a user
who has one is skipped entirely here. And a user whose roles name no home page at
all is skipped too, which leaves Portal Settings, the `home_page` hooks and
Website Settings to answer exactly as before.

Not to be confused with [website_link.py], which is where the *Website button*
goes. This one is the landing page.
"""

import frappe

FIELDNAME = "home_page_priority"


# One hash, keyed by user. Rebuilt by a single query, so clearing it wholesale on
# any Role change costs almost nothing.
CACHE_KEY = "commons_home_page"


def candidates(user: str) -> list[frappe._dict]:
	"""The user's roles that name a home page, most important first.

	One query rather than core's one per role, and the `order_by` is the whole
	point: a stable priority, then role name so that equal priorities -- which is
	every role until someone sets a number -- still resolve the same way twice.
	"""
	if not frappe.db.has_column("Role", FIELDNAME):
		# Installed but not yet migrated.
		return []

	roles = frappe.get_roles(user)
	if not roles:
		return []

	return frappe.get_all(
		"Role",
		# `is set` rather than a `not in ("", None)`, which SQL evaluates to NULL
		# for every row and quietly matches nothing.
		filters={"name": ("in", roles), "home_page": ("is", "set")},
		fields=["name", "home_page", FIELDNAME],
		order_by=f"{FIELDNAME} asc, name asc",
	)


def resolve(user: str) -> str:
	"""The home page this user's roles ask for, or "" to let core decide."""

	def _resolve() -> str:
		if frappe.db.get_value("User", user, "default_workspace"):
			# Core applies this after every other rule, so it outranks the roles.
			return ""

		rows = candidates(user)
		return rows[0].home_page.strip("/") if rows else ""

	return frappe.cache.hget(CACHE_KEY, user, _resolve) or ""


def set_home_page_flag() -> None:
	"""`before_request`: settle the home page before anything reads it.

	Runs on every request because there is no narrower seam -- the landing page is
	read by login, by `/`, and by the desk boot. The cost is one Redis hash read
	for a user whose answer is already known, and nothing at all for Guest.
	"""
	session = getattr(frappe.local, "session", None)
	user = session and session.user
	if not user or user == "Guest":
		# No session on OPTIONS requests, and Guest never had a role rule.
		return

	if frappe.local.flags.home_page:
		# Something upstream has decided already; do not second-guess it.
		return

	home_page = resolve(user)
	if home_page:
		frappe.local.flags.home_page = home_page


def clear_cache(doc=None, method=None) -> None:
	"""Drop every cached answer. Bound to Role, whose change can move anyone."""
	frappe.cache.delete_value(CACHE_KEY)


def clear_user_cache(doc, method=None) -> None:
	"""Drop one user's answer. Bound to User, which owns the `Has Role` rows."""
	frappe.cache.hdel(CACHE_KEY, doc.name)
