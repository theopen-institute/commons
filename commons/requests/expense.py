"""Expenses: what is their own, and the endpoints the frontend reaches.

Expense claims are self-service: an employee claims what they spent, and an
approver settles it. `request_expense_claim` raises one and
`decide_expense_claim` settles one; HRMS's own validation is what a claim has to
get past either way.

The shape of all that is `approvals.RequestType`, shared with leave. This file
used to be a near-copy of leave's, and said so; what is left of it now is what
is genuinely not leave's:

* the decision is `approval_status`, not `status` -- HRMS derives the latter
  from the former and the docstatus and marks it read-only, and it answers a
  different question (has an approved claim been paid yet) that rides along
  beside the decision rather than instead of it;
* HRMS refuses a claimant's own *submit* rather than their own approval, so
  preventing self-approval takes away every outcome rather than one, and takes
  the row out of the queue and the badge along with it;
* `Expense Claim` grants `Expense Approver` and `HR User` identical permission
  rows, so the backstop leave derives from the doctype cannot be derived here
  without handing every approver on the site everyone else's claims --
  `Expenses.admin_roles`;
* a claim is money with accounts behind it. The exchange rate, the cost centre
  and the expense account are ERPNext's answers, fetched or computed from the
  employee and the company rather than collected from a form -- `_claim_context`
  and `request_expense_claim`.
"""

import frappe
from frappe.utils import flt

from commons.api import session_employee
from commons.requests import approvals
from commons.requests.approvers import default_expense_approver

EXPENSE_CLAIM = "Expense Claim"
EXPENSE_CLAIM_DETAIL = "Expense Claim Detail"

# What one expense on a claim may set. `sanctioned_amount` is deliberately
# absent: what a claimant asks for is `amount`, and what is actually allowed is
# the approver's answer -- see `_expense_row` and `decide_expense_claim`.
EXPENSE_FIELDS = ("expense_date", "expense_type", "description", "amount")

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


