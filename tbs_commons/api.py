"""Whitelisted endpoints for the TBS Commons employee tool frontend."""

import frappe
from frappe.utils import flt

from tbs_commons.procurement.doctype.procurement_request.procurement_request import get_committed_qty_map

EMPLOYEE = "Employee"

# What the frontend gates on. `submit`/`cancel` are absent because Employee is
# not a submittable doctype.
PERMISSION_TYPES = ("read", "write", "create", "delete")


@frappe.whitelist()
def get_employee_permissions() -> dict[str, bool]:
	"""Return the session user's doctype-level permissions on Employee.

	The frontend uses this to decide what to render — a create button, an
	editable form, a delete action. It is a UI hint only: every write still
	goes through the REST API, which runs the same checks server-side.
	"""
	return {
		ptype: bool(frappe.has_permission(EMPLOYEE, ptype))
		for ptype in PERMISSION_TYPES
	}


@frappe.whitelist()
def get_session_user() -> dict:
	"""Return the session user, for the sidebar's account row.

	A production build gets this from the page's boot data; the Vite dev
	server serves index.html without the Jinja pass, so the SPA asks for it.
	"""
	from tbs_commons.www.tbs_commons import get_user_info

	return get_user_info()


def check_app_permission() -> bool:
	"""Gate this app's presence on the desk — either of its two sections.

	Deliberately the union rather than an Employee check. Frappe gates *every*
	`Desktop Icon` belonging to an app with the first `add_to_apps_screen`
	entry's `has_permission` (see `desktop_icon.check_app_permission`), so a
	narrower check here would hide the Leave and Procurement icons from someone
	who can only do those. Each section still gates itself: the tiles on
	`/apps` use their own entry's check, and the pages refuse what the user may
	not see.

	Not whitelisted: `frappe.get_attr` calls it directly from the icon and
	apps-screen builders, so exposing it over HTTP would only widen the surface.
	"""
	if frappe.session.user == "Administrator":
		return True

	return bool(
		frappe.has_permission(EMPLOYEE, "read")
		or frappe.has_permission(LEAVE_APPLICATION, "read")
		or frappe.has_permission(PROCUREMENT_REQUEST, "read")
	)


# --- Leave -----------------------------------------------------------------

LEAVE_APPLICATION = "Leave Application"

DECISIONS = ("Approved", "Rejected")

# Roles that own the doctype and act as the backstop when a named approver has
# left or is unavailable. The Leave Approver role alone is deliberately not
# enough: it grants submit on *every* leave application, which would let one
# team's supervisor decide another team's requests.
LEAVE_ADMIN_ROLES = {"HR Manager", "HR User"}

def check_leave_app_permission() -> bool:
	"""Gate the Leave tile, which is a separate app on the apps screen.

	Deliberately not the same check as the Employees tile: someone who may
	request their own leave has no business seeing an employee directory, and
	the point of two tiles is that each stands on its own.
	"""
	if frappe.session.user == "Administrator":
		return True

	return bool(frappe.has_permission(LEAVE_APPLICATION, "read"))


@frappe.whitelist()
def get_my_employee() -> dict | None:
	"""Return the Employee record linked to the session user, or None.

	Leave is self-service, so every leave page starts from "which employee am
	I". A user with no linked Employee (`user_id`) cannot request leave — the
	page says so rather than failing at submit.
	"""
	name = frappe.db.get_value(
		"Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
	)
	if not name:
		return None

	employee = frappe.db.get_value(
		"Employee",
		name,
		[
			"name",
			"employee_name",
			"department",
			"company",
			"leave_approver",
			# Procurement borrows this one — see `get_procurement_approvers`.
			"expense_approver",
			"image",
		],
		as_dict=True,
	)
	if employee.leave_approver:
		employee["leave_approver_name"] = frappe.utils.get_fullname(employee.leave_approver)
	return employee


