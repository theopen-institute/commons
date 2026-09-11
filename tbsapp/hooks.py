app_name = "tbsapp"
app_title = "TBS App"
app_publisher = "Peter"
app_description = "Tools for TBS"
app_email = "pgraif@gmail.com"
app_license = "unlicense"

# Send non-GET requests for this app's endpoints as native `application/json`
# bodies instead of form-encoded, per-key JSON-stringified values.
use_json_request_body = True

# Apps
# ------------------

# `Procurement Request` links to Item, UOM, Company and Supplier, and hands over
# to Material Request, so the doctypes cannot migrate without ERPNext present.
required_apps = ["erpnext"]

# Where the SPA lives. The two apps below are sections of one bundle served
# under this prefix, so the route is written once.
app_home = "/tbsapp"

# Two tiles, not one: the apps screen renders an entry per item here, so one
# Frappe app can present itself as several. Employee records and leave are
# separate jobs for separate people — each tile gets its own icon, landing
# route and permission check, and the SPA gives each its own sidebar.
add_to_apps_screen = [
	{
		"name": "tbsapp",
		"logo": "/assets/tbsapp/images/tbsapp-employees-logo.svg",
		"title": "TBS Employees",
		"route": f"{app_home}/employees",
		"has_permission": "tbsapp.api.check_app_permission",
	},
	{
		"name": "tbsapp-leave",
		"logo": "/assets/tbsapp/images/tbsapp-leave-logo.svg",
		"title": "TBS Leave",
		"route": f"{app_home}/leave",
		"has_permission": "tbsapp.api.check_leave_app_permission",
	},
]

# The SPA owns its own history, so every path under /tbsapp has to resolve to
# the one built page (tbsapp/www/tbsapp.html) rather than 404 on a deep link
# or a refresh.
website_route_rules = [
	{"from_route": "/tbsapp/<path:app_path>", "to_route": "tbsapp"},
]

# The desk draws `Desktop Icon` documents, which Frappe seeds once per app at
# install and never updates. Both hooks run the same idempotent sync, so a
# fresh install and an existing site end up with the same two icons.
after_install = "tbsapp.install.after_install"
after_migrate = "tbsapp.install.after_migrate"

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `tbsapp/dock/tbsapp/tbsapp.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# Loaded on the desk only. It stops this app's desk icons from opening a new
# tab — see the file for why the framework does that.
app_include_js = "tbsapp.bundle.js"

# include js, css files in header of desk.html
# app_include_css = "/assets/tbsapp/css/tbsapp.css"
# app_include_js = "/assets/tbsapp/js/tbsapp.js"

# include js, css files in header of web template
# web_include_css = "/assets/tbsapp/css/tbsapp.css"
# web_include_js = "/assets/tbsapp/js/tbsapp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "tbsapp/public/scss/website"

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
# app_include_icons = "tbsapp/public/icons.svg"

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
# setup_wizard_url = "/tbsapp/setup"

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
# 	"methods": "tbsapp.utils.jinja_methods",
# 	"filters": "tbsapp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "tbsapp.install.before_install"

# Uninstallation
# ------------

# before_uninstall = "tbsapp.uninstall.before_uninstall"
# after_uninstall = "tbsapp.uninstall.after_uninstall"

# Disable / Enable
# ----------------
# Called when this app is logically disabled or re-enabled on a site,
# without uninstalling it. Use this to hide/restore fields this app adds
# to other apps' doctypes.

# before_disable = "tbsapp.uninstall.before_disable"
# after_disable = "tbsapp.uninstall.after_disable"
# before_enable = "tbsapp.install.before_enable"
# after_enable = "tbsapp.install.after_enable"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "tbsapp.utils.before_app_install"
# after_app_install = "tbsapp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "tbsapp.utils.before_app_uninstall"
# after_app_uninstall = "tbsapp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "tbsapp.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "tbsapp.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "tbsapp.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["tbsapp.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# A Material Request raised from a Procurement Request is what makes that
# request "ordered". Submit and cancel are the only two events that change
# whether it counts — a draft Material Request commits to nothing.
doc_events = {
	"Material Request": {
		"on_submit": "tbsapp.tbs_app.doctype.procurement_request.procurement_request.update_linked_procurement_requests",
		"on_cancel": "tbsapp.tbs_app.doctype.procurement_request.procurement_request.update_linked_procurement_requests",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"tbsapp.tasks.all"
# 	],
# 	"daily": [
# 		"tbsapp.tasks.daily"
# 	],
# 	"hourly": [
# 		"tbsapp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"tbsapp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"tbsapp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "tbsapp.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "tbsapp.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "tbsapp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "tbsapp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["tbsapp.utils.before_request"]
# after_request = ["tbsapp.utils.after_request"]

# Job Events
# ----------
# before_job = ["tbsapp.utils.before_job"]
# after_job = ["tbsapp.utils.after_job"]

# after_file_upload = ["tbsapp.utils.after_file_upload"]

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
# 	"tbsapp.auth.validate"
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

