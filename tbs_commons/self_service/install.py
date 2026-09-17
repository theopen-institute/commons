"""Install/migrate hook for the self-service section: its Workflow.

Everything else this section needs is in its own doctype definitions, which
migrate imports on its own. What is left is the Workflow -- a document, not a
schema, so nothing syncs it -- wired into `hooks.py` the way
`tbs_commons.procurement.install` is.

One workflow governs every registered record type, because there is one request
doctype. That is the right shape while the registered records are HR's -- an
employee's own details, and the records that hang off them -- and the roles below
say so. A site that registers something HR has no business deciding (a supplier
correcting their own contact details, say) needs a transition for whoever does
decide it, added to this workflow in the desk. The seeding here never rewrites an
existing workflow, so that edit survives every migrate.
"""

import frappe

from tbs_commons.self_service import registry

CHANGE_WORKFLOW = "Record Change Request Workflow"
DOCTYPE = "Record Change Request"

# Approval is the submission, as it is for `Procurement Request`: everything
# before a decision is docstatus 0, and only `Approved` reaches 1 -- which is
# what lets `RecordChangeRequest.on_submit` apply the change without consulting
# the name of a state.
#
# Order is load-bearing. `Pending` is first, so it is the state Frappe assigns a
# request that arrives without one -- and this section has no draft step, because
# a proposal nobody has sent is just a form nobody has pressed Send on.
# `Approved` is the first `doc_status` 1 row, so it is what
# `set_workflow_state_on_action` picks if something submits a request outside the
# workflow.
WORKFLOW_STATES = (
	{"state": "Pending", "style": "Warning", "doc_status": "0", "allow_edit": "Employee"},
	{
		"state": "Approved",
		"style": "Success",
		"doc_status": "1",
		"allow_edit": "HR Manager",
	},
	{
		"state": "Rejected",
		"style": "Danger",
		"doc_status": "0",
		"allow_edit": "HR Manager",
	},
	# The requester's own way out, and the reason it is not `Cancel`: a request
	# that was never decided should not read as one somebody turned down.
	{"state": "Withdrawn", "style": "Inverse", "doc_status": "0", "allow_edit": "HR Manager"},
	# Cancelling an *approved* request. It does not put the old values back --
	# see `RecordChangeRequest.on_cancel` -- so the state says what happened to
	# the request, not to the record.
	{"state": "Reversed", "style": "Inverse", "doc_status": "2", "allow_edit": "HR Manager"},
)

WORKFLOW_ACTIONS = ("Approve", "Reject", "Withdraw", "Reverse")

WORKFLOW_TRANSITIONS = (
	{"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR Manager"},
	{"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR Manager"},
	{"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR User"},
	{"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR User"},
	# Withdrawing decides nothing, so a requester may do it to their own
	# request -- which is the only kind they can see. Without `allow_self_approval`
	# Frappe would refuse it as approving your own document.
	{
		"state": "Pending",
		"action": "Withdraw",
		"next_state": "Withdrawn",
		"allowed": "Employee",
		"allow_self_approval": 1,
	},
	{"state": "Approved", "action": "Reverse", "next_state": "Reversed", "allowed": "HR Manager"},
)


def sync_self_service() -> None:
	"""Everything the self-service section asserts on both install and migrate."""
	seed_records()
	backfill_presentation()
	# The resolved registry is cached across requests and keyed by nothing that
	# changes on deploy, so a migrate that seeds or alters configuration has to
	# drop it. `frappe.clear_cache` does not know about this key.
	registry.clear_cache()
	sync_change_workflow()


# Fields added to `Self Service Record` after it first shipped. A record seeded
# before they existed has them empty, and two of them are mandatory -- so the
# next save of an untouched record would fail on something nobody had ever been
# asked for. Backfilled from the seed rather than guessed at.
PRESENTATION_FIELDS = (
	"label",
	"route_slug",
	"icon",
	"nav_order",
	"read_only_notice",
	"empty_notice",
)


