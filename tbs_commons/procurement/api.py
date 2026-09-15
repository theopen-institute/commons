"""Whitelisted endpoints for the procurement section of the TBS Commons frontend.

The budget readout has its own module (`tbs_commons.procurement.budget`); what
is here is the request lifecycle -- raising one, listing your own, and working
the approval queue the Workflow defines.
"""

import frappe
from frappe.utils import flt

from tbs_commons.api import roles_with_permission, session_employee
from tbs_commons.procurement.doctype.procurement_request.procurement_request import (
	DOCTYPE as PROCUREMENT_REQUEST,
)
from tbs_commons.procurement.doctype.procurement_request.procurement_request import (
	get_committed_qty_map,
)
from tbs_commons.procurement.workflow import approver_roles as _approver_roles
from tbs_commons.procurement.workflow import procurement_workflow as _procurement_workflow
from tbs_commons.procurement.workflow import state_field as _state_field

# How many rows either list returns. The badge on the sidebar counts to the same
# ceiling, so it never promises more than the page will show.
PAGE_LENGTH = 20

# Stored columns both lists select. `total_estimated_cost`, `approver_name` and
# `requester_name` are deliberately absent: they are virtual, so `get_list` drops
# them from the select without a word -- `_add_procurement_costs` fills them in.
LIST_FIELDS = (
	"name",
	"title",
	"company",
	"currency",
	"transaction_date",
	"schedule_date",
	"requested_by",
	"department",
	"approver",
	"justification",
	"rejection_reason",
	"status",
	"docstatus",
	"modified",
)


def _list_fields(state_field: str, *extra: str) -> list[str]:
	"""`LIST_FIELDS` plus the workflow's state column, without repeating it."""
	fields = [*LIST_FIELDS, *extra]
	if state_field not in fields:
		fields.append(state_field)
	return fields


@frappe.whitelist()
def get_procurement_permissions() -> dict:
	"""What the session user may do with procurement, plus their backlog.

	Carries the server-owned defaults a new request needs as well. They are cheap, and
	the alternative is the request form making its own round trips for a
	company and a unit before it can render a single blank line.
	"""
	workflow = _procurement_workflow()
	can_read = bool(frappe.has_permission(PROCUREMENT_REQUEST, "read"))
	is_approver = bool(_approver_roles(workflow) & set(frappe.get_roles()))
	workflow_access = bool(workflow and can_read and is_approver)
	pending = _pending_workflow_count(workflow) if workflow_access else 0

	company = _default_company()
	employee = session_employee(["name", "department", "expense_approver"])

	return {
		"read": can_read,
		"request": bool(frappe.has_permission(PROCUREMENT_REQUEST, "create")),
		"workflow_access": workflow_access,
		"pending_workflow_actions": pending,
		"default_company": company,
		"default_currency": (
			frappe.db.get_value("Company", company, "default_currency") if company else None
		),
		"default_department": employee.department if employee else None,
		"default_approver": _default_procurement_approver(employee),
		"default_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
	}


def _default_procurement_approver(employee: frappe._dict | None) -> str | None:
	"""Who a new request should name, before the requester touches the field.

	The employee's own expense approver first; failing that the first approver
	their department lists, which is how the desk's expense claims decide it
	too. A disabled department is not an answer, and neither is a department
	with an empty table — the form then opens blank and the requester picks.
	"""
	if not employee:
		return None
	if employee.expense_approver:
		return employee.expense_approver
	if not employee.department:
		return None
	if frappe.db.get_value("Department", employee.department, "disabled"):
		return None
	return frappe.db.get_value(
		"Department Approver",
		{"parent": employee.department, "parentfield": "expense_approvers", "idx": 1},
		"approver",
	)


