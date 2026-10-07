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

Nothing falls back to a conventional answer, either. A site with no workflow
has no approvals queue, and one shaped differently is read, not corrected.
"""

import re

from commons.commons_core import workflow as wf

# Spelled out rather than imported from the controller, which `procurement`
# imports alongside this module; one string is not worth the coupling.
PROCUREMENT_REQUEST = "Procurement Request"

# The field a transition condition names when the workflow routes a request to
# one *person* rather than to a role. See `approver_roles`.
APPROVER_FIELD = "approver"

# A condition reading that field off the document, in any of the ways a
# transition condition can: `doc.approver`, `doc.get("approver")` or
# `doc["approver"]`. Not the bare word, which `doc.approver_name` or a field
# like `doc.approver_level` would match without routing anything to a person.
NAMES_APPROVER = re.compile(
	r"\bdoc\s*(?:\.\s*{0}\b|\.\s*get\(\s*['\"]{0}['\"]|\[\s*['\"]{0}['\"]\s*\])".format(
		re.escape(APPROVER_FIELD)
	)
)


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

	A workflow that names no approver anywhere is read for the people who
	approve at all: the roles allowed a transition into a submitted state, which
	is what approving a request is.
	"""
	workflow = workflow if workflow is not None else wf.active_workflow(PROCUREMENT_REQUEST)
	if not workflow:
		return set()
	roles = {
		row.allowed
		for row in workflow.transitions
		if row.allowed and NAMES_APPROVER.search(row.condition or "")
	}
	if roles:
		return roles
	submitted = _states_by_doc_status(workflow, 1)
	return {row.allowed for row in workflow.transitions if row.allowed and row.next_state in submitted}
