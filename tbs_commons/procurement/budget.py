"""Submitted Purchase/Material Issue requests are the sole budget tally.

Usage is never stored, and neither is attribution. A request belongs to whichever
allocation covers its department on its transaction date, so the tally is summed
from the requests themselves and cannot drift from the documents it describes.
Procurement Requests provide live provisional estimates only. No purchase or stock
ledger events affect usage.

History comes from the documents themselves: `docstatus` and `amended_from` on
the Material Request, its Version log, and the Department Budget amendment chain.
"""

import frappe
from frappe import _
from frappe.utils import flt

from tbs_commons.procurement.budget_math import number, outstanding_value

BUDGET = "Department Budget"
MR_TYPES = ("Purchase", "Material Issue")


def budget_name(company, department, date, submitted_only=True):
	return frappe.db.get_value(
		BUDGET,
		{
			"company": company,
			"department": department,
			"start_date": ["<=", date],
			"end_date": [">=", date],
			# Only a submitted allocation authorises a charge; a draft is shown
			# in procurement feedback but cannot be spent against.
			"docstatus": 1 if submitted_only else ["<", 2],
		},
		"name",
	)


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
	rows = frappe.db.sql("select * from `tabDepartment Budget` where name=%s for update", name, as_dict=True)
	if not rows:
		frappe.throw(_("Department budget no longer exists."))
	return rows[0]


def usage_rows(budget, lock=False):
	"""Submitted Purchase/Material Issue rows falling in this budget's department and period.

	Attribution is derived, not stored: a request belongs to whichever allocation
	covers its department on its transaction date. `for update` is not decoration:
	the tally is read inside the Department Budget row lock, and a locking read is
	what makes it see rows another transaction committed after this one's snapshot.
	"""
	return frappe.db.sql(
		"""select i.name, i.parent, i.amount from `tabMaterial Request Item` i
		inner join `tabMaterial Request` mr on mr.name=i.parent
		where mr.docstatus=1 and mr.material_request_type in %(types)s
		and mr.company=%(company)s and mr.department=%(department)s
		and mr.transaction_date between %(start)s and %(end)s"""
		+ (" for update" if lock else ""),
		{
			"types": MR_TYPES,
			"company": budget.company,
			"department": budget.department,
			"start": budget.start_date,
			"end": budget.end_date,
		},
		as_dict=True,
	)


def used_amount(budget, lock=False):
	return sum((number(row.amount) for row in usage_rows(budget, lock=lock)), number(0))


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
			["company", "department", "docstatus", "status"],
			as_dict=True,
		)
		if (
			not parent
			or parent.company != doc.company
			or parent.docstatus != 1
			or parent.status not in ("Approved", "Completed")
		):
			frappe.throw(
				_("Material Requests must refer to an approved Procurement Request in the same company.")
			)
		departments.add(parent.department)
	if doc.get("procurement_request"):
		parent = frappe.db.get_value(
			"Procurement Request",
			doc.procurement_request,
			["department", "company", "docstatus", "status"],
			as_dict=True,
		)
		if (
			not parent
			or parent.company != doc.company
			or parent.docstatus != 1
			or parent.status not in ("Approved", "Completed")
		):
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
			frappe.throw(_("Select a Budget Department before submitting this Material Request."))
		# Checked, never stored: the allocation is a function of department and date.
		find_budget(doc.company, department, doc.transaction_date)


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
	validate_material_request(doc)
	for row in doc.items:
		frappe.db.set_value("Material Request Item", row.name, "amount", row.amount, update_modified=False)
	return doc


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
	doc = persist_amounts(doc.name)
	enforce_allocation(
		lock_budget(find_budget(doc.company, doc.department, doc.transaction_date)), doc
	)


def enforce_allocation(current, doc):
	"""Throw unless every submitted request charged to `current` fits its allocation."""
	rows = usage_rows(current, lock=True)
	charged = sum((number(row.amount) for row in rows), number(0))
	allocation = number(current.annual_amount)
	if charged <= allocation:
		return
	own = sum((number(row.amount) for row in rows if row.parent == doc.name), number(0))
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


def provisional_requests(budget):
	"""Sent/review/approved requests only; batch-read rows and their MR coverage."""
	names = frappe.get_all(
		"Procurement Request",
		filters={
			"company": budget.company,
			"department": budget.department,
			"transaction_date": ["between", [budget.start_date, budget.end_date]],
			"docstatus": ["<", 2],
			"status": ["in", ["Pending", "Under Review", "Approved", "Completed"]],
		},
		pluck="name",
	)
	if not names:
		return {}
	items = frappe.get_all(
		"Procurement Request Item",
		filters={"parent": ["in", names]},
		fields=["name", "parent", "qty", "item_code", "uom", "verified_rate", "estimated_rate"],
	)
	return outstanding_values(names, items)