@frappe.whitelist()
def get_procurement_workflow() -> dict | None:
	"""The active Workflow definition, reduced to fields the SPA can render."""
	frappe.has_permission(PROCUREMENT_REQUEST, "read", throw=True)
	workflow = _procurement_workflow()
	if not workflow:
		return None
	styles = dict(
		frappe.get_all(
			"Workflow State",
			filters={"name": ["in", [row.state for row in workflow.states]]},
			fields=["name", "style"],
			as_list=True,
		)
	)
	return {
		"name": workflow.name,
		"workflow_state_field": workflow.workflow_state_field,
		"initial_actions": _initial_workflow_actions(workflow),
		"states": [
			{"state": row.state, "doc_status": int(row.doc_status), "style": styles.get(row.state)}
			for row in workflow.states
		],
		"transitions": [
			{"state": row.state, "action": row.action, "next_state": row.next_state}
			for row in workflow.transitions
		],
	}


def _initial_workflow_actions(workflow) -> list[dict]:
	"""Actions a document created by this user can take from the initial state."""
	if not workflow.states:
		return []

	initial_state = workflow.states[0].state
	roles = set(frappe.get_roles())
	return _unique_workflow_actions(
		row
		for row in workflow.transitions
		if row.state == initial_state
		and row.allowed in roles
		and (row.allow_self_approval or frappe.session.user == "Administrator")
	)


def _unique_workflow_actions(transitions) -> list[dict]:
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


@frappe.whitelist(methods=["POST"])
def save_procurement_request(doc: str | dict, action: str | None = None) -> dict:
	"""Insert or edit a request, optionally applying a Workflow action atomically."""
	values = frappe.parse_json(doc) or {}
	if not isinstance(values, dict):
		frappe.throw(frappe._("A Procurement Request document is required."))
	if values.get("doctype") not in (None, PROCUREMENT_REQUEST):
		frappe.throw(frappe._("Only Procurement Requests can be created here."))

	name = values.pop("name", None)
	values["doctype"] = PROCUREMENT_REQUEST
	values["docstatus"] = 0
	workflow = _procurement_workflow()
	if workflow:
		values.pop(workflow.workflow_state_field, None)
	for row in values.get("items") or []:
		# Vue's stable rendering key is not part of the child doctype.
		row.pop("key", None)

	if name:
		request = frappe.get_doc(PROCUREMENT_REQUEST, name)
		if not _can_edit_procurement_request(request, workflow):
			frappe.throw(
				frappe._("You are not permitted to edit this Procurement Request in its current workflow state."),
				frappe.PermissionError,
			)
		values.pop("doctype", None)
		values.pop("docstatus", None)
		_preserve_non_frontend_line_fields(values.get("items") or [], request)
		request.update(values)
		request.save()
	else:
		_preserve_non_frontend_line_fields(values.get("items") or [])
		request = frappe.get_doc(values).insert()
	if action:
		from frappe.model.workflow import apply_workflow

		request = apply_workflow(request, action)
	return request.as_dict()


def _can_edit_procurement_request(doc, workflow=None) -> bool:
	"""Match Frappe Desk's Workflow allow-edit rule, with server permissions."""
	if doc.docstatus != 0 or not doc.has_permission("write"):
		return False

	workflow = workflow if workflow is not None else _procurement_workflow()
	if not workflow:
		return True

	state = doc.get(workflow.workflow_state_field)
	if not state:
		state = next(
			(row.state for row in workflow.states if int(row.doc_status or 0) == doc.docstatus),
			None,
		)
	state_row = next((row for row in workflow.states if row.state == state), None)
	if not state_row:
		return False
	return state_row.allow_edit in frappe.get_roles()


def _preserve_non_frontend_line_fields(items: list[dict], request=None) -> None:
	"""Keep catalogue assignment and verification outside the requester UI."""
	stored = {row.name: row for row in request.items} if request else {}
	for row in items:
		previous = stored.get(row.get("name"))
		for fieldname in ("item_code", "verified_rate"):
			if previous:
				row[fieldname] = previous.get(fieldname)
			else:
				row.pop(fieldname, None)


def _default_company() -> str | None:
	"""The company a new request is raised against.

	The user's own default first — a multi-company site sets one per user —
	and the only company otherwise, which is the single-company case that
	covers most sites.
	"""
	default = frappe.defaults.get_user_default("Company")
	if default:
		return default

	companies = frappe.get_all("Company", limit=2, pluck="name")
	return companies[0] if len(companies) == 1 else None


