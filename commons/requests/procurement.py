"""Whitelisted endpoints for the procurement section of the Commons frontend.

The budget readout has its own module (`commons.requests.budget`); what
is here is the request lifecycle -- raising one, listing your own, and working
the approval queue the Workflow defines.

Procurement is the third of this module's request types, and the one that has
always been a Workflow from the start. What it shares with leave and expenses
is `approvals.RequestType` -- reading the active Workflow, naming the state
column, counting a badge, and vetting the parent names behind a child-table
read. What it does not share is the queue itself: a procurement queue is
grouped by the department whose budget it spends, and a request carries a
priced readout beside it, so `get_procurement_workflow_queue` answers a shape
of its own rather than the flat list the other two return.
"""

import frappe
from frappe.utils import flt

from commons.api import session_employee
from commons.commons_core import workflow as wf
from commons.commons_core.doc_perms import roles_with_permission
from commons.requests import approvals, approvers
from commons.requests.doctype.procurement_request.procurement_request import (
	DOCTYPE as PROCUREMENT_REQUEST,
)
from commons.requests.doctype.procurement_request.procurement_request import (
	get_committed_qty_map,
)
from commons.requests.procurement_workflow import APPROVER_FIELD
from commons.requests.procurement_workflow import approver_roles as _approver_roles


class Procurement(approvals.RequestType):
	"""Procurement's half of the shared shape.

	Only the half a Workflow answers. `queue_predicate` and `row_is_theirs` are
	deliberately left unimplemented: they are the no-workflow path the other two
	sections need because HRMS ships those doctypes without one, and procurement
	has never had a decision that was not a workflow transition. A site that
	disables the Workflow loses the approvals page, which is what
	`workflow_access` in the permissions payload says.
	"""

	doctype = PROCUREMENT_REQUEST

	# `Procurement Request` is this app's own doctype, so it is here on every
	# site this app is -- and the section still does not work without ERPNext.
	# A request names a Company, an Item and a UOM, it is charged to a
	# Department against a Fiscal Year, it hands over to a Material Request, and
	# the readout beside it is counted from those. See
	# `approvals.RequestType.available` and `commons.commons_core.apps`.
	requires_apps = ("erpnext",)

	# The field a transition condition names when the workflow routes a request
	# to one *person* rather than to a role -- see `procurement_workflow`, which
	# reads that condition to work out whose queue this section even is.
	approver_field = APPROVER_FIELD

	# The link query behind the request form's approver field. Sent to the
	# frontend rather than named there, so a site that wants a different set of
	# candidates changes the query in one place -- see `get_procurement_approvers`.
	approver_query = "commons.requests.procurement.get_procurement_approvers"

	# Stored columns both lists select. `total_estimated_cost`, `approver_name`
	# and `requester_name` are deliberately absent: they are virtual, so
	# `get_list` drops them from the select without a word --
	# `_add_procurement_costs` fills them in.
	list_fields = (
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


PROCUREMENT = Procurement()


def _list_fields(state_field: str, *extra: str) -> list[str]:
	"""The stored columns, plus the workflow's state column, without repeating it."""
	fields = [*PROCUREMENT.list_fields, *extra]
	if state_field not in fields:
		fields.append(state_field)
	return fields


@frappe.whitelist()
def get_procurement_permissions() -> dict:
	"""What the session user may do with procurement, plus their backlog.

	Capabilities only. The blank-request defaults used to ride along here, which
	meant every page load resolved a company, an employee, a department approver
	and a stock UOM for a form most visits never open -- see
	`get_procurement_request_defaults`, which answers that when the form asks.

	`workflow` does ride along, because it is not form state: every page that
	reads it also reads this, and refreshed one without the other after acting on
	a request. `None` on a site running no Workflow, which the pages handle.

	Answers rather than throws on a site with no ERPNext, for the reason
	`approvals.RequestType.permissions` gives: this is what every page asks
	before it draws anything, and `read: false` is what takes the section off
	the navigation, the tabs and the badge.
	"""
	if not PROCUREMENT.available():
		return _unavailable_permissions()

	workflow = PROCUREMENT.workflow()
	can_read = bool(frappe.has_permission(PROCUREMENT_REQUEST, "read"))
	is_approver = bool(_approver_roles(workflow) & set(frappe.get_roles()))
	workflow_access = bool(workflow and can_read and is_approver)
	pending = PROCUREMENT.pending_count(workflow, admin=False) if workflow_access else 0

	return {
		"read": can_read,
		"request": bool(frappe.has_permission(PROCUREMENT_REQUEST, "create")),
		"workflow": wf.describe(workflow) if can_read else None,
		"workflow_access": workflow_access,
		"pending_workflow_actions": pending,
		"approver_query": PROCUREMENT.approver_query,
		"page_length": PROCUREMENT.page_length,
	}


def _unavailable_permissions() -> dict:
	"""The same payload with every capability withheld.

	Procurement's permissions are a different shape from leave's and expenses'
	-- workflow access rather than an approve right -- so it says this for
	itself rather than borrowing `approvals.RequestType.unavailable`. The two
	agree on the field that matters: `read` false, and the page is gone.
	"""
	return {
		"read": False,
		"request": False,
		"workflow": None,
		"workflow_access": False,
		"pending_workflow_actions": 0,
		"approver_query": PROCUREMENT.approver_query,
		"page_length": PROCUREMENT.page_length,
	}


@frappe.whitelist()
def get_procurement_request_defaults() -> dict:
	"""What a blank request opens with, before the requester touches anything.

	Asked by the form rather than sent with the permissions, because that is what
	it is: form state, wanted by the one page that draws a blank request and by
	none of the pages that merely list them. Four queries -- a company, the
	employee behind the session, their department's approver, the stock UOM --
	that used to run on every visit to the section.

	Gated on `create` for the same reason `get_procurement_approvers` is: someone
	who cannot raise a request has no blank form to fill, and each of these
	answers is a small fact about the site or about the caller's own employee
	record.

	Every value may be `None`. A default nobody has configured is left out rather
	than guessed at, and Frappe then applies the user's own default or says it
	cannot decide -- which is better than a form that quietly picked one.
	"""
	PROCUREMENT.require_available()
	frappe.has_permission(PROCUREMENT_REQUEST, "create", throw=True)

	company = _default_company()
	employee = session_employee(["name", "department"])

	return {
		"company": company,
		"currency": (frappe.db.get_value("Company", company, "default_currency") if company else None),
		"department": employee.department if employee else None,
		# The department's head, and only the department's head. A request spends
		# the department's budget, so the requester's own expense approver -- who
		# signs off their personal claims -- is not an answer here.
		"approver": approvers.department_head(employee.department if employee else None),
		"uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
	}


@frappe.whitelist(methods=["POST"])
def save_procurement_request(doc: str | dict, action: str | None = None) -> dict:
	"""Insert or edit a request, optionally applying a Workflow action atomically."""
	PROCUREMENT.require_available()
	values = frappe.parse_json(doc) or {}
	if not isinstance(values, dict):
		frappe.throw(frappe._("A Procurement Request document is required."))
	if values.get("doctype") not in (None, PROCUREMENT_REQUEST):
		frappe.throw(frappe._("Only Procurement Requests can be created here."))

	name = values.pop("name", None)
	values["doctype"] = PROCUREMENT_REQUEST
	values["docstatus"] = 0
	workflow = PROCUREMENT.workflow()
	if workflow:
		values.pop(workflow.workflow_state_field, None)
	for row in values.get("items") or []:
		# Vue's stable rendering key is not part of the child doctype.
		row.pop("key", None)

	if name:
		request = frappe.get_doc(PROCUREMENT_REQUEST, name)
		if not _can_edit_procurement_request(request, workflow):
			frappe.throw(
				frappe._(
					"You are not permitted to edit this Procurement Request in its current workflow state."
				),
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

	workflow = workflow if workflow is not None else PROCUREMENT.workflow()
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
	PROCUREMENT.require_available()
	state_field = PROCUREMENT.state_field(PROCUREMENT.workflow())
	requests = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"requested_by": frappe.session.user},
		fields=_list_fields(state_field, "amended_from"),
		order_by="creation desc, name desc",
		limit_page_length=0,
	)
	# Collapse before limiting so amendments cannot disappear across a page boundary.
	requests = _replace_cancelled_requests(requests)[: PROCUREMENT.page_length]
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