def outstanding_values(names, items):
	from erpnext.stock.get_item_details import get_conversion_factor

	covered = frappe.db.sql(
		"""select i.procurement_request_item, sum(i.stock_qty) as stock_qty
		from `tabMaterial Request Item` i inner join `tabMaterial Request` mr on mr.name=i.parent
		where mr.docstatus=1 and mr.material_request_type in ('Purchase', 'Material Issue')
		and i.procurement_request in %(names)s group by i.procurement_request_item""",
		{"names": tuple(names)},
		as_dict=True,
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


def request_outstanding(doc):
	return outstanding_values([doc.name], doc.items)[doc.name]


def can_view_summary(doc):
	frappe.has_permission(doc.doctype, "read", doc=doc, throw=True)
	return bool(
		(doc.approver == frappe.session.user and frappe.has_permission(doc.doctype, "submit", doc=doc))
		or set(frappe.get_roles()) & {"Accounts Manager", "Purchase Manager", "System Manager"}
	)


def request_summary(doc):
	if not can_view_summary(doc):
		return None
	name = budget_name(doc.company, doc.department, doc.transaction_date, submitted_only=False)
	if not name:
		return dict(missing=True, department=doc.department)
	budget = frappe.get_doc(BUDGET, name)
	used = used_amount(budget)
	available = number(budget.annual_amount) - used
	provisional = provisional_requests(budget)
	outstanding = request_outstanding(doc) if doc.docstatus != 2 and doc.status != "Rejected" else number(0)
	# Include the displayed draft once when previewing, but never in other users' pipeline totals.
	projection = sum(provisional.values(), number(0)) + (
		outstanding if doc.name not in provisional else number(0)
	)
	return dict(
		missing=False,
		inactive=budget.docstatus != 1,
		name=name,
		department=budget.department,
		fiscal_year=budget.fiscal_year,
		currency=budget.currency,
		budget=float(number(budget.annual_amount)),
		used=float(used),
		available=float(available),
		provisional=float(sum(provisional.values(), number(0))),
		request_amount=float(outstanding),
		projected_available=float(available - projection),
	)


@frappe.whitelist()
def get_request_budget(name: str) -> dict | None:
	return request_summary(frappe.get_doc("Procurement Request", name))


@frappe.whitelist()
def get_budget_documents(request: str) -> list[dict]:
	summary = get_request_budget(request)
	if not summary or summary.get("missing"):
		return []
	charged = {}
	for row in usage_rows(frappe.get_doc(BUDGET, summary["name"])):
		charged[row.parent] = charged.get(row.parent, number(0)) + number(row.amount)
	return [
		dict(doctype="Material Request", name=name, amount=float(amount))
		for name, amount in charged.items()
		if frappe.has_permission("Material Request", "read", doc=name)
	]


@frappe.whitelist()
def get_material_request_budget(name: str) -> dict | None:
	doc = frappe.get_doc("Material Request", name)
	frappe.has_permission(doc.doctype, "read", doc=doc, throw=True)
	if not (
		frappe.has_permission(doc.doctype, "submit", doc=doc)
		or set(frappe.get_roles()) & {"Accounts Manager", "System Manager"}
	):
		return None
	if doc.material_request_type not in MR_TYPES:
		return None
	department = doc.get("department") or material_request_department(doc)
	name = budget_name(doc.company, department, doc.transaction_date, submitted_only=False)
	if not name:
		return dict(missing=True)
	budget = frappe.get_doc(BUDGET, name)
	used = used_amount(budget)
	return dict(
		missing=False,
		inactive=budget.docstatus != 1,
		currency=budget.currency,
		budget=float(number(budget.annual_amount)),
		used=float(used),
		available=float(number(budget.annual_amount) - used),
		amount=float(sum((number(row.qty) * number(row.rate) for row in doc.items), number(0))),
	)


def register_existing_documents(documents):
	"""Attribute historical submitted Material Requests to a department.

	Attribution is all there is to import: once a request carries a budget
	department, whichever allocation covers its date counts it.
	"""
	frappe.only_for(["Accounts Manager", "System Manager"])
	references = frappe.parse_json(documents)
	affected = set()
	for reference in references:
		if reference["doctype"] != "Material Request":
			frappe.throw(_("Only Material Requests affect department budget usage."))
		doc = frappe.get_doc("Material Request", reference["name"])
		if doc.docstatus != 1 or doc.material_request_type not in MR_TYPES:
			frappe.throw(_("Only submitted Purchase or Material Issue requests can be imported."))
		department = reference.get("department") or doc.get("department")
		if not department:
			frappe.throw(
				_("Material Request {0} has no department. Supply one to attribute it.").format(doc.name)
			)
		if doc.get("department") and doc.department != department:
			frappe.throw(_("Existing Material Request department does not match the import."))
		name = find_budget(doc.company, department, doc.transaction_date)
		frappe.db.set_value(
			"Material Request", doc.name, "department", department, update_modified=False
		)
		persist_amounts(doc.name)
		affected.add(name)
	for name in sorted(affected):
		current = lock_budget(name)
		if remaining(current, lock=True) < 0:
			frappe.throw(
				_("Submitted Material Requests exceed the allocation for {0}.").format(current.department)
			)
	return {"registered": len(references)}


class BudgetMaterialRequestMixin:
	def update_item_rates(self):
		# A later price-list refresh must never revalue a submitted MR. This is not
		# belt-and-braces: ERPNext writes the new rate and amount with `db_set`,
		# which bypasses `validate` and `before_update_after_submit` entirely, and
		# `amount` is the budget tally itself.
		if self.docstatus != 0 and self.get("department"):
			return
		super().update_item_rates()
