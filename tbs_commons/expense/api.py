"""Whitelisted endpoints for the expense section of the TBS Commons frontend.

Expense claims are self-service: an employee claims what they spent, and an
approver settles it. `request_expense_claim` raises one and
`decide_expense_claim` settles one; HRMS's own validation is what a claim has to
get past either way.

Written to the shape leave settled on -- see `tbs_commons.leave.api`, whose
docstrings argue for most of what is here -- because the two doctypes are the
same shape: submittable, decided through a field at permlevel 1, routed to one
named approver, and standing aside for a Frappe Workflow where a site runs one.
What is here is everything the frontend would otherwise have had to decide for
itself. Who may settle a claim, which ones are waiting on you, how many there
are, what the outcomes are called and how each one reads are one rule with
several faces, and a frontend stating any of them a second time states it in a
place where changing it does not change what the server does.

Three things are genuinely not leave's, and each is spelled out where it lives:

* HRMS refuses a claimant's own *submit* rather than their own approval, so
  preventing self-approval takes away every outcome rather than one --
  `self_approval_blocked`.
* `Expense Claim` grants `Expense Approver` and `HR User` identical permission
  rows, so the backstop leave derives from the doctype cannot be derived here
  without handing every approver on the site everyone else's claims --
  `may_decide`.
* A claim is money with accounts behind it. The exchange rate, the cost centre
  and the expense account are ERPNext's answers, fetched or computed from the
  employee and the company rather than collected from a form -- `_claim_context`
  and `request_expense_claim`.
"""

import frappe
from frappe.utils import flt

from tbs_commons import workflow as wf
from tbs_commons.api import (
	default_expense_approver,
	session_employee,
	session_employee_access,
	session_employee_filters,
)

EXPENSE_CLAIM = "Expense Claim"
EXPENSE_CLAIM_DETAIL = "Expense Claim Detail"

# The field an approver settles. Not `status`, which HRMS derives from this and
# the docstatus -- see `ExpenseClaim.set_status` -- and marks read-only: it says
# whether an approved claim has been reimbursed yet, which is a separate
# question from whether it was approved, and it is carried separately.
DECISION_FIELD = "approval_status"

# Statuses that are not a decision. `Draft` is where a claim starts, and the one
# value `ExpenseClaim.on_submit` refuses to submit; `Cancelled` is where
# cancelling or discarding one lands. Everything else the field offers is an
# outcome an approver can choose, so a site that adds one is offered it without
# editing this file.
NON_DECISION_STATUSES = ("Draft", "Cancelled")

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
# then up the department tree, not from a filter over User. It answers for
# several doctypes and is told which by a `doctype` filter, so the frontend
# sends `{"employee": ..., "doctype": "Expense Claim"}` with it. Named here
# rather than there, so a site that wants a different set of candidates changes
# the query in one place.
APPROVER_QUERY = "hrms.hr.doctype.department_approver.department_approver.get_approvers"

# How many rows the approvals queue returns. The badge counts to the same
# ceiling, so it never promises more than the page will show.
PAGE_LENGTH = 20

# What a claim may set. Server-owned on purpose, and deliberately short:
# `approval_status` sits at permlevel 1, `employee` is resolved from the session
# rather than accepted, and the money fields are ERPNext's -- see
# `request_expense_claim`. Everything absent here (the naming series, the
# posting date, a workflow's initial state) is the doctype's to fill in, so a
# site that customises any of them gets what it configured.
REQUEST_FIELDS = ("expense_approver", "remark")

# What one expense on a claim may set. `sanctioned_amount` is deliberately
# absent: what a claimant asks for is `amount`, and what is actually allowed is
# the approver's answer -- see `_expense_row` and `decide_expense_claim`.
EXPENSE_FIELDS = ("expense_date", "expense_type", "description", "amount")

# What a queue row carries. Server-owned, so a field that turns out to need a
# permlevel or a rename is changed in one place.
LIST_FIELDS = [
	"name",
	"employee",
	"employee_name",
	"department",
	"company",
	"currency",
	"posting_date",
	"remark",
	"approval_status",
	# Whether an approved claim has been paid out. HRMS derives it; it is carried
	# beside the decision rather than instead of it, because "Approved" and
	# "Unpaid" are two different answers and a claimant wants both.
	"status",
	"docstatus",
	"expense_approver",
	"total_claimed_amount",
	"total_sanctioned_amount",
	"total_amount_reimbursed",
	"grand_total",
]

