"""Submitted Purchase/Material Issue requests are the sole budget tally.

Usage is never stored, and neither is attribution. A request belongs to whichever
allocation covers its department on its transaction date, so the tally is summed
from the requests themselves and cannot drift from the documents it describes.
Procurement Requests provide live provisional estimates only. No purchase or stock
ledger events affect usage.

History comes from the documents themselves: `docstatus` and `amended_from` on
the Material Request, its Version log, and the Department Budget amendment chain.
"""

from decimal import Decimal
from urllib.parse import quote

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt

from commons.requests.procurement_workflow import open_request_states

BUDGET = "Department Budget"
REQUEST = "Procurement Request"
MR_TYPES = ("Purchase", "Material Issue")
# A received or issued request is money gone; every other submitted one is money
# the department has committed but still holds. `Stopped` counts as committed --
# it is still charged to the allocation until someone cancels it.
MR_DELIVERED = ("Received", "Issued")


# Money is carried as `Decimal`, never the `flt` floats used elsewhere in this
# module: the provisional estimate multiplies a quantity by a rate, and binary
# floats make that drift by cents. `test_budget_math` pins that, and needs no site.
def number(value):
	return Decimal(str(value or 0))


def outstanding_value(qty, covered_qty, rate):
	return max(number(qty) - number(covered_qty), Decimal(0)) * max(number(rate), Decimal(0))


def budget_name(company, department, date, submitted_only=True):
	"""The allocation covering this department on this date.

	Asks for a submitted allocation first and only then, when the caller will
	display a draft, for a draft. A stale draft can outlive the allocation it was
	meant to replace, and precedence here is explicit rather than left to whatever
	order the database happens to return rows in.
	"""
	for docstatus in (1, 0) if not submitted_only else (1,):
		name = frappe.db.get_value(
			BUDGET,
			{
				"company": company,
				"department": department,
				"start_date": ["<=", date],
				"end_date": [">=", date],
				"docstatus": docstatus,
			},
			"name",
		)
		if name:
			return name
	return None


def find_budget(company, department, date):
	name = budget_name(company, department, date)
	if not name:
		frappe.throw(
			_(
				"No submitted department budget exists for {0} on {1}. Finance must submit the allocation before this Material Request."
			).format(department or _("this department"), date)
		)
	return name


def lock_budget(name):
	budget = frappe.qb.DocType(BUDGET)
	# Every column, because the callers read the whole allocation off the row
	# they locked rather than loading it a second time.
	rows = frappe.qb.from_(budget).select("*").where(budget.name == name).for_update().run(as_dict=True)
	if not rows:
		frappe.throw(_("Department budget no longer exists."))
	return rows[0]


def usage_rows(budget, lock=False):
	"""Submitted Purchase/Material Issue rows falling in this budget's department and period.

	Attribution is derived, not stored: a request belongs to whichever allocation
	covers its department on its transaction date. `for_update` is not decoration:
	the tally is read inside the Department Budget row lock, and a locking read is
	what makes it see rows another transaction committed after this one's snapshot.
	"""
	item = frappe.qb.DocType("Material Request Item")
	request = frappe.qb.DocType("Material Request")
	query = (
		frappe.qb.from_(item)
		.inner_join(request)
		.on(request.name == item.parent)
		.select(item.name, item.parent, item.amount, request.status)
		.where(
			(request.docstatus == 1)
			& request.material_request_type.isin(MR_TYPES)
			& (request.company == budget.company)
			& (request.department == budget.department)
			& request.transaction_date.between(budget.start_date, budget.end_date)
		)
	)
	return (query.for_update() if lock else query).run(as_dict=True)


def total(rows):
	return sum((number(row.amount) for row in rows), number(0))


def used_amount(budget, lock=False):
	return total(usage_rows(budget, lock=lock))


def spent_amount(rows):
	"""The delivered half of the tally. The rest of it is still only committed."""
	return total(row for row in rows if row.status in MR_DELIVERED)


def remaining(budget, lock=False):
	return number(budget.annual_amount) - used_amount(budget, lock=lock)


