"""Submitted Purchase/Material Issue requests are the sole budget tally.

Procurement Requests provide live provisional estimates only. Source snapshots
and audit movements are written in the Material Request transaction, serialized
by the Department Budget row. No purchase or stock ledger events affect usage.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from tbs_commons.budget_math import number, outstanding_value, totals

BUDGET = "Department Budget"
POSITION = "Department Budget Position"
MOVEMENT = "Department Budget Movement"
MR_TYPES = ("Purchase", "Material Issue")


def budget_name(company, department, date):
	return frappe.db.get_value(
		BUDGET,
		{
			"company": company,
			"department": department,
			"start_date": ["<=", date],
			"end_date": [">=", date],
		},
		"name",
	)


def find_budget(company, department, date):
	name = budget_name(company, department, date)
	if not name:
		frappe.throw(
			_(
				"No department budget exists for {0} on {1}. Finance must create the allocation before submitting this Material Request."
			).format(department or _("this department"), date)
		)
	return name


def lock_budget(name):
	rows = frappe.db.sql("select * from `tabDepartment Budget` where name=%s for update", name, as_dict=True)
	if not rows:
		frappe.throw(_("Department budget no longer exists."))
	return rows[0]


def positions(name, lock=False):
	return frappe.db.sql(
		"select * from `tabDepartment Budget Position` where budget=%s and source_type='Material Request'"
		+ (" for update" if lock else ""),
		name,
		as_dict=True,
	)


def portfolio(records):
	return [row for record in records for row in json.loads(record.payload)]


def allocation(budget, lock=False):
	adjustments = frappe.db.sql(
		"select amount from `tabDepartment Budget Adjustment` where parent=%s"
		+ (" for update" if lock else ""),
		budget.name,
	)
	return number(budget.annual_amount) + sum((number(row[0]) for row in adjustments), number(0))


def remaining(budget, amounts, lock=False):
	return allocation(budget, lock=lock) - amounts["used"]


def material_request_department(doc):
	"""Resolve department from validated request-row links, or the explicit MR field."""
	departments = set()
	if doc.get("budget_department"):
		departments.add(doc.budget_department)
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
		doc.budget_amount = 0
		doc.department_budget = None
		return
	department = material_request_department(doc)
	doc.budget_department = department
	doc.budget_currency = frappe.db.get_value("Company", doc.company, "default_currency")
	if doc.get("buying_price_list"):
		list_currency = frappe.db.get_value("Price List", doc.buying_price_list, "currency")
		if list_currency and list_currency != doc.budget_currency:
			frappe.throw(
				_("Material Request rates are in {0}. Select a buying price list in that currency.").format(
					doc.budget_currency
				)
			)
	amount = number(0)
	for row in doc.items:
		qty, rate = number(row.qty), number(row.rate)
		if not qty.is_finite() or not rate.is_finite() or qty <= 0 or rate < 0:
			frappe.throw(
				_("Row {0}: budget quantity must be positive and rate cannot be negative.").format(row.idx)
			)
		if doc.docstatus == 1 and rate <= 0:
			frappe.throw(
				_("Row {0}: enter a positive Material Request rate in {1} before submitting.").format(
					row.idx, doc.budget_currency
				)
			)
		# MR amounts are company currency. Recompute server-side, never trust client totals.
		row.amount = flt(qty * rate, row.precision("amount"))
		amount += number(row.amount)
	doc.budget_amount = float(amount)
	doc.department_budget = budget_name(doc.company, department, doc.transaction_date) if department else None
	if doc.docstatus == 1:
		if not department:
			frappe.throw(_("Select a Budget Department before submitting this Material Request."))
		doc.department_budget = find_budget(doc.company, department, doc.transaction_date)


def material_rows(doc):
	return [
		dict(
			kind="material_request",
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
	if not frappe.db.exists(POSITION, {"source_key": f"Material Request:{doc.name}"}):
		return
	old = doc.get_doc_before_save()
	if not old or (old.material_request_type not in MR_TYPES and doc.material_request_type not in MR_TYPES):
		return
	for field in (
		"company",
		"transaction_date",
		"material_request_type",
		"budget_department",
		"department_budget",
		"budget_amount",
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


def sync_document(doc, method=None):
	# Defense in depth: callers outside MR hooks cannot post purchasing values.
	if doc.doctype != "Material Request" or doc.material_request_type not in MR_TYPES:
		return
	key = f"Material Request:{doc.name}"
	previous = frappe.db.get_value(POSITION, {"source_key": key}, ["name", "budget", "payload"], as_dict=True)
	if doc.docstatus != 1 and not previous:
		return
	if doc.docstatus == 1:
		# Read persisted rows: ERPNext can update rates in on_update before on_submit.
		doc = frappe.get_doc("Material Request", doc.name)
		validate_material_request(doc)
		rows = material_rows(doc)
		name = doc.department_budget
	else:
		rows = []
		name = previous.budget
	if previous and previous.budget != name:
		frappe.throw(_("Cancel and amend to move a submitted Material Request to another budget."))
	current = lock_budget(name)
	if rows and not current.ready and method != "register_existing":
		frappe.throw(
			_("Finance must reconcile submitted Material Requests before using this department budget.")
		)
	if method == "register_existing" and current.ready:
		frappe.throw(_("Disable this budget before importing existing Material Requests."))
	records = positions(name, lock=True)
	previous = next((record for record in records if record.source_key == key), None)
	before = totals(portfolio(records))
	after = totals(portfolio([record for record in records if record.source_key != key]) + rows)
	increase = after["used"] - before["used"]
	available = remaining(current, before, lock=True)
	if method != "register_existing" and increase > 0 and increase > available:
		frappe.throw(
			_(
				"Department {0}: this Material Request requires {1} {2} additional budget; {3} is available. Shortfall: {4}."
			).format(
				current.department,
				current.currency,
				f"{increase:,.2f}",
				f"{available:,.2f}",
				f"{increase - available:,.2f}",
			),
			title=_("Department budget exceeded"),
		)
	payload = json.dumps(rows, sort_keys=True)
	if previous and previous.payload == payload:
		return
	if previous:
		frappe.db.set_value(POSITION, previous.name, "payload", payload)
	else:
		frappe.get_doc(
			dict(
				doctype=POSITION,
				source_key=key,
				budget=name,
				source_type=doc.doctype,
				source_name=doc.name,
				payload=payload,
			)
		).insert(ignore_permissions=True)
	frappe.get_doc(
		dict(
			doctype=MOVEMENT,
			budget=name,
			source_type=doc.doctype,
			source_name=doc.name,
			used=float(increase),
			details=json.dumps(
				{"before": json.loads(previous.payload) if previous else [], "after": rows}, sort_keys=True
			),
		)
	).insert(ignore_permissions=True, ignore_links=True)
	if rows:
		if method == "register_existing":
			for row in doc.items:
				frappe.db.set_value(
					"Material Request Item", row.name, "amount", row.amount, update_modified=False
				)
		frappe.db.set_value(
			"Material Request",
			doc.name,
			{
				"budget_department": current.department,
				"department_budget": name,
				"budget_currency": current.currency,
				"budget_amount": float(totals(rows)["used"]),
			},
			update_modified=False,
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
	name = budget_name(doc.company, doc.department, doc.transaction_date)
	if not name:
		return dict(missing=True, department=doc.department)
	budget = frappe.get_doc(BUDGET, name)
	amounts = totals(portfolio(positions(name)))
	available = remaining(budget, amounts)
	provisional = provisional_requests(budget)
	outstanding = request_outstanding(doc) if doc.docstatus != 2 and doc.status != "Rejected" else number(0)
	# Include the displayed draft once when previewing, but never in other users' pipeline totals.
	projection = sum(provisional.values(), number(0)) + (
		outstanding if doc.name not in provisional else number(0)
	)
	return dict(
		missing=False,
		inactive=not bool(budget.ready),
		name=name,
		department=budget.department,
		fiscal_year=budget.fiscal_year,
		currency=budget.currency,
		budget=float(allocation(budget)),
		used=float(amounts["used"]),
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
	return [
		dict(
			doctype=record.source_type,
			name=record.source_name,
			amount=float(totals(json.loads(record.payload))["used"]),
		)
		for record in positions(summary["name"])
		if json.loads(record.payload)
		and frappe.has_permission(record.source_type, "read", doc=record.source_name)
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
	department = doc.get("budget_department") or material_request_department(doc)
	name = doc.get("department_budget") or budget_name(doc.company, department, doc.transaction_date)
	if not name:
		return dict(missing=True)
	budget = frappe.get_doc(BUDGET, name)
	used = totals(portfolio(positions(name)))["used"]
	return dict(
		missing=False,
		inactive=not bool(budget.ready),
		currency=budget.currency,
		budget=float(allocation(budget)),
		used=float(used),
		available=float(allocation(budget) - used),
		amount=float(sum((number(row.qty) * number(row.rate) for row in doc.items), number(0))),
	)


def register_existing_documents(documents):
	"""Finance can import reviewed submitted Material Requests into inactive budgets."""
	frappe.only_for(["Accounts Manager", "System Manager"])
	affected = set()
	for reference in frappe.parse_json(documents):
		if reference["doctype"] != "Material Request":
			frappe.throw(_("Only Material Requests affect department budget usage."))
		doc = frappe.get_doc("Material Request", reference["name"])
		if reference.get("department"):
			if doc.get("budget_department") and doc.budget_department != reference["department"]:
				frappe.throw(_("Existing Material Request department does not match the import."))
			frappe.db.set_value("Material Request", doc.name, "budget_department", reference["department"])
			doc.reload()
		if doc.docstatus != 1 or doc.material_request_type not in MR_TYPES:
			frappe.throw(_("Only submitted Purchase or Material Issue requests can be imported."))
		sync_document(doc, method="register_existing")
		affected.add(frappe.db.get_value(POSITION, {"source_key": f"Material Request:{doc.name}"}, "budget"))
	for name in sorted(affected):
		current = lock_budget(name)
		if remaining(current, totals(portfolio(positions(name, lock=True))), lock=True) < 0:
			frappe.throw(
				_("Submitted Material Requests exceed the allocation for {0}.").format(current.department)
			)
	return {"registered": len(frappe.parse_json(documents))}


class BudgetMaterialRequestMixin:
	def update_item_rates(self):
		# A later price-list refresh must never revalue a submitted MR.
		if self.docstatus != 0 and self.get("department_budget"):
			return
		super().update_item_rates()
		self.db_set(
			"budget_amount",
			sum(flt(row.amount) for row in self.items) if self.material_request_type in MR_TYPES else 0,
			update_modified=False,
		)


def validate_reconciled_material_requests(budget):
	"""Do not activate a budget while its known submitted MRs are missing or stale."""
	names = frappe.db.sql(
		"""select distinct mr.name from `tabMaterial Request` mr
		left join `tabMaterial Request Item` i on i.parent=mr.name
		left join `tabProcurement Request` pr on pr.name=i.procurement_request
		left join `tabProcurement Request` header_pr on header_pr.name=mr.procurement_request
		where mr.docstatus=1 and mr.material_request_type in ('Purchase', 'Material Issue')
		and mr.company=%s and mr.transaction_date between %s and %s
		and (mr.budget_department=%s or pr.department=%s or header_pr.department=%s)""",
		(
			budget.company,
			budget.start_date,
			budget.end_date,
			budget.department,
			budget.department,
			budget.department,
		),
	)
	registered = {row.source_name: json.loads(row.payload) for row in positions(budget.name, lock=True)}
	for (name,) in names:
		doc = frappe.get_doc("Material Request", name)
		if registered.get(name) != material_rows(doc):
			frappe.throw(
				_(
					"Register and reconcile submitted Material Request {0} before enabling this budget."
				).format(name)
			)