@frappe.whitelist()
def get_procurement_request_transitions(requests: str) -> dict[str, list[dict]]:
	"""Workflow transitions Frappe currently permits for each readable request."""
	PROCUREMENT.require_available()
	names = frappe.parse_json(requests) or []
	workflow = PROCUREMENT.workflow()
	if not names or not workflow:
		return {}
	return wf.permitted_transitions(PROCUREMENT_REQUEST, PROCUREMENT.readable(names), workflow)


@frappe.whitelist()
def get_procurement_workflow_queue(decided: int = 0) -> dict:
	"""The requests waiting on this user, or the ones they have already decided."""
	PROCUREMENT.require_available()
	return _procurement_workflow_queue(bool(frappe.utils.cint(decided)))


def _procurement_workflow_queue(decided: bool) -> dict:
	workflow = PROCUREMENT.workflow()
	state_field = PROCUREMENT.state_field(workflow)

	# Pending: the first page of what this user may actually move, found before
	# the page is cut -- see `wf.first_actionable`, and `PROCUREMENT.actionable`,
	# which the badge asks too.
	available = PROCUREMENT.actionable(workflow) if not decided else None
	names = list(available) if not decided else approvals.completed_by_session(PROCUREMENT_REQUEST)

	if not names:
		return {"requests": [], "actions": {}, "groups": []}
	requests = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"name": ["in", names]},
		fields=_list_fields(state_field),
		order_by="modified desc",
		limit_page_length=PROCUREMENT.page_length,
	)
	_add_procurement_costs(requests)
	if decided:
		# `get_list` has already settled what this user may read, so the names
		# below need no second permission pass.
		available = wf.permitted_transitions(PROCUREMENT_REQUEST, [row.name for row in requests], workflow)
	for request in requests:
		request.workflow_state = request.get(state_field)
	return {
		"requests": requests,
		"actions": available,
		"groups": group_by_department(requests),
	}