def material_request_department(doc):
	"""Resolve department from validated request-row links, or the explicit MR field."""
	departments = set()
	if doc.get("department"):
		departments.add(doc.department)
	for row in doc.items:
		if row.get("procurement_request_item"):
			source = frappe.db.get_value(
				"Procurement Request Item",
				row.procurement_request_item,
				["parent", "item_code"],
				as_dict=True,
			)
			if (
				not source
				or source.parent != row.get("procurement_request")
				or source.item_code != row.item_code
			):
				frappe.throw(_("Row {0}: invalid Procurement Request item reference.").format(row.idx))
		elif row.get("procurement_request"):
			frappe.throw(_("Row {0}: select the linked Procurement Request item as well.").format(row.idx))
		else:
			continue
		parent = frappe.db.get_value(
			"Procurement Request",
			source.parent,
			["company", "department", "docstatus"],
			as_dict=True,
		)
		# `docstatus` 1 *is* the approval -- approving is what submits a request --
		# so the state it is sitting in has no say here. Asking for its name as
		# well would refuse every Material Request on a site that renamed a state,
		# and would let one through on a site that kept the name while meaning
		# something else by it.
		if not parent or parent.company != doc.company or parent.docstatus != 1:
			frappe.throw(
				_("Material Requests must refer to an approved Procurement Request in the same company.")
			)
		departments.add(parent.department)
	if doc.get("procurement_request"):
		parent = frappe.db.get_value(
			"Procurement Request",
			doc.procurement_request,
			["department", "company", "docstatus"],
			as_dict=True,
		)
		if not parent or parent.company != doc.company or parent.docstatus != 1:
			frappe.throw(_("Invalid Procurement Request reference."))
		departments.add(parent.department)
	if len(departments) > 1:
		frappe.throw(_("Use a separate Material Request for each department."))
	department = next(iter(departments), None)
	if department:
		department_company = frappe.db.get_value("Department", department, "company")
		if department_company and department_company != doc.company:
			frappe.throw(_("Material Request and department must belong to the same company."))
	return department


def validate_material_request(doc, method=None):
	if doc.material_request_type not in MR_TYPES:
		return
	department = material_request_department(doc)
	doc.department = department
	currency = frappe.db.get_value("Company", doc.company, "default_currency")
	if doc.get("buying_price_list"):
		list_currency = frappe.db.get_value("Price List", doc.buying_price_list, "currency")
		if list_currency and list_currency != currency:
			frappe.throw(
				_("Material Request rates are in {0}. Select a buying price list in that currency.").format(
					currency
				)
			)
	for row in doc.items:
		qty, rate = number(row.qty), number(row.rate)
		if not qty.is_finite() or not rate.is_finite() or qty <= 0 or rate < 0:
			frappe.throw(
				_("Row {0}: budget quantity must be positive and rate cannot be negative.").format(row.idx)
			)
		if doc.docstatus == 1 and rate <= 0:
			frappe.throw(
				_("Row {0}: enter a positive Material Request rate in {1} before submitting.").format(
					row.idx, currency
				)
			)
		# MR amounts are company currency, and are the tally itself. Recompute
		# server-side, never trust client totals.
		row.amount = flt(qty * rate, row.precision("amount"))
	if doc.docstatus == 1:
		if not department:
			frappe.throw(_("Select a Department before submitting this Material Request."))
		# Checked, never stored: the allocation is a function of department and date.
		# Handed back so the submit hook need not resolve it a second time.
		return find_budget(doc.company, department, doc.transaction_date)


def material_rows(doc):
	return [
		dict(
			row=row.name,
			amount=str(number(row.amount)),
			qty=str(number(row.qty)),
			rate=str(number(row.rate)),
			stock_qty=str(number(row.stock_qty)),
			conversion_factor=str(number(row.conversion_factor)),
			uom=row.uom,
			request=row.get("procurement_request_item"),
			request_name=row.get("procurement_request"),
			type=doc.material_request_type,
		)
		for row in doc.items
	]


