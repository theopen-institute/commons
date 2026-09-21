"""What a request is, said once for the three things this module is about.

Leave, expenses and procurement are one shape wearing three names. Somebody
raises something about themselves, somebody else decides it, and everything
between the two -- which outcomes exist, how each one reads, whose queue a row
is in, how many are waiting, what a decision actually writes -- is the same
question asked of a different doctype.

It used to be answered three times. `leave/api.py` and `expense/api.py` were
near-identical files, and the second said so in its own opening line: "written
to the shape leave settled on". Agreement by transcription is agreement right
up until somebody edits one of them, and the first thing that went was the
decision vocabulary: two copies of the same derivation, styled from two copies
of the same table.

So the shape is here, as `RequestType`, and each section keeps what is
genuinely its own -- the doctype, the field an approver settles, what a queue
row carries, and the handful of rules HRMS applies to one and not the other.
Each of those is a named attribute or an overridden method, so a difference
between two sections is a line you can point at rather than a diff you have to
run.

Nothing here names a state, a role or an outcome. Those are read off the site's
own Workflow where it runs one, and off the deciding field's own options where
it does not -- which is what lets a site add an outcome by Property Setter, or
retune a workflow, and be offered what it configured.
"""

import frappe

from commons.api import (
	session_employee,
	session_employee_access,
	session_employee_filters,
)
from commons.commons_core import apps
from commons.commons_core import workflow as wf

# How an outcome reads when no Workflow is styling it. The names are Frappe's
# Workflow State styles, so a badge or a button is coloured from one vocabulary
# whether a workflow is running or not. An outcome this does not know is offered
# unstyled rather than withheld.
DEFAULT_DECISION_STYLES = {"Approved": "Success", "Rejected": "Danger"}

# Which outcome is the affirmative one, and so the only one a page may apply
# without asking twice. Derived from the style rather than from the name: a
# workflow that calls its approval something else still gets one solid button.
AFFIRMATIVE_STYLE = "Success"

# The desk's own approver query: candidates come from the employee record and
# then up the department tree, not from a filter over User. Sent to the frontend
# rather than named there, so a site that wants a different set of candidates
# changes the query in one place. HRMS's own, wrapped so the picker reads a name
# rather than a comma-separated one -- see `commons.requests.approvers`.
APPROVER_QUERY = "commons.requests.approvers.get_approvers"

# How many rows an approvals queue returns. The badge counts to the same
# ceiling, so it never promises more than the page will show.
PAGE_LENGTH = 20


def decision(value: str, style: str | None) -> dict:
	"""One outcome, and how it reads.

	`confirm` travels with the outcome rather than being inferred from its
	colour by whoever draws the button. Whether an irreversible choice deserves
	a second look is policy, and a site that adds an outcome should not have to
	know that a page somewhere decides that by reading a CSS variant.
	"""
	return {"value": value, "style": style, "confirm": style != AFFIRMATIVE_STYLE}


def completed_by_session(doctype: str) -> list[str]:
	"""Documents of `doctype` this user has already acted on through a Workflow.

	What somebody did is recorded nowhere else, and `completed_by` names them,
	so a Workflow Action answers a History tab exactly. Deduplicated in order:
	one document collects an action per transition, and a queue wants it once.
	"""
	actions = frappe.get_all(
		"Workflow Action",
		filters={
			"reference_doctype": doctype,
			"status": "Completed",
			"completed_by": frappe.session.user,
		},
		fields=["reference_name"],
	)
	return list(dict.fromkeys(row.reference_name for row in actions if row.reference_name))


