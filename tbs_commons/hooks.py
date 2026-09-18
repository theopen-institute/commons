app_name = "tbs_commons"
app_title = "TBS Commons"
app_publisher = "Peter"
app_description = "Tools for TBS"
app_email = "pgraif@gmail.com"
app_license = "none"

# Send non-GET requests for this app's endpoints as native `application/json`
# bodies instead of form-encoded, per-key JSON-stringified values.
use_json_request_body = True

# Apps
# ------------------

# `Procurement Request` links to Item, UOM, Company and Supplier, and hands over
# to Material Request, and the self-service registry below points at Employee and
# writes to it, so the doctypes cannot migrate without ERPNext present.
required_apps = ["erpnext", "hrms"]

# Where the SPA lives. Every section below is served from one bundle under this
# prefix, so the route is written once.
app_home = "/tbs_commons"

# The SPA owns its own history, so every path under /tbs_commons has to resolve to
# the one built page (tbs_commons/www/tbs_commons.html) rather than 404 on a deep link
# or a refresh.
website_route_rules = [
	{"from_route": "/tbs_commons/<path:app_path>", "to_route": "tbs_commons"},
]

# The desk icon ships as a file under `tbs_commons/desktop_icon/` and is imported by
# migrate's own sync. These hooks only do what that sync cannot, and each entry is
# the install module of the module that owns it -- nothing here is app-wide.
# `requests.install` seeds procurement's Custom Fields and Workflow; leave and
# expenses run on HRMS's own doctypes and assert nothing. `commons_core.install`
# creates the two Custom Fields the core extensions read.
after_install = [
	"tbs_commons.requests.install.sync_procurement",
	"tbs_commons.self_service.install.sync_self_service",
	"tbs_commons.safer_permissions.install.sync_gate_field",
	"tbs_commons.commons_core.install.sync_commons_core",
]
after_migrate = [
	"tbs_commons.requests.install.sync_procurement",
	"tbs_commons.self_service.install.sync_self_service",
	"tbs_commons.safer_permissions.install.sync_gate_field",
	"tbs_commons.commons_core.install.sync_commons_core",
]