# What one expense row carries. `sanctioned_amount` rides along on every read:
# an approver needs it to settle the claim and a claimant needs it to see what
# was actually allowed.
LINE_FIELDS = [
	"name",
	"parent",
	"idx",
	"expense_date",
	"expense_type",
	"description",
	"amount",
	"sanctioned_amount",
]


def expense_workflow():
	"""The active Workflow for `Expense Claim`, or None."""
	return wf.active_workflow(EXPENSE_CLAIM)


def decision_vocabulary(workflow) -> list[dict]:
	"""Every outcome an approver could be offered, and how each one reads.

	With a workflow, the outcomes are its actions and the styling is the site's:
	an action reads as the Workflow State it leads to. Without one they are
	`approval_status`'s own options less the two that are not decisions, styled
	by `DEFAULT_DECISION_STYLES`.

	`confirm` travels with the outcome rather than being inferred from its
	colour by whoever draws the button. Whether an irreversible choice deserves
	a second look is policy, and a site that adds an outcome should not have to
	know that a page somewhere decides that by reading a CSS variant.
	"""
	if workflow:
		styles = wf.state_styles(workflow)
		offered = wf.unique_actions(workflow.transitions)
		return [_decision(row["action"], styles.get(row["next_state"])) for row in offered]

	field = frappe.get_meta(EXPENSE_CLAIM).get_field(DECISION_FIELD)
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
	"""Whether the session user may settle *this* claim at all.

	The doctype-level right first, checked against the document so user
	permissions and sharing apply, and then narrower than the role: this claim's
	own approver, or a claim that names nobody.

	Deliberately without leave's role-derived backstop. `leave_admin_roles` can
	tell the roles that own `Leave Application` apart from the role its approver
	field points at, because HRMS grants `Leave Approver` submit without create.
	On `Expense Claim` it grants `Expense Approver` both -- the rows it ships for
	that role and for `HR User` are identical, right for right -- so the same
	derivation would name every approver on the site a backstop and hand each of
	them everyone else's claims. There is no third state in the permission rows
	to read, and inventing one here would be a role name in Python by another
	name.

	So the backstop is narrowed to the case it was written for: a claim with no
	approver on it is nobody's to decide, which would leave it stuck. A site that
	wants a wider one says so with a Workflow, whose transitions are honoured
	here in full -- including a condition naming a role that may act on anything.

	Which *outcomes* they may apply is a further question -- see
	`permitted_decisions`.
	"""
	if not frappe.has_permission(EXPENSE_CLAIM, "submit", doc=doc):
		return False
	approver = doc.get("expense_approver")
	return not approver or approver == frappe.session.user


def self_approval_blocked(employee: str | None, workflow) -> bool:
	"""Whether HRMS will refuse this user settling this employee's claim.

	Mirrors `ExpenseClaim.validate_for_self_approval`, down to standing aside
	when a workflow is running -- the workflow's own conditions decide it then.
	Asked here so the queue never draws a button the write would throw on; the
	throw is still the server's, and still what actually stops it.

	One thing it does *not* mirror from leave. `LeaveApplication` tests the
	outcome (`self.status == "Approved"`), so an approver may still turn their
	own application down; `ExpenseClaim` tests the submit itself, in
	`before_submit`, whatever the claim was settled at. So a claimant on a site
	that prevents self-approval loses every outcome, not just the affirmative
	one, and `permitted_decisions` takes them all away rather than filtering one
	out.
	"""
	if workflow or not employee:
		return False
	if not frappe.db.get_single_value("HR Settings", "prevent_self_expense_approval"):
		return False
	return frappe.db.get_value("Employee", employee, "user_id", cache=True) == frappe.session.user


def permitted_decisions(row, workflow, vocabulary, can_submit: bool) -> list[str]:
	"""The outcomes this user may apply to *this* row, named as the server names them.

	With a workflow this is `get_transitions` in this user's session, which is
	the only thing that can read a condition naming them. Without one it is the
	whole vocabulary -- and nothing at all unless this row is undecided, theirs
	to decide, and not one HRMS would refuse them on the way to the database.
	"""
	if workflow:
		return [action["action"] for action in row.get("_transitions") or []]
	if not (
		can_submit
		and row.docstatus == 0
		and (not row.expense_approver or row.expense_approver == frappe.session.user)
	):
		return []
	if self_approval_blocked(row.get("employee"), workflow):
		return []
	return [decision["value"] for decision in vocabulary]


