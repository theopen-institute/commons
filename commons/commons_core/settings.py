"""This app's own settings: what it is called, and the switches for the places it
changes Frappe's own behaviour.

The document is `Commons Settings`, a Single with one field, and it lives here
rather than with the navigation it names because it is a fact about the *app*
rather than about the sidebar. The sidebar is one reader of it; the browser tab
is another, and the desk's Awesome Bar labels this app's pages with it
(`commons.better_navigation.search`). A second setting that had nothing to do with navigation
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

	Read behind the same guard `better_navigation.workspaces.installed` explains: code lands
	before migrate runs it, and for that one window there is no doctype to read
	a Single of.
	"""
	stored = None
	if frappe.db.exists("DocType", SETTINGS, cache=True):
		stored = frappe.db.get_single_value(SETTINGS, "title")
	return (stored or "").strip() or DEFAULT_TITLE


# Optional features
# -----------------
# Each is opt-in: a site that never ticked one runs Frappe's own behaviour.

# `commons/public/js/bikram_sambat/`. Additive -- nothing is stored in Bikram
# Sambat -- so it sits in the form's main section, not among the overrides.
ENABLE_BIKRAM_SAMBAT = "enable_bikram_sambat"

# Better Navigation: overrides too, of the desk's navigation, grouped in the
# form because they are one design with this app's own sidebar
# (`commons.better_navigation`).

# `commons/better_navigation/js/navigation_rail.js`, from the apps
# `commons.better_navigation.navigation_apps` resolves
ENABLE_NAVIGATION_RAIL = "enable_navigation_rail"
# `commons/better_navigation/js/user_menu.js`, and the frontend's copy of the
# same menu (`commons.better_navigation.user_menu.get_user_menu` says which)
ENABLE_USER_MENU = "enable_user_menu"
# `commons/better_navigation/js/workspace_sidebar_memory.js`
ENABLE_SIDEBAR_MEMORY = "enable_sidebar_memory"
# `commons.better_navigation.home_page`, which preempts core's `get_home_page`
ENABLE_HOME_PAGE_PRIORITY = "enable_home_page_priority"

# Core behaviour overrides: the places this app changes how Frappe itself
# behaves, rather than adding beside it, and which lean on details of core that
# an upgrade can move. Each has a switch so that a site whose desk or
# permissions start misbehaving can rule them out first, without a deploy.

# `commons/public/js/unencoded_at_in_routes.js`
ENABLE_UNENCODED_AT = "enable_unencoded_at_in_routes"
# `commons.safer_permissions`, and the checkbox it draws in the Role Permission Manager
ENABLE_PERMISSION_GATE = "enable_user_permission_gate"
# `commons.derived_docfields`, which swaps core's query engine and document
# classes, and `commons/public/js/derived_docfields.js`
ENABLE_DERIVED_DOCFIELDS = "enable_derived_docfields"
# `commons/public/js/email_composer.js`, which adds to core's email composer
ENABLE_VISUAL_EMAIL_EDITOR = "enable_visual_email_editor"

# What the desk is told, under `frappe.boot.commons_features`: each key is the
# name the browser half checks, and each value the field that switches it.
DESK_FEATURES = {
	"bikram_sambat": ENABLE_BIKRAM_SAMBAT,
	"unencoded_at_in_routes": ENABLE_UNENCODED_AT,
	"user_permission_gate": ENABLE_PERMISSION_GATE,
	"sidebar_memory": ENABLE_SIDEBAR_MEMORY,
	"user_menu": ENABLE_USER_MENU,
	"navigation_rail": ENABLE_NAVIGATION_RAIL,
	"derived_docfields": ENABLE_DERIVED_DOCFIELDS,
	"visual_email_editor": ENABLE_VISUAL_EMAIL_EDITOR,
}


def feature_enabled(fieldname: str) -> bool:
	"""Whether a site has switched on the feature behind an `ENABLE_*` field.

	Off until somebody says otherwise. A Check with no row in `tabSingles` --
	a site that has never saved the form, or saved it before the field existed --
	reads as 0, which is exactly that; so does a site with no doctype yet.

	Read through the document cache rather than `get_single_value`: the gate asks
	this on every permission check and the home page on every request, and a
	save clears the cached copy.
	"""
	if not frappe.db.exists("DocType", SETTINGS, cache=True):
		return False
	return bool(frappe.get_cached_doc(SETTINGS).get(fieldname))


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Tell the desk which of its patches to install.

	Read once, when the scripts load, so a change reaches a user on their next reload.
	The home page is not here: it is decided on the server, per request.
	"""
	bootinfo.commons_features = {key: feature_enabled(field) for key, field in DESK_FEATURES.items()}
