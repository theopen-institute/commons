"""What the SPA needs before it can draw anything: its name, and its navigation.

One endpoint, answered once per page load. A production build never calls it --
`commons/www/commons.py` puts the same answer on `window` through the page's
boot data, so the sidebar has a name and its rows on first paint rather than
after a round trip. The Vite dev server serves `index.html` without the Jinja
pass, so there the frontend asks. That is the split `website_link.py` already
makes for the Website button, and this follows it.

Whitelisted, and the same answer either way. Nothing here is about the caller:
the title is the site's name for itself, and the workspaces are what the site
offers, not what this user may open -- see `workspaces.py` on why permission is
the frontend's half of the answer.
"""

import frappe

from commons.shell import workspaces

SETTINGS = "Commons Settings"

# What the sidebar says under the workspace when a site has not named itself.
# Also the field's own default, so the two agree; this is what answers for a
# site whose Single has never been saved, where there is no row to read at all.
DEFAULT_TITLE = "Commons"


def title() -> str:
	"""The name over the navigation, and the browser tab's.

	`Commons Settings` is a Single, so the field is a row in `tabSingles` rather
	than a column -- between this app being installed and its first migrate
	there is simply no row, and a site that has never opened the form has no
	value in it. Both read as unset here rather than as an empty sidebar.

	Read behind the same guard `workspaces.installed` explains: code lands
	before migrate runs it, and for that one window there is no doctype to read
	a Single of.
	"""
	stored = None
	if frappe.db.exists("DocType", SETTINGS, cache=True):
		stored = frappe.db.get_single_value(SETTINGS, "title")
	return (stored or "").strip() or DEFAULT_TITLE


@frappe.whitelist()
def get_shell() -> dict:
	"""The name and the navigation, together, because they are read together."""
	return {"title": title(), "workspaces": workspaces.workspaces()}
