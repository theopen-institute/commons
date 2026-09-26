app_name = "commons"
app_title = "Commons"
app_publisher = "Peter"
app_description = "Shared tools for Frappe"
app_email = "pgraif@gmail.com"
app_license = "none"

# Send non-GET requests for this app's endpoints as native `application/json`
# bodies instead of form-encoded, per-key JSON-stringified values.
use_json_request_body = True

# Apps
# ------------------

# Nothing but Frappe. This app uses ERPNext and HRMS where a site runs them and
# takes the features that need them away where it does not -- see
# `commons.commons_core.apps`, and `approvals.RequestType.available`, which is the one
# question every such feature asks.
#
# Which features those are: leave and expenses are HRMS doctypes end to end, and
# procurement spends against a Company, orders Items in a UOM and hands over to
# a Material Request, so it needs ERPNext. What is left on a bare Frappe site is
# self-service, announcements, workspaces, the permission gate and the desk
# additions -- none of which reads another app's doctype.
#
# Two things had to change before this could be empty, and both are worth
# knowing about before it is put back.
#
# The doctypes are not the obstacle. Frappe's app sync imports them with
# `ignore_validate`, so a Link field naming a doctype that is not on the site
# does not stop migrate; only writing a value into one fails, and a feature that
# has taken itself away writes none.
#
# The fixtures were, once: a Custom Field naming an absent doctype used to raise
# `LinkValidationError`, which escaped `import_fixtures` and aborted migrate for
# the whole site. On Frappe 16.34 it raises `DoesNotExistError` instead, which
# `import_fixtures` catches, skipping that file. So the fields this app adds to
# ERPNext and Education are fixtures, one file per app --
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

# Almost nothing is left here, and that is the point. The desk icon ships as a
# file under `commons/desktop_icon/`; every Custom Field this app adds, to
# Frappe's doctypes, to ERPNext's and Education's, and the derived fields on its
# own, ships under `commons/fixtures/`, as do the Property Setters that go with
# them (`commons/fixtures/README.md` lists both). All of it is written by
# Frappe's own sync on install and on every migrate. None of it needs a hook,
# and a hook that re-asserted it would only be a second, quieter copy of the
# same declaration.
#
# What is left are the things no sync can do: registering this app's modules,
# dropping a cache whose key `frappe.clear_cache` does not know about, and
# getting a changed `page_js` in front of admins whose desks are still holding
# the last copy of it.
#
# No approval chain, no self-service configuration and no statement print
# formats. Those are a System Manager's to set up on a new site, and a deploy is
# not where they get made. The app ships none of them in any form, and the code
# reads whatever a site has rather than assuming any particular shape -- see
# `commons.requests.procurement_workflow`, `commons.self_service.registry` and
# `commons.statement.api.download_statement`.
after_install = [
	"commons.self_service.install.sync_self_service",
	"commons.safer_permissions.install.sync_permission_manager",
]
after_migrate = [
	# The other half of `before_migrate`'s module registration: records for
	# modules this app no longer has, removed once the sync has moved whatever
	# used to name them. See `commons.commons_core.install.drop_stale_module_defs`.
	"commons.commons_core.install.drop_stale_module_defs",
	"commons.self_service.install.sync_self_service",
	"commons.safer_permissions.install.sync_permission_manager",
	# A migrate is when a doctype along some derived field's path most often
	# changes under it. Reports what no longer resolves; repairs nothing.
	"commons.derived_docfields.validation.check_all",
	# An app installed or removed changes the rail's inputs without a doc event.
	"commons.better_navigation.navigation_apps.clear_cache",
]