def group_by_department(requests: list[dict]) -> list[dict]:
	"""The queue in the unit the decision is actually made in.

	A budget is a department's, not a request's, so one readout stands over every
	request charged to it rather than being repeated on each. Grouped here rather
	than in the page because `estimate` is money: it is weighed against the
	allocation printed beside it, and the two figures should not be arrived at in
	different places by different rules.

	Keyed by allocation, not by department name alone. A department's requests can
	straddle two budget periods and one readout cannot speak for both -- the
	figures belong to the period a request's transaction date falls in, so requests
	answering to different allocations are different groups even when the
	department above them is the same.

	Departments are ordered by name rather than by recency, so acting on a request
	-- which reloads the queue -- does not shuffle the groups around the approver
	working through them. Requests keep the query's order within a group, and a
	group without a department sorts last: it is the exception, not the heading to
	start from.
	"""
	groups: dict[str, dict] = {}
	for request in requests:
		summary = request.get("budget_summary") or None
		department = request.get("department") or (summary or {}).get("department")
		key = f"{department or ''}::{(summary or {}).get('name') or ''}"
		group = groups.get(key)
		if group:
			group["requests"].append(request.name)
		else:
			groups[key] = {
				"key": key,
				"department": department,
				"summary": summary,
				"requests": [request.name],
				"currency": request.get("currency"),
				"estimate": None,
			}

	by_name = {request.name: request for request in requests}
	for group in groups.values():
		rows = [by_name[name] for name in group["requests"]]
		# Null unless they share one currency: there is no honest single figure to
		# print over a mixture, and a total nobody can act on is worse than none.
		if any(row.get("currency") != group["currency"] for row in rows):
			continue
		group["estimate"] = float(sum(flt(row.get("total_estimated_cost")) for row in rows))

	return sorted(
		groups.values(),
		key=lambda group: (group["department"] is None, group["department"] or ""),
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
	from commons.requests.budget import request_summary

	workflow = PROCUREMENT.workflow()
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

	One `get_list` on the child table, with `parent_doctype` set. That is what
	applies the parent's permissions: `frappe.database.query` inner-joins the
	child to `Procurement Request` and puts the parent's conditions on the join
	-- role permissions, User Permissions, `if_owner`, and this app's own gate
	in `commons.safer_permissions`, which is registered against `"*"` and so is
	consulted here too. A request this user may not read contributes no rows,
	and nothing in this function decides that.

	Still not `/api/v2/document/Procurement Request Item`, and the reason has
	not changed: `document_list` never forwards a `parent`, so a child table
	read there is permission-checked against a doctype that has no permissions
	and refuses everyone. What changed is that this function used to read the
	argument the document API drops as a reason to vet the names itself -- with
	`RequestType.readable` and then a `frappe.get_all`, which is
	`ignore_permissions=True`. The vetting was correct and it was a second copy
	of a rule `get_list` already applies, one layer lower.

	What is left is the arithmetic below, which is the reason to be an endpoint
	at all: `committed_qty` is counted from submitted Material Requests rather
	than stored, so no list query can ask for it.
	"""
	PROCUREMENT.require_available()
	requests = frappe.parse_json(requests) or []
	if not requests:
		return []

	lines = frappe.get_list(
		"Procurement Request Item",
		parent_doctype=PROCUREMENT_REQUEST,
		filters={"parent": ["in", requests]},
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
	#
	# Scoped to the parents the read above actually returned, not to the names
	# the caller asked about: the tally is raw QB and asks no permission of its
	# own, so the permission-checked rows are what it is allowed to count. The
	# lines are handed over as `items` too, since we are holding them -- which
	# is what that argument is for, and saves the helper a second read.
	ordered = get_committed_qty_map(sorted({line.parent for line in lines}), items=lines)
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

	Gated on `create` over `Procurement Request`, because the query builder below
	asks no permission of its own: it joins `User` to `Has Role` directly and so
	enumerates people, with their full names, for anyone who can reach it.

	`create` rather than `read` deliberately. This exists to fill one field on
	one form, and that form is only ever open to someone raising a request --
	whereas read is held by everyone who can so much as see a queue, which is a
	wide door to a directory query. Narrowing it costs nothing: a user who cannot
	raise a request has no field to fill.
	"""
	PROCUREMENT.require_available()
	frappe.has_permission(PROCUREMENT_REQUEST, "create", throw=True)
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
	"""Who this employee's expenses already go to, and their department's.

	A sort order and nothing more, so all of it is skipped on a site without
	HRMS: `Employee.expense_approver` and the `Department.expense_approvers`
	table are both HRMS's, and neither exists to read there. The candidate set
	is unchanged -- it comes from the doctype's own submit permission -- and the
	picker simply falls back to sorting by name.
	"""
	if not employee or not approvers.installed():
		return set()

	record = frappe.db.get_value("Employee", employee, ["department", "expense_approver"], as_dict=True)
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
		.where((department.lft <= bounds.lft) & (department.rgt >= bounds.rgt) & (department.disabled == 0))
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