def status_display(row, workflow, styles: dict) -> tuple[str, str | None]:
	"""How a row reads to a person: its label, and the style to say it in.

	Settled here rather than in the page because `approval_status` alone is not
	the answer. Without a workflow a decision is a field change *and* a submit,
	so an unsubmitted claim is still pending whatever that field says, and a
	cancelled one reads as cancelled whatever decision it carried. With a
	workflow the state is the answer and the site's Workflow State supplies the
	style.

	Whether an approved claim has actually been reimbursed is a different
	question, answered by `status`, and it is carried beside this rather than
	folded into it.
	"""
	if workflow:
		state = row.get(wf.state_field(workflow, DECISION_FIELD))
		return state or row.get(DECISION_FIELD), styles.get(state)
	if row.docstatus == 2:
		return frappe._("Cancelled"), None
	if row.docstatus == 0:
		return frappe._("Pending"), "Warning"
	decided = row.get(DECISION_FIELD)
	return decided, DEFAULT_DECISION_STYLES.get(decided)


def _queue_predicate(decided: bool) -> tuple[dict, list | None]:
	"""Which claims are this user's to look at, deciding or decided.

	The no-workflow predicate, as one answer, because the page's rows and the
	badge counting them both have to ask it. `docstatus` is what "decided" means
	here, not `approval_status`: settling a claim is a field change *and* a
	submit, and only a submitted claim books anything. An undecided one is
	`Draft` as well, which is where HRMS leaves one -- without it a status
	somebody set from the desk without submitting would show up in the queue with
	buttons on it and be missing from the badge beside it.

	The `or_filters` are the backstop `may_decide` describes: a claim naming
	nobody is waiting on whoever can pick it up. History needs none, because
	`decide_expense_claim` writes the decider onto a claim that named nobody --
	so by the time it is history it names someone, and that someone is them.

	The claimant's own claims come out of the pending half where HR Settings says
	they may not settle them. `self_approval_blocked` takes every outcome away
	from such a row -- HRMS refuses the submit itself, not the outcome -- so
	leaving them in would put rows with no buttons in the queue and count them in
	the badge beside it, which is exactly the drift this one predicate exists to
	prevent. History keeps them: a claim they raised and somebody else settled is
	still theirs to have seen.
	"""
	filters = {"docstatus": 1 if decided else 0}
	if decided:
		filters["expense_approver"] = frappe.session.user
		return filters, None

	filters[DECISION_FIELD] = "Draft"
	if frappe.db.get_single_value("HR Settings", "prevent_self_expense_approval"):
		mine = _session_employee_name()
		if mine:
			filters["employee"] = ["!=", mine]

	return filters, [
		["expense_approver", "=", frappe.session.user],
		["expense_approver", "is", "not set"],
	]


def _session_employee_name() -> str | None:
	"""The employee record behind this session, as the queue needs to exclude it.

	A raw read rather than `session_employee`, and deliberately so. What it
	returns is the caller's own employee id and nothing else -- the same bounded
	disclosure `session_employee_access` makes -- whereas the permission-checked
	read answers `None` for a user whose `Employee` access is gated, which here
	would quietly put their own claims back into their own queue.
	"""
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _pending_count(workflow=None) -> int:
	"""The badge. Capped the way the queue is, so the two agree."""
	if workflow:
		names = wf.names_in_movable_states(
			EXPENSE_CLAIM, workflow, wf.state_field(workflow, DECISION_FIELD)
		)[:PAGE_LENGTH]
		moves = wf.permitted_transitions(EXPENSE_CLAIM, names, workflow)
		return sum(1 for actions in moves.values() if actions)

	filters, or_filters = _queue_predicate(decided=False)
	return len(
		frappe.get_list(
			EXPENSE_CLAIM,
			filters=filters,
			or_filters=or_filters,
			pluck="name",
			limit_page_length=PAGE_LENGTH,
		)
	)


def _has_approvals_queue(workflow, can_read: bool) -> bool:
	"""Whether this user has an approvals queue at all -- see `get_expense_permissions`."""
	if not workflow:
		return bool(frappe.has_permission(EXPENSE_CLAIM, "submit"))
	roles = set(frappe.get_roles())
	return can_read and bool({row.allowed for row in workflow.transitions} & roles)