def protect_submitted_material_request(doc, method=None):
	if not doc.get("department"):
		return
	old = doc.get_doc_before_save()
	if not old or (old.material_request_type not in MR_TYPES and doc.material_request_type not in MR_TYPES):
		return
	for field in (
		"company",
		"transaction_date",
		"material_request_type",
		"department",
		"buying_price_list",
		"procurement_request",
	):
		if doc.get(field) != old.get(field):
			frappe.throw(_("Cancel and amend the Material Request to change its submitted budget values."))
	if material_rows(doc) != material_rows(old):
		frappe.throw(
			_(
				"Cancel and amend the Material Request to change its submitted quantities, rates or source references."
			)
		)


def persist_amounts(name):
	"""Re-read and rewrite row amounts so the stored column is the tally's truth.

	ERPNext can revise rates in `on_update` before `on_submit` runs.
	"""
	doc = frappe.get_doc("Material Request", name)
	budget = validate_material_request(doc)
	for row in doc.items:
		frappe.db.set_value("Material Request Item", row.name, "amount", row.amount, update_modified=False)
	return doc, budget


def charge_material_request(doc, method=None):
	"""on_submit: refuse the submission if it overruns the department allocation.

	Cancellation needs no counterpart. A cancelled request leaves the tally by
	virtue of its docstatus.
	"""
	# Defense in depth: callers outside MR hooks cannot post purchasing values.
	if doc.doctype != "Material Request" or doc.material_request_type not in MR_TYPES:
		return
	if doc.docstatus != 1:
		return
	doc, budget = persist_amounts(doc.name)
	current = lock_budget(budget)
	# Re-read under the lock: the allocation may have been cancelled between
	# validation and here, and a cancelled one authorises nothing.
	if current.docstatus != 1:
		frappe.throw(_("Submit the department budget before charging Material Requests to it."))
	enforce_allocation(current, doc)


def enforce_allocation(current, doc):
	"""Throw unless every submitted request charged to `current` fits its allocation."""
	rows = usage_rows(current, lock=True)
	charged = total(rows)
	allocation = number(current.annual_amount)
	if charged <= allocation:
		return
	own = total(row for row in rows if row.parent == doc.name)
	available = allocation - (charged - own)
	frappe.throw(
		_(
			"Department {0}: this Material Request needs {1} {2}; only {3} remains. Shortfall: {4}."
		).format(
			current.department,
			current.currency,
			f"{own:,.2f}",
			f"{available:,.2f}",
			f"{own - available:,.2f}",
		),
		title=_("Department budget exceeded"),
	)


# Which undecided requests are an open ask is read off the active Workflow --
# see `workflow.open_request_states`, which is where the reasoning lives. It is
# the only place in this module that consults a state name at all, and it only
# reaches the readout's `open_requests` figure: on the approved side `docstatus`
# 1 is the approval, so a site running without the Workflow cannot slip past the
# gate by leaving a submitted request at some other status.


def request_rows(budget, approved_only=False, lock=False):
	"""Item rows of the requests falling in this budget's department and period.

	Attribution is derived exactly as `usage_rows` derives it, and `for_update` is
	there for the same reason: read inside the Department Budget row lock, a
	locking read is what makes an approval another transaction committed after
	this one's snapshot visible. Without it two requests that each fit on their
	own can both be approved, and the allocation holds neither.
	"""
	item = frappe.qb.DocType("Procurement Request Item")
	request = frappe.qb.DocType("Procurement Request")
	approved = request.docstatus == 1
	# A workflow with no open states of its own leaves only the approved half --
	# and an empty `isin` is not a query the database will accept.
	open_states = () if approved_only else open_request_states()
	decided_or_open = (
		approved | ((request.docstatus == 0) & request.status.isin(open_states))
		if open_states
		else approved
	)
	query = (
		frappe.qb.from_(item)
		.inner_join(request)
		.on(request.name == item.parent)
		.select(
			item.name,
			item.parent,
			item.qty,
			item.item_code,
			item.uom,
			item.verified_rate,
			item.estimated_rate,
			request.docstatus,
		)
		.where(
			(item.parenttype == REQUEST)
			& decided_or_open
			& (request.company == budget.company)
			& (request.department == budget.department)
			& request.transaction_date.between(budget.start_date, budget.end_date)
		)
	)
	return (query.for_update() if lock else query).run(as_dict=True)


