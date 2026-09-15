"""Whitelisted endpoints for the leave section of the TBS Commons frontend.

Leave is self-service: an employee requests their own, and a named approver
decides it. Reading and creating go straight through the REST API against
`Leave Application`; only the two questions Frappe cannot answer in one call --
"which employee am I" and "decide this one" -- live here.
"""

import frappe

from tbs_commons.api import session_employee

LEAVE_APPLICATION = "Leave Application"

DECISIONS = ("Approved", "Rejected")

# Roles that own the doctype and act as the backstop when a named approver has
# left or is unavailable. The Leave Approver role alone is deliberately not
# enough: it grants submit on *every* leave application, which would let one
# team's supervisor decide another team's requests.
LEAVE_ADMIN_ROLES = {"HR Manager", "HR User"}

# What the leave pages render for the employee behind the session user.
# `expense_approver` is procurement's, borrowed here because one query is
# cheaper than two -- see `tbs_commons.procurement.api.get_procurement_approvers`.
MY_EMPLOYEE_FIELDS = [
	"name",
	"employee_name",
	"department",
	"company",
	"leave_approver",
	"expense_approver",
	"image",
]


@frappe.whitelist()
def get_my_employee() -> dict | None:
	"""Return the Employee record linked to the session user, or None.

	Every leave page starts from "which employee am I". A user with no linked
	Employee (`user_id`) cannot request leave — the page says so rather than
	failing at submit.
	"""
	employee = session_employee(MY_EMPLOYEE_FIELDS)
	if not employee:
		return None

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