@frappe.whitelist()
def get_expense_permissions() -> dict:
	"""What the session user may do with expenses, plus their approval backlog.

	`approve` is whether this user has an approvals queue at all. With a workflow
	that is holding a role some transition is open to -- not the doctype's submit
	right, because a workflow may route a claim back to its author without
	deciding it, and gating on submit would hide the page from exactly the people
	a site added those states for. Without one it is the submit right, which is
	what settling a claim takes. Whether this user settles *this* claim is a
	separate question -- `get_expense_approval_queue` answers it per row, and
	`decide_expense_claim` answers it again before writing anything.

	`decisions` is here so the page's buttons are the outcomes the server will
	actually accept, styled as the site styles them. `approver_mandatory` is
	HR Settings' answer rather than the form's assumption: a site that makes the
	approver optional is one where the form must let it through.

	`employee_filters` is what makes an Employee row this session's own, and
	`employee_access` is why there is no employee record when that read comes
	back empty. Both are the same split leave and self-service settled on: the
	*predicate* stays the server's, and the page fetches its own claims through
	Frappe's document API, where every permission the site has configured applies
	without this module restating any of them.

	`workflow` rides along because the page labels its own rows. The states and
	their styling are still the site's. The approvals queue is unaffected: those
	rows are still labelled server-side by `status_display`, because which
	outcomes a row accepts is a permission question and has to be.
	"""
	workflow = expense_workflow()
	can_read = bool(frappe.has_permission(EXPENSE_CLAIM, "read"))
	can_approve = _has_approvals_queue(workflow, can_read)

	return {
		"read": can_read,
		"request": bool(frappe.has_permission(EXPENSE_CLAIM, "create")),
		"employee_filters": session_employee_filters(),
		"employee_access": session_employee_access(),
		"workflow": wf.describe(workflow) if can_read else None,
		"approve": can_approve,
		"pending_approvals": _pending_count(workflow) if can_approve else 0,
		"decisions": decision_vocabulary(workflow),
		"page_length": PAGE_LENGTH,
		"approver_mandatory": bool(
			frappe.db.get_single_value("HR Settings", "expense_approver_mandatory_in_expense_claim")
		),
		"approver_query": APPROVER_QUERY,
	}


def _claim_context(employee: frappe._dict) -> frappe._dict:
	"""The company, currency and cost centre a claim for this employee is raised in.

	The same links `Expense Claim`'s own `fetch_from` would follow -- the
	employee's company and salary currency, and the company's cost centre --
	resolved before the insert rather than by it. Two things need them earlier
	than that: `exchange_rate` is mandatory, has no default and cannot be
	computed without knowing the currency, and each expense row needs the cost
	centre the desk form copies down (`set_child_cost_center`), without which
	`validate_account_details` refuses to book the claim at submit.

	Safe to set explicitly because every one of those fields carries
	`fetch_if_empty`: a value that is already there is what the document keeps.
	"""
	import erpnext

	company = employee.get("company")
	company_currency = erpnext.get_company_currency(company) if company else None
	return frappe._dict(
		company=company,
		company_currency=company_currency,
		currency=employee.get("salary_currency") or company_currency,
		cost_center=erpnext.get_default_cost_center(company) if company else None,
	)


def _exchange_rate(context: frappe._dict) -> float:
	"""What one unit of the claim's currency is worth in the company's.

	ERPNext's own answer, which is 1 when the two are the same and otherwise the
	most recent `Currency Exchange` it will accept. A zero comes back when a site
	has no rate to give and has turned the provider off, and that is refused
	rather than quietly written: every base amount on the claim is multiplied by
	this, so a zero would book the claim at nothing.
	"""
	from erpnext.setup.utils import get_exchange_rate

	if not context.currency or not context.company_currency:
		return 1.0

	rate = flt(get_exchange_rate(context.currency, context.company_currency))
	if not rate:
		frappe.throw(
			frappe._(
				"No exchange rate is available from {0} to {1}, so a claim in {0} cannot be priced. "
				"Ask Accounts to add a Currency Exchange rate."
			).format(context.currency, context.company_currency)
		)
	return rate