@frappe.whitelist()
def get_leave_permissions() -> dict[str, bool | int]:
	"""What the session user may do with leave, plus their approval backlog.

	`approve` is the doctype-level submit right (the Leave Approver role and
	the HR roles carry it). Whether this user approves *this* application is a
	separate question — `decide_leave_application` answers it per document.
	"""
	can_approve = bool(frappe.has_permission(LEAVE_APPLICATION, "submit"))

	pending = 0
	if can_approve:
		pending = frappe.db.count(
			LEAVE_APPLICATION,
			{"leave_approver": frappe.session.user, "docstatus": 0, "status": "Open"},
		)

	return {
		"read": bool(frappe.has_permission(LEAVE_APPLICATION, "read")),
		"request": bool(frappe.has_permission(LEAVE_APPLICATION, "create")),
		"approve": can_approve,
		"pending_approvals": pending,
	}


@frappe.whitelist(methods=["POST"])
def decide_leave_application(name: str, decision: str) -> dict:
	"""Approve or reject a leave application and submit it.

	The two halves are one action for the approver but two writes underneath:
	`status` sits at permlevel 1, and only a submitted (docstatus 1)
	application actually books the leave. Doing both here keeps them in one
	transaction — a status change that never got submitted would leave the
	request looking decided to the approver and still pending to everyone else.
	"""
	if decision not in DECISIONS:
		frappe.throw(
			frappe._("Decision must be one of {0}").format(", ".join(DECISIONS)),
			frappe.ValidationError,
		)

	doc = frappe.get_doc(LEAVE_APPLICATION, name)

	# The right to decide, not just to read: `submit` is what the Leave
	# Approver role grants, and it is checked against this document so user
	# permissions and sharing apply.
	doc.check_permission("submit")

	# ...and then, narrower than the role: this application's own approver.
	# `check_permission` answers "may this user submit leave applications",
	# which for the Leave Approver role means all of them.
	is_named_approver = doc.leave_approver == frappe.session.user
	if not is_named_approver and not (LEAVE_ADMIN_ROLES & set(frappe.get_roles())):
		frappe.throw(
			frappe._("{0} is not your leave application to decide — it is assigned to {1}.").format(
				name, doc.leave_approver_name or doc.leave_approver or frappe._("nobody")
			),
			frappe.PermissionError,
		)

	if doc.docstatus != 0:
		frappe.throw(
			frappe._("{0} has already been {1}.").format(name, doc.status.lower()),
			frappe.ValidationError,
		)

	doc.status = decision
	doc.save()

	# `status` is permlevel 1: a user without write access there has the change
	# silently reverted rather than refused, and would then hit a confusing
	# "only Approved and Rejected can be submitted" error from on_submit.
	if doc.status != decision:
		frappe.throw(
			frappe._("You are not permitted to decide leave applications. The Leave Approver role grants this."),
			frappe.PermissionError,
		)

	doc.submit()

	return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}


# --- Procurement -----------------------------------------------------------

PROCUREMENT_REQUEST = "Procurement Request"

def check_procurement_app_permission() -> bool:
	"""Gate the Procurement tile, which is its own app on the apps screen."""
	if frappe.session.user == "Administrator":
		return True

	return bool(frappe.has_permission(PROCUREMENT_REQUEST, "read"))


@frappe.whitelist()
def get_procurement_permissions() -> dict:
	"""What the session user may do with procurement, plus their backlog.

	Carries the server-owned defaults a new request needs as well. They are cheap, and
	the alternative is the request form making its own round trips for a
	company and a unit before it can render a single blank line.
	"""
	workflow = _procurement_workflow()
	can_read = bool(frappe.has_permission(PROCUREMENT_REQUEST, "read"))
	workflow_access = bool(workflow and can_read)
	pending = len(_procurement_workflow_queue(False)["requests"]) if workflow_access else 0

	company = _default_company()
	employee = frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user, "status": "Active"},
		["name", "department", "expense_approver"],
		as_dict=True,
	)

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
		"default_approver": employee.expense_approver if employee else None,
		"default_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
	}