class Expenses(approvals.RequestType):
	doctype = EXPENSE_CLAIM
	approver_field = "expense_approver"

	# The field an approver settles. Not `status`, which HRMS derives from this
	# and the docstatus -- see `ExpenseClaim.set_status` -- and marks read-only:
	# it says whether an approved claim has been reimbursed yet, which is a
	# separate question from whether it was approved, and it is carried
	# separately in `list_fields`.
	decision_field = "approval_status"

	# `Draft` is where a claim starts, and the one value `ExpenseClaim.on_submit`
	# refuses to submit; `Cancelled` is where cancelling or discarding one lands.
	non_decision_values = ("Draft", "Cancelled")

	# `ExpenseClaim` tests the submit itself, in `before_submit`, whatever the
	# claim was settled at -- so a claimant on a site that prevents
	# self-approval loses every outcome, which is what leaving
	# `self_approval_outcome` unset means.
	self_approval_setting = "prevent_self_expense_approval"

	approver_mandatory_setting = "expense_approver_mandatory_in_expense_claim"

	# Oldest first while they are still decisions to make -- a claim waits on
	# somebody's money -- and most recently touched first once they are history.
	pending_order_by = "posting_date asc, creation asc"
	decided_order_by = "modified desc"

	# Deliberately short: `approval_status` sits at permlevel 1, `employee` is
	# resolved from the session, and the money fields are ERPNext's -- see
	# `request_expense_claim`.
	request_fields = ("expense_approver", "remark")

	list_fields = (
		"name",
		"employee",
		"employee_name",
		"department",
		"company",
		"currency",
		"posting_date",
		"remark",
		"approval_status",
		# Whether an approved claim has been paid out. HRMS derives it; it is
		# carried beside the decision rather than instead of it, because
		# "Approved" and "Unpaid" are two different answers and a claimant wants
		# both.
		"status",
		"docstatus",
		"expense_approver",
		"total_claimed_amount",
		"total_sanctioned_amount",
		"total_amount_reimbursed",
		"grand_total",
	)

	def admin_roles(self) -> set[str]:
		"""None, deliberately -- there is nothing here to derive one from.

		`Leave.admin_roles` can tell the roles that own `Leave Application`
		apart from the role its approver field points at, because HRMS grants
		`Leave Approver` submit without create. On `Expense Claim` it grants
		`Expense Approver` both -- the rows it ships for that role and for
		`HR User` are identical, right for right -- so the same derivation would
		name every approver on the site a backstop and hand each of them
		everyone else's claims. There is no third state in the permission rows
		to read, and inventing one here would be a role name in Python by
		another name.

		So the backstop is narrowed to the case it was written for, in
		`row_is_theirs`: a claim with no approver on it. A site that wants a
		wider one says so with a Workflow, whose transitions are honoured here
		in full -- including a condition naming a role that may act on anything.
		"""
		return set()

	def row_is_theirs(self, row, admin: bool) -> bool:
		"""This claim's own approver, or a claim that names nobody.

		A claim nobody was named on would otherwise be stuck: nobody's to
		decide, and so waiting for ever. `decide` writes the decider onto it as
		it settles -- see `before_decision`.
		"""
		approver = row.get(self.approver_field)
		return not approver or approver == frappe.session.user

	def queue_predicate(self, decided: bool, admin: bool) -> tuple[dict, list | None]:
		"""Which claims are this user's to look at, deciding or decided.

		An undecided one is `Draft` as well as unsubmitted, which is where HRMS
		leaves one -- without it an approval status somebody set from the desk
		without submitting would show up in the queue with buttons on it and be
		missing from the badge beside it.

		The `or_filters` are the backstop `row_is_theirs` describes: a claim
		naming nobody is waiting on whoever can pick it up. History needs none,
		because a claim that named nobody has the decider written onto it as it
		is settled -- so by the time it is history it names someone, and that
		someone is them.

		The claimant's own claims come out of the pending half where HR Settings
		says they may not settle them. `self_approval_blocked` takes every
		outcome away from such a row -- HRMS refuses the submit itself, not the
		outcome -- so leaving them in would put rows with no buttons in the
		queue and count them in the badge beside it, which is exactly the drift
		one predicate exists to prevent. History keeps them: a claim they raised
		and somebody else settled is still theirs to have seen.
		"""
		filters = {"docstatus": 1 if decided else 0}
		if decided:
			filters[self.approver_field] = frappe.session.user
			return filters, None

		filters[self.decision_field] = "Draft"
		if frappe.db.get_single_value("HR Settings", self.self_approval_setting):
			mine = _session_employee_name()
			if mine:
				filters["employee"] = ["!=", mine]

		return filters, [
			[self.approver_field, "=", frappe.session.user],
			[self.approver_field, "is", "not set"],
		]

	def decorate(self, claims: list[dict]) -> None:
		"""Who each claim is assigned to, as a person rather than as a login.

		`Expense Claim` stores the approver as a User link and keeps no fetched
		name beside it, the way `Leave Application` does with
		`leave_approver_name`. One read covers the page; a login with no User
		row left keeps its own id, which is the honest thing to show for an
		account that has been removed.
		"""
		logins = {row.get(self.approver_field) for row in claims if row.get(self.approver_field)}
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
			login = claim.get(self.approver_field)
			claim.expense_approver_name = names.get(login) or login

	def before_decision(self, doc) -> None:
		"""A claim nobody was named on is settled by whoever picked it up.

		The record should say so -- otherwise it goes missing from the history
		of the one person who decided it the moment they do.
		"""
		if not doc.get(self.approver_field):
			doc.set(self.approver_field, frappe.session.user)

	def decision_result(self, doc, state_field: str) -> dict:
		"""The base answer, plus what the claim actually settled at."""
		return {
			**super().decision_result(doc, state_field),
			"total_sanctioned_amount": flt(doc.total_sanctioned_amount),
			"currency": doc.currency,
		}

	def no_employee_message(self) -> str:
		return frappe._(
			"Your login is not linked to an employee record, so expenses cannot be claimed against it."
		)

	def foreign_employee_message(self) -> str:
		return frappe._("Expenses can only be claimed for your own employee record here.")

	def permlevel_message(self) -> str:
		return frappe._(
			"You are not permitted to decide expense claims. The Expense Approver role grants this."
		)

	def not_yours_message(self, doc) -> str:
		return frappe._("{0} is not your expense claim to decide — it is assigned to {1}.").format(
			doc.name, doc.get(self.approver_field) or frappe._("nobody")
		)


