"""What the sidebar offers, resolved from `Commons Workspace` documents.

One function matters -- `workspaces()` -- and it answers the same shape whether
a site has configured anything or not, because the sidebar should not have two
code paths for "a site that has been set up" and "a site that has not".

Three things are settled here rather than in the browser.

*Which rows, in what order, under which heading.* The order is the order of the
child table, and a heading is a row's own `group`: consecutive rows sharing one
are drawn as a section, and a row with none is drawn on its own above them. That
is the sidebar's existing shape -- an ungated row, then Profile, then Requests
-- expressed as configuration instead of as markup.

*What a row that points at configuration is called.* A `Self Service Record`
already carries a label and an icon, so a row pointing at one is resolved
against the registry here and the browser is told the answer. A row pointing at
a page this app ships carries no label unless someone typed an override; the
default belongs in the frontend, where the build can see the icon class written
down. See `pages.py`.

*What is not there any more.* A row naming a record type that has since been
disabled or deleted is dropped, and a workspace left with no rows at all is
dropped with it: the switcher would otherwise offer somewhere with nothing in
it, and the landing redirect would have nowhere to land.

Not settled here: whether *this user* may open any of it. Every row is sent to
everyone, and the frontend hides the ones this user has no permission for -- the
same split the self-service navigation already makes, for the same reason. A
workspace is a fact about the site; what is in it for you is a fact about you.

No cache. The registry behind `Self Service Record` is cached because it sits on
the path of every self-service permission check; this is two queries that run
once when the page boots, and a second cache would be a second thing to
invalidate for no measurable gain.
"""

import frappe

from commons.self_service import registry
from commons.shell.pages import DEFAULT_REQUEST_PAGES, PAGES

WORKSPACE = "Commons Workspace"
ITEM = "Commons Workspace Item"

# The workspace a site gets before it has said otherwise: the sidebar this app
# shipped when there was only one of these and it was a constant in the
# frontend. The title is the name that constant held.
DEFAULT_TITLE = "Staff Member"
DEFAULT_ICON = "lucide-inbox"

# Headings the default workspace groups its rows under. Configuration once a
# site writes its own workspace; here they are only what the old sidebar said.
PROFILE_GROUP = "Profile"
REQUESTS_GROUP = "Requests"


def workspaces() -> list[dict]:
	"""Every workspace this site offers, in sidebar order.

	The configured ones, or -- for a site that has configured none -- the single
	default. Never empty in the sense that matters: a site with no self-service
	and no workspaces still gets the default workspace with its ungated page in
	it, which is the sidebar it had before any of this was configurable.
	"""
	return _configured() or [_default()]


def installed() -> bool:
	"""Whether the workspace doctype is on this site yet.

	Asked because code lands before migrate runs, and this is read by the page's
	boot data -- so for one deploy window `Commons Workspace` is a doctype the
	bundle knows about and the database has never heard of. Without this the
	whole app would answer 500 until somebody migrated, which is a bad way to
	find out. Cached, so the usual answer costs a lookup rather than a query.
	"""
	return bool(frappe.db.exists("DocType", WORKSPACE, cache=True))


def _configured() -> list[dict]:
	"""The enabled `Commons Workspace` documents, resolved.

	Read with `frappe.get_all` and an explicit field list rather than as
	documents: this runs before the first page renders, and the child rows are
	the only second query it needs.
	"""
	if not installed():
		return []

	rows = frappe.get_all(
		WORKSPACE,
		filters={"enabled": 1},
		fields=["name", "title", "icon", "logo", "nav_order"],
		order_by="nav_order asc, title asc",
	)
	if not rows:
		return []

	items = frappe.get_all(
		ITEM,
		filters={"parent": ["in", [row.name for row in rows]], "parenttype": WORKSPACE},
		fields=["parent", "item_type", "page", "self_service_record", "item_group", "label", "icon", "idx"],
		order_by="parent asc, idx asc",
		parent_doctype=WORKSPACE,
	)
	by_parent: dict[str, list] = {}
	for item in items:
		by_parent.setdefault(item.parent, []).append(item)

	found: list[dict] = []
	for row in rows:
		entries = [
			entry for entry in (_entry(item) for item in by_parent.get(row.name) or []) if entry
		]
		if not entries:
			continue
		found.append(
			{
				"name": row.name,
				"title": row.title,
				"icon": row.icon or None,
				"logo": row.logo or None,
				"items": entries,
			}
		)
	return found


