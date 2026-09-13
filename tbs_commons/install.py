"""Install/migrate hooks: the app's icons on the desk, and its Custom Fields.

The desk renders `Desktop Icon` *documents*, not the `add_to_apps_screen` hook.
Frappe seeds one icon per installed app at site install
(`create_desktop_icons_from_installed_apps`), taking only the first hook entry
and never revisiting it — so an app that wants two icons, or that changes its
title or route later, has to maintain those records itself.
"""

import frappe

APP = "tbs_commons"
PROCUREMENT_WORKFLOW = "Procurement Request Workflow"

WORKFLOW_STATES = (
	{"state": "Draft", "style": "Primary", "doc_status": "0", "allow_edit": "Employee"},
	{"state": "Pending", "style": "Warning", "doc_status": "0", "allow_edit": "Purchase User"},
	{"state": "Under Review", "style": "Info", "doc_status": "0", "allow_edit": "Expense Approver"},
	{"state": "Approved", "style": "Success", "doc_status": "1", "allow_edit": "Purchase User"},
	{"state": "Rejected", "style": "Danger", "doc_status": "1", "allow_edit": "Expense Approver"},
	{"state": "Completed", "style": "Success", "doc_status": "1", "allow_edit": "Purchase User"},
	{"state": "Canceled", "style": "Inverse", "doc_status": "2", "allow_edit": "Purchase User"},
)

WORKFLOW_ACTIONS = ("Send to Procurement", "Send for Review", "Approve", "Reject", "Cancel")

WORKFLOW_TRANSITIONS = (
	{"state": "Draft", "action": "Send to Procurement", "next_state": "Pending", "allowed": "Employee", "allow_self_approval": 1},
	{
		"state": "Pending",
		"action": "Send for Review",
		"next_state": "Under Review",
		"allowed": "Purchase User",
		"condition": 'not frappe.db.get_value("Procurement Request Item", {"parent": doc.name, "item_code": ["is", "not set"]}, "name")',
	},
	{
		"state": "Under Review",
		"action": "Approve",
		"next_state": "Approved",
		"allowed": "Expense Approver",
		"condition": "doc.approver == frappe.session.user",
	},
	{
		"state": "Under Review",
		"action": "Reject",
		"next_state": "Rejected",
		"allowed": "Expense Approver",
		"condition": "doc.approver == frappe.session.user",
	},
	{"state": "Under Review", "action": "Approve", "next_state": "Approved", "allowed": "Purchase Manager"},
	{"state": "Under Review", "action": "Reject", "next_state": "Rejected", "allowed": "Purchase Manager"},
	{"state": "Approved", "action": "Cancel", "next_state": "Canceled", "allowed": "Purchase User"},
)

# Back-references from the stock document to the request it came from. They live
# on ERPNext's doctypes, so they are Custom Fields rather than part of the
# `Procurement Request` definition. `make_material_request` fills them in, and
# every read of a request counts back through them to see what has actually been
# ordered -- which is why the two on the item rows are indexed.
CUSTOM_FIELDS = {
	"Material Request": [
		{
			"fieldname": "procurement_request",
			"label": "Procurement Request",
			"fieldtype": "Link",
			"options": "Procurement Request",
			"insert_after": "job_card",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
		}
	],
	"Material Request Item": [
		{
			"fieldname": "procurement_request",
			"label": "Procurement Request",
			"fieldtype": "Link",
			"options": "Procurement Request",
			"insert_after": "job_card_item",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"search_index": 1,
		},
		{
			"fieldname": "procurement_request_item",
			"label": "Procurement Request Item",
			"fieldtype": "Data",
			"insert_after": "procurement_request",
			"read_only": 1,
			"no_copy": 1,
			"hidden": 1,
			"print_hide": 1,
			"search_index": 1,
		},
	],
}

# Budget usage is attributed at the Material Request, including direct requests.
CUSTOM_FIELDS["Material Request"].extend([
	{"fieldname": "budget_department", "label": "Budget Department", "fieldtype": "Link",
	 "options": "Department", "insert_after": "company",
	 "description": "Required to submit Purchase/Material Issue requests; inherited from linked Procurement Requests."},
	{"fieldname": "budget_currency", "label": "Budget Currency", "fieldtype": "Link",
	 "options": "Currency", "insert_after": "budget_department", "read_only": 1},
	{"fieldname": "department_budget", "label": "Department Budget", "fieldtype": "Link",
	 "options": "Department Budget", "insert_after": "budget_currency", "read_only": 1, "no_copy": 1},
	{"fieldname": "budget_amount", "label": "Budget Usage", "fieldtype": "Currency",
	 "options": "budget_currency", "insert_after": "department_budget", "read_only": 1,
	 "description": "Sum of MR quantity × rate in company currency. Counted only on submission."},
])
# Preserve any existing PO/PI attribution data but retire those obsolete controls.
for _doctype in ("Purchase Order Item", "Purchase Invoice Item"):
	CUSTOM_FIELDS[_doctype] = [{
		"fieldname": "budget_department", "label": "Budget Department (Legacy)",
		"fieldtype": "Link", "options": "Department", "insert_after": "cost_center",
		"hidden": 1, "read_only": 1,
		"description": "Historical attribution only. Departmental budget usage is now recorded on Material Requests.",
	}]

