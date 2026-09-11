"""Whitelisted endpoints for the TBS App employee tool frontend."""

import frappe

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
	"""Gate the app's tile on the desk apps screen.

	Not whitelisted: `frappe.get_attr` calls it directly from the apps-screen
	builder, so exposing it over HTTP would only widen the surface.
	"""
	if frappe.session.user == "Administrator":
		return True

	return bool(frappe.has_permission(EMPLOYEE, "read"))


# --- Leave -----------------------------------------------------------------

LEAVE_APPLICATION = "Leave Application"

DECISIONS = ("Approved", "Rejected")

# Roles that own the doctype and act as the backstop when a named approver has
# left or is unavailable. The Leave Approver role alone is deliberately not
# enough: it grants submit on *every* leave application, which would let one
# team's supervisor decide another team's requests.
LEAVE_ADMIN_ROLES = {"HR Manager", "HR User"}


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
		["name", "employee_name", "department", "company", "leave_approver", "image"],
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