def claim_types(company: str | None) -> list[dict]:
	"""The expense types this company can actually book to.

	A type with no `Expense Claim Account` row for the company is not a choice:
	`ExpenseClaim.set_expense_account` looks that account up on every save and
	throws when it is missing, so offering the type would only produce a claim
	that cannot be saved. Better to leave it out and let the form say the set is
	empty -- which sends the reader to Accounts, who configure it, rather than
	into an error whose wording sends them to the same place one failed save
	later.
	"""
	if not company:
		return []

	# `frappe.get_all` on a child table answers to no permission of its own, which
	# is why the endpoints that reach this gate on `Expense Claim` first. What it
	# discloses is a list of expense categories and their accounts, to someone
	# already entitled to spend against them.
	parents = frappe.get_all(
		"Expense Claim Account",
		parent_doctype="Expense Claim Type",
		filters={"company": company, "default_account": ["is", "set"]},
		pluck="parent",
	)
	if not parents:
		return []

	return frappe.get_all(
		"Expense Claim Type",
		filters={"name": ["in", sorted(set(parents))]},
		fields=["name", "description"],
		order_by="name asc",
	)


@frappe.whitelist()
def get_expense_claim_defaults() -> dict:
	"""What a blank claim opens with, before the claimant touches anything.

	Asked by the form rather than sent with the permissions, because that is what
	it is: form state, wanted by the one page that draws a blank claim and by
	none of the pages that merely list them -- the same split procurement
	settled on.

	Gated on `create`, because a user who cannot raise a claim has no blank form
	to fill, and because `claim_types` reads a child table directly and so asks
	no permission of its own.

	Every value may be `None`, and `expense_types` may be empty. A default nobody
	has configured is left out rather than guessed at, and the form says so --
	an empty type list in particular is the site telling the claimant that
	nothing has been set up to claim against yet.
	"""
	frappe.has_permission(EXPENSE_CLAIM, "create", throw=True)

	employee = session_employee(
		["name", "company", "department", "expense_approver", "salary_currency"]
	)
	if not employee:
		return {
			"employee": None,
			"company": None,
			"currency": None,
			"approver": None,
			"expense_types": [],
		}

	context = _claim_context(employee)
	return {
		"employee": employee.name,
		"company": context.company,
		"currency": context.currency,
		"approver": default_expense_approver(employee),
		"expense_types": claim_types(context.company),
	}


@frappe.whitelist(methods=["POST"])
def request_expense_claim(doc: str | dict) -> dict:
	"""Raise an expense claim for the employee behind this session.

	Through here rather than straight at the document API so the field list a
	claim may set is the server's. `employee` is resolved from the session
	instead of accepted: a claim on somebody else's behalf is a desk job with its
	own permissions, and a self-service form that can name an employee is a
	self-service form that can name the wrong one.

	The money is settled here too, and not by the form. What a claim costs in the
	company's books is a product of the employee's currency, the company's, and
	ERPNext's exchange rate; which account it lands in is the expense type's; and
	which cost centre it is charged to is the company's. The desk collects all of
	that with a screenful of JavaScript and four round trips -- see
	`expense_claim.js` -- and every one of those answers is the same wherever it
	is asked. A form that asked them would be a second place they could be
	answered differently.

	Everything `REQUEST_FIELDS` leaves out -- the naming series, the posting
	date, the approval status, a workflow's initial state -- is filled in by the
	doctype, so a site that customises any of them gets what it configured.
	"""
	values = frappe.parse_json(doc) or {}
	if not isinstance(values, dict):
		frappe.throw(frappe._("An Expense Claim document is required."))
	if values.get("doctype") not in (None, EXPENSE_CLAIM):
		frappe.throw(frappe._("Only Expense Claims can be created here."))

	employee = session_employee(["name", "company", "salary_currency"])
	if not employee:
		frappe.throw(
			frappe._(
				"Your login is not linked to an employee record, so expenses cannot be claimed against it."
			),
			frappe.ValidationError,
		)
	named = values.get("employee")
	if named and named != employee.name:
		frappe.throw(
			frappe._("Expenses can only be claimed for your own employee record here."),
			frappe.PermissionError,
		)

	rows = values.get("expenses") or []
	if not isinstance(rows, list) or not rows:
		frappe.throw(
			frappe._("A claim needs at least one expense on it."),
			frappe.ValidationError,
		)

	context = _claim_context(employee)
	claim = {field: values[field] for field in REQUEST_FIELDS if field in values}
	claim["doctype"] = EXPENSE_CLAIM
	claim["employee"] = employee.name
	claim["company"] = context.company
	claim["currency"] = context.currency
	claim["cost_center"] = context.cost_center
	claim["exchange_rate"] = _exchange_rate(context)
	claim["expenses"] = [_expense_row(row, context) for row in rows]

	return frappe.get_doc(claim).insert().as_dict()