def _procurement_workflow():
	from frappe.model.workflow import get_workflow_name

	name = get_workflow_name(PROCUREMENT_REQUEST)
	return frappe.get_cached_doc("Workflow", name) if name else None


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
	workflow = _procurement_workflow()
	state_field = workflow.workflow_state_field if workflow else "status"
	fields = [
		"name", "amended_from", "title", "company", "currency", "transaction_date",
		"schedule_date", "requested_by", "requester_name", "department", "approver",
		"approver_name", "justification", "rejection_reason", "total_qty", "status",
		"docstatus", "modified",
	]
	if state_field not in fields:
		fields.append(state_field)
	requests = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"requested_by": frappe.session.user},
		fields=fields,
		order_by="creation desc, name desc",
		limit_page_length=0,
	)
	# Collapse before limiting so amendments cannot disappear across a page boundary.
	requests = _replace_cancelled_requests(requests)[:20]
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
	from frappe.model.workflow import get_transitions

	names = frappe.parse_json(requests) or []
	if not names or not _procurement_workflow():
		return {}
	readable = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"name": ["in", names]},
		pluck="name",
		limit_page_length=0,
	)
	available = {}
	for name in readable:
		available[name] = _unique_workflow_actions(
			get_transitions(frappe.get_doc(PROCUREMENT_REQUEST, name))
		)
	return available


@frappe.whitelist()
def get_procurement_workflow_queue(decided: int = 0) -> dict:
	"""Requests represented by this user's open or completed Workflow Actions."""
	return _procurement_workflow_queue(bool(frappe.utils.cint(decided)))


def _procurement_workflow_queue(decided: bool) -> dict:
	filters = {"reference_doctype": PROCUREMENT_REQUEST}
	if decided:
		filters.update({"status": "Completed", "completed_by": frappe.session.user})
		actions = frappe.get_all("Workflow Action", filters=filters, fields=["reference_name"])
	else:
		filters["status"] = "Open"
		actions = frappe.get_list(
			"Workflow Action", filters=filters, fields=["reference_name"], limit_page_length=0
		)

	names = list(dict.fromkeys(row.reference_name for row in actions if row.reference_name))
	if not names:
		return {"requests": [], "actions": {}}
	workflow = _procurement_workflow()
	state_field = workflow.workflow_state_field if workflow else "status"
	fields = [
		"name", "title", "company", "currency", "transaction_date", "schedule_date",
		"requested_by", "requester_name", "department", "approver", "approver_name",
		"justification", "rejection_reason", "total_qty", "status", "docstatus", "modified",
	]
	if state_field not in fields:
		fields.append(state_field)
	requests = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"name": ["in", names]},
		fields=fields,
		order_by="modified desc",
		limit_page_length=20,
	)
	_add_procurement_costs(requests)
	available = get_procurement_request_transitions(frappe.as_json([row.name for row in requests]))
	for request in requests:
		request.workflow_state = request.get(state_field)
	if not decided:
		requests = [row for row in requests if available.get(row.name)]
	return {"requests": requests, "actions": available}


def _add_procurement_costs(requests: list[dict]) -> None:
	"""Attach server-owned virtual totals and edit capabilities to list rows."""
	from tbs_commons.procurement.budget import request_summary

	workflow = _procurement_workflow()
	for request in requests:
		doc = frappe.get_doc(PROCUREMENT_REQUEST, request.name)
		request.total_estimated_cost = doc.total_estimated_cost
		request.can_edit = _can_edit_procurement_request(doc, workflow)
		request.budget_summary = request_summary(doc)


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
	names = frappe.parse_json(requests) or []
	if not names:
		return []

	readable = frappe.get_list(
		PROCUREMENT_REQUEST,
		filters={"name": ["in", names]},
		pluck="name",
		limit_page_length=0,
	)
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
			"item_group",
			"description",
			"preferred_supplier",
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
		employee = frappe.db.get_value(
			"Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
		)
	preferred = _preferred_approvers(employee)
	candidates.sort(key=lambda row: (row[0] not in preferred, (row[1] or row[0]).lower()))

	start, page_len = frappe.utils.cint(start), frappe.utils.cint(page_len)
	return candidates[start : start + page_len]


def _roles_that_may_approve() -> set[str]:
	"""Roles whose Frappe DocPerm allows submitting this doctype."""
	# Custom DocPerm replaces the standard permission rows when present.
	for source in ("Custom DocPerm", "DocPerm"):
		roles = frappe.get_all(
			source, filters={"parent": PROCUREMENT_REQUEST, "submit": 1}, pluck="role"
		)
		if roles:
			return set(roles)
	return set()


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