def request_values(budget, approved_only=False, lock=False):
	"""Outstanding request value for this department and period, by request name."""
	rows = request_rows(budget, approved_only=approved_only, lock=lock)
	names = list({row.parent for row in rows})
	return outstanding_values(names, rows) if names else {}


def provisional_requests(budget):
	"""Outstanding request value for this department and period, split by decision.

	Approval is what submits a request, so `docstatus` 1 is spending the
	department has committed to and a draft already with procurement or its
	approver is only an open ask. Neither a request still being written nor a
	rejected one counts at all, and a cancelled one has left the pipeline
	altogether.

	Outstanding, not total: whatever a request has already been ordered for is
	counted by the Material Request tally instead, and counting both would spend
	the allocation twice.
	"""
	rows = request_rows(budget)
	names = list({row.parent for row in rows})
	if not names:
		return number(0), number(0)
	values = outstanding_values(names, rows)
	approved = {row.parent for row in rows if row.docstatus == 1}
	committed = sum((value for name, value in values.items() if name in approved), number(0))
	return committed, sum(values.values(), number(0)) - committed


def outstanding_values(names, items):
	from erpnext.stock.get_item_details import get_conversion_factor

	# Not a locking read, unlike the tally either side of it. A quantity a
	# concurrent Material Request covered after this transaction's snapshot is
	# missed here, which counts that quantity as still outstanding while the
	# Material Request tally also charges it -- the approval gate errs towards
	# refusing, never towards letting an overrun through.
	item = frappe.qb.DocType("Material Request Item")
	request = frappe.qb.DocType("Material Request")
	covered = (
		frappe.qb.from_(item)
		.inner_join(request)
		.on(request.name == item.parent)
		.select(item.procurement_request_item, Sum(item.stock_qty).as_("stock_qty"))
		.where(
			(request.docstatus == 1)
			& request.material_request_type.isin(MR_TYPES)
			& item.procurement_request.isin(names)
		)
		.groupby(item.procurement_request_item)
		.run(as_dict=True)
	)
	by_row = {row.procurement_request_item: number(row.stock_qty) for row in covered}
	result = dict.fromkeys(names, number(0))
	factors = {}
	for row in items:
		qty = number(0)
		if row.name in by_row:
			key = (row.item_code, row.uom)
			if key not in factors:
				factors[key] = number(get_conversion_factor(*key).get("conversion_factor"))
			if factors[key] <= 0:
				frappe.throw(_("Missing UOM conversion for the outstanding procurement estimate."))
			qty = by_row[row.name] / factors[key]
		result[row.parent] += outstanding_value(
			row.qty, qty, number(row.verified_rate) or number(row.estimated_rate)
		)
	return result


def enforce_request_allocation(doc, method=None):
	"""on_submit: refuse an approval the department's allocation cannot hold.

	Approval is where the allocation has to hold, because approval is where the
	department commits. By the time a Material Request is raised the decision has
	already been taken, and refusing it there refuses the wrong document -- the
	one gate this adds is the one an approver can still act on.

	What it measures is the readout's own `remaining`: the Material Request tally
	plus every approved request's outstanding estimate, this one included. So the
	refusal fires exactly when the approver's own budget banner would have gone
	negative, and the two can never tell different stories.

	No allocation, no gate. A department Finance has not budgeted is not over
	budget, and the Material Request stage still refuses to spend against a
	missing allocation -- so nothing escapes the control, it only lands later. A
	draft allocation authorises nothing either, and reads here as the absence of
	one.
	"""
	if doc.doctype != REQUEST or doc.docstatus != 1:
		return
	name = budget_name(doc.company, doc.department, doc.transaction_date)
	if not name:
		return
	current = lock_budget(name)
	# Re-read under the lock: the allocation may have been cancelled between
	# resolving it and here, and a cancelled one is no allocation at all.
	if current.docstatus != 1:
		return
	values = request_values(current, approved_only=True, lock=True)
	# This request is already at `docstatus` 1 in the database -- `on_submit` runs
	# after the write -- so it is one of the rows above, and its own share has to
	# come back out to say what was left before it.
	own = values.get(doc.name, number(0))
	if own <= 0:
		# Nothing to charge. An estimate is not required to approve a request, and a
		# request that commits nothing cannot be what takes a department over.
		return
	committed = sum(values.values(), number(0))
	available = number(current.annual_amount) - used_amount(current, lock=True) - (committed - own)
	if own <= available:
		return
	frappe.throw(
		_(
			"Department {0}: approving this request commits {1} {2}; only {3} remains. Shortfall: {4}."
		).format(
			current.department,
			current.currency,
			f"{own:,.2f}",
			f"{available:,.2f}",
			f"{own - available:,.2f}",
		),
		title=_("Department budget exceeded"),
	)