def _expense_row(row: dict, context: frappe._dict) -> dict:
	"""One line of a claim, with what the claimant does not get to decide.

	`sanctioned_amount` opens at what was claimed, which is what the desk form
	does as the amount is typed. An approver settles it downwards from there; a
	claim that reached submission sanctioning nothing would book nothing. It is
	rewritten by `decide_expense_claim` and zeroed by HRMS on a rejection, so
	nothing set here is the last word on it.

	`cost_center` is the company's, copied down the way `set_child_cost_center`
	does in the desk. `default_account` is deliberately left alone:
	`set_expense_account` fills it from the expense type on every save, and that
	is the answer wanted -- a claim that named its own account would be a claim
	that could name the wrong one.
	"""
	if not isinstance(row, dict):
		frappe.throw(frappe._("Each expense must be a row of its own."), frappe.ValidationError)

	line = {field: row[field] for field in EXPENSE_FIELDS if field in row}
	amount = flt(line.get("amount"))
	if amount <= 0:
		frappe.throw(
			frappe._("Every expense needs an amount above zero."),
			frappe.ValidationError,
		)
	line["amount"] = amount
	line["sanctioned_amount"] = amount
	line["cost_center"] = context.cost_center
	return line


@frappe.whitelist()
def get_expense_approval_queue(decided: int = 0) -> list[dict]:
	"""Claims waiting on this user's decision, or ones already decided.

	Here rather than in a list query the frontend builds, so "waiting on you"
	means one thing. The page's rows, the badge counting them and the endpoint
	that writes the decision all read the same predicate, and none of them can
	drift into a slightly different idea of what is pending.

	Each row carries the outcomes this user may apply to it and how the row
	itself reads, so the buttons and the badge are both the server's answer --
	a reader who merely has the page open gets none, and an approver looking at
	their own claim gets none either where HR Settings says so.
	"""
	decided = bool(frappe.utils.cint(decided))
	workflow = expense_workflow()

	if workflow:
		claims = _workflow_queue(workflow, decided)
	else:
		filters, or_filters = _queue_predicate(decided)
		claims = frappe.get_list(
			EXPENSE_CLAIM,
			filters=filters,
			or_filters=or_filters,
			fields=LIST_FIELDS,
			# Oldest first while they are still decisions to make -- a claim waits
			# on somebody's money -- and most recently touched first once they are
			# history.
			order_by="modified desc" if decided else "posting_date asc, creation asc",
			limit_page_length=PAGE_LENGTH,
		)

	styles = wf.state_styles(workflow)
	vocabulary = decision_vocabulary(workflow)
	can_submit = workflow is not None or bool(frappe.has_permission(EXPENSE_CLAIM, "submit"))
	for claim in claims:
		claim.actions = permitted_decisions(claim, workflow, vocabulary, can_submit)
		claim.can_decide = bool(claim.actions)
		claim.status_label, claim.status_style = status_display(claim, workflow, styles)
		claim.pop("_transitions", None)
	_add_approver_names(claims)
	return claims


def _workflow_queue(workflow, decided: bool) -> list[dict]:
	"""The queue a site running a Workflow on expense claims sees.

	Candidates are the claims parked in a state one of this user's roles can
	move; which of them they may actually act on is `get_transitions` in their
	own session, and a row it offers nothing for is not waiting on them. History
	is what they have completed, which only a Workflow Action records.
	"""
	state_field = wf.state_field(workflow, DECISION_FIELD)
	if decided:
		actions = frappe.get_all(
			"Workflow Action",
			filters={
				"reference_doctype": EXPENSE_CLAIM,
				"status": "Completed",
				"completed_by": frappe.session.user,
			},
			fields=["reference_name"],
		)
		names = list(dict.fromkeys(row.reference_name for row in actions if row.reference_name))
	else:
		names = wf.names_in_movable_states(EXPENSE_CLAIM, workflow, state_field)

	if not names:
		return []
	fields = LIST_FIELDS if state_field in LIST_FIELDS else [*LIST_FIELDS, state_field]
	claims = frappe.get_list(
		EXPENSE_CLAIM,
		filters={"name": ["in", names]},
		fields=fields,
		order_by="modified desc" if decided else "posting_date asc, creation asc",
		limit_page_length=PAGE_LENGTH,
	)
	# `get_list` has already settled what this user may read, so these names need
	# no second permission pass.
	available = wf.permitted_transitions(EXPENSE_CLAIM, [row.name for row in claims], workflow)
	for claim in claims:
		claim._transitions = available.get(claim.name) or []
	if not decided:
		claims = [row for row in claims if row._transitions]
	return claims


