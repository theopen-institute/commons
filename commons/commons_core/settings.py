"""This app's own settings: what it is called, and the switches for the places it
changes Frappe's own behaviour.

The document is `Commons Settings`, a Single, and it lives here rather than with
any one section because it is a fact about the *app*. Its General tab holds the
title, the landing page and the Bikram Sambat switch; Better Navigation and Core
Overrides hold the rest of the switches read below; Requests, Attendance and Data Sync hold the policy those
sections read for themselves. The title has the most readers: the sidebar, the
browser tab, and the desk's Awesome Bar, which labels this app's pages with it
(`commons.better_navigation.search`).

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
	stored = (_settings() or {}).get("title")
	return (stored or "").strip() or DEFAULT_TITLE


def _settings():
	"""The cached settings document, or None between this app landing and its migrate.

	Asked on every request, so the missing-doctype case is the exception path
	rather than an existence query up front: `DocType` lookups are cached only
	for the request, so checking first cost a query on every one. Frappe raises
	`ImportError` for a Single whose doctype isn't there; the same error from a
	doctype that *is* there is a real fault, and is raised.
	"""
	try:
		return frappe.get_cached_doc(SETTINGS)
	except (ImportError, frappe.DoesNotExistError):
		if frappe.db.exists("DocType", SETTINGS):
			raise
		return None


# Optional features
# -----------------
# Each is opt-in: a site that never ticked one runs Frappe's own behaviour.

# `commons/public/js/bikram_sambat/`. Additive -- nothing is stored in Bikram
# Sambat -- so it sits in the form's main section, not among the overrides.
ENABLE_BIKRAM_SAMBAT = "enable_bikram_sambat"

# Everything below is a core override: a place this app changes how Frappe, or
# an app beside it, behaves, rather than adding beside it, and which leans on
# details of that code an upgrade can move. Each has a switch so that a site
# whose desk, permissions or books start misbehaving can rule them out first,
# without a deploy.

# Better Navigation, on a tab of its own in the form. The desk's navigation -- the
# rail, the Apps screen and the desk's user menu -- is Open Desk's now; what is left
# here is this app's own frontend and two desk additions (`commons.better_navigation`).

# The frontend's user menu (`commons.better_navigation.user_menu.get_user_menu`)
ENABLE_USER_MENU = "enable_user_menu"
# `commons.better_navigation.home_page`, which preempts core's `get_home_page`
ENABLE_HOME_PAGE_PRIORITY = "enable_home_page_priority"
# `commons/public/js/desk_todos/`, which adds a To Do button and drawer beside
# Frappe's bell, in the sidebar or, with Open Desk's rail, on the rail
ENABLE_DESK_TODOS = "enable_desk_todos"

# The rest share the Core Overrides tab, a section per theme, in the order they
# are listed here.

# Desk.
# `commons/public/js/unencoded_at_in_routes.js`
ENABLE_UNENCODED_AT = "enable_unencoded_at_in_routes"
# `commons.pseudo_islands`, which installs frappe develop's `frappe.ui.mount_island`
# on a v16 desk and draws this app's island pages with it
ENABLE_PSEUDO_ISLANDS = "enable_pseudo_islands"

# Permissions and data.
# `commons.safer_permissions`, and the checkbox it draws in the Role Permission Manager
ENABLE_PERMISSION_GATE = "enable_user_permission_gate"
# `commons.derived_docfields`, which swaps core's query engine and document
# classes, and `commons/public/js/derived_docfields.js`
ENABLE_DERIVED_DOCFIELDS = "enable_derived_docfields"

# Email.
# `commons/public/js/email_composer.js`, which adds to core's email composer
ENABLE_VISUAL_EMAIL_EDITOR = "enable_visual_email_editor"

# Accounting: what ERPNext, HRMS and Lending write to the books.
# `commons.banking.payable_party`, which adds to ERPNext's Payment Entry ledger
# lines. Server-side only, so not among the desk's features.
ENABLE_PAYABLE_PARTY = "enable_party_on_payable_payment_lines"
# `commons.banking.payroll_lines`, which splits HRMS's payroll accrual journal.
# Server-side only too.
ENABLE_PAYROLL_LINES = "enable_payroll_lines_per_employee"
# `commons.banking.internal_transfers`, which sets the clearance date of journal
# entries that move no money at the bank. Server-side only too.
ENABLE_CLEAR_INTERNAL_TRANSFERS = "enable_clearing_internal_transfers"
# `commons.banking.loan_own_dates`, which keeps lending's vouchers and their GL on
# their own dates. Server-side only too.
ENABLE_LOAN_OWN_DATES = "enable_loan_vouchers_on_own_dates"

# Financial reports: what ERPNext's reports read back out of the books.
# `commons.banking.financial_statements`, which cuts ERPNext's report columns
# inside each fiscal year. Server-side only.
ENABLE_FISCAL_YEAR_COLUMNS = "enable_fiscal_year_columns"
# `commons.banking.financial_statements` again, and the report filter
# `commons/public/js/hide_internal_accounts.js` adds
ENABLE_HIDING_INTERNAL_ACCOUNTS = "enable_hiding_internal_accounts"

# Values rather than switches, read with `value`.

# `commons.banking.payroll_payments`: the Mode of Payment and the Reference No
# its "Create Payment Entries" dialog starts on. Blank for none.
PAYROLL_PAYMENT_MODE_OF_PAYMENT = "payroll_payment_mode_of_payment"
PAYROLL_PAYMENT_REFERENCE = "payroll_payment_reference"

# What the desk is told, under `frappe.boot.commons_features`: each key is the
# name the browser half checks, and each value the field that switches it.
DESK_FEATURES = {
	"bikram_sambat": ENABLE_BIKRAM_SAMBAT,
	"unencoded_at_in_routes": ENABLE_UNENCODED_AT,
	"user_permission_gate": ENABLE_PERMISSION_GATE,
	"user_menu": ENABLE_USER_MENU,
	"derived_docfields": ENABLE_DERIVED_DOCFIELDS,
	"visual_email_editor": ENABLE_VISUAL_EMAIL_EDITOR,
	"pseudo_islands": ENABLE_PSEUDO_ISLANDS,
	"desk_todos": ENABLE_DESK_TODOS,
	"hide_internal_accounts": ENABLE_HIDING_INTERNAL_ACCOUNTS,
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
	doc = _settings()
	return bool(doc and doc.get(fieldname))


def value(fieldname: str) -> str | None:
	"""A setting's stored value, stripped, or None when it is blank or the
	doctype is not there yet."""
	doc = _settings()
	stored = doc.get(fieldname) if doc else None
	return (stored.strip() if isinstance(stored, str) else stored) or None


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Tell the desk which of its patches to install.

	Read once, when the scripts load, so a change reaches a user on their next reload.
	The home page is not here: it is decided on the server, per request.
	"""
	bootinfo.commons_features = {key: feature_enabled(field) for key, field in DESK_FEATURES.items()}