@frappe.whitelist()
def get_my_procurement_requests() -> list[dict]:
	"""One entry per request chain, showing the latest readable amendment."""
	state_field = _state_field(_procurement_workflow())
	requests = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"requested_by": frappe.session.user},
		fields=_list_fields(state_field, "amended_from"),
		order_by="creation desc, name desc",
		limit_page_length=0,
	)
	# Collapse before limiting so amendments cannot disappear across a page boundary.
	requests = _replace_cancelled_requests(requests)[:PAGE_LENGTH]
	_add_procurement_costs(requests)
	for request in requests:
		request.workflow_state = request.get(state_field)
	return requests


def _replace_cancelled_requests(requests: list[dict]) -> list[dict]:
	"""Keep original positions, replacing cancelled ancestors with their descendants.

	Input is newest first. If several amendments exist, the newest wins.
	Only rows already returned by the permission-checked query participate.
	"""
	by_name = {row["name"]: row for row in requests}
	amendments = {}
	for row in requests:
		parent = by_name.get(row.get("amended_from"))
		if parent and parent["docstatus"] == 2:
			amendments.setdefault(parent["name"], row)

	result = []
	emitted = set()
	for row in requests:
		parent = by_name.get(row.get("amended_from"))
		if parent and parent["docstatus"] == 2:
			continue
		seen = set()
		while row["docstatus"] == 2 and row["name"] in amendments and row["name"] not in seen:
			seen.add(row["name"])
			row = amendments[row["name"]]
		if row["name"] not in emitted:
			result.append(row)
			emitted.add(row["name"])
	return result


def _transitions_for(names: list[str], workflow=None) -> dict[str, list[dict]]:
	"""Workflow transitions Frappe currently permits, per already-readable name.

	The workflow is passed in rather than looked up per document: `get_transitions`
	otherwise resolves it again for every row, and with none at all it raises
	rather than returning nothing.
	"""
	from frappe.model.workflow import get_transitions

	workflow = workflow if workflow is not None else _procurement_workflow()
	if not workflow or not names:
		return {}
	return {
		name: _unique_workflow_actions(
			get_transitions(frappe.get_doc(PROCUREMENT_REQUEST, name), workflow)
		)
		for name in names
	}


def _readable_requests(names: list[str]) -> list[str]:
	"""Those of `names` this user may read, in one permission-checked query."""
	if not names:
		return []
	return frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"name": ["in", names]},
		pluck="name",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_procurement_request_transitions(requests: str) -> dict[str, list[dict]]:
	"""Workflow transitions Frappe currently permits for each readable request."""
	names = frappe.parse_json(requests) or []
	workflow = _procurement_workflow()
	if not names or not workflow:
		return {}
	return _transitions_for(_readable_requests(names), workflow)


@frappe.whitelist()
def get_procurement_workflow_queue(decided: int = 0) -> dict:
	"""The requests waiting on this user, or the ones they have already decided."""
	return _procurement_workflow_queue(bool(frappe.utils.cint(decided)))


def _procurement_workflow_queue(decided: bool) -> dict:
	workflow = _procurement_workflow()
	state_field = _state_field(workflow)

	if decided:
		# What this user did is recorded nowhere else, and `completed_by` names
		# them, so a Workflow Action answers the History tab exactly.
		actions = frappe.get_all(
			"Workflow Action",
			filters={
				"reference_doctype": PROCUREMENT_REQUEST,
				"status": "Completed",
				"completed_by": frappe.session.user,
			},
			fields=["reference_name"],
		)
		names = list(dict.fromkeys(row.reference_name for row in actions if row.reference_name))
	else:
		names = _requests_awaiting_user(workflow, state_field)

	if not names:
		return {"requests": [], "actions": {}}
	requests = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"name": ["in", names]},
		fields=_list_fields(state_field),
		order_by="modified desc",
		limit_page_length=PAGE_LENGTH,
	)
	_add_procurement_costs(requests)
	# `get_list` has already settled what this user may read, so the names below
	# need no second permission pass.
	available = _transitions_for([row.name for row in requests], workflow)
	for request in requests:
		request.workflow_state = request.get(state_field)
	if not decided:
		requests = [row for row in requests if available.get(row.name)]
	return {"requests": requests, "actions": available}