def _add_approver_names(claims: list[dict]) -> None:
	"""Who each claim is assigned to, as a person rather than as a login.

	`Expense Claim` stores the approver as a User link and keeps no fetched name
	beside it, the way `Leave Application` does with `leave_approver_name`. One
	read covers the page; a login with no User row left keeps its own id, which
	is the honest thing to show for an account that has been removed.
	"""
	logins = {row.get("expense_approver") for row in claims if row.get("expense_approver")}
	if not logins:
		return
	names = dict(
		frappe.get_all(
			"User",
			filters={"name": ["in", sorted(logins)]},
			fields=["name", "full_name"],
			as_list=True,
		)
	)
	for claim in claims:
		login = claim.get("expense_approver")
		claim.expense_approver_name = names.get(login) or login


@frappe.whitelist()
def get_expense_claim_lines(claims: str) -> list[dict]:
	"""The expense rows of several claims at once, for a list of them.

	Not `/api/v2/document/Expense Claim Detail`: that endpoint never forwards its
	`parent` argument to the query builder, so a child table is permission-checked
	against itself -- and a child table has no permissions, so every such read is
	a 403. The parent names are vetted here with a single `get_list`, which
	applies the doctype's rules, user permissions and `if_owner`; the rows then
	follow from names this user has already been allowed to see.

	`description` is a Text Editor field, so what comes out of the desk is HTML.
	It is flattened to text on the way out: nothing on these pages renders markup
	it was handed, and a description that arrives as text can be rendered as text
	-- which is the version of this that cannot carry a script.
	"""
	readable = _readable_claims(frappe.parse_json(claims) or [])
	if not readable:
		return []

	lines = frappe.get_all(
		EXPENSE_CLAIM_DETAIL,
		parent_doctype=EXPENSE_CLAIM,
		filters={"parent": ["in", readable]},
		fields=LINE_FIELDS,
		order_by="parent asc, idx asc",
		limit_page_length=0,
	)
	for line in lines:
		if line.description:
			line.description = frappe.utils.strip_html(line.description).strip()
	return lines


def _readable_claims(names: list[str]) -> list[str]:
	"""Those of `names` this user may read, in one permission-checked query."""
	if not names:
		return []
	return frappe.get_list(
		EXPENSE_CLAIM,
		filters={"name": ["in", names]},
		pluck="name",
		limit_page_length=0,
	)