def backfill_presentation() -> None:
	"""Fill presentation fields that predate their own introduction.

	Only where empty, so a site that has renamed a page or rewritten a notice
	keeps what it wrote. Written with `db_set` rather than a save: this runs on
	every migrate, the values are the ones the document would have validated
	against anyway, and a save here would fire `on_update` for every record on
	every deploy.
	"""
	from tbs_commons.self_service.policies import SEED

	for entry in SEED:
		name = entry["document_type"]
		if not frappe.db.exists(registry.CONFIG, name):
			continue
		missing = {
			field: entry[field]
			for field in PRESENTATION_FIELDS
			if field in entry and not frappe.db.get_value(registry.CONFIG, name, field)
		}
		if missing:
			frappe.db.set_value(registry.CONFIG, name, missing, update_modified=False)


def seed_records() -> None:
	"""Create the configuration this app ships, once, for record types with none.

	Never rewrites an existing record, and never recreates a deleted one it can
	tell apart from a new install -- the configuration is the administrator's
	once the app is on the site. A site that removed a field, added one, or
	turned a record type off keeps what it decided, and this quietly does
	nothing on every migrate after the first.

	A record whose doctype is not installed is skipped rather than failing the
	migrate: `Bank Account` is ERPNext's, and an app that lost that dependency
	should degrade to "no bank accounts here", not to a broken deploy.
	"""
	from tbs_commons.self_service.policies import SEED

	for entry in SEED:
		doctype = entry["document_type"]
		if frappe.db.exists(registry.CONFIG, doctype):
			continue
		if not frappe.db.exists("DocType", doctype):
			continue
		record = frappe.new_doc(registry.CONFIG)
		record.update({key: value for key, value in entry.items() if key != "fields"})
		meta = frappe.get_meta(doctype)
		for section, fieldname, proposable in entry["fields"]:
			# A field the site's version of the doctype does not have is dropped
			# rather than seeded, so the first save does not fail validation on
			# something upstream renamed.
			if not meta.has_field(fieldname):
				continue
			record.append(
				"fields",
				{
					"section": section,
					"fieldname": fieldname,
					"viewable": 1,
					"proposable": 1 if proposable else 0,
				},
			)
		if record.fields:
			record.insert(ignore_permissions=True)


def sync_change_workflow() -> None:
	"""Seed the workflow once, then leave its business rules to Frappe.

	An existing workflow, including an inactive one an administrator deliberately
	switched off, is never rewritten during migrate -- the same rule procurement's
	seeding follows, and for the same reason: a site that tuned who may approve
	what should not have that undone by a deploy.
	"""
	if frappe.db.exists("Workflow", {"document_type": DOCTYPE}):
		return

	# A `Workflow State` is a site-wide record shared with every other workflow
	# that names it, so an existing one is never restyled here -- `Pending` ships
	# with Frappe unstyled and is procurement's too, and giving it a colour from
	# this section would silently recolour that section's badges as well. The
	# consequence is that a state this app did not create reads however the site
	# has it, which is the same contract the rest of the section keeps: the
	# styling is the site's, and an admin who wants one changed changes it once.
	for state in WORKFLOW_STATES:
		name = state["state"]
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": state["style"]}
			).insert(ignore_permissions=True)

	for action in WORKFLOW_ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	workflow = frappe.new_doc("Workflow")
	workflow.update(
		{
			"workflow_name": CHANGE_WORKFLOW,
			"document_type": DOCTYPE,
			"workflow_state_field": "status",
			"is_active": 1,
			"send_email_alert": 1,
		}
	)
	workflow.set("states", [{k: v for k, v in state.items() if k != "style"} for state in WORKFLOW_STATES])
	workflow.set("transitions", list(WORKFLOW_TRANSITIONS))
	workflow.save(ignore_permissions=True)