def _pending_workflow_count(workflow) -> int:
	"""How many waiting requests this user can actually act on, for the badge.

	Deliberately not `_procurement_workflow_queue`: that loads every row and
	prices its department's budget to arrive at a number nobody reads the rest
	of. Capped the way the queue is, so the badge never promises more rows than
	the page will show.
	"""
	names = _requests_awaiting_user(workflow, _state_field(workflow))[:PAGE_LENGTH]
	return sum(1 for actions in _transitions_for(names, workflow).values() if actions)


def _requests_awaiting_user(workflow, state_field: str) -> list[str]:
	"""Readable requests parked in a state one of this user's roles can move.

	Not the open `Workflow Action` rows, which is how Frappe itself answers
	"what is waiting on me". A Workflow Action records the *roles* a transition
	is open to, and this workflow decides by *user*: the `Expense Approver`
	transitions out of `Under Review` are conditioned on `doc.approver ==
	frappe.session.user`. Frappe evaluates that condition in
	`process_workflow_actions`, which runs in the session of whoever made the
	*previous* transition -- the buyer who sent the request for review, never
	the approver it names. So the condition is false at the moment the action is
	written, `Expense Approver` is dropped from its `permitted_roles`, and the
	one person entitled to decide is the one person the queue never shows it to.

	Roles and states are read off the workflow rather than named here, so a
	transition added or re-pointed later does not have to be remembered twice.
	Holding the role only makes a request a candidate: which of these rows this
	user may actually act on is settled afterwards by `get_transitions`, in
	*their* session, where that condition means what it says.
	"""
	if not workflow:
		return []
	roles = set(frappe.get_roles())
	states = {t.state for t in workflow.transitions if t.allowed in roles}
	if not states:
		return []
	return frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={state_field: ["in", sorted(states)]},
		pluck="name",
		order_by="modified desc",
		limit_page_length=0,
	)


def _add_procurement_costs(requests: list[dict]) -> None:
	"""Attach the virtual fields and edit capabilities a list query cannot select.

	`total_estimated_cost`, `approver_name` and `requester_name` are all virtual:
	they are computed by an `options` expression rather than stored, and
	`get_list` drops a virtual field from the select without saying so --
	`get_permitted_fields` is asked for the permitted ones with
	`ignore_virtual=True`, so the field is simply never permitted.

	Through `as_dict` rather than attribute access, because Frappe backs a
	virtual field two ways and only one of them answers to `doc.fieldname`: a
	controller property does, an `options` expression on the DocField does not
	-- it is evaluated by `get_valid_dict`, and reading the attribute raises
	`AttributeError`. Going through the dict works whichever way a field is
	backed, so switching between them stays a DocType-only change.
	"""
	from tbs_commons.procurement.budget import request_summary

	workflow = _procurement_workflow()
	# Rows on one page usually share a department, and the department-wide half of
	# a summary is the expensive half: the Material Request join, the outstanding
	# Procurement Request scan and its UOM conversions. Compute it once per budget.
	position_cache: dict = {}
	for request in requests:
		doc = frappe.get_doc(PROCUREMENT_REQUEST, request.name)
		computed = doc.as_dict()
		request.approver_name = computed.get("approver_name")
		request.requester_name = computed.get("requester_name")
		request.total_estimated_cost = flt(computed.get("total_estimated_cost"))
		request.can_edit = _can_edit_procurement_request(doc, workflow)
		request.budget_summary = request_summary(doc, position_cache)