# Modules are added to `modules.txt` after this app has already been installed
# somewhere -- `Safer Permissions` was, and `Requests` is `Procurement` renamed
# -- and `Module Def` records are only written at install. Without one, migrate
# cannot import a doctype that names the module, so this has to run before the
# doctype sync, not after it.
before_migrate = "commons.commons_core.install.sync_module_defs"

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `commons/dock/commons/commons.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
#
# One bundle, loaded after core's own `app_include_js`, so the classes it patches
# already exist. It holds the desk halves of Better Navigation -- the sidebar's
# user menu, the "Website" button's target and sidebar memory, all under
# `commons/better_navigation/js/` -- and the Bikram Sambat readout that
# `commons/public/js/bikram_sambat/` puts on Date and Datetime fields, which
# draws itself only where Commons Settings switches it on.
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
# Two entries, of the two kinds there are. `make_qr_code` belongs to no section
# and is useful to any template that wants an image -- it lives in
# `commons/commons_core/jinja.py`, which is where a helper goes when the section
# it came from is not part of the answer. It came from the retired NepalERP app,
# whose own hook is where sites that print QR codes first got the name.
#
# `party_statement` is the other kind: the statement section's own data function,
# the same one the SPA calls over HTTP. It is here so the print format at
# `commons/statement/print/statement.html` asks the app what somebody's balance
# is rather than working it out again in Jinja, which is the whole reason the
# printed statement and the one in the browser cannot drift. Which way a balance
# runs, which accounts are left out because they belong to the lending module,
# how a running balance reconciles with a total: all of that is answered once, in
# Python, for both.
#
# Both are exposed by name to every template on the site, not only to the formats
# this app creates. For `party_statement` that is why it does its own permission
# check rather than trusting its caller -- see `commons.statement.parties.named`;
# `make_qr_code` reads nothing and so has nothing to check.
jinja = {
	"methods": [
		"commons.commons_core.jinja.make_qr_code",
		"commons.statement.api.party_statement",
	],
}

# Installation
# ------------

# before_install = "commons.commons_core.install.before_install"

# Uninstallation
# ------------

# before_uninstall = "commons.uninstall.before_uninstall"
# after_uninstall = "commons.uninstall.after_uninstall"

# Disable / Enable
# ----------------
# Called when this app is logically disabled or re-enabled on a site,
# without uninstalling it. Use this to hide/restore fields this app adds
# to other apps' doctypes.

# before_disable = "commons.uninstall.before_disable"
# after_disable = "commons.uninstall.after_disable"
# before_enable = "commons.commons_core.install.before_enable"
# after_enable = "commons.commons_core.install.after_enable"

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

# A Material Request raised from a Procurement Request is what makes that request
# "ordered", but nothing is written back to the request when it happens: how much
# has been ordered is counted live from the submitted Material Requests that point
# at it. Only the budget needs a hook, and only on submit — usage is summed from
# submitted requests, so a cancelled one leaves the tally by its docstatus alone.
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
	# Every derived field is a Custom Field, from whichever door it came in by.
	# See `commons.derived_docfields.validation`.
	"Custom Field": {
		"before_validate": "commons.derived_docfields.validation.normalize",
		"validate": "commons.derived_docfields.validation.check",
		"on_update": "commons.derived_docfields.registry.clear",
		# Not `on_trash`, which runs while the row is still there to be re-read.
		"after_delete": "commons.derived_docfields.registry.clear",
		# Notification.email_template is skipped as a fixture on a Frappe that has
		# the field itself. See `commons.email_extensions.notification`.
		"before_import": "commons.email_extensions.notification.skip_field_fixture",
	},
	"Material Request": {
		"validate": "commons.requests.budget.validate_material_request",
		"before_update_after_submit": "commons.requests.budget.protect_submitted_material_request",
		"on_submit": "commons.requests.budget.charge_material_request",
	},
	# The navigation rail's site-level inputs are cached; these are what it reads.
	# See `commons.better_navigation.navigation_apps._site_inputs`.
	**{
		doctype: {
			"on_update": "commons.better_navigation.navigation_apps.clear_cache",
			"after_delete": "commons.better_navigation.navigation_apps.clear_cache",
		}
		for doctype in ("Navigation App", "Workspace Sidebar", "Desktop Icon", "Module Def")
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

# Testing
# -------

# before_tests = "commons.commons_core.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "commons.custom.task.CustomTaskMixin"
# }

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
]
# after_request = ["commons.utils.after_request"]

# At `POST /login` the session is still Guest's when `before_request` runs, so the
# login redirect is settled here instead. See `commons.better_navigation.home_page`.
on_login = ["commons.better_navigation.home_page.set_home_page_on_login"]

# Job Events
# ----------
# The workers run queries too, so they get the same engine the web does.
before_job = ["commons.derived_docfields.install"]
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


# Submitted MR rates are immutable even when a price-list update is requested.
extend_doctype_class = {
	"Material Request": ["commons.requests.budget.BudgetMaterialRequestMixin"],
	# A Notification may send an Email Template's content in place of its own
	# message. See `commons.email_extensions.notification`.
	"Notification": ["commons.email_extensions.notification.TemplateNotificationMixin"],
	# An Auto Email Report runs its report without the endpoints the permission
	# gate stands in front of. See `commons.safer_permissions.auto_email_report`.
	"Auto Email Report": ["commons.safer_permissions.auto_email_report.GatedAutoEmailReport"],
}

# The gate checkbox is drawn next to "Only if Creator" rather than among the
# rights, because it scopes rows rather than granting a right.
page_js = {"permission-manager": "public/js/permission_manager_gate.js"}


# The desk's "Website" button reads its target from the boot, so the sidebar does
# not have to fetch a setting before it can render. See
# `commons/better_navigation/website_link.py` for why this is not simply the home page.
extend_bootinfo = [
	"commons.better_navigation.website_link.extend_bootinfo",
	# The navigation rail's apps, when Commons Settings switches it on.
	"commons.better_navigation.navigation_apps.extend_bootinfo",
	"commons.commons_core.settings.extend_bootinfo",
	# Which Email Templates each doctype's forms offer, so a form can draw its
	# Email menu without asking. See `commons.email_extensions`.
	"commons.email_extensions.api.extend_bootinfo",
]