EXPENSES = Expenses()


def _session_employee_name() -> str | None:
	"""The employee record behind this session, as the queue needs to exclude it.

	A raw read rather than `session_employee`, and deliberately so. What it
	returns is the caller's own employee id and nothing else -- the same bounded
	disclosure `session_employee_access` makes -- whereas the permission-checked
	read answers `None` for a user whose `Employee` access is gated, which here
	would quietly put their own claims back into their own queue.
	"""
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


@frappe.whitelist()
def get_expense_permissions() -> dict:
	"""What the session user may do with expenses, plus their approval backlog.

	See `approvals.RequestType.permissions`, which is this answer and the
	argument for every field in it.
	"""
	return EXPENSES.permissions()


@frappe.whitelist()
def get_expense_approval_queue(decided: int = 0) -> list[dict]:
	"""Claims waiting on this user's decision, or ones already settled.

	A reader who merely has the page open gets no buttons, and an approver
	looking at their own claim gets none either where HR Settings says so. See
	`approvals.RequestType.approval_queue`.
	"""
	return EXPENSES.approval_queue(bool(frappe.utils.cint(decided)))


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

	The field list a claim may set and the employee it is for are the server's
	-- see `approvals.RequestType.request_employee`.

	The money is settled here too, and not by the form. What a claim costs in the
	company's books is a product of the employee's currency, the company's, and
	ERPNext's exchange rate; which account it lands in is the expense type's; and
	which cost centre it is charged to is the company's. The desk collects all of
	that with a screenful of JavaScript and four round trips -- see
	`expense_claim.js` -- and every one of those answers is the same wherever it
	is asked. A form that asked them would be a second place they could be
	answered differently.
	"""
	values = EXPENSES.parse_request(doc)
	employee = EXPENSES.request_employee(values, ["name", "company", "salary_currency"])

	rows = values.get("expenses") or []
	if not isinstance(rows, list) or not rows:
		frappe.throw(
			frappe._("A claim needs at least one expense on it."),
			frappe.ValidationError,
		)

	context = _claim_context(employee)
	claim = EXPENSES.new_request(values, employee)
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
def get_expense_claim_lines(claims: str) -> list[dict]:
	"""The expense rows of several claims at once, for a list of them.

	The parent names are vetted by `RequestType.readable`, whose docstring says
	why this is not a child-table read over REST; the rows then follow from names
	this user has already been allowed to see.

	`description` is a Text Editor field, so what comes out of the desk is HTML.
	It is flattened to text on the way out: nothing on these pages renders markup
	it was handed, and a description that arrives as text can be rendered as text
	-- which is the version of this that cannot carry a script.
	"""
	readable = EXPENSES.readable(frappe.parse_json(claims) or [])
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


@frappe.whitelist(methods=["POST"])
def decide_expense_claim(
	name: str, decision: str, sanctioned: str | dict | None = None
) -> dict:
	"""Settle an expense claim, by the route the site has configured.

	See `approvals.RequestType.decide`: a Workflow transition where one is
	running, and an approval status plus a submit in one transaction where none
	is.

	`sanctioned` is what the approver is allowing, per expense row, when that is
	not simply what was claimed. It is applied to the document before either
	route writes it, so the amount and the decision land together and HRMS
	revalidates both: `validate_sanctioned_amount` refuses anything above what
	was claimed, and a rejection zeroes them all whatever was passed.
	"""
	amounts = _sanctioned_amounts(sanctioned)
	return EXPENSES.decide(
		name, decision, prepare=lambda doc: _apply_sanctioned_amounts(doc, amounts)
	)


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
