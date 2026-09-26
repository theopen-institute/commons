"""What the active Workflow says, read by everything that needs to know.

Nothing installs a Workflow for `Procurement Request`. The one an administrator
builds on a new site is entirely theirs -- whatever states they name, whatever
roles they point the transitions at, however many review steps they want.
Everything in this module is derived from that document rather than named in
code, so whatever they build moves the app with it instead of leaving constants
behind pointing at states and roles that were never going to exist.

Reading the workflow itself, naming its state column and listing its
transitions are not here: those are the same questions leave and expenses ask,
and they are answered once in `commons.commons_core.workflow`. What is here
is only what is derived from *this* workflow's particular shape.

The two derivations below both fall back to a conventional answer. A site with
no workflow at all -- which is every site until somebody builds one -- still
gets something coherent rather than an empty page, and a site whose workflow
happens to be shaped differently is read, not corrected. The fallbacks are a
floor, never an override.
"""

from commons.commons_core import workflow as wf

# Spelled out rather than imported from the controller: `budget` reads this
# module and the controller reads `budget`, so importing it here would close a
# cycle over a single string.
PROCUREMENT_REQUEST = "Procurement Request"

# The field a transition condition names when the workflow routes a request to
# one *person* rather than to a role. See `approver_roles`.
APPROVER_FIELD = "approver"

# What the reference chain answers, for a site running without a workflow.
FALLBACK_APPROVER_ROLE = "Expense Approver"
FALLBACK_OPEN_REQUEST_STATES = ("Pending", "Under Review")


def _states_by_doc_status(workflow, doc_status: int) -> set[str]:
	return {row.state for row in workflow.states if int(row.doc_status or 0) == doc_status}


def approver_roles(workflow=None) -> set[str]:
	"""Roles the workflow routes to a *named* approver, not merely to a role.

	Whose queue the SPA's Approvals page is. Holding a transition is not the
	test: a chain will typically grant the same Approve and Reject actions to a
	procurement role as an override, and gating on any transition at all would
	put this page -- and its sidebar row -- in front of everyone who moves a
	request along from the desk.

	What singles the approver out is that their transitions are conditioned on
	the request's own `approver` field. That condition is the whole reason the
	page exists: Frappe's own "waiting on me" list cannot see past it, which is
	what `commons_core.workflow.names_in_movable_states` is written around. So the people this page is
	for are exactly the people the workflow decides by name, and asking the
	condition says so without a role name in this file.
	"""
	workflow = workflow if workflow is not None else wf.active_workflow(PROCUREMENT_REQUEST)
	if not workflow:
		return set()
	roles = {
		row.allowed for row in workflow.transitions if row.allowed and APPROVER_FIELD in (row.condition or "")
	}
	return roles or {FALLBACK_APPROVER_ROLE}


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
	workflow = workflow if workflow is not None else wf.active_workflow(PROCUREMENT_REQUEST)
	if not workflow or not workflow.states:
		return FALLBACK_OPEN_REQUEST_STATES

	drafts = _states_by_doc_status(workflow, 0)
	submitted = _states_by_doc_status(workflow, 1)
	deciding = {row.state for row in workflow.transitions if row.next_state in submitted}
	decided = {
		row.next_state for row in workflow.transitions if row.state in deciding and row.next_state in drafts
	}
	# Empty is a real answer -- a workflow whose every draft state is either the
	# author's own or the outcome of a decision has no open asks -- so it is
	# returned as one rather than papered over with the fallback names. Only the
	# absence of a workflow above falls back.
	return tuple(sorted(drafts - decided - {workflow.states[0].state}))