# Modules are added to `modules.txt` after this app has already been installed
# somewhere -- `Safer Permissions` was, and `Requests` is `Procurement` renamed
# -- and `Module Def` records are only written at install. Without one, migrate
# cannot import a doctype that names the module, so this has to run before the
# doctype sync, not after it.
before_migrate = "tbs_commons.install.sync_module_defs"

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `tbs_commons/dock/tbs_commons/tbs_commons.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/tbs_commons/css/tbs_commons.css"
#
# One bundle, loaded after core's own `app_include_js`, so the classes it patches
# already exist. Today it holds only the "Website" button's target -- see
# `tbs_commons/public/js/website_button.js`, whose server half is
# `tbs_commons/commons_core/website_link.py`.
app_include_js = "tbs_commons.bundle.js"

# include js, css files in header of web template
# web_include_css = "/assets/tbs_commons/css/tbs_commons.css"
# web_include_js = "/assets/tbs_commons/js/tbs_commons.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "tbs_commons/public/scss/website"

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
# app_include_icons = "tbs_commons/public/icons.svg"

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
# setup_wizard_url = "/tbs_commons/setup"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "tbs_commons.utils.jinja_methods",
# 	"filters": "tbs_commons.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "tbs_commons.install.before_install"

# Uninstallation
# ------------

# before_uninstall = "tbs_commons.uninstall.before_uninstall"
# after_uninstall = "tbs_commons.uninstall.after_uninstall"

# Disable / Enable
# ----------------
# Called when this app is logically disabled or re-enabled on a site,
# without uninstalling it. Use this to hide/restore fields this app adds
# to other apps' doctypes.

# before_disable = "tbs_commons.uninstall.before_disable"
# after_disable = "tbs_commons.uninstall.after_disable"
# before_enable = "tbs_commons.install.before_enable"
# after_enable = "tbs_commons.install.after_enable"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "tbs_commons.utils.before_app_install"
# after_app_install = "tbs_commons.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "tbs_commons.utils.before_app_uninstall"
# after_app_uninstall = "tbs_commons.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "tbs_commons.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "tbs_commons.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "tbs_commons.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["tbs_commons.search.awesomebar_results"]

# Permissions
# -----------
# Role Permissions grant access to a whole doctype and User Permissions take
# most of it back, so the restriction is always the second step -- and a User
# Permission that was never created reads exactly like a user meant to see
# everything. `tbs_commons.safer_permissions.permissions` adds the missing third state: a role
# marked "Require User Permission" in the Role Permission Manager grants
# nothing until one exists.
#
# Registered against every doctype rather than a named few, because which
# doctypes are gated is configuration (a tick in the Role Permission Manager), not code.
# Both hooks can only deny, and both answer a cached dict lookup for doctypes
# nobody has gated.
permission_query_conditions = {
	"*": "tbs_commons.safer_permissions.permissions.permission_query_conditions",
}

has_permission = {
	"*": "tbs_commons.safer_permissions.permissions.has_permission",
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
		"on_update": "tbs_commons.commons_core.home_page.clear_cache",
		"on_trash": "tbs_commons.commons_core.home_page.clear_cache",
	},
	"User": {
		"on_update": "tbs_commons.commons_core.home_page.clear_user_cache",
	},
	"Material Request": {
		"validate": "tbs_commons.requests.budget.validate_material_request",
		"before_update_after_submit": "tbs_commons.requests.budget.protect_submitted_material_request",
		"on_submit": "tbs_commons.requests.budget.charge_material_request",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"tbs_commons.tasks.all"
# 	],
# 	"daily": [
# 		"tbs_commons.tasks.daily"
# 	],
# 	"hourly": [
# 		"tbs_commons.tasks.hourly"
# 	],
# 	"weekly": [
# 		"tbs_commons.tasks.weekly"
# 	],
# 	"monthly": [
# 		"tbs_commons.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "tbs_commons.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "tbs_commons.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# Query and Script Reports run the report author's SQL and consult neither
# permission hook, so a gated role cannot be shown one safely -- not even with
# its User Permission in place. These two wrappers refuse them; everything else
# about the reports is untouched.
override_whitelisted_methods = {
	"frappe.desk.query_report.run": "tbs_commons.safer_permissions.permissions.run_query_report",
	"frappe.desk.query_report.export_query": "tbs_commons.safer_permissions.permissions.export_query_report",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "tbs_commons.task.get_dashboard_data"
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
# happened to return first -- see `tbs_commons/commons_core/home_page.py`. That
# loop cannot be ordered from outside and the hook core offers runs after it, so
# the answer is settled here instead, early enough that login, `/` and the desk
# boot all see it.
before_request = ["tbs_commons.commons_core.home_page.set_home_page_flag"]
# after_request = ["tbs_commons.utils.after_request"]

# Job Events
# ----------
# before_job = ["tbs_commons.utils.before_job"]
# after_job = ["tbs_commons.utils.after_job"]

# after_file_upload = ["tbs_commons.utils.after_file_upload"]

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
# 	"tbs_commons.auth.validate"
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
	"Material Request": ["tbs_commons.requests.budget.BudgetMaterialRequestMixin"],
}

# The gate checkbox is drawn next to "Only if Creator" rather than among the
# rights, because it scopes rows rather than granting a right.
page_js = {"permission-manager": "public/js/permission_manager_gate.js"}


# The desk's "Website" button reads its target from the boot, so the sidebar does
# not have to fetch a setting before it can render. See
# `tbs_commons/commons_core/website_link.py` for why this is not simply the home page.
extend_bootinfo = "tbs_commons.commons_core.website_link.extend_bootinfo"
