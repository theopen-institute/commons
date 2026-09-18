"""What an active Frappe Workflow says, read the same way by both sections.

Procurement was written around a Workflow from the start and leave was not.
Adding one to leave meant either a second copy of this or one module every
section reads, and a second copy is the thing that drifts: the two would have
started out agreeing on what an action is and ended up disagreeing about which
ones a user may take.

This stays at the app level rather than moving into `tbs_commons.requests` with
its three callers, because nothing in it is about a request: it is what an
active Workflow says, for any doctype. `requests.approvals` is the layer above
that does know what a request is.

Nothing here decides anything. `get_transitions` is Frappe's own answer to "what
may this user do to this document, right now", asked in that user's session --
what is here is the shapes around it that the sections needed, and none of them
names a state, a role or an action.
"""

import frappe


def active_workflow(doctype: str):
	"""The active Workflow for `doctype`, or None if the site runs without one."""
	from frappe.model.workflow import get_workflow_name

	name = get_workflow_name(doctype)
	return frappe.get_cached_doc("Workflow", name) if name else None


def state_field(workflow, fallback: str = "status") -> str:
	"""The column a workflow keeps its state in, or the doctype's own status."""
	return workflow.workflow_state_field if workflow else fallback


def unique_actions(transitions) -> list[dict]:
	"""Return one button per action accepted by Frappe's Workflow API.

	A Workflow needs parallel transition rows to grant the same action to
	different roles. Users who hold more than one of those roles receive every
	matching row from ``get_transitions``, while ``apply_workflow`` accepts only
	the action name and therefore exposes a single effective choice.
	"""
	actions = []
	seen = set()
	for row in transitions:
		if row.action in seen:
			continue
		seen.add(row.action)
		actions.append({"action": row.action, "next_state": row.next_state})
	return actions


def state_styles(workflow) -> dict[str, str | None]:
	"""Each state of `workflow` mapped to the style its Workflow State carries.

	The style is the site's, set on the Workflow State document, and it is the
	only thing either frontend colours a badge or a button from. A state a site
	left unstyled maps to None, which both pages read as "no emphasis".
	"""
	if not workflow or not workflow.states:
		return {}
	return dict(
		frappe.get_all(
			"Workflow State",
			filters={"name": ["in", [row.state for row in workflow.states]]},
			fields=["name", "style"],
			as_list=True,
		)
	)


def initial_actions(workflow) -> list[dict]:
	"""Actions a document created by this user can take from the initial state."""
	if not workflow or not workflow.states:
		return []

	initial_state = workflow.states[0].state
	roles = set(frappe.get_roles())
	return unique_actions(
		row
		for row in workflow.transitions
		if row.state == initial_state
		and row.allowed in roles
		and (row.allow_self_approval or frappe.session.user == "Administrator")
	)


def describe(workflow) -> dict | None:
	"""The Workflow reduced to the fields an SPA can render.

	Every section sends the same shape, so the frontend reads a state's style
	and a transition's target the same way everywhere -- there is one styling
	vocabulary across the app, and it is the site's own.
	"""
	if not workflow:
		return None
	styles = state_styles(workflow)
	return {
		"name": workflow.name,
		"workflow_state_field": workflow.workflow_state_field,
		"initial_actions": initial_actions(workflow),
		"states": [
			{"state": row.state, "doc_status": int(row.doc_status), "style": styles.get(row.state)}
			for row in workflow.states
		],
		"transitions": [
			{"state": row.state, "action": row.action, "next_state": row.next_state}
			for row in workflow.transitions
		],
	}


def permitted_transitions(doctype: str, names: list[str], workflow=None) -> dict[str, list[dict]]:
	"""Transitions Frappe currently permits, per already-readable name.

	The workflow is passed in rather than looked up per document: `get_transitions`
	otherwise resolves it again for every row, and with none at all it raises
	rather than returning nothing.

	Asked in this user's session on purpose. A transition condition that names
	the session user -- the usual way a workflow routes a document to one person
	rather than to a role -- only means what it says here.

	Every caller reaches this with names a `get_list` has already settled, and
	each of them says so where it calls. The check below is not a second opinion
	on that -- `get_transitions` read-checks the document itself -- it is about
	what happens when one slips through: core *throws*, so a single unreadable
	name takes the whole queue down with it rather than costing it one row.
	Dropping it is the answer a queue wants, because a queue is a list of what
	you may act on and an empty entry says exactly that. It also stops the
	invariant living only in four call sites across three modules.
	"""
	from frappe.model.workflow import get_transitions

	workflow = workflow if workflow is not None else active_workflow(doctype)
	if not workflow or not names:
		return {}
	permitted = {}
	for name in names:
		doc = frappe.get_doc(doctype, name)
		if not doc.has_permission("read"):
			continue
		permitted[name] = unique_actions(get_transitions(doc, workflow))
	return permitted


def names_in_movable_states(doctype: str, workflow, field: str) -> list[str]:
	"""Readable documents parked in a state one of this user's roles can move.

	Not the open `Workflow Action` rows, which is how Frappe itself answers
	"what is waiting on me". A Workflow Action records the *roles* a transition
	is open to, and it is written by `process_workflow_actions` in the session of
	whoever made the *previous* transition -- so a transition conditioned on the
	document's own approver field is evaluated against the wrong user, its role
	is dropped from `permitted_roles`, and the one person entitled to decide is
	the one person the queue never shows it to.

	Roles and states are read off the workflow rather than named by a caller, so
	a transition added or re-pointed later does not have to be remembered twice.
	Holding the role only makes a document a candidate: which of these rows this
	user may actually act on is settled afterwards by `permitted_transitions`, in
	*their* session, where that condition means what it says.
	"""
	if not workflow:
		return []
	roles = set(frappe.get_roles())
	states = {row.state for row in workflow.transitions if row.allowed in roles}
	if not states:
		return []
	return frappe.get_list(
		doctype,
		filters={field: ["in", sorted(states)]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=0,
	)
