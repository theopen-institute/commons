# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Make rejection a draft state a request can come back from.

`make_material_request` used to ask twice whether a request could be ordered:
once for `docstatus` 1, and again for a hardcoded `Approved`. The second check
existed only because `Rejected` submitted the document, which put a turned-down
request at the same docstatus as an approved one.

With rejection leaving the request a draft, docstatus says it on its own -- and
a rejected request stops being a dead end, so this also adds the `Reopen`
transition that hands one back to procurement at `Pending`.

Both are changes to the Workflow, and `sync_procurement_workflow` seeds a
workflow once and then never touches it again -- an administrator may have
edited it -- so the existing record has to be migrated here rather than
re-seeded.
"""

import frappe

from tbs_commons.install import PROCUREMENT_WORKFLOW


def execute() -> None:
	# Only the workflow this app ships is assumed to mean what this patch thinks
	# it means. A hand-built one is left alone.
	if not frappe.db.exists("Workflow", PROCUREMENT_WORKFLOW):
		return

	workflow = frappe.get_doc("Workflow", PROCUREMENT_WORKFLOW)
	states = {row.state: row for row in workflow.states}
	dirty = False

	# Not reached by `Reject` any more, so it never leaves docstatus 0.
	rejected = states.get("Rejected")
	if rejected and rejected.doc_status != "0":
		rejected.doc_status = "0"
		dirty = True

	# Where a rejection stops standing, so the reason does not outlive it.
	pending = states.get("Pending")
	if pending and not pending.update_field:
		pending.update_field = "rejection_reason"
		pending.update_value = ""
		dirty = True

	if rejected and pending and not any(
		row.state == "Rejected" and row.next_state == "Pending" for row in workflow.transitions
	):
		if not frappe.db.exists("Workflow Action Master", "Reopen"):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": "Reopen"}).insert(
				ignore_permissions=True
			)
		workflow.append(
			"transitions",
			{
				"state": "Rejected",
				"action": "Reopen",
				"next_state": "Pending",
				"allowed": "Purchase User",
				"allow_self_approval": 1,
			},
		)
		dirty = True

	if dirty:
		workflow.save(ignore_permissions=True)

	# Submitted only because the old state said so: nothing can have been
	# ordered from a rejected request, so there is nothing downstream to unwind.
	for name in frappe.get_all(
		"Procurement Request", filters={"status": "Rejected", "docstatus": 1}, pluck="name"
	):
		frappe.db.set_value("Procurement Request", name, "docstatus", 0, update_modified=False)
		frappe.clear_document_cache("Procurement Request", name)