class RequestType:
	"""One thing a person raises and an approver settles.

	Subclassed once per section. What a subclass sets is what is actually
	different about it; everything it does not set is answered the same way for
	every section, here, where changing it changes all three at once.
	"""

	# The doctype behind the section, and the field an approver settles. Not
	# always `status`: `Expense Claim` derives that one from the decision and the
	# docstatus and marks it read-only -- see `expense.Expenses`.
	doctype: str
	decision_field = "status"

	# The field naming whose decision a row is waiting on, and the fetched name
	# beside it where the doctype keeps one.
	approver_field: str
	approver_name_field: str | None = None

	# Values of `decision_field` that are not a decision: where a request starts
	# and where cancelling one lands. Everything else the field offers is an
	# outcome an approver can choose, so a site that adds one is offered it
	# without editing any of this.
	non_decision_values: tuple[str, ...] = ()

	# What a queue row carries. Server-owned, so a field that turns out to need a
	# permlevel or a rename is changed in one place.
	list_fields: tuple[str, ...] = ()

	# What a request may set. Server-owned on purpose: the deciding field sits at
	# permlevel 1, `employee` is resolved from the session rather than accepted,
	# and everything absent -- the naming series, the posting date, a workflow's
	# initial state -- is the doctype's to fill in, so a site that customises any
	# of them gets what it configured.
	request_fields: tuple[str, ...] = ()

	# Soonest or oldest first while they are still decisions to make; most
	# recently touched first once they are history.
	pending_order_by = "modified desc"
	decided_order_by = "modified desc"

	# HR Settings' own switches, named rather than read: which one prevents
	# settling your own, and which one makes the approver mandatory.
	self_approval_setting: str | None = None
	approver_mandatory_setting: str | None = None

	# Which outcome self-approval costs, when the site prevents it. `None` means
	# every one of them. `LeaveApplication.validate_for_self_approval` tests the
	# outcome, so an approver may still turn their own application down;
	# `ExpenseClaim` tests the submit itself, so nothing is left to offer.
	self_approval_outcome: str | None = None

	page_length = PAGE_LENGTH
	approver_query = APPROVER_QUERY

	# Apps a section cannot work without, beyond its own doctype being here.
	# Empty for a section whose doctype is the whole of the answer -- see
	# `available`.
	requires_apps: tuple[str, ...] = ()

	# -- whether the site has this section at all ----------------------------

	def available(self) -> bool:
		"""Whether this site has what the section needs in order to work at all.

		`required_apps` names only Frappe, so every section here is optional and
		each one is absent for its own reason.

		Leave and expenses are absent when their doctype is: `Leave Application`
		and `Expense Claim` are HRMS's, and that doctype is the whole of what
		the section touches.

		Procurement's own doctype is this app's and is therefore always here,
		so the doctype test would answer yes on a site where nothing about the
		section works. What it is missing there is ERPNext, which it names in
		`requires_apps` -- see `commons.commons_core.apps` on why that one is asked
		about the app and these two about a doctype.
		"""
		if not all(apps.installed(app) for app in self.requires_apps):
			return False
		return apps.has_doctype(self.doctype)

	def require_available(self) -> None:
		"""Refuse an endpoint for a section this site does not have.

		Said here rather than left to the `DoesNotExistError` `frappe.get_meta`
		or a missing table would raise several frames in, so somebody calling one
		of these directly is told what is actually missing -- the app, where an
		app is what is missing, because "Procurement Request is not available"
		would be a puzzle on a site where that doctype is plainly there. The
		pages never reach this: `permissions` answers first, and a section it
		says `read: false` for is drawn nowhere.
		"""
		if self.available():
			return

		missing = [app for app in self.requires_apps if not apps.installed(app)]
		if missing:
			frappe.throw(
				frappe._("{0} needs {1}, which is not installed on this site.").format(
					frappe._(self.doctype), ", ".join(missing)
				),
				frappe.DoesNotExistError,
			)
		frappe.throw(
			frappe._("{0} is not available on this site.").format(frappe._(self.doctype)),
			frappe.DoesNotExistError,
		)

	def unavailable(self) -> dict:
		"""The permissions payload for a section this site does not have.

		Every answer false and every list empty -- which is exactly the
		placeholder the frontend already holds while the real answer is in
		flight (`section.ts`'s `NONE`), so nothing in the browser has to learn
		what an uninstalled app is. `read: false` is the whole of it: the sidebar
		row, the tabs, the badge and the search bar's "New ..." all hang off it.

		The employee fields are left blank rather than looked up. They are read
		only by a page this answer has just taken away, and two queries to fill
		in something nobody renders is two queries on every page load of a site
		that does not have the section.
		"""
		return {
			"read": False,
			"request": False,
			"employee_filters": {},
			"employee_access": "missing",
			"workflow": None,
			"approve": False,
			"pending_approvals": 0,
			"decisions": [],
			"page_length": self.page_length,
			"approver_mandatory": False,
			"approver_query": self.approver_query,
		}

	# -- the site's configuration -------------------------------------------

	def workflow(self):
		"""The active Workflow for this doctype, or None if the site runs none."""
		return wf.active_workflow(self.doctype)

	def state_field(self, workflow) -> str:
		"""The column a workflow keeps its state in, or this section's own."""
		return wf.state_field(workflow, self.decision_field)

	def decision_vocabulary(self, workflow) -> list[dict]:
		"""Every outcome an approver could be offered, and how each one reads.

		With a workflow, the outcomes are its actions and the styling is the
		site's: an action reads as the Workflow State it leads to. Without one
		they are the deciding field's own options less the ones that are not
		decisions, styled by `DEFAULT_DECISION_STYLES`.
		"""
		if workflow:
			styles = wf.state_styles(workflow)
			offered = wf.unique_actions(workflow.transitions)
			return [decision(row["action"], styles.get(row["next_state"])) for row in offered]

		field = frappe.get_meta(self.doctype).get_field(self.decision_field)
		options = [option.strip() for option in (field.options or "").split("\n") if option.strip()]
		return [
			decision(option, DEFAULT_DECISION_STYLES.get(option))
			for option in options
			if option not in self.non_decision_values
		]

	# -- who decides ---------------------------------------------------------

	def admin_roles(self) -> set[str]:
		"""Roles that act as the backstop for an absent or unreachable approver.

		Empty for a section that has no such role to derive -- see
		`expense.Expenses.admin_roles`, which explains why deriving one there
		would hand every approver on the site everybody else's claims.
		"""
		return set()

	def is_admin(self) -> bool:
		"""Whether this session holds one of them. Passed around rather than
		re-asked: `admin_roles` reads the doctype's permission rows, and a queue
		would otherwise ask once per row."""
		roles = self.admin_roles()
		return bool(roles and roles & set(frappe.get_roles()))

	def row_is_theirs(self, row, admin: bool) -> bool:
		"""Whether this row is this user's to act on, beyond the doctype right.

		The doctype-level `submit` right is the wrong test on its own: on the
		standard permission rows it means *every* document of the type, which is
		exactly the over-reach each section narrows here.
		"""
		raise NotImplementedError

	def may_decide(self, doc) -> bool:
		"""Whether the session user may settle *this* document at all.

		The doctype-level right first, checked against the document so user
		permissions and sharing apply, and then narrower than the role.

		Which *outcomes* they may apply is a further question -- see
		`permitted_decisions`.
		"""
		if not frappe.has_permission(self.doctype, "submit", doc=doc):
			return False
		return self.row_is_theirs(doc, self.is_admin())

	def self_approval_blocked(self, employee: str | None, workflow) -> bool:
		"""Whether HRMS will refuse this user settling this employee's request.

		Mirrors HRMS's own `validate_for_self_approval`, down to standing aside
		when a workflow is running -- the workflow's own conditions decide it
		then. Asked here so a queue never draws a button the write would throw
		on; the throw is still the server's, and still what actually stops it.
		"""
		if workflow or not employee or not self.self_approval_setting:
			return False
		if not frappe.db.get_single_value("HR Settings", self.self_approval_setting):
			return False
		return frappe.db.get_value("Employee", employee, "user_id", cache=True) == frappe.session.user

	def permitted_decisions(self, row, workflow, vocabulary, admin: bool, can_submit: bool) -> list[str]:
		"""The outcomes this user may apply to *this* row, in the server's words.

		With a workflow this is `get_transitions` in this user's session, which
		is the only thing that can read a condition naming them. Without one it
		is the whole vocabulary -- and nothing at all unless this row is
		undecided, theirs to decide, and not one HRMS would refuse them on the
		way to the database.
		"""
		if workflow:
			return [action["action"] for action in row.get("_transitions") or []]
		if not (can_submit and row.docstatus == 0 and self.row_is_theirs(row, admin)):
			return []

		values = [option["value"] for option in vocabulary]
		if not self.self_approval_blocked(row.get("employee"), workflow):
			return values
		# Every outcome goes where HRMS refuses the submit rather than the
		# outcome; see `self_approval_outcome`.
		if self.self_approval_outcome is None:
			return []
		return [value for value in values if value != self.self_approval_outcome]

	# -- how a row reads -----------------------------------------------------

	def status_display(self, row, workflow, styles: dict) -> tuple[str, str | None]:
		"""How a row reads to a person: its label, and the style to say it in.

		Settled here rather than in the page because the deciding field alone is
		not the answer. Without a workflow a decision is a field change *and* a
		submit, so an unsubmitted request is still pending whatever that field
		says, and a cancelled one reads as cancelled whatever decision it
		carried. With a workflow the state is the answer and the site's Workflow
		State supplies the style.
		"""
		if workflow:
			state = row.get(self.state_field(workflow))
			return state or row.get(self.decision_field), styles.get(state)
		if row.docstatus == 2:
			return frappe._("Cancelled"), None
		if row.docstatus == 0:
			return frappe._("Pending"), "Warning"
		decided = row.get(self.decision_field)
		return decided, DEFAULT_DECISION_STYLES.get(decided)

	# -- the queue -----------------------------------------------------------

	def queue_predicate(self, decided: bool, admin: bool) -> tuple[dict, list | None]:
		"""Which documents are this user's to look at, deciding or decided.

		The no-workflow predicate, as one answer, because the page's rows and
		the badge counting them both have to ask it. `docstatus` is what
		"decided" means, not the deciding field: settling a request is a field
		change *and* a submit, and only a submitted one books anything.
		"""
		raise NotImplementedError

	def pending_count(self, workflow, admin: bool) -> int:
		"""The badge. Capped the way the queue is, so the two agree."""
		if workflow:
			names = wf.names_in_movable_states(
				self.doctype, workflow, self.state_field(workflow)
			)[: self.page_length]
			moves = wf.permitted_transitions(self.doctype, names, workflow)
			return sum(1 for actions in moves.values() if actions)

		filters, or_filters = self.queue_predicate(decided=False, admin=admin)
		return len(
			frappe.get_list(
				self.doctype,
				filters=filters,
				or_filters=or_filters,
				pluck="name",
				limit_page_length=self.page_length,
			)
		)

	def has_approvals_queue(self, workflow, can_read: bool) -> bool:
		"""Whether this user has an approvals queue at all.

		With a workflow that is holding a role some transition is open to -- not
		the doctype's submit right, because a workflow may route a request back
		to its author without deciding it, and gating on submit would hide the
		page from exactly the people a site added those states for. Without one
		it is the submit right, which is what deciding takes.
		"""
		if not workflow:
			return bool(frappe.has_permission(self.doctype, "submit"))
		roles = set(frappe.get_roles())
		return can_read and bool({row.allowed for row in workflow.transitions} & roles)

	def approval_queue(self, decided: bool) -> list[dict]:
		"""Requests waiting on this user's decision, or ones already decided.

		Here rather than in a list query the frontend builds, so "waiting on
		you" means one thing. The page's rows, the badge counting them and the
		endpoint that writes the decision all read the same predicate, and none
		of them can drift into a slightly different idea of what is pending.

		Each row carries the outcomes this user may apply to it and how the row
		itself reads, so the buttons and the badge are both the server's answer.
		"""
		self.require_available()
		workflow = self.workflow()
		admin = self.is_admin()

		if workflow:
			rows = self.workflow_queue(workflow, decided)
		else:
			filters, or_filters = self.queue_predicate(decided, admin)
			rows = frappe.get_list(
				self.doctype,
				filters=filters,
				or_filters=or_filters,
				fields=list(self.list_fields),
				order_by=self.decided_order_by if decided else self.pending_order_by,
				limit_page_length=self.page_length,
			)

		styles = wf.state_styles(workflow)
		vocabulary = self.decision_vocabulary(workflow)
		can_submit = workflow is not None or bool(frappe.has_permission(self.doctype, "submit"))
		for row in rows:
			row.actions = self.permitted_decisions(row, workflow, vocabulary, admin, can_submit)
			row.can_decide = bool(row.actions)
			row.status_label, row.status_style = self.status_display(row, workflow, styles)
			row.pop("_transitions", None)
		self.decorate(rows)
		return rows

	def workflow_queue(self, workflow, decided: bool) -> list[dict]:
		"""The queue a site running a Workflow on this doctype sees.

		Candidates are the requests parked in a state one of this user's roles
		can move; which of them they may actually act on is `get_transitions` in
		their own session, and a row it offers nothing for is not waiting on
		them. History is what they have completed, which only a Workflow Action
		records.
		"""
		state_field = self.state_field(workflow)
		names = (
			completed_by_session(self.doctype)
			if decided
			else wf.names_in_movable_states(self.doctype, workflow, state_field)
		)
		if not names:
			return []

		fields = list(self.list_fields)
		if state_field not in fields:
			fields.append(state_field)
		rows = frappe.get_list(
			self.doctype,
			filters={"name": ["in", names]},
			fields=fields,
			order_by=self.decided_order_by if decided else self.pending_order_by,
			limit_page_length=self.page_length,
		)
		# `get_list` has already settled what this user may read, so these names
		# need no second permission pass.
		available = wf.permitted_transitions(self.doctype, [row.name for row in rows], workflow)
		for row in rows:
			row._transitions = available.get(row.name) or []
		if not decided:
			rows = [row for row in rows if row._transitions]
		return rows

	def decorate(self, rows: list[dict]) -> None:
		"""Anything a queue row needs that the list query could not select.

		Nothing, for a doctype that fetches every name it displays. See
		`expense.Expenses.decorate`, whose approver link has no fetched name
		beside it.
		"""

	def readable(self, names: list[str]) -> list[str]:
		"""Those of `names` this user may read, in one permission-checked query.

		What every child-table read on these pages is vetted against. Frappe's
		own `/api/v2/document/<child doctype>` never forwards its `parent`
		argument to the query builder, so a child table is permission-checked
		against itself -- and a child table has no permissions, so every such
		read is a 403. One `get_list` here applies the doctype's rules, user
		permissions and `if_owner`, and the rows then follow from names this
		user has already been allowed to see.
		"""
		if not names or not self.available():
			return []
		return frappe.get_list(
			self.doctype,
			filters={"name": ["in", names]},
			pluck="name",
			limit_page_length=0,
		)

	# -- what the page is told -----------------------------------------------

	def permissions(self) -> dict:
		"""What the session user may do here, plus their approval backlog.

		`approve` is whether this user has an approvals queue at all. Whether
		they decide *this* request is a separate question -- `approval_queue`
		answers it per row, and `decide` answers it again before writing.

		`decisions` is here so the page's buttons are the outcomes the server
		will actually accept, styled as the site styles them.
		`approver_mandatory` is HR Settings' answer rather than the form's
		assumption: a site that makes the approver optional is one where the
		form must let it through.

		`employee_filters` is what makes an Employee row this session's own,
		and `employee_access` is why there is no employee record when that read
		comes back empty -- `visible`, `forbidden` or `missing`. Both are the
		same split self-service settled on: the *predicate* stays the server's,
		and the page fetches its own requests through Frappe's document API,
		where every permission the site has configured applies without this
		module restating any of them. Two answers rather than one because
		"you have no record" and "you may not see your record" send the reader
		to different people -- see `session_employee_access`.

		`workflow` rides along because the page labels the rows it fetched for
		itself. The states and their styling are still the site's. The approvals
		queue is unaffected: those rows are labelled server-side by
		`status_display`, because which outcomes a row accepts is a permission
		question and has to be.

		Answers rather than throws for a section this site does not have -- see
		`unavailable`. This is the one endpoint that must: it is what every page
		asks before it draws anything, and the answer it wants is "you have no
		such section", not an error.
		"""
		if not self.available():
			return self.unavailable()

		workflow = self.workflow()
		can_read = bool(frappe.has_permission(self.doctype, "read"))
		can_approve = self.has_approvals_queue(workflow, can_read)

		return {
			"read": can_read,
			"request": bool(frappe.has_permission(self.doctype, "create")),
			"employee_filters": session_employee_filters(),
			"employee_access": session_employee_access(),
			"workflow": wf.describe(workflow) if can_read else None,
			"approve": can_approve,
			"pending_approvals": self.pending_count(workflow, self.is_admin()) if can_approve else 0,
			"decisions": self.decision_vocabulary(workflow),
			"page_length": self.page_length,
			"approver_mandatory": bool(
				frappe.db.get_single_value("HR Settings", self.approver_mandatory_setting)
			),
			"approver_query": self.approver_query,
		}

	# -- raising one ---------------------------------------------------------

	def parse_request(self, doc: str | dict) -> dict:
		"""The payload, once it is a document of this type and nothing else.

		The availability check sits here because this is the first thing every
		endpoint that raises one calls, and a section whose doctype is absent has
		nothing to insert into.
		"""
		self.require_available()
		values = frappe.parse_json(doc) or {}
		if not isinstance(values, dict):
			frappe.throw(frappe._("A {0} document is required.").format(self.doctype))
		if values.get("doctype") not in (None, self.doctype):
			frappe.throw(frappe._("Only {0} documents can be created here.").format(self.doctype))
		return values

	def request_employee(self, values: dict, fieldnames: list[str]) -> frappe._dict:
		"""The employee this request is for: the session's, never the payload's.

		A request on somebody else's behalf is a desk job with its own
		permissions, and a self-service form that can name an employee is a
		self-service form that can name the wrong one. A payload that names one
		anyway is refused rather than quietly overwritten, so a form with a bug
		in it hears about the bug.
		"""
		employee = session_employee(fieldnames)
		if not employee:
			frappe.throw(self.no_employee_message(), frappe.ValidationError)
		named = values.get("employee")
		if named and named != employee.name:
			frappe.throw(self.foreign_employee_message(), frappe.PermissionError)
		return employee

	def new_request(self, values: dict, employee: frappe._dict) -> dict:
		"""The document to insert: what the form may set, and who it is for."""
		request = {field: values[field] for field in self.request_fields if field in values}
		request["doctype"] = self.doctype
		request["employee"] = employee.name
		return request

	# -- settling one --------------------------------------------------------

	def decide(self, name: str, verdict: str, prepare=None) -> dict:
		"""Settle a request, by the route the site has configured.

		With a Workflow that is `apply_workflow`, so the transition's own
		conditions, permitted roles and next state are what decide and what gets
		written. Without one the two halves are one action for the approver but
		two writes underneath: the deciding field sits at permlevel 1, and only
		a submitted (docstatus 1) request actually books anything. Doing both
		here keeps them in one transaction -- a field change that never got
		submitted would leave the request looking decided to the approver and
		still pending to everyone else.

		`prepare` is whatever else the approver is settling in the same breath,
		applied to the document in memory before either route writes it, so it
		rides along on that write rather than arriving in one of its own -- see
		`expense.decide_expense_claim`, whose sanctioned amounts HRMS then
		revalidates against the decision they arrived with.
		"""
		self.require_available()
		workflow = self.workflow()
		offered = [option["value"] for option in self.decision_vocabulary(workflow)]
		if verdict not in offered:
			frappe.throw(
				frappe._("Decision must be one of {0}").format(", ".join(offered)),
				frappe.ValidationError,
			)

		doc = frappe.get_doc(self.doctype, name)

		if workflow:
			# No submit check here, deliberately. Not every transition submits --
			# a workflow may route a request back to its author without deciding
			# it -- and `apply_workflow` already refuses an action this user's
			# roles or the transition's own condition do not allow, having
			# read-checked the document through `get_transitions` on the way.
			# Demanding submit as well would block exactly the states a site
			# added a workflow in order to have.
			from frappe.model.workflow import apply_workflow

			if prepare:
				prepare(doc)
			doc = apply_workflow(doc, verdict)
			return self.decision_result(doc, self.state_field(workflow))

		# The right to decide, not just to read, and checked against this
		# document so user permissions and sharing apply. `check_permission`
		# first, so a user without the right at all gets Frappe's own message
		# rather than this one.
		doc.check_permission("submit")
		if not self.may_decide(doc):
			frappe.throw(self.not_yours_message(doc), frappe.PermissionError)
		if doc.docstatus != 0:
			frappe.throw(self.already_decided_message(doc), frappe.ValidationError)

		if prepare:
			prepare(doc)
		self.before_decision(doc)
		doc.set(self.decision_field, verdict)
		doc.save()

		# The deciding field is permlevel 1: a user without write access there
		# has the change silently reverted rather than refused, and would then
		# hit a confusing complaint from `on_submit` about a value they cannot
		# see they failed to set.
		if doc.get(self.decision_field) != verdict:
			frappe.throw(self.permlevel_message(), frappe.PermissionError)

		doc.submit()
		return self.decision_result(doc, self.decision_field)

	def before_decision(self, doc) -> None:
		"""Anything the act of deciding writes besides the decision itself."""

	def decision_result(self, doc, state_field: str) -> dict:
		"""What the page needs to say what just happened, in the server's words."""
		return {
			"name": doc.name,
			"status": doc.get(state_field),
			"docstatus": doc.docstatus,
		}

	# The sentences a section says in its own words. Methods rather than class
	# attributes so each stays a literal inside `frappe._()`, which is the only
	# shape Frappe's translation extractor can see. The first three name the
	# thing being raised and so have no sensible default; the last two do, and a
	# section overrides them only where it has something more exact to say.

	def no_employee_message(self) -> str:
		raise NotImplementedError

	def foreign_employee_message(self) -> str:
		raise NotImplementedError

	def permlevel_message(self) -> str:
		raise NotImplementedError

	def not_yours_message(self, doc) -> str:
		return frappe._("{0} is not yours to decide — it is assigned to {1}.").format(
			doc.name, doc.get(self.approver_field) or frappe._("nobody")
		)

	def already_decided_message(self, doc) -> str:
		return frappe._("{0} has already been settled.").format(doc.name)
