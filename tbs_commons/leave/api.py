"""Whitelisted endpoints for the leave section of the TBS Commons frontend.

Leave is self-service: an employee requests their own, and an approver decides
it. `request_leave` raises one and `decide_leave_application` settles one; HRMS's
own validation is what a request has to get past either way.

What is here is everything the frontend would otherwise have had to decide for
itself. Who may decide an application, which ones are waiting on you, how many
there are, what the outcomes are called and how each one reads are one rule with
several faces, and a frontend stating any of them a second time states it in a
place where changing it does not change what the server does.

Decisions come from the active Frappe Workflow when the site runs one. HRMS
expects that -- `validate_for_self_approval` steps aside for a workflow -- and
procurement has worked that way from the start, so a site that configures one
here gets its states, its styling and its transitions honoured rather than
bypassed. Without a workflow the outcomes are read off the `status` field's own
options, so a site that adds one by Property Setter is offered it. Neither path
has a state name or a role name behind it in this file.
"""

import frappe

from tbs_commons import workflow as wf
from tbs_commons.api import (
	roles_with_permission,
	session_employee,
	session_employee_access,
	session_employee_filters,
)

LEAVE_APPLICATION = "Leave Application"

# Statuses that are not a decision. Exactly the two `LeaveApplication.on_submit`
# refuses to submit: `Open` is where an application starts and `Cancelled` is
# where cancelling it lands. Everything else the field offers is an outcome an
# approver can choose, so a site that adds one is offered it without editing
# this file.
NON_DECISION_STATUSES = ("Open", "Cancelled")

# How an outcome reads when no Workflow is styling it. The names are Frappe's
# Workflow State styles, so both frontends colour a badge or a button from one
# vocabulary whether a workflow is running or not. An outcome this does not
# know is offered unstyled rather than withheld.
DEFAULT_DECISION_STYLES = {"Approved": "Success", "Rejected": "Danger"}

# Which outcome is the affirmative one, and so the only one a page may apply
# without asking twice. Derived from the style rather than from the name: a
# workflow that calls its approval something else still gets one solid button.
AFFIRMATIVE_STYLE = "Success"

# The outcome HRMS will not let an employee apply to their own application --
# see `LeaveApplication.validate_for_self_approval`, which tests
# `self.status == "Approved"` and so blocks approving but not turning down.
SELF_APPROVAL_STATUS = "Approved"

# The desk's own approver query: candidates come from the employee record and
# then up the department tree, not from a filter over User. Sent to the frontend
# rather than named there, so a site that wants a different set of candidates
# changes the query in one place.
# HRMS's own approver query, wrapped so the picker reads a name rather than a
# comma-separated one -- see `tbs_commons.api.get_approvers`.
APPROVER_QUERY = "tbs_commons.api.get_approvers"

# How many rows the approvals queue returns. The badge counts to the same
# ceiling, so it never promises more than the page will show.
PAGE_LENGTH = 20

# What a leave request may set. Server-owned on purpose: `status` sits at
# permlevel 1, `employee` is resolved from the session rather than accepted, and
# everything absent here -- the naming series, the posting date, the workflow's
# initial state -- is the doctype's to fill in, so a site that customises any of
# them gets what it configured.
REQUEST_FIELDS = (
	"leave_type",
	"from_date",
	"to_date",
	"half_day",
	"half_day_date",
	"description",
	"leave_approver",
)

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


def leave_workflow():
	"""The active Workflow for `Leave Application`, or None."""
	return wf.active_workflow(LEAVE_APPLICATION)


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


def decision_vocabulary(workflow) -> list[dict]:
	"""Every outcome an approver could be offered, and how each one reads.

	With a workflow, the outcomes are its actions and the styling is the site's:
	an action reads as the Workflow State it leads to. Without one they are the
	`status` field's own options less the two that are not decisions, styled by
	`DEFAULT_DECISION_STYLES`.

	`confirm` travels with the outcome rather than being inferred from its
	colour by whoever draws the button. Whether an irreversible choice deserves
	a second look is policy, and a site that adds an outcome should not have to
	know that a page somewhere decides that by reading a CSS variant.
	"""
	if workflow:
		styles = wf.state_styles(workflow)
		offered = wf.unique_actions(workflow.transitions)
		return [_decision(row["action"], styles.get(row["next_state"])) for row in offered]

	field = frappe.get_meta(LEAVE_APPLICATION).get_field("status")
	options = [option.strip() for option in (field.options or "").split("\n") if option.strip()]
	return [
		_decision(option, DEFAULT_DECISION_STYLES.get(option))
		for option in options
		if option not in NON_DECISION_STATUSES
	]


def _decision(value: str, style: str | None) -> dict:
	return {
		"value": value,
		"style": style,
		"confirm": style != AFFIRMATIVE_STYLE,
	}