@frappe.whitelist()
def get_procurement_request_lines(requests: str) -> list[dict]:
	"""The item lines of several requests at once, for a list of them.

	Not `/api/v2/document/Procurement Request Item`: that endpoint never
	forwards its `parent` argument to the query builder, so a child table is
	permission-checked against itself — and a child table has no permissions,
	so every such read is a 403. The parent names are vetted here with a single
	`get_list`, which applies the doctype's rules, user permissions and
	`if_owner`; the lines then follow from names this user has already been
	allowed to see.
	"""
	readable = _readable_requests(frappe.parse_json(requests) or [])
	if not readable:
		return []

	lines = frappe.get_all(
		"Procurement Request Item",
		parent_doctype=PROCUREMENT_REQUEST,
		filters={"parent": ["in", readable]},
		fields=[
			"name",
			"parent",
			"idx",
			"item_code",
			"item_name",
			"reference_url",
			"description",
			"qty",
			"uom",
			"estimated_rate",
			"verified_rate",
		],
		order_by="parent asc, idx asc",
		limit_page_length=0,
	)

	# `committed_qty` and what is left of each row are counted, not stored, so a
	# list query cannot ask for them. One grouped read covers every line on the
	# page -- see `get_committed_qty_map`.
	ordered = get_committed_qty_map(readable)
	for line in lines:
		line.committed_qty = flt(ordered.get(line.name))
		line.uncommitted_qty = max(flt(line.qty) - line.committed_qty, 0.0)
		line.estimated_cost = flt(line.qty) * (flt(line.verified_rate) or flt(line.estimated_rate))

	return lines


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_procurement_approvers(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
) -> list[tuple[str, str]]:
	"""Link-field query: users who could actually decide a request.

	Candidates are everyone holding a role with submit on the doctype. Anyone
	else is a dead end — named as approver, then unable to act — and HRMS's own
	approver query is no use here, because it reads the employee and department
	approver fields that most sites never fill in. Those preferences are not
	ignored, just demoted to a sort order: the requester's expense approver and
	their department's come first when they are in the set at all.
	"""
	roles = _roles_that_may_approve()
	if not roles:
		return []

	user = frappe.qb.DocType("User")
	has_role = frappe.qb.DocType("Has Role")
	like = f"%{txt or ''}%"

	# `list`, not the query's own tuple: the preference sort below is applied
	# in Python, where the department walk already lives.
	candidates = list(
		frappe.qb.from_(user)
		.join(has_role)
		.on(has_role.parent == user.name)
		.select(user.name, user.full_name)
		.distinct()
		.where(
			(has_role.parenttype == "User")
			& (has_role.role.isin(sorted(roles)))
			& (user.enabled == 1)
			& (user.name.notin(["Administrator", "Guest"]))
			& (user.name.like(like) | user.full_name.like(like))
		)
		.run()
	)

	employee = filters.get("employee") if filters else None
	if not employee:
		session = session_employee(["name"])
		employee = session.name if session else None
	preferred = _preferred_approvers(employee)
	candidates.sort(key=lambda row: (row[0] not in preferred, (row[1] or row[0]).lower()))

	start, page_len = frappe.utils.cint(start), frappe.utils.cint(page_len)
	return candidates[start : start + page_len]


def _roles_that_may_approve() -> set[str]:
	"""Roles whose Frappe DocPerm allows submitting this doctype."""
	return roles_with_permission(PROCUREMENT_REQUEST, submit=1)


def _preferred_approvers(employee: str | None) -> set[str]:
	"""Who this employee's expenses already go to, and their department's."""
	if not employee:
		return set()

	record = frappe.db.get_value(
		"Employee", employee, ["department", "expense_approver"], as_dict=True
	)
	if not record:
		return set()

	preferred = {record.expense_approver} - {None}
	if not record.department:
		return preferred

	bounds = frappe.db.get_value("Department", record.department, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return preferred

	# Up the tree, not just the immediate department: the nearest level that
	# names anyone is the one that should get the request.
	department = frappe.qb.DocType("Department")
	ancestors = (
		frappe.qb.from_(department)
		.select(department.name)
		.where(
			(department.lft <= bounds.lft)
			& (department.rgt >= bounds.rgt)
			& (department.disabled == 0)
		)
	).run(pluck=True)

	if ancestors:
		preferred |= set(
			frappe.get_all(
				"Department Approver",
				filters={"parent": ["in", ancestors], "parentfield": "expense_approvers"},
				pluck="approver",
			)
		)

	return preferred
