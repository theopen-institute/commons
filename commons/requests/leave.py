"""Leave: what is its own, and the endpoints the frontend reaches.

Leave is self-service: an employee requests their own, and an approver decides
it. `request_leave` raises one and `decide_leave_application` settles one;
HRMS's own validation is what a request has to get past either way.

The shape of all that -- who may decide, which rows are waiting on you, how
many there are, what the outcomes are called and how each one reads -- is
`approvals.RequestType`, shared with expenses and read by procurement. What is
left here is what is genuinely leave's:

* the doctype, its deciding field and the two values on it that are not a
  decision;
* a backstop derived from the doctype's own permission rows, which leave can do
  and expenses cannot -- `Leave.admin_roles`;
* HRMS refusing an approver's own *approval* rather than their own submit, so
  preventing self-approval costs one outcome and not all of them --
  `self_approval_outcome`.

Decisions come from the active Frappe Workflow when the site runs one. HRMS
expects that -- `validate_for_self_approval` steps aside for a workflow -- and
procurement has worked that way from the start, so a site that configures one
here gets its states, its styling and its transitions honoured rather than
bypassed. Without a workflow the outcomes are read off the `status` field's own
options, so a site that adds one by Property Setter is offered it. Neither path
has a state name or a role name behind it in this file.
"""

import frappe

from commons.commons_core.doc_perms import roles_with_permission
from commons.requests import approvals

LEAVE_APPLICATION = "Leave Application"


class Leave(approvals.RequestType):
	doctype = LEAVE_APPLICATION
	approver_field = "leave_approver"
	approver_name_field = "leave_approver_name"

	# Exactly the two `LeaveApplication.on_submit` refuses to submit: `Open` is
	# where an application starts and `Cancelled` is where cancelling it lands.
	non_decision_values = ("Open", "Cancelled")

	# HRMS will not let an employee apply *this* outcome to their own
	# application -- see `LeaveApplication.validate_for_self_approval`, which
	# tests `self.status == "Approved"` and so blocks approving but not turning
	# down. Expenses have no equivalent; see `approvals.self_approval_outcome`.
	self_approval_setting = "prevent_self_leave_approval"
	self_approval_outcome = "Approved"

	approver_mandatory_setting = "leave_approver_mandatory_in_leave_application"

	# Soonest first while they are still decisions to make; most recently
	# touched first once they are history.
	pending_order_by = "from_date asc"
	decided_order_by = "modified desc"

	request_fields = (
		"leave_type",
		"from_date",
		"to_date",
		"half_day",
		"half_day_date",
		"description",
		"leave_approver",
	)

	list_fields = (
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
	)

	def admin_roles(self) -> set[str]:
		"""Roles that own the doctype, and so back up an absent approver.

		Derived from the doctype's own permission rows rather than named here,
		so a site that renames its HR roles or grants the backstop to another one
		says so once, in the Role Permission Manager, and this follows.

		The test is submit *and* create at once. Deciding is what `submit`
		grants, and on the standard rows `Leave Approver` holds it too -- for
		every application on the site, which is exactly the over-reach this
		narrows. A role that may also raise applications is one that owns the
		doctype rather than one the workflow points at, and that is the backstop
		wanted here.

		Empty is a legitimate answer: a site whose permissions name no such role
		has no backstop, and the named approver is then the only person who can
		decide.
		"""
		return roles_with_permission(self.doctype, submit=1, create=1)

	def row_is_theirs(self, row, admin: bool) -> bool:
		"""This application's own approver, or one of the roles that own it.

		Narrower than the doctype right on purpose: `has_permission("submit")`
		answers "may this user submit leave applications", which for the
		`Leave Approver` role means all of them.
		"""
		return admin or row.get(self.approver_field) == frappe.session.user

	def queue_predicate(self, decided: bool, admin: bool) -> tuple[dict, list | None]:
		"""Which applications are this user's to look at, deciding or decided.

		An undecided one is `Open` as well as unsubmitted, which is the state
		HRMS leaves a draft in -- without it a status somebody set from the desk
		without submitting would show up in the queue with buttons on it and be
		missing from the badge beside it.

		An admin sees everyone's, which is what makes them a usable backstop;
		anyone else sees the ones that name them.
		"""
		filters = {"docstatus": 1 if decided else 0}
		if not decided:
			filters["status"] = "Open"
		if not admin:
			filters[self.approver_field] = frappe.session.user
		return filters, None

	def no_employee_message(self) -> str:
		return frappe._(
			"Your login is not linked to an employee record, so leave cannot be requested for it."
		)

	def foreign_employee_message(self) -> str:
		return frappe._("Leave can only be requested for your own employee record here.")

	def permlevel_message(self) -> str:
		return frappe._(
			"You are not permitted to decide leave applications. The Leave Approver role grants this."
		)

	def not_yours_message(self, doc) -> str:
		return frappe._("{0} is not your leave application to decide — it is assigned to {1}.").format(
			doc.name,
			doc.get(self.approver_name_field) or doc.get(self.approver_field) or frappe._("nobody"),
		)

	def already_decided_message(self, doc) -> str:
		return frappe._("{0} has already been {1}.").format(doc.name, doc.status.lower())


LEAVE = Leave()


@frappe.whitelist()
def get_leave_permissions() -> dict:
	"""What the session user may do with leave, plus their approval backlog.

	See `approvals.RequestType.permissions`, which is this answer and the
	argument for every field in it.
	"""
	return LEAVE.permissions()


@frappe.whitelist()
def get_leave_approval_queue(decided: int = 0) -> list[dict]:
	"""Applications waiting on this user's decision, or ones already decided.

	An admin looking at somebody else's queue gets buttons, a reader who merely
	has the page open does not, and an approver looking at their own application
	does not get the one HRMS would refuse. See
	`approvals.RequestType.approval_queue`.
	"""
	return LEAVE.approval_queue(bool(frappe.utils.cint(decided)))


@frappe.whitelist(methods=["POST"])
def request_leave(doc: str | dict) -> dict:
	"""Raise a leave application for the employee behind this session.

	Through here rather than straight at the document API so the field list a
	request may set is the server's, and so the employee is resolved from the
	session instead of accepted -- see `approvals.RequestType.request_employee`.
	"""
	values = LEAVE.parse_request(doc)
	employee = LEAVE.request_employee(values, ["name"])
	return frappe.get_doc(LEAVE.new_request(values, employee)).insert().as_dict()


@frappe.whitelist(methods=["POST"])
def decide_leave_application(name: str, decision: str) -> dict:
	"""Settle a leave application, by the route the site has configured.

	See `approvals.RequestType.decide`: a Workflow transition where one is
	running, and a status change plus a submit in one transaction where none is.
	"""
	return LEAVE.decide(name, decision)