@frappe.whitelist(methods=["POST"])
def decide_expense_claim(
	name: str, decision: str, sanctioned: str | dict | None = None
) -> dict:
	"""Settle an expense claim, by the route the site has configured.

	With a Workflow that is `apply_workflow`, so the transition's own conditions,
	permitted roles and next state are what decide and what gets written. Without
	one the two halves are one action for the approver but two writes underneath:
	`approval_status` sits at permlevel 1, and only a submitted (docstatus 1)
	claim actually books anything. Doing both here keeps them in one transaction
	-- a status change that never got submitted would leave the claim looking
	decided to the approver and still pending to everyone else.

	`sanctioned` is what the approver is allowing, per expense row, when that is
	not simply what was claimed. It is applied to the document before either
	route writes it, so the amount and the decision land together and HRMS
	revalidates both: `validate_sanctioned_amount` refuses anything above what
	was claimed, and a rejection zeroes them all whatever was passed.
	"""
	workflow = expense_workflow()
	offered = [option["value"] for option in decision_vocabulary(workflow)]
	if decision not in offered:
		frappe.throw(
			frappe._("Decision must be one of {0}").format(", ".join(offered)),
			frappe.ValidationError,
		)

	doc = frappe.get_doc(EXPENSE_CLAIM, name)
	amounts = _sanctioned_amounts(sanctioned)

	if workflow:
		# No submit check here, deliberately. Not every transition submits -- a
		# workflow may route a claim back to its author without deciding it -- and
		# `apply_workflow` already refuses an action this user's roles or the
		# transition's own condition do not allow, having read-checked the document
		# through `get_transitions` on the way. Demanding submit as well would block
		# exactly the states a site added a workflow in order to have.
		from frappe.model.workflow import apply_workflow

		# In memory, then handed over: `apply_workflow` saves or submits the
		# document it is given, so the amounts ride along on its write rather than
		# arriving in one of their own.
		_apply_sanctioned_amounts(doc, amounts)
		doc = apply_workflow(doc, decision)
		return _decision_result(doc, wf.state_field(workflow, DECISION_FIELD))

	# The right to decide, not just to read, and checked against this document so
	# user permissions and sharing apply. `check_permission` first, so a user
	# without the right at all gets Frappe's own message rather than this one.
	doc.check_permission("submit")
	if not may_decide(doc):
		frappe.throw(
			frappe._("{0} is not your expense claim to decide — it is assigned to {1}.").format(
				name, doc.expense_approver or frappe._("nobody")
			),
			frappe.PermissionError,
		)

	if doc.docstatus != 0:
		frappe.throw(
			frappe._("{0} has already been settled.").format(name),
			frappe.ValidationError,
		)

	_apply_sanctioned_amounts(doc, amounts)
	if not doc.expense_approver:
		# A claim nobody was named on is settled by whoever picked it up, and the
		# record should say so -- otherwise it goes missing from the history of the
		# one person who decided it the moment they do.
		doc.expense_approver = frappe.session.user
	doc.set(DECISION_FIELD, decision)
	doc.save()

	# `approval_status` is permlevel 1: a user without write access there has the
	# change silently reverted rather than refused, and would then hit a confusing
	# "Approval Status must be 'Approved' or 'Rejected'" error from on_submit.
	if doc.get(DECISION_FIELD) != decision:
		frappe.throw(
			frappe._(
				"You are not permitted to decide expense claims. The Expense Approver role grants this."
			),
			frappe.PermissionError,
		)

	doc.submit()
	return _decision_result(doc, DECISION_FIELD)


def _decision_result(doc, state_field: str) -> dict:
	"""What the page needs to say what just happened, in the server's own words."""
	return {
		"name": doc.name,
		"status": doc.get(state_field),
		"docstatus": doc.docstatus,
		"total_sanctioned_amount": flt(doc.total_sanctioned_amount),
		"currency": doc.currency,
	}


def _sanctioned_amounts(sanctioned: str | dict | None) -> dict[str, float]:
	"""What the approver is settling each expense at, keyed by that row's own name."""
	if not sanctioned:
		return {}

	values = frappe.parse_json(sanctioned)
	if not isinstance(values, dict):
		frappe.throw(
			frappe._("Sanctioned amounts must be given per expense row."),
			frappe.ValidationError,
		)

	amounts = {}
	for row, amount in values.items():
		amount = flt(amount)
		if amount < 0:
			frappe.throw(
				frappe._("A sanctioned amount cannot be negative."),
				frappe.ValidationError,
			)
		amounts[row] = amount
	return amounts


def _apply_sanctioned_amounts(doc, amounts: dict[str, float]) -> None:
	"""Write the approver's figures onto the claim's own rows.

	By row name, not by position: a queue loaded before the claimant added a line
	would otherwise settle the wrong expense at the wrong amount. A name the
	claim does not have is refused rather than skipped, because a silently
	dropped figure reads on screen as an approval of the full amount.

	Whether a figure is allowed at all is HRMS's answer and not this one --
	`validate_sanctioned_amount` refuses anything above what was claimed, on the
	save that follows.
	"""
	if not amounts:
		return

	rows = {row.name: row for row in doc.expenses}
	unknown = sorted(set(amounts) - set(rows))
	if unknown:
		frappe.throw(
			frappe._("{0} has no expense row {1}. Reload the queue and try again.").format(
				doc.name, unknown[0]
			),
			frappe.ValidationError,
		)
	for row, amount in amounts.items():
		rows[row].sanctioned_amount = amount
