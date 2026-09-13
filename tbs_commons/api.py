"""Whitelisted endpoints for the TBS Commons employee tool frontend."""

import frappe
from frappe.utils import flt

from tbsapp.tbs_app.doctype.procurement_request.procurement_request import get_ordered_qty_map

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
	from tbsapp.www.tbsapp import get_user_info

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

# Roles that may decide a request they are not named on — the backstop for an
# approver who has left, and the people who run procurement anyway. Narrower
# than "whoever can submit", which by design includes every Purchase User.
PROCUREMENT_ADMIN_ROLES = {"Purchase Manager"}

PENDING_APPROVAL = "Pending Approval"


def check_procurement_app_permission() -> bool:
	"""Gate the Procurement tile, which is its own app on the apps screen."""
	if frappe.session.user == "Administrator":
		return True

	return bool(frappe.has_permission(PROCUREMENT_REQUEST, "read"))


@frappe.whitelist()
def get_procurement_permissions() -> dict:
	"""What the session user may do with procurement, plus their backlog.

	`approve` is the doctype-level submit right. Whether this user decides
	*this* request is a separate question that `decide_procurement_request`
	answers per document.

	Carries the two defaults a new request needs as well. They are cheap, and
	the alternative is the request form making its own round trips for a
	company and a unit before it can render a single blank line.
	"""
	can_approve = bool(frappe.has_permission(PROCUREMENT_REQUEST, "submit"))

	pending = 0
	if can_approve:
		pending = frappe.db.count(
			PROCUREMENT_REQUEST,
			{"approver": frappe.session.user, "docstatus": 0, "status": PENDING_APPROVAL},
		)

	company = _default_company()

	return {
		"read": bool(frappe.has_permission(PROCUREMENT_REQUEST, "read")),
		"request": bool(frappe.has_permission(PROCUREMENT_REQUEST, "create")),
		"approve": can_approve,
		"pending_approvals": pending,
		"default_company": company,
		"default_currency": (
			frappe.db.get_value("Company", company, "default_currency") if company else None
		),
		"default_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
	}


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


@frappe.whitelist(methods=["POST"])
def send_procurement_request(name: str) -> dict:
	"""Hand a draft to its approver.

	Separate from creating it: a request assembled in the desk is a draft until
	someone says it is ready, and the line items are the part that takes more
	than one sitting.
	"""
	doc = frappe.get_doc(PROCUREMENT_REQUEST, name)
	doc.check_permission("write")

	if doc.docstatus != 0:
		frappe.throw(
			frappe._("{0} has already been decided.").format(name), frappe.ValidationError
		)

	if doc.status == PENDING_APPROVAL:
		frappe.throw(
			frappe._("{0} is already with {1}.").format(
				name, doc.approver_name or doc.approver or frappe._("its approver")
			),
			frappe.ValidationError,
		)

	if not doc.approver:
		frappe.throw(
			frappe._("Name an approver before sending this request."), frappe.ValidationError
		)

	# `db_set`, not `save`: `status` is permlevel 1 and the requester cannot
	# write it, which is the whole point — they may hand the request over, not
	# decide it. The value is fixed here, not user input.
	doc.db_set("status", PENDING_APPROVAL)

	return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}


@frappe.whitelist(methods=["POST"])
def decide_procurement_request(name: str, decision: str, reason: str | None = None) -> dict:
	"""Approve or reject a procurement request and submit it.

	One action for the approver, two writes underneath, for the same reason as
	`decide_leave_application`: `status` is permlevel 1, and only a submitted
	request can go on to become a Material Request. Splitting them would leave
	a request that reads as decided to one person and pending to everyone else.
	"""
	if decision not in DECISIONS:
		frappe.throw(
			frappe._("Decision must be one of {0}").format(", ".join(DECISIONS)),
			frappe.ValidationError,
		)

	doc = frappe.get_doc(PROCUREMENT_REQUEST, name)

	# The right to decide, not merely to read, checked against this document so
	# user permissions and sharing apply.
	doc.check_permission("submit")

	# ...and then narrower: this request's own approver. `check_permission`
	# only answers "may this user submit procurement requests", which for a
	# Purchase User means all of them.
	if doc.approver != frappe.session.user and not (
		PROCUREMENT_ADMIN_ROLES & set(frappe.get_roles())
	):
		frappe.throw(
			frappe._("{0} is not yours to decide — it is assigned to {1}.").format(
				name, doc.approver_name or doc.approver or frappe._("nobody")
			),
			frappe.PermissionError,
		)

	if doc.docstatus != 0:
		frappe.throw(
			frappe._("{0} has already been {1}.").format(name, doc.status.lower()),
			frappe.ValidationError,
		)

	if doc.status != PENDING_APPROVAL:
		frappe.throw(
			frappe._("{0} has not been sent for approval yet.").format(name),
			frappe.ValidationError,
		)

	doc.status = decision
	if decision == "Rejected":
		doc.rejection_reason = reason or None
	doc.save()

	# permlevel 1 again: a user without write access there has the change
	# silently reverted rather than refused, and would then submit a request
	# that still says it is pending.
	if doc.status != decision:
		frappe.throw(
			frappe._(
				"You are not permitted to decide procurement requests. The Purchase User and Purchase Manager roles grant this."
			),
			frappe.PermissionError,
		)

	doc.submit()

	return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}


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
			"schedule_date",
			"estimated_rate",
			"estimated_amount",
		],
		order_by="parent asc, idx asc",
		limit_page_length=0,
	)

	# `ordered_qty` and what is left of each row are counted, not stored, so a
	# list query cannot ask for them. One grouped read covers every line on the
	# page -- see `get_ordered_qty_map`.
	ordered = get_ordered_qty_map(readable)
	for line in lines:
		line.ordered_qty = flt(ordered.get(line.name))
		line.pending_qty = max(flt(line.qty) - line.ordered_qty, 0.0)

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

	preferred = _preferred_approvers(filters.get("employee") if filters else None)
	candidates.sort(key=lambda row: (row[0] not in preferred, (row[1] or row[0]).lower()))

	start, page_len = frappe.utils.cint(start), frappe.utils.cint(page_len)
	return candidates[start : start + page_len]


def _roles_that_may_approve() -> set[str]:
	"""Roles with submit on Procurement Request.

	Custom DocPerm replaces the shipped rows wholesale when a site has any, so
	it is checked first rather than merged.
	"""
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
