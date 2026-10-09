app_name = "commons"
app_title = "Commons"
app_publisher = "Peter"
app_description = "Shared tools for Frappe"
app_email = "pgraif@gmail.com"
app_license = "none"
# This app's logo where `add_to_apps_screen` below gives none; where it does, that
# one wins.
app_logo_url = "/assets/commons/images/commons-logo.svg"
# Commons' tile on Frappe's Apps screen (/desk), opening its own frontend. Open
# Desk's rail, where it is installed, offers the same address as the app's
# "Commons app" row, read from the boot's `app_data`, which Frappe builds from this
# hook.
add_to_apps_screen = [
	{
		"name": "commons",
		"logo": "/assets/commons/images/commons-logo.svg",
		"title": "Commons",
		"route": "/commons",
	}
]

# Apps
# ------------------

# Nothing but Frappe. This app uses ERPNext, HRMS, Lending and Education where a
# site runs them, and takes the features that need them away where it does not.
# Each such feature asks `commons.commons_core.apps` first.
#
# Which features those are: procurement, bank reconciliation, the financial
# statement overrides and Purchase Invoice capture need ERPNext; leave, expenses, receipt capture and the payroll extensions need HRMS;
# loan matching and loan dates need Lending; the attendance register needs
# Education. What is left on a bare Frappe site is self-service, workspaces and
# navigation, the permission gate, derived fields, email, print templates and
# the desk additions -- none of which reads another app's doctype.
#
# Two things had to hold before this could be empty, and both are worth knowing
# about before it is put back.
#
# The doctypes are not the obstacle. Frappe's app sync imports them with
# `ignore_validate`, so a Link field naming a doctype that is not on the site
# does not stop migrate; only writing a value into one fails, and a feature that
# has taken itself away writes none.
#
# The fixtures were, once: a Custom Field naming an absent doctype used to raise
# `LinkValidationError`, which escaped `import_fixtures` and aborted migrate for
# the whole site. Since Frappe 16.34 it raises `DoesNotExistError` instead, which
# `import_fixtures` catches, skipping that file. So the fields this app adds to
# ERPNext's doctypes are a fixture file of their own --
# `commons/fixtures/README.md` says why that is safe, and
# `commons.commons_core.test_fixtures` fails if it stops being.
required_apps = []

# Where the SPA lives. Every section below is served from one bundle under this
# prefix, so the route is written once.
app_home = "/commons"

# The SPA owns its own history, so every path under /commons has to resolve to
# the one built page (commons/www/commons.html) rather than 404 on a deep link
# or a refresh.
website_route_rules = [
	{"from_route": "/commons/<path:app_path>", "to_route": "commons"},
]

# Almost nothing is left here, and that is the point. The Apps screen tile is
# the `add_to_apps_screen` hook above; every Custom Field this app adds, to
# Frappe's doctypes, to ERPNext's, and the derived fields on its own, ships under
# `commons/fixtures/`, as do the Property Setters that go with them
# (`commons/fixtures/README.md` lists both). All of it is written by Frappe's own
# sync on install and on every migrate, and since 16.50 so are the `Module Def`
# rows of modules added to `modules.txt` after install. None of it needs a hook,
# and a hook that re-asserted it would only be a second, quieter copy of the
# same declaration.
#
# What is left are the things no sync does: making the doctype sync see a module
# added since the last migrate, getting a changed `page_js` in front of admins
# whose desks are still holding the last copy of it, and checking derived fields.
# Server-side caches need nothing: migrate's own `frappe.clear_cache()` drops
# every key the site has.
#
# No approval chain and no self-service configuration. Those are a System
# Manager's to set up on a new site, and a deploy is not where they get made.
# The app ships neither, and the code reads whatever a site has rather than
# assuming any particular shape -- see `commons.requests.procurement_workflow`
# and `commons.self_service.registry`.
after_install = ["commons.safer_permissions.install.sync_permission_manager"]
after_migrate = [
	"commons.safer_permissions.install.sync_permission_manager",
	# A migrate is when a doctype along some derived field's path most often
	# changes under it. Reports what no longer resolves; repairs nothing.
	"commons.derived_docfields.validation.check_all",
]

# Core writes a new module's `Module Def` before this runs, but the module map
# the doctype sync walks can still be the one cached before the pull, which
# would skip the new module's doctypes until the next migrate. See
# `commons.commons_core.install.refresh_module_map`.
before_migrate = [
	"commons.commons_core.install.refresh_module_map",
]