def can_view_summary(doc):
	"""Whether the allocation behind this request may be summarised to this user.

	Two ways in, and both are the site's configuration rather than a role named
	here. Read on `Department Budget` is the general one: whoever the Role
	Permission Manager lets open an allocation may see its position stated beside
	a request charged to it. The narrower one is the approver this request names,
	who is about to commit against that allocation and has to see what is left --
	a grant tied to the decision in front of them rather than to the doctype, so
	it survives a site that keeps budgets away from approvers generally.

	This was a hardcoded `{"Accounts Manager", "Purchase Manager", "System
	Manager"}` -- the one place in this app where who may see something was
	decided in Python rather than in the Role Permission Manager. A site that
	renamed a finance role lost the readout silently; one that created an
	`Accounts Manager` for an unrelated reason gained it. `Purchase Manager` now
	holds read on `Department Budget` in that doctype's own permission rows,
	which is both where the grant belongs and where a site can take it back.

	`has_permission` rather than a role scan, so User Permissions and this app's
	own gate in `commons.safer_permissions` narrow it as well.
	"""
	frappe.has_permission(doc.doctype, "read", doc=doc, throw=True)
	if frappe.has_permission(BUDGET, "read"):
		return True
	return bool(
		doc.approver == frappe.session.user and frappe.has_permission(doc.doctype, "submit", doc=doc)
	)


def department_position(name, cache=None):
	"""The figures every request in a department and period shares.

	Given a cache, a list of requests from one department computes this once
	instead of once per row -- it is the expensive half of a summary.
	"""
	if cache is not None and name in cache:
		return cache[name]
	budget = frappe.get_doc(BUDGET, name)
	rows = usage_rows(budget)
	spent = spent_amount(rows)
	approved, open_requests = provisional_requests(budget)
	# An undelivered Material Request and an approved request nobody has ordered
	# against yet are the same kind of money: decided on, not yet gone.
	position = (budget, spent, total(rows) - spent + approved, open_requests)
	if cache is not None:
		cache[name] = position
	return position


def budget_lines(budget, spent, committed, open_requests):
	"""The readout itself: what was allocated, where it has gone, what is left.

	Open requests sit outside the subtraction on purpose. Nobody has decided to
	spend them, so they are context for the approver rather than a claim on the
	allocation -- and a request its author has not sent anywhere yet is not even
	that, so it is not counted at all.
	"""
	annual = number(budget.annual_amount)
	return dict(
		inactive=budget.docstatus != 1,
		currency=budget.currency,
		annual=float(annual),
		spent=float(spent),
		committed=float(committed),
		remaining=float(annual - spent - committed),
		open_requests=float(open_requests),
	)


