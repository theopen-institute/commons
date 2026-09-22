"""This app's own settings, and the one thing in them so far: what it is called.

The document is `Commons Settings`, a Single with one field, and it lives here
rather than with the navigation it names because it is a fact about the *app*
rather than about the sidebar. The sidebar is one reader of it; the browser tab
is another, and the desk's Awesome Bar labels this app's pages with it
(`commons.shell.search`). A second setting that had nothing to do with navigation
would belong here too, which is the test that settled where it goes.

Reading it is one line and one caveat, so the reader sits beside the document
rather than in each caller.
"""

import frappe

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

	Read behind the same guard `shell.workspaces.installed` explains: code lands
	before migrate runs it, and for that one window there is no doctype to read
	a Single of.
	"""
	stored = None
	if frappe.db.exists("DocType", SETTINGS, cache=True):
		stored = frappe.db.get_single_value(SETTINGS, "title")
	return (stored or "").strip() or DEFAULT_TITLE