def may_decide(doc) -> bool:
	"""Whether the session user may decide *this* application at all.

	The doctype-level right first, checked against the document so user
	permissions and sharing apply, and then narrower than the role: this
	application's own approver, or one of the roles that own the doctype.
	`check_permission("submit")` answers "may this user submit leave
	applications", which for the `Leave Approver` role means all of them.

	Which *outcomes* they may apply is a further question -- see
	`permitted_decisions`.
	"""
	if not frappe.has_permission(LEAVE_APPLICATION, "submit", doc=doc):
		return False
	if doc.get("leave_approver") == frappe.session.user:
		return True
	return bool(leave_admin_roles() & set(frappe.get_roles()))


def self_approval_blocked(employee: str | None, workflow) -> bool:
	"""Whether HRMS will refuse this user approving this employee's leave.

	Mirrors `LeaveApplication.validate_for_self_approval`, down to standing
	aside when a workflow is running -- the workflow's own conditions decide it
	then. Asked here so the queue never draws a button the write would throw on;
	the throw is still the server's, and still what actually stops it.
	"""
	if workflow or not employee:
		return False
	if not frappe.db.get_single_value("HR Settings", "prevent_self_leave_approval"):
		return False
	return frappe.db.get_value("Employee", employee, "user_id", cache=True) == frappe.session.user


def permitted_decisions(row, workflow, vocabulary, admin: bool, can_submit: bool) -> list[str]:
	"""The outcomes this user may apply to *this* row, named as the server names them.

	With a workflow this is `get_transitions` in this user's session, which is
	the only thing that can read a condition naming them. Without one it is the
	whole vocabulary, less anything HRMS would refuse -- and nothing at all
	unless this row is undecided and theirs to decide.
	"""
	if workflow:
		return [action["action"] for action in row.get("_transitions") or []]
	if not (
		can_submit
		and row.docstatus == 0
		and (admin or row.leave_approver == frappe.session.user)
	):
		return []
	values = [decision["value"] for decision in vocabulary]
	if self_approval_blocked(row.get("employee"), workflow):
		values = [value for value in values if value != SELF_APPROVAL_STATUS]
	return values


def status_display(row, workflow, styles: dict) -> tuple[str, str | None]:
	"""How a row reads to a person: its label, and the style to say it in.

	Settled here rather than in the page because `status` alone is not the
	answer. Without a workflow a decision is a status change *and* a submit, so
	an unsubmitted application is still pending whatever its status field says,
	and a cancelled one reads as cancelled whatever decision it carried. With a
	workflow the state is the answer and the site's Workflow State supplies the
	style.
	"""
	if workflow:
		state = row.get(wf.state_field(workflow))
		return state or row.status, styles.get(state)
	if row.docstatus == 2:
		return frappe._("Cancelled"), None
	if row.docstatus == 0:
		return frappe._("Pending"), "Warning"
	return row.status, DEFAULT_DECISION_STYLES.get(row.status)


def _queue_filters(decided: bool, admin: bool) -> dict:
	"""Which applications are this user's to look at, deciding or decided.

	The no-workflow predicate. `docstatus` is what "decided" means here, not
	`status`: a decision is a status change *and* a submit, and only a submitted
	application actually books the leave. An undecided one is `Open` as well,
	which is the state HRMS leaves a draft in -- without it a status somebody set
	from the desk without submitting would show up in the queue with buttons on
	it and be missing from the badge beside it.

	An admin sees everyone's, which is what makes them a usable backstop; anyone
	else sees the ones that name them.
	"""
	filters = {"docstatus": 1 if decided else 0}
	if not decided:
		filters["status"] = "Open"
	if not admin:
		filters["leave_approver"] = frappe.session.user
	return filters


def _pending_count(admin: bool, workflow=None) -> int:
	"""The badge. Capped the way the queue is, so the two agree."""
	if workflow:
		names = wf.names_in_movable_states(
			LEAVE_APPLICATION, workflow, wf.state_field(workflow)
		)[:PAGE_LENGTH]
		moves = wf.permitted_transitions(LEAVE_APPLICATION, names, workflow)
		return sum(1 for actions in moves.values() if actions)
	return len(
		frappe.get_list(
			LEAVE_APPLICATION,
			filters=_queue_filters(decided=False, admin=admin),
			pluck="name",
			limit_page_length=PAGE_LENGTH,
		)
	)


def _has_approvals_queue(workflow, can_read: bool) -> bool:
	"""Whether this user has an approvals queue at all -- see `get_leave_permissions`."""
	if not workflow:
		return bool(frappe.has_permission(LEAVE_APPLICATION, "submit"))
	roles = set(frappe.get_roles())
	return can_read and bool({row.allowed for row in workflow.transitions} & roles)


