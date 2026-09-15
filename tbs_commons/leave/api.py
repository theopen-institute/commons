"""Whitelisted endpoints for the leave section of the TBS Commons frontend.

Leave is self-service: an employee requests their own, and a named approver
decides it. Requesting one goes straight through the REST API against `Leave
Application`, where HRMS's own validation is what matters.

Everything about *deciding* one lives here instead. Who may decide an
application, which ones are waiting on you, how many there are and what the two
answers are called are one rule with four faces, and a frontend that asked the
`Leave Application` list for its own version of any of them would be stating
that rule a second time -- in a place where changing it does not change what the
server actually does.
"""

import frappe

from tbs_commons.api import roles_with_permission, session_employee

LEAVE_APPLICATION = "Leave Application"

DECISIONS = ("Approved", "Rejected")

# How many rows the approvals queue returns. The badge counts to the same
# ceiling, so it never promises more than the page will show.
PAGE_LENGTH = 20

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

# What a queue row carries. Server-owned, so a field that turns out to need a
# permlevel or a rename is changed in one place.
LIST_FIELDS = [
	"name",
	"employee",
	"employee_name",
	"leave_type",
	"from_date",
	"to_date",
	"total_leave_days",
	"half_day",
	"description",
	"status",
	"docstatus",
	"leave_approver",
	"leave_approver_name",
	"posting_date",
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


def leave_admin_roles() -> set[str]:
	"""Roles that own the doctype, and so act as the backstop for an absent approver.

	Derived from the doctype's own permission rows rather than named here, so a
	site that renames its HR roles or grants the backstop to another one says so
	once, in the Role Permission Manager, and this follows.

	The test is submit *and* create at once. Deciding is what `submit` grants,
	and on the standard rows `Leave Approver` holds it too -- for every
	application on the site, which is exactly the over-reach this narrows. A role
	that may also raise applications is one that owns the doctype rather than one
	the workflow points at, and that is the backstop wanted here.

	Empty is a legitimate answer: a site whose permissions name no such role has
	no backstop, and the named approver is then the only person who can decide.
	"""
	return roles_with_permission(LEAVE_APPLICATION, submit=1, create=1)


def may_decide(doc) -> bool:
	"""Whether the session user may decide *this* application.

	The doctype-level right first, checked against the document so user
	permissions and sharing apply, and then narrower than the role: this
	application's own approver, or one of the roles that own the doctype.
	`check_permission("submit")` answers "may this user submit leave
	applications", which for the `Leave Approver` role means all of them.
	"""
	if not frappe.has_permission(LEAVE_APPLICATION, "submit", doc=doc):
		return False
	if doc.get("leave_approver") == frappe.session.user:
		return True
	return bool(leave_admin_roles() & set(frappe.get_roles()))


def _queue_filters(decided: bool, admin: bool) -> dict:
	"""Which applications are this user's to look at, deciding or decided.

	`docstatus` is what "decided" means here, not `status`: a decision is a
	status change *and* a submit, and only a submitted application actually books
	the leave. An undecided one is `Open` as well, which is the state HRMS leaves
	a draft in -- without it a status somebody set from the desk without
	submitting would show up in the queue with buttons on it and be missing from
	the badge beside it.

	An admin sees everyone's, which is what makes them a usable backstop; anyone
	else sees the ones that name them.
	"""
	filters = {"docstatus": 1 if decided else 0}
	if not decided:
		filters["status"] = "Open"
	if not admin:
		filters["leave_approver"] = frappe.session.user
	return filters


def _pending_count(admin: bool) -> int:
	"""The badge. Capped the way the queue is, so the two agree."""
	return len(
		frappe.get_list(
			LEAVE_APPLICATION,
			filters=_queue_filters(decided=False, admin=admin),
			pluck="name",
			limit_page_length=PAGE_LENGTH,
		)
	)


@frappe.whitelist()
def get_leave_permissions() -> dict:
	"""What the session user may do with leave, plus their approval backlog.

	`approve` is the doctype-level submit right (the Leave Approver role and the
	HR roles carry it). Whether this user approves *this* application is a
	separate question — `get_leave_approval_queue` answers it per row, and
	`decide_leave_application` answers it again before writing anything.

	`decisions` is here so the page's two buttons are the two outcomes the server
	will actually accept, rather than a pair spelled out again in the frontend.
	"""
	can_approve = bool(frappe.has_permission(LEAVE_APPLICATION, "submit"))
	admin = bool(leave_admin_roles() & set(frappe.get_roles()))

	return {
		"read": bool(frappe.has_permission(LEAVE_APPLICATION, "read")),
		"request": bool(frappe.has_permission(LEAVE_APPLICATION, "create")),
		"approve": can_approve,
		"pending_approvals": _pending_count(admin) if can_approve else 0,
		"decisions": list(DECISIONS),
		"page_length": PAGE_LENGTH,
	}


@frappe.whitelist()
def get_leave_approval_queue(decided: int = 0) -> list[dict]:
	"""Applications waiting on this user's decision, or ones already decided.

	Here rather than in a list query the frontend builds, so "waiting on you"
	means one thing. The page's rows, the badge counting them and the endpoint
	that writes the decision all read the same predicate, and none of them can
	drift into a slightly different idea of what is pending.

	Each row carries `can_decide`, so the buttons are drawn from the server's
	answer rather than from `docstatus` -- an admin looking at somebody else's
	queue gets them, and a reader who merely has the page open does not.
	"""
	decided = bool(frappe.utils.cint(decided))
	admin = bool(leave_admin_roles() & set(frappe.get_roles()))

	applications = frappe.get_list(
		LEAVE_APPLICATION,
		filters=_queue_filters(decided, admin),
		fields=LIST_FIELDS,
		# Soonest first while they are still decisions to make; most recently
		# touched first once they are history.
		order_by="modified desc" if decided else "from_date asc",
		limit_page_length=PAGE_LENGTH,
	)

	can_submit = bool(frappe.has_permission(LEAVE_APPLICATION, "submit"))
	for application in applications:
		application.can_decide = bool(
			can_submit
			and application.docstatus == 0
			and (admin or application.leave_approver == frappe.session.user)
		)
	return applications


@frappe.whitelist()
def get_my_leave_applications() -> list[dict]:
	"""The session user's own applications, newest first.

	Filtered on the employee this login is linked to rather than on the login,
	because leave is requested against an employee record. A user with none has
	no leave of their own — an empty list, not everyone else's, which is what an
	unfiltered read would give an approver.
	"""
	employee = session_employee(["name"])
	if not employee:
		return []
	return frappe.get_list(
		LEAVE_APPLICATION,
		filters={"employee": employee.name},
		fields=LIST_FIELDS,
		order_by="from_date desc",
		limit_page_length=PAGE_LENGTH,
	)


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

	# The right to decide, not just to read, and checked against this document so
	# user permissions and sharing apply. `check_permission` first, so a user
	# without the right at all gets Frappe's own message rather than this one.
	doc.check_permission("submit")
	if not may_decide(doc):
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
