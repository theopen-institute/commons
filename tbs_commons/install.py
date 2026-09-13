"""Install/migrate hooks: this app's Custom Fields and its procurement Workflow.

The desk icon is *not* here. It ships as a file in `tbs_commons/desktop_icon/`,
which `frappe.model.sync` imports on every migrate — `desktop_icon` is one of its
`app_level_folders`. Keeping it as a record built at runtime meant migrate's orphan
sweep deleted it (it drops any `standard` icon with no backing file) and
`after_migrate` put it straight back, once per migrate.

Its label is the `app_title`, which is also what Frappe looks for before seeding an
icon of its own (`get_app_desktop_icon`), so the shipped file suppresses that too.
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
	sync_custom_fields()
	sync_procurement_workflow()


def after_migrate() -> None:
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