@frappe.whitelist()
def get_leave_permissions() -> dict:
	"""What the session user may do with leave, plus their approval backlog.

	`approve` is whether this user has an approvals queue at all. With a workflow
	that is holding a role some transition is open to -- not the doctype's submit
	right, because a workflow may route an application back to its author without
	deciding it, and gating on submit would hide the page from exactly the people
	a site added those states for. Without one it is the submit right, which is
	what deciding takes. Whether this user decides *this* application is a
	separate question — `get_leave_approval_queue` answers it per row, and
	`decide_leave_application` answers it again before writing anything.

	`decisions` is here so the page's buttons are the outcomes the server will
	actually accept, styled as the site styles them. `approver_mandatory` is
	HR Settings' answer rather than the form's assumption: a site that makes the
	approver optional is one where the form must let it through.

	`employee_filters` is what makes an Employee row this session's own. Sent
	rather than assembled in the page, because the page fetches that record --
	and its own applications -- through Frappe's document API, where every
	permission the site has configured applies without this module restating
	any of them. What stays the server's is the *predicate*: `user_id` names the
	login and `status` rules out a leaver, and a frontend writing that filter
	for itself would be the second place the rule lived. The same split
	self-service settled on -- see `get_change_permissions`, which sends
	`owner_field` and `owner_value` and lets the document API do the rest.

	`employee_access` is why there is no employee record, when that read comes
	back empty -- `visible`, `forbidden` or `missing`. Leave is requested against
	an employee record, so a page with no employee has to say something, and it
	used to say the same thing either way: ask HR to link your login. For a user
	whose `Employee` read was revoked that sent them to the wrong person about a
	record that already names them. It costs nothing on the common path: the raw
	existence check runs only once the permission-checked read has come back
	empty. It doubles as the page's cue not to attempt the read at all.

	`workflow` rides along because the page now labels its own rows. The states
	and their styling are still the site's -- what a badge says and what colour
	it is are read from here, not decided there. The approvals queue is
	unaffected: those rows are still labelled server-side by `status_display`,
	because which outcomes a row accepts is a permission question and has to be.
	"""
	workflow = leave_workflow()
	can_read = bool(frappe.has_permission(LEAVE_APPLICATION, "read"))
	can_approve = _has_approvals_queue(workflow, can_read)
	admin = bool(leave_admin_roles() & set(frappe.get_roles()))

	return {
		"read": can_read,
		"request": bool(frappe.has_permission(LEAVE_APPLICATION, "create")),
		"employee_filters": session_employee_filters(),
		"employee_access": session_employee_access(),
		"workflow": wf.describe(workflow) if can_read else None,
		"approve": can_approve,
		"pending_approvals": _pending_count(admin, workflow) if can_approve else 0,
		"decisions": decision_vocabulary(workflow),
		"page_length": PAGE_LENGTH,
		"approver_mandatory": bool(
			frappe.db.get_single_value(
				"HR Settings", "leave_approver_mandatory_in_leave_application"
			)
		),
		"approver_query": APPROVER_QUERY,
	}


@frappe.whitelist()
def get_leave_approval_queue(decided: int = 0) -> list[dict]:
	"""Applications waiting on this user's decision, or ones already decided.

	Here rather than in a list query the frontend builds, so "waiting on you"
	means one thing. The page's rows, the badge counting them and the endpoint
	that writes the decision all read the same predicate, and none of them can
	drift into a slightly different idea of what is pending.

	Each row carries the outcomes this user may apply to it and how the row
	itself reads, so the buttons and the badge are both the server's answer --
	an admin looking at somebody else's queue gets them, a reader who merely has
	the page open does not, and an approver looking at their own application
	does not get the one HRMS would refuse.
	"""
	decided = bool(frappe.utils.cint(decided))
	workflow = leave_workflow()
	admin = bool(leave_admin_roles() & set(frappe.get_roles()))

	if workflow:
		applications = _workflow_queue(workflow, decided)
	else:
		applications = frappe.get_list(
			LEAVE_APPLICATION,
			filters=_queue_filters(decided, admin),
			fields=LIST_FIELDS,
			# Soonest first while they are still decisions to make; most recently
			# touched first once they are history.
			order_by="modified desc" if decided else "from_date asc",
			limit_page_length=PAGE_LENGTH,
		)

	styles = wf.state_styles(workflow)
	vocabulary = decision_vocabulary(workflow)
	can_submit = workflow is not None or bool(
		frappe.has_permission(LEAVE_APPLICATION, "submit")
	)
	for application in applications:
		application.actions = permitted_decisions(
			application, workflow, vocabulary, admin, can_submit
		)
		application.can_decide = bool(application.actions)
		application.status_label, application.status_style = status_display(
			application, workflow, styles
		)
		application.pop("_transitions", None)
	return applications


