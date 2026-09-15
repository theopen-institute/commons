"""What the active Workflow says, read by everything that needs to know.

`sync_procurement_workflow` seeds a Workflow once and never rewrites it, so the
one an administrator ends up running is theirs to retune -- states renamed,
transitions re-pointed at different roles, a review step added. Everything in
this module is derived from that document rather than named in code, so a
retuned workflow moves the app with it instead of leaving constants behind
pointing at states and roles that no longer exist.

The two derivations below both fall back to what `install.py` seeds. A site with
no workflow at all still gets the app's own answer, which is what it had before
any of this was derived -- the fallbacks are a floor, never an override.
"""

import frappe

# Spelled out rather than imported from the controller: `budget` reads this
# module and the controller reads `budget`, so importing it here would close a
# cycle over a single string.
PROCUREMENT_REQUEST = "Procurement Request"

# The field a transition condition names when the workflow routes a request to
# one *person* rather than to a role. See `approver_roles`.
APPROVER_FIELD = "approver"

# What the seeded workflow answers, for a site running without one.
SEEDED_APPROVER_ROLE = "Expense Approver"
SEEDED_OPEN_REQUEST_STATES = ("Pending", "Under Review")


def procurement_workflow():
	"""The active Workflow for `Procurement Request`, or None."""
	from frappe.model.workflow import get_workflow_name

	name = get_workflow_name(PROCUREMENT_REQUEST)
	return frappe.get_cached_doc("Workflow", name) if name else None


def state_field(workflow) -> str:
	return workflow.workflow_state_field if workflow else "status"


def _states_by_doc_status(workflow, doc_status: int) -> set[str]:
	return {row.state for row in workflow.states if int(row.doc_status or 0) == doc_status}


def approver_roles(workflow=None) -> set[str]:
	"""Roles the workflow routes to a *named* approver, not merely to a role.

	Whose queue the SPA's Approvals page is. Holding a transition is not the
	test: the seeded workflow grants the same Approve and Reject actions to
	`Purchase Manager` as an override, and gating on any transition at all would
	put this page -- and its sidebar row -- in front of everyone who moves a
	request along from the desk.

	What singles the approver out is that their transitions are conditioned on
	the request's own `approver` field. That condition is the whole reason the
	page exists: Frappe's own "waiting on me" list cannot see past it, which is
	what `_requests_awaiting_user` is written around. So the people this page is
	for are exactly the people the workflow decides by name, and asking the
	condition says so without a role name in this file.
	"""
	workflow = workflow if workflow is not None else procurement_workflow()
	if not workflow:
		return set()
	roles = {
		row.allowed
		for row in workflow.transitions
		if row.allowed and APPROVER_FIELD in (row.condition or "")
	}
	return roles or {SEEDED_APPROVER_ROLE}


def open_request_states(workflow=None) -> tuple[str, ...]:
	"""Undecided states that are an open ask on a department's budget.

	Not every draft is one. The state a request is created in is its author's
	private working copy -- nobody has been asked for anything yet -- and a state
	reached by turning a request down is a decision not to spend, not an
	outstanding one.

	Both fall out of the workflow's own shape. The initial state is the first
	row, which is what Frappe assigns a document that arrives without one. A
	rejection is a draft state you land in from a state that can also approve:
	the same person, at the same moment, chose between them, so whatever they
	chose is a decision either way.

	Only the readout's `open_requests` figure depends on this. The approval gate
	counts submitted requests and consults no state name at all, so a workflow
	this cannot read leaves the control itself untouched.
	"""
	workflow = workflow if workflow is not None else procurement_workflow()
	if not workflow or not workflow.states:
		return SEEDED_OPEN_REQUEST_STATES

	drafts = _states_by_doc_status(workflow, 0)
	submitted = _states_by_doc_status(workflow, 1)
	deciding = {row.state for row in workflow.transitions if row.next_state in submitted}
	decided = {
		row.next_state
		for row in workflow.transitions
		if row.state in deciding and row.next_state in drafts
	}
	# Empty is a real answer -- a workflow whose every draft state is either the
	# author's own or the outcome of a decision has no open asks -- so it is
	# returned as one rather than papered over with the seeded names. Only the
	# absence of a workflow above falls back.
	return tuple(sorted(drafts - decided - {workflow.states[0].state}))