# The stale single icon Frappe seeds from the `app_title` hook. Replaced by the
# two below on the first migrate after this app grew a second section.
LEGACY_ICON_LABEL = "TBS Commons"

DESKTOP_ICONS = (
	{
		"label": "TBS Employees",
		"link": "/tbs_commons/employees",
		"logo_url": "/assets/tbs_commons/images/tbs_commons-employees-logo.svg",
	},
	{
		"label": "TBS Leave",
		"link": "/tbs_commons/leave",
		"logo_url": "/assets/tbs_commons/images/tbs_commons-leave-logo.svg",
	},
	{
		"label": "TBS Procurement",
		"link": "/tbs_commons/procurement",
		"logo_url": "/assets/tbs_commons/images/tbs_commons-procurement-logo.svg",
	},
)


def before_migrate() -> None:
	sync_module_defs()


def sync_module_defs() -> None:
	"""Register this app's modules before migrate imports doctypes into them.

	`Module Def` records are created by `add_module_defs` when an app is
	*installed* and never again, so a module added to `modules.txt` afterwards
	has none -- and importing a doctype that names it fails. This runs from
	`before_migrate`, ahead of the doctype sync that would trip over it.
	"""
	from frappe.installer import add_module_defs

	add_module_defs(APP, ignore_if_duplicate=True)


def after_install() -> None:
	sync_desktop_icons()
	sync_custom_fields()
	sync_procurement_workflow()


def after_migrate() -> None:
	sync_desktop_icons()
	sync_custom_fields()
	sync_procurement_workflow()


def sync_custom_fields() -> None:
	"""Add this app's fields to ERPNext's doctypes. Safe to run repeatedly."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(CUSTOM_FIELDS, update=True)


def sync_procurement_workflow() -> None:
	"""Seed the workflow once, then leave its business rules to Frappe.

	An existing workflow, including an inactive one deliberately disabled by an
	administrator, is never rewritten during migrate.
	"""
	if frappe.db.exists("Workflow", {"document_type": "Procurement Request"}):
		return

	for state in WORKFLOW_STATES:
		name = state["state"]
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": state["style"]}
			).insert(ignore_permissions=True)

	for action in WORKFLOW_ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	# Preserve the meaning of documents created before this workflow shipped.
	for old, new in {
		"Pending Approval": "Under Review",
		"Partially Ordered": "Approved",
		"Ordered": "Completed",
		"Cancelled": "Canceled",
	}.items():
		frappe.db.set_value("Procurement Request", {"status": old}, "status", new, update_modified=False)

	workflow = frappe.new_doc("Workflow")
	workflow.update(
		{
			"workflow_name": PROCUREMENT_WORKFLOW,
			"document_type": "Procurement Request",
			"workflow_state_field": "status",
			"is_active": 1,
			"send_email_alert": 1,
		}
	)
	workflow.set("states", [{k: v for k, v in state.items() if k != "style"} for state in WORKFLOW_STATES])
	workflow.set("transitions", list(WORKFLOW_TRANSITIONS))
	workflow.save(ignore_permissions=True)


def sync_desktop_icons() -> None:
	"""Create or refresh this app's desk icons. Safe to run repeatedly."""
	_remove_legacy_icon()

	for index, spec in enumerate(DESKTOP_ICONS):
		existing = frappe.db.exists("Desktop Icon", spec["label"])
		if existing:
			icon = frappe.get_doc("Desktop Icon", existing)
		else:
			icon = frappe.new_doc("Desktop Icon")
			icon.label = spec["label"]
			# Only on create: a user who hid or reordered the icon keeps that.
			icon.idx = index
			icon.hidden = 0

		icon.link = spec["link"]
		icon.logo_url = spec["logo_url"]
		icon.link_type = "External"
		icon.icon_type = "App"
		icon.app = APP
		# Shipped by the app rather than owned by whoever ran the migrate, so
		# every user sees it — `get_desktop_icons` loads non-standard icons
		# only for their owner.
		icon.standard = 1
		icon.save(ignore_permissions=True)

	frappe.db.commit()
	_clear_icon_caches()


def _remove_legacy_icon() -> None:
	if not frappe.db.exists("Desktop Icon", LEGACY_ICON_LABEL):
		return

	# Only if it is the one Frappe made for this app — a user-made icon that
	# happens to share the label is theirs, not ours to delete.
	if frappe.db.get_value("Desktop Icon", LEGACY_ICON_LABEL, "app") != APP:
		return

	frappe.delete_doc("Desktop Icon", LEGACY_ICON_LABEL, ignore_permissions=True, force=True)


def _clear_icon_caches() -> None:
	"""Icons are cached per user, so a changed set is invisible until cleared."""
	from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache

	for user in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
		clear_desktop_icons_cache(user)
	frappe.clear_cache()