def _workflow_queue(workflow, decided: bool) -> list[dict]:
	"""The queue a site running a Workflow on leave sees.

	Candidates are the applications parked in a state one of this user's roles
	can move; which of them they may actually act on is `get_transitions` in
	their own session, and a row it offers nothing for is not waiting on them.
	History is what they have completed, which only a Workflow Action records.
	"""
	state_field = wf.state_field(workflow)
	if decided:
		actions = frappe.get_all(
			"Workflow Action",
			filters={
				"reference_doctype": LEAVE_APPLICATION,
				"status": "Completed",
				"completed_by": frappe.session.user,
			},
			fields=["reference_name"],
		)
		names = list(dict.fromkeys(row.reference_name for row in actions if row.reference_name))
	else:
		names = wf.names_in_movable_states(LEAVE_APPLICATION, workflow, state_field)

	if not names:
		return []
	fields = LIST_FIELDS if state_field in LIST_FIELDS else [*LIST_FIELDS, state_field]
	applications = frappe.get_list(
		LEAVE_APPLICATION,
		filters={"name": ["in", names]},
		fields=fields,
		order_by="modified desc" if decided else "from_date asc",
		limit_page_length=PAGE_LENGTH,
	)
	# `get_list` has already settled what this user may read, so these names
	# need no second permission pass.
	available = wf.permitted_transitions(
		LEAVE_APPLICATION, [row.name for row in applications], workflow
	)
	for application in applications:
		application._transitions = available.get(application.name) or []
	if not decided:
		applications = [row for row in applications if row._transitions]
	return applications


@frappe.whitelist(methods=["POST"])
def request_leave(doc: str | dict) -> dict:
	"""Raise a leave application for the employee behind this session.

	Through here rather than straight at the document API so the field list a
	request may set is the server's. `employee` is resolved from the session
	instead of accepted: leave raised on somebody else's behalf is a desk job
	with its own permissions, and a self-service form that can name an employee
	is a self-service form that can name the wrong one.

	Everything `REQUEST_FIELDS` leaves out -- the naming series, the posting
	date, the status, a workflow's initial state -- is filled in by the doctype,
	so a site that customises any of them gets what it configured.
	"""
	values = frappe.parse_json(doc) or {}
	if not isinstance(values, dict):
		frappe.throw(frappe._("A Leave Application document is required."))
	if values.get("doctype") not in (None, LEAVE_APPLICATION):
		frappe.throw(frappe._("Only Leave Applications can be created here."))

	employee = session_employee(["name"])
	if not employee:
		frappe.throw(
			frappe._(
				"Your login is not linked to an employee record, so leave cannot be requested for it."
			),
			frappe.ValidationError,
		)
	named = values.get("employee")
	if named and named != employee.name:
		frappe.throw(
			frappe._("Leave can only be requested for your own employee record here."),
			frappe.PermissionError,
		)

	application = {field: values[field] for field in REQUEST_FIELDS if field in values}
	application["doctype"] = LEAVE_APPLICATION
	application["employee"] = employee.name
	return frappe.get_doc(application).insert().as_dict()


@frappe.whitelist(methods=["POST"])
def decide_leave_application(name: str, decision: str) -> dict:
	"""Settle a leave application, by the route the site has configured.

	With a Workflow that is `apply_workflow`, so the transition's own conditions,
	permitted roles and next state are what decide and what gets written. Without
	one the two halves are one action for the approver but two writes underneath:
	`status` sits at permlevel 1, and only a submitted (docstatus 1) application
	actually books the leave. Doing both here keeps them in one transaction — a
	status change that never got submitted would leave the request looking
	decided to the approver and still pending to everyone else.
	"""
	workflow = leave_workflow()
	offered = [option["value"] for option in decision_vocabulary(workflow)]
	if decision not in offered:
		frappe.throw(
			frappe._("Decision must be one of {0}").format(", ".join(offered)),
			frappe.ValidationError,
		)

	doc = frappe.get_doc(LEAVE_APPLICATION, name)

	if workflow:
		# No submit check here, deliberately. Not every transition submits -- a
		# workflow may route an application back to its author without deciding it
		# -- and `apply_workflow` already refuses an action this user's roles or the
		# transition's own condition do not allow, having read-checked the document
		# through `get_transitions` on the way. Demanding submit as well would block
		# exactly the states a site added a workflow in order to have.
		from frappe.model.workflow import apply_workflow

		doc = apply_workflow(doc, decision)
		return {
			"name": doc.name,
			"status": doc.get(wf.state_field(workflow)),
			"docstatus": doc.docstatus,
		}

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