def _entry(row) -> dict | None:
	"""One child row as the sidebar needs it, or None if it no longer resolves."""
	group = row.item_group or None
	if row.item_type == "Page":
		key = PAGES.get(row.page)
		if not key:
			return None
		return _item("page", key, group, label=row.label or None, icon=row.icon or None)

	# The link is a `Self Service Record`, whose docname *is* the doctype it
	# governs (`autoname: field:document_type`), which is also how the registry
	# is keyed. A record that has since been disabled or deleted is absent from
	# the registry, and its row goes with it.
	policy = registry.policies().get(row.self_service_record)
	if not policy:
		return None
	return _item(
		"record",
		policy["doctype"],
		group,
		label=row.label or policy["label"],
		icon=row.icon or policy["icon"],
		slug=policy["slug"],
	)


def _item(
	kind: str,
	key: str,
	group: str | None,
	label: str | None = None,
	icon: str | None = None,
	slug: str | None = None,
) -> dict:
	"""One sidebar row.

	`label` and `icon` are null for a page nobody overrode: the frontend holds
	what a page this app ships is called and drawn with, and a null here means
	"whatever you call it". For a record they are always filled, because the
	record says.
	"""
	return {
		"kind": kind,
		"key": key,
		"slug": slug,
		"group": group,
		"label": label,
		"icon": icon,
	}


def _default() -> dict:
	"""The sidebar this app had before workspaces were documents.

	Built from whatever self-service the site has configured rather than from a
	fixed list, so the record types that used to appear under Profile still do.
	A site that installs this app and never opens `Commons Workspace` sees no
	change at all -- which is the only honest default for a feature that is
	about renaming things.
	"""
	items = [_item("page", PAGES["Announcements"], None)]
	for doctype in registry.registered():
		policy = registry.policy(doctype)
		items.append(
			_item(
				"record",
				doctype,
				PROFILE_GROUP,
				label=policy["label"],
				icon=policy["icon"],
				slug=policy["slug"],
			)
		)
	items += [_item("page", key, REQUESTS_GROUP) for key in DEFAULT_REQUEST_PAGES]
	return {
		"name": None,
		"title": DEFAULT_TITLE,
		"icon": DEFAULT_ICON,
		"logo": None,
		"items": items,
	}


def claimed_elsewhere(workspace: str | None) -> dict[tuple[str, str], str]:
	"""Which rows every *other* enabled workspace has already taken.

	Keyed by the pair a row is identified by -- its type and what it points at --
	and valued by the workspace holding it, so a refusal can name the one you
	would be taking it from. Used by `CommonsWorkspace.validate`; see there for
	why a page or a record may only be in one place.

	Two queries rather than a join: a child row carries no copy of its parent's
	`enabled`, and the parents are a handful of rows.
	"""
	if not installed():
		return {}

	others = [
		row.name
		for row in frappe.get_all(WORKSPACE, filters={"enabled": 1}, fields=["name"])
		if row.name != workspace
	]
	if not others:
		return {}

	rows = frappe.get_all(
		ITEM,
		filters={"parenttype": WORKSPACE, "parent": ["in", others]},
		fields=["parent", "item_type", "page", "self_service_record"],
		parent_doctype=WORKSPACE,
	)
	taken: dict[tuple[str, str], str] = {}
	for row in rows:
		target = row.page if row.item_type == "Page" else row.self_service_record
		if target:
			taken[(row.item_type, target)] = row.parent
	return taken
