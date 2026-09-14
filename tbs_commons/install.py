"""Install/migrate hooks: this app's Custom Fields and its procurement Workflow.

The desk icon is *not* here. It ships as a file in `tbs_commons/desktop_icon/`,
which `frappe.model.sync` imports on every migrate — `desktop_icon` is one of its
`app_level_folders`. Keeping it as a record built at runtime meant migrate's orphan
sweep deleted it (it drops any `standard` icon with no backing file) and
`after_migrate` put it straight back, once per migrate.

"""

import frappe

APP = "tbs_commons"
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
	{"state": "Under Review", "action": "Approve", "next_state": "Approved", "allowed": "Purchase Manager"},
	{"state": "Under Review", "action": "Reject", "next_state": "Rejected", "allowed": "Purchase Manager"},
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
	# Header-level and singular on purpose: one request charges one department's
	# budget. Note that enabling a Department accounting dimension would add a
	# separate per-row `department` to Material Request Item, which is ERPNext's
	# accounting attribution and not this.
	{"fieldname": "department", "label": "Department", "fieldtype": "Link",
	 "options": "Department", "insert_after": "company", "search_index": 1,
	 "description": "Whose budget this request is charged to. Required to submit Purchase/Material Issue requests; inherited from linked Procurement Requests."},
])
# Preserve any existing PO/PI attribution data but retire those obsolete controls.
for _doctype in ("Purchase Order Item", "Purchase Invoice Item"):
	CUSTOM_FIELDS[_doctype] = [{
		"fieldname": "budget_department", "label": "Budget Department (Legacy)",
		"fieldtype": "Link", "options": "Department", "insert_after": "cost_center",
		"hidden": 1, "read_only": 1,
		"description": "Historical attribution only. Departmental budget usage is now recorded on Material Requests.",
	}]

# The icon this app ships is labelled "TBS", but Frappe seeds one per installed
# app labelled with the `app_title` ("TBS Commons") and looks for *that* label
# before deciding it already has one (`get_app_desktop_icon`). Ours does not
# match, so a second icon appears pointing at the first `add_to_apps_screen`
# route. It is created with `standard` = 0, which migrate's orphan sweep never
# touches, so nothing else will clear it.
LEGACY_ICON_LABEL = "TBS Commons"


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
	sync_app()


def after_migrate() -> None:
	sync_app()


def sync_app() -> None:
	"""Everything this app asserts on both install and migrate, in order.

	Field renames run between creating the new Custom Fields and dropping the
	retired ones, which is the only moment both sides of a rename exist.
	"""
	sync_custom_fields()
	migrate_renamed_custom_fields()
	remove_obsolete_custom_fields()
	sync_material_request_tracking()
	sync_procurement_workflow()


def sync_custom_fields() -> None:
	"""Add this app's fields to ERPNext's doctypes. Safe to run repeatedly."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(CUSTOM_FIELDS, update=True)


# Fields this app used to add and no longer wants. `create_custom_fields` only
# creates and updates, so a field dropped from `CUSTOM_FIELDS` would otherwise
# linger on every existing site -- and a stale Link keeps its link integrity,
# which is the whole reason this one had to go.
OBSOLETE_CUSTOM_FIELDS = (
	# Which budget a request is charged to is a function of its department and
	# transaction date. Storing it made Material Request link to Department Budget,
	# which blocked the cancel-and-amend the allocation is restated by.
	("Material Request", "department_budget"),
	# A stored sum of the very rows the tally reads, and the company currency it
	# was formatted in. Both were written on every save and read for no decision.
	("Material Request", "budget_amount"),
	("Material Request", "budget_currency"),
	# Renamed to `department`; see LEGACY_FIELD_RENAMES, which carries the values
	# across before this drops the old field.
	("Material Request", "budget_department"),
)

# (doctype, old fieldname, new fieldname) for fields this app has since renamed.
LEGACY_FIELD_RENAMES = (("Material Request", "budget_department", "department"),)


def migrate_renamed_custom_fields() -> None:
	"""Carry values across from fields this app has since renamed.

	Runs between creating the new Custom Field and deleting the old one. Deleting
	a Custom Field leaves its column behind, so both columns are still present
	here -- and the `where` clause is what makes re-running it a no-op.
	"""
	for doctype, old, new in LEGACY_FIELD_RENAMES:
		# The retired Custom Field, not its column: deleting a Custom Field leaves
		# the column behind forever, so a column check would rescan this table on
		# every migrate for the life of the site. The record is dropped in the same
		# run, just after this, which makes the next migrate skip immediately.
		if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": old}):
			continue
		if not frappe.db.has_column(doctype, new):
			continue
		frappe.db.sql(
			f"""update `tab{doctype}` set `{new}` = `{old}`
			where ifnull(`{new}`, '') = '' and ifnull(`{old}`, '') != ''"""
		)


def remove_obsolete_custom_fields() -> None:
	"""Drop this app's retired Custom Fields. Safe to run repeatedly."""
	for doctype, fieldname in OBSOLETE_CUSTOM_FIELDS:
		name = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


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
