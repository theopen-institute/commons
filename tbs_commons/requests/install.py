"""Install/migrate hooks for the Requests module: Custom Fields, tracking, Workflow.

All of it is procurement's. Leave and expenses assert nothing at install time --
they run on HRMS's own doctypes and read whatever Workflow a site has configured
-- so there is one install module for the section rather than one per request
type, and it seeds the one thing that does need seeding.

Everything it asserts lives on ERPNext's doctypes -- `Material Request` and its
item rows -- or on `Procurement Request`'s own Workflow. None of it is shared
with the rest of the app, so it is wired straight into `hooks.py` the way
`tbs_commons.safer_permissions.install` is.
"""

import frappe


def sync_procurement() -> None:
	"""Everything procurement asserts on both install and migrate."""
	sync_custom_fields()
	sync_material_request_tracking()
	sync_procurement_workflow()


PROCUREMENT_WORKFLOW = "Procurement Request Workflow"

# Approval is the submission. Everything before a decision is a draft, a
# rejection leaves it one, and only `Approved` carries the request to docstatus
# 1 -- which is what lets `make_material_request` gate on `docstatus` alone
# rather than on the name of a state. `Completed` and `Canceled` are the two
# ways out of it afterwards.
#
# Order is load-bearing twice over. `Draft` is first, so it is the state Frappe
# assigns a document that arrives without one, and `Approved` is the first
# `doc_status` 1 row, so it is the state `set_workflow_state_on_action` picks
# when something submits a request without going through the workflow.
WORKFLOW_STATES = (
	{"state": "Draft", "style": "Primary", "doc_status": "0", "allow_edit": "Employee"},
	{
		"state": "Pending",
		"style": "Warning",
		"doc_status": "0",
		"allow_edit": "Purchase User",
		# Reopening brings a rejected request back here, so this is also where a
		# rejection stops standing. Left alone, last time's reason would still be
		# on the request the next time an approver turned it down. An empty
		# `update_value` clears the field: `evaluate_workflow_value` reads any
		# falsy value as None.
		"update_field": "rejection_reason",
		"update_value": "",
	},
	{"state": "Under Review", "style": "Info", "doc_status": "0", "allow_edit": "Expense Approver"},
	{"state": "Approved", "style": "Success", "doc_status": "1", "allow_edit": "Purchase User"},
	{"state": "Rejected", "style": "Danger", "doc_status": "0", "allow_edit": "Expense Approver"},
	{"state": "Completed", "style": "Success", "doc_status": "1", "allow_edit": "Purchase User"},
	{"state": "Canceled", "style": "Inverse", "doc_status": "2", "allow_edit": "Purchase User"},
)

WORKFLOW_ACTIONS = ("Send to Procurement", "Send for Review", "Approve", "Reject", "Cancel", "Reopen")

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
	{"state": "Under Review", "action": "Approve", "next_state": "Approved", "allowed": "Purchase User"},
	{"state": "Under Review", "action": "Reject", "next_state": "Rejected", "allowed": "Purchase User"},
	{"state": "Approved", "action": "Cancel", "next_state": "Canceled", "allowed": "Purchase User"},
	# A rejection is a decision, not a shredder. Procurement owns the queue, so
	# they are the ones who decide whether a turned-down request is worth
	# reworking, and reopening puts it back in their hands at `Pending` -- where
	# it is theirs to edit again, which `Rejected` deliberately is not.
	{
		"state": "Rejected",
		"action": "Reopen",
		"next_state": "Pending",
		"allowed": "Purchase User",
		# Reopening decides nothing, so a buyer may reopen their own request.
		"allow_self_approval": 1,
	},
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
		},
		# Budget usage is attributed here, including on requests raised directly.
		# Header-level and singular on purpose: one request charges one department's
		# budget. Note that enabling a Department accounting dimension would add a
		# separate per-row `department` to Material Request Item, which is ERPNext's
		# accounting attribution and not this.
		{
			"fieldname": "department",
			"label": "Department",
			"fieldtype": "Link",
			"options": "Department",
			"insert_after": "company",
			"search_index": 1,
			"description": "Whose budget this request is charged to. Required to submit Purchase/Material Issue requests; inherited from linked Procurement Requests.",
		},
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


def sync_custom_fields() -> None:
	"""Add this app's fields to ERPNext's doctypes. Safe to run repeatedly."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(CUSTOM_FIELDS, update=True)


def sync_material_request_tracking() -> None:
	"""Turn on Frappe's own change log for Material Requests.

	Budget usage is summed live from submitted requests and no longer keeps a
	bespoke ledger of its own, so the audit trail is the requests' history:
	`Version` records every field change and every docstatus transition, with the
	user and timestamp. ERPNext ships Material Request with tracking off.
	"""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	# `for_doctype` makes this a DocType-level property rather than a field one.
	# Re-running is safe: Property Setter drops any earlier setter for the same
	# property before inserting, so `after_migrate` can call this every time.
	make_property_setter("Material Request", None, "track_changes", 1, "Check", for_doctype=True)


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