# Frappe's dock, the rail of an app's modules down the left of the desk, is a
# document an app ships as `<app>/dock/<app>/<app>.json`, not a hook. This app's
# lists the sidebars its modules ship under `<module>/sidebar/`. Modules whose
# pages and doctypes one of those sidebars carries are named hidden, so a rail
# leaves them off rather than listing them after; modules with nothing to open
# get no sidebar from Frappe and are not named. Open Desk's rail, where it is
# installed and on, shows apps instead and draws itself over the dock.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
#
# One bundle, loaded after core's own `app_include_js`, so the classes it patches
# already exist. `commons/public/js/commons.bundle.js` lists what is in it: the
# user menu's rows of this app's own, Desk To Do, the Bikram Sambat readout on Date and Datetime fields (a tooltip in tables), the Email
# menu and composer, print templates, derived fields, hiding cancelled documents
# and internal accounts, and the desk islands. Each draws itself only where its
# setting or its data says so.
app_include_js = "commons.bundle.js"
app_include_css = "commons.bundle.css"

# include js, css files in header of web template
# web_include_css = "/assets/commons/css/commons.css"
# web_include_js = "/assets/commons/js/commons.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "commons/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# The Payroll Entry form's "Create Payment Entries". See `commons.banking.payroll_payments`.
doctype_js = {"Payroll Entry": "public/js/payroll_entry.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "commons/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Setup Wizard
# ------------

# open a fresh site's setup in this app's own UI instead of the desk wizard.
# must be a non-desk route (not under /desk or /app); to customize setup within
# desk, use setup_wizard_stages / setup_wizard_complete instead.
# setup_wizard_url = "/commons/setup"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# What a print format, a letterhead or a web template on this site may call.
#
# Two entries, both exposed by name to every template on the site, not only to
# the formats this app creates.
#
# `make_qr_code` belongs to no section and is useful to any template that wants
# an image -- it lives in `commons/commons_core/jinja.py`, which is where a
# helper goes when the section it came from is not part of the answer. It came
# from the retired NepalERP app, whose own hook is where sites that print QR
# codes first got the name. It reads nothing and so has nothing to check.
#
# `render_web_template` prints one Web Template, a layout kept on the site, from
# as many doctypes' formats as call it, each through the template's own Context
# Prep. It reads only the `doc` its caller already holds. Data a layout needs
# from an app is fetched in the prep, through `frappe.call`, so no section's
# functions need a name in Jinja. See `commons.print_templates`.
jinja = {
	"methods": [
		"commons.commons_core.jinja.make_qr_code",
		"commons.print_templates.api.render_web_template",
	],
}

# Installation
# ------------

# before_install = "commons.install.before_install"

# Uninstallation
# ------------

# Frappe deletes by module, which is too little for this app's configuration and
# derived fields, and too much for a site's own records filed under its modules.
# This evens it out, refuses while such records are there, and warns where
# uninstalling widens access. See `commons.commons_core.uninstall`.
before_uninstall = "commons.commons_core.uninstall.before_uninstall"
# after_uninstall = "commons.uninstall.after_uninstall"

# Disable / Enable
# ----------------
# Called when this app is logically disabled or re-enabled on a site,
# without uninstalling it. Use this to hide/restore fields this app adds
# to other apps' doctypes.

# before_disable = "commons.uninstall.before_disable"
# after_disable = "commons.uninstall.after_disable"
# before_enable = "commons.install.before_enable"
# after_enable = "commons.install.after_enable"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "commons.utils.before_app_install"
# after_app_install = "commons.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "commons.utils.before_app_uninstall"
# after_app_uninstall = "commons.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "commons.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "commons.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "commons.notifications.get_notification_config"

# Awesome Bar
# -----------
# This app's pages, offered in the desk's own search box. The bar builds its
# results from `frappe.boot` -- doctypes, reports, workspaces -- so a page under
# `/commons` is invisible to it without this. See `commons/better_navigation/search.py`,
# which also explains why it offers pages and not documents.
awesomebar_search = ["commons.better_navigation.search.awesomebar_results"]

# Permissions
# -----------
# Role Permissions grant access to a whole doctype and User Permissions take
# most of it back, so the restriction is always the second step -- and a User
# Permission that was never created reads exactly like a user meant to see
# everything. `commons.safer_permissions.permissions` adds the missing third state: a role
# marked "Require User Permission" in the Role Permission Manager grants
# nothing until one exists.
#
# Registered against every doctype rather than a named few, because which
# doctypes are gated is configuration (a tick in the Role Permission Manager), not code.
# Both hooks can only deny, and both answer a cached dict lookup for doctypes
# nobody has gated.
permission_query_conditions = {
	"*": "commons.safer_permissions.permissions.permission_query_conditions",
}

has_permission = {
	"*": "commons.safer_permissions.permissions.has_permission",
	# A report's stored results are the rows themselves, and core lets anyone who
	# may access the report read them. Core registers its own hook for this
	# doctype too; both are consulted, and either can deny.
	"Prepared Report": "commons.safer_permissions.permissions.has_prepared_report_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	# Who lands where is cached per user, and both ends of the rule can move it:
	# a Role's home page or priority, and a User's own list of roles.
	"Role": {
		"on_update": "commons.better_navigation.home_page.clear_cache",
		# Not `on_trash`, which runs while the row is still there to be re-read.
		"after_delete": "commons.better_navigation.home_page.clear_cache",
	},
	"User": {
		"on_update": "commons.better_navigation.home_page.clear_user_cache",
	},
	# An account's scans may only be sorted into a kind this site captures.
	# See `commons.document_capture.capture.validate_email_account`.
	"Email Account": {
		"validate": "commons.document_capture.capture.validate_email_account",
	},
	# Every derived field is a Custom Field, from whichever door it came in by.
	# See `commons.derived_docfields.validation`.
	"Custom Field": {
		"before_validate": "commons.derived_docfields.validation.normalize",
		"validate": "commons.derived_docfields.validation.check",
		"on_update": "commons.derived_docfields.registry.clear",
		# Not `on_trash`, which runs while the row is still there to be re-read.
		"after_delete": "commons.derived_docfields.registry.clear",
	},
	# A journal entry that moves no money at the bank is cleared on its own date,
	# where Commons Settings switches it on. See `commons.banking.internal_transfers`.
	"Journal Entry": {
		"on_submit": "commons.banking.internal_transfers.clear_on_submit",
	},
	# A Material Request raised from a Procurement Request is what makes that
	# request "ordered", but nothing is written back to the request when it
	# happens: how much has been ordered is counted live from the submitted
	# Material Requests that point at it. What this checks is that those links
	# point at an approved request of the same company -- see
	# `commons.requests.material_request`.
	"Material Request": {
		"validate": "commons.requests.material_request.validate_procurement_links",
	},
	# A cancelled document's Notification emails that are still waiting in the
	# queue are not sent. See `commons.email_extensions.scheduled`.
	"*": {
		"on_cancel": "commons.email_extensions.scheduled.cancel_pending",
	},
	# Which doctypes delay a Notification's email is cached for the desk boot.
	# See `commons.email_extensions.scheduled.delayed_doctypes`.
	"Notification": {
		"on_update": "commons.email_extensions.scheduled.forget_delayed_doctypes",
		"after_delete": "commons.email_extensions.scheduled.forget_delayed_doctypes",
	},
	# A template designed in MJML is sent as the HTML it compiles to, compiled
	# here on every save. See `commons.email_extensions.mjml`.
	"Email Template": {
		"before_validate": "commons.email_extensions.mjml.compile_template",
	},
	# A Web Template's Context Prep is Python every print through it runs, so
	# only a Script Manager may change it. See `commons.print_templates`.
	"Web Template": {
		"validate": "commons.print_templates.api.validate_template",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"commons.tasks.all"
# 	],
# 	"daily": [
# 		"commons.tasks.daily"
# 	],
# 	"hourly": [
# 		"commons.tasks.hourly"
# 	],
# 	"weekly": [
# 		"commons.tasks.weekly"
# 	],
# 	"monthly": [
# 		"commons.tasks.monthly"
# 	],
# }

# Keeps the Bikram Sambat calendar current from opensource-nepal's. See
# `commons.sambat.table`.
scheduler_events = {
	"weekly": ["commons.sambat.table.refresh"],
}

# Testing
# -------

# before_tests = "commons.install.before_tests"

# Overriding Methods
# ------------------------------
#
# Query and Script Reports run the report author's SQL and consult neither
# permission hook, so a gated role cannot be shown one safely -- not even with
# its User Permission in place. These three wrappers refuse them; everything else
# about the reports is untouched.
#
# The one piece of the gate that stays in place with the gate switched off in
# Commons Settings, because hooks are read before any setting is. The wrappers
# then check nothing and forward to core. They are written to survive core
# changing underneath them -- see "Standing in front of core" in
# `commons.safer_permissions.permissions` -- and
# `test_permission_gate.CoreStillLooksTheSame` checks these paths against the
# installed Frappe: run it after every upgrade.
override_whitelisted_methods = {
	"frappe.desk.query_report.run": "commons.safer_permissions.permissions.run_query_report",
	"frappe.desk.query_report.export_query": "commons.safer_permissions.permissions.export_query_report",
	# Runs a report without going through either of the two above.
	"frappe.core.doctype.prepared_report.prepared_report.make_prepared_report": "commons.safer_permissions.permissions.make_prepared_report",
	# Not an override: v16 has no `frappe.utils.island`. The name is the one an
	# `<Island>` host calls on frappe develop, so it keeps working when v17
	# brings the real one and this line goes. See `commons/pseudo_islands/`.
	"frappe.utils.island.get_island_assets": "commons.pseudo_islands.registry.get_island_assets",
	# TEMPORARY: Frappe 16.50 cannot save a workspace from its editor (it rejects its
	# own request). Hands Frappe's function what it expects; delete the line, and
	# `commons.commons_core.frappe_fixes.save_page`, once Frappe fixes it.
	"frappe.desk.doctype.workspace.workspace.save_page": "commons.commons_core.frappe_fixes.save_page",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "commons.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------
# A `Record Change Request` points at the record it was about, and after a `New`
# request is approved it points at the record it created. That link would
# otherwise make the record undeletable by its own history -- including through
# the `Delete` requests this app offers, which is the shape that found it.
#
# Safe because the link is a record *about* the document rather than a dependency
# on it: every request captures `reference_title` when it is raised, so a settled
# request still says what it was about once the record is gone.
ignore_links_on_delete = ["Record Change Request"]

# Request Events
# ----------------
# Core picks the home page from whichever of the user's roles the database
# happened to return first -- see `commons/better_navigation/home_page.py`. That
# loop cannot be ordered from outside and the hook core offers runs after it, so
# the answer is settled here instead, early enough that login, `/` and the desk
# boot all see it. Does nothing unless Commons Settings switches it on.
#
# The second swaps core's query engine for one that knows derived fields --
# once per process, and inert per query until Commons Settings switches it on.
# See `commons.derived_docfields.install`.
before_request = [
	"commons.better_navigation.home_page.set_home_page_flag",
	"commons.derived_docfields.install",
	# ERPNext's financial reports, before any of them is first run in the process.
	# See `commons.banking.financial_statements`.
	"commons.banking.financial_statements.install",
]
# after_request = ["commons.utils.after_request"]

# At `POST /login` the session is still Guest's when `before_request` runs, so the
# login redirect is settled here instead. See `commons.better_navigation.home_page`.
on_login = ["commons.better_navigation.home_page.set_home_page_on_login"]

# Job Events
# ----------
# The workers run queries too, so they get the same engine the web does; and
# prepared reports run there, so they get the same financial statements.
before_job = ["commons.derived_docfields.install", "commons.banking.financial_statements.install"]
# after_job = ["commons.utils.after_job"]

# after_file_upload = ["commons.utils.after_file_upload"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"commons.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# Extend DocType Class
# ------------------------------
# Mixins over another app's controller, applied on top of whatever class that
# doctype already has, `override_doctype_class` included. The banking ones each
# do nothing until their Commons Settings switch is on.
extend_doctype_class = {
	# A Notification's Email Template is rendered with `doc`, `alert` and
	# `comments`, as its own message is, and a Notification set to Once Across
	# Amendments skips a document amended from one it already emailed about. See
	# `commons.email_extensions.notification`.
	"Notification": ["commons.email_extensions.notification.TemplateNotificationMixin"],
	# An Auto Email Report runs its report without the endpoints the permission
	# gate stands in front of. See `commons.safer_permissions.auto_email_report`.
	"Auto Email Report": ["commons.safer_permissions.auto_email_report.GatedAutoEmailReport"],
	# A payment's party on its tax and deduction lines to payable accounts, such
	# as TDS. Extended rather than overridden, so it sits on top of HRMS's own
	# Payment Entry class. See `commons.banking.payable_party`.
	# An employee's payment may also settle their salary on a payroll run. See
	# `commons.banking.payroll_payments`.
	"Payment Entry": [
		"commons.banking.payable_party.PayablePartyPaymentEntryMixin",
		"commons.banking.payroll_payments.PayrollPaymentEntryMixin",
	],
	# A payroll run's accrual journal split per employee, with their department
	# and, on payable accounts, their party. See `commons.banking.payroll_lines`.
	"Payroll Entry": ["commons.banking.payroll_lines.EmployeePayrollLinesMixin"],
	# Lending's vouchers and their GL on their own dates, not the day they are
	# saved. See `commons.banking.loan_own_dates`.
	"Loan Repayment": ["commons.banking.loan_own_dates.OwnDateLoanRepaymentMixin"],
	"Loan Write Off": ["commons.banking.loan_own_dates.OwnDateLoanWriteOffMixin"],
	"Loan Disbursement": ["commons.banking.loan_own_dates.OwnDateLoanDisbursementMixin"],
}

# The gate checkbox is drawn next to "Only if Creator" rather than among the
# rights, because it scopes rows rather than granting a right.
page_js = {"permission-manager": "public/js/permission_manager_gate.js"}


extend_bootinfo = [
	# Which of the desk patches Commons Settings switches on.
	"commons.commons_core.settings.extend_bootinfo",
	# Which Email Templates each doctype's forms offer, so a form can draw its
	# Email menu without asking. See `commons.email_extensions`.
	"commons.email_extensions.api.extend_bootinfo",
	# The islands this site has, which frappe develop sends itself and v16 does
	# not, when Commons Settings switches desk islands on.
	"commons.pseudo_islands.boot.extend_bootinfo",
]