def summary_notices(lines, department=None):
	"""What the readout's figures mean for the person about to decide.

	Written here, beside the gates that make them true, rather than in the page
	that draws them. Each line below is a restatement of code in this module, and
	a site that changes one of those rules should not have to remember that a
	frontend somewhere is still promising the old one:

	* no allocation, and a draft allocation, both read as the absence of one --
	  `enforce_request_allocation` returns without gating, and `find_budget`
	  refuses the Material Request that comes later;
	* the overdraft line is `budget_lines`'s own subtraction, said in words;
	* open requests sit outside that subtraction, which is `budget_lines`'s
	  docstring.

	`severity` is the page's cue for how loudly to say it, not a decision of its
	own: "warning" is something Finance has to act on, "info" is a footnote.
	"""
	if lines.get("missing"):
		return [
			dict(
				severity="warning",
				message=_(
					"No annual budget is configured for {0}. Approval is not gated by an allocation, but Finance must create one before any Material Request can be charged."
				).format(department or _("this department")),
			)
		]

	notices = []
	if lines.get("inactive"):
		notices.append(
			dict(
				severity="warning",
				message=_(
					"This allocation is still a draft. A draft authorises nothing, so approval is not gated by it and Material Requests cannot be charged against it until Finance submits it."
				),
			)
		)
	if flt(lines.get("remaining")) < 0:
		notices.append(
			dict(
				severity="warning",
				message=_("Over budget by {0}.").format(
					frappe.utils.fmt_money(-flt(lines["remaining"]), currency=lines.get("currency"))
				),
			)
		)
	notices.append(
		dict(
			severity="info",
			message=_("Open requests are not yet approved, so they are not subtracted from what remains."),
		)
	)
	return notices


def request_summary(doc, cache=None):
	if not can_view_summary(doc):
		return None
	name = budget_name(doc.company, doc.department, doc.transaction_date, submitted_only=False)
	if not name:
		missing = dict(missing=True, department=doc.department)
		return dict(missing, notices=summary_notices(missing, doc.department))
	budget, *position = department_position(name, cache)
	lines = budget_lines(budget, *position)
	return dict(
		missing=False,
		name=name,
		department=budget.department,
		fiscal_year=budget.fiscal_year,
		notices=summary_notices(lines, budget.department),
		**lines,
	)


@frappe.whitelist()
def get_budget_documents(request: str) -> list[dict]:
	doc = frappe.get_doc("Procurement Request", request)
	if not can_view_summary(doc):
		return []
	name = budget_name(doc.company, doc.department, doc.transaction_date, submitted_only=False)
	if not name:
		return []
	charged = {}
	for row in usage_rows(frappe.get_doc(BUDGET, name)):
		charged[row.parent] = charged.get(row.parent, number(0)) + number(row.amount)
	# One permission-filtered query, rather than loading every request to ask.
	# `get_list`, never `get_all`: the tally above is raw SQL by necessity -- an
	# allocation has to count rows the reader cannot see -- so this is the only
	# thing standing between that tally and a list of documents. `get_all` skips
	# permissions entirely, which made the filter below a no-op.
	readable = (
		set(frappe.get_list("Material Request", filters={"name": ["in", list(charged)]}, pluck="name"))
		if charged
		else set()
	)
	# The link is built here rather than by the page, using the desk's own `slug`:
	# turning a doctype name into a route is core's convention, not something a
	# frontend should reimplement. `/app` rather than `/desk` deliberately -- see
	# `AppSidebar.userDeskUrl`: Frappe has forwarded it across two renames of the
	# desk, which is more than the current name can promise.
	from frappe.desk.utils import slug

	return [
		dict(
			doctype="Material Request",
			name=request_name,
			amount=float(amount),
			url=f"/app/{slug('Material Request')}/{quote(request_name)}",
		)
		for request_name, amount in charged.items()
		if request_name in readable
	]


class BudgetMaterialRequestMixin:
	def update_item_rates(self):
		# A later price-list refresh must never revalue a submitted MR. This is not
		# belt-and-braces: ERPNext writes the new rate and amount with `db_set`,
		# which bypasses `validate` and `before_update_after_submit` entirely, and
		# `amount` is the budget tally itself.
		# Keyed on purpose, not on `department`: that field is not cleared when a
		# request's type changes, and a stale value would silently suppress the
		# refresh on a submitted Material Transfer.
		if self.docstatus != 0 and self.material_request_type in MR_TYPES:
			return
		super().update_item_rates()
