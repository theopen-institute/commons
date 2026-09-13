"""Department procurement budgets. All writes run in the source document transaction.

Budget rows serialize writers. Positions retain approved valuations; append-only
movements record every change to the portfolio, including cancellation/reopening.
No independent commits: a budget refusal rolls back the source document too.
"""

import json

import frappe
from frappe import _

from tbs_commons.budget_math import number, totals

BUDGET = "Department Budget"
POSITION = "Department Budget Position"
MOVEMENT = "Department Budget Movement"


def find_budget(company, department, date):
	name = frappe.db.get_value(
		BUDGET,
		{
			"company": company,
			"department": department,
			"start_date": ["<=", date],
			"end_date": [">=", date],
		},
		"name",
	)
	if not name:
		frappe.throw(
			_(
				"No department budget exists for {0} on {1}. Ask Finance to create the annual allocation."
			).format(department or _("this department"), date)
		)
	return name


def lock_budget(name):
	# Current reads after waiting for a concurrent approver, including on MariaDB.
	rows = frappe.db.sql("select * from `tabDepartment Budget` where name=%s for update", name, as_dict=True)
	if not rows:
		frappe.throw(_("Department budget no longer exists."))
	return rows[0]


def positions(name, lock=False):
	return frappe.db.sql(
		"select * from `tabDepartment Budget Position` where budget=%s" + (" for update" if lock else ""),
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
	return number(budget.annual_amount) + sum((number(r[0]) for r in adjustments), number(0))


def remaining(budget, amounts, lock=False):
	return allocation(budget, lock=lock) - sum(amounts.values(), number(0))


def linked_position(kind, row):
	parenttype = {
		"request": "Procurement Request Item",
		"order": "Purchase Order Item",
		"invoice": "Purchase Invoice Item",
	}[kind]
	parent = frappe.db.get_value(parenttype, row, "parent")
	if not parent:
		frappe.throw(_("Invalid budget source row {0}.").format(row))
	source_type = parenttype.removesuffix(" Item")
	position = frappe.db.get_value(
		POSITION, {"source_key": f"{source_type}:{parent}"}, ["budget", "payload"], as_dict=True
	)
	if position:
		for entry in json.loads(position.payload):
			if entry["row"] == row:
				return position.budget, entry
	frappe.throw(
		_(
			"Source {0} has no active budget reservation. Finance must reconcile existing documents before continuing."
		).format(parent)
	)


def build_rows(doc):
	if doc.docstatus != 1 or (doc.doctype == "Procurement Request" and doc.status == "Rejected"):
		return None, []
	rows = []
	budgets = set()
	for row in doc.items:
		request = order = None
		linked = None
		if doc.doctype == "Procurement Request":
			if doc.currency != frappe.db.get_value("Company", doc.company, "default_currency"):
				frappe.throw(_("Procurement estimates must use the company currency."))
			budget = find_budget(doc.company, doc.department, doc.transaction_date)
			amount = number(row.qty) * (number(row.verified_rate) or number(row.estimated_rate))
			if amount <= 0:
				frappe.throw(
					_("Row {0}: a positive estimate is required before budget approval.").format(row.idx)
				)
			kind = "request"
			qty = number(row.qty)
		else:
			kind = "order" if doc.doctype == "Purchase Order" else "invoice"
			order = row.get("po_detail")
			mr_row = row.get("material_request_item")
			# Invoices mapped through a receipt still inherit its order/request lineage.
			if row.get("pr_detail"):
				receipt = frappe.db.get_value(
					"Purchase Receipt Item",
					row.pr_detail,
					["purchase_order_item", "material_request_item"],
					as_dict=True,
				)
				if receipt:
					order = order or receipt.purchase_order_item
					mr_row = mr_row or receipt.material_request_item
			if order:
				budget, linked = linked_position("order", order)
				request = linked.get("request")
			elif mr_row:
				request = frappe.db.get_value("Material Request Item", mr_row, "procurement_request_item")
				if request:
					budget, linked = linked_position("request", request)
			if doc.get("is_return"):
				if not row.get("purchase_invoice_item"):
					frappe.throw(
						_("Returns require the original purchase invoice item for budget attribution.")
					)
				budget, linked = linked_position("invoice", row.purchase_invoice_item)
				request, order = linked.get("request"), linked.get("order")
			if linked:
				if linked.get("item_code") and linked["item_code"] != row.item_code:
					frappe.throw(_("Row {0}: the budget source item cannot change.").format(row.idx))
				if row.uom == linked["uom"]:
					qty = number(row.qty)
				else:
					from erpnext.stock.get_item_details import get_conversion_factor

					factor = number(
						get_conversion_factor(row.item_code, linked["uom"]).get("conversion_factor")
					)
					if factor <= 0:
						frappe.throw(_("Missing budget UOM conversion."))
					qty = number(row.qty) * number(row.conversion_factor) / factor
			else:
				budget = find_budget(
					doc.company, row.get("budget_department"), doc.get("posting_date") or doc.transaction_date
				)
				qty = number(row.qty)
			amount = number(row.base_net_amount)
			if qty == 0 or (not doc.get("is_return") and (qty < 0 or amount < 0)):
				frappe.throw(_("Invalid quantity or amount for department budget control."))
			if doc.get("is_return") and (qty > 0 or amount > 0):
				frappe.throw(_("Budget returns must have negative quantities and amounts."))
			if frappe.db.get_value(BUDGET, budget, "company") != doc.company:
				frappe.throw(_("Budget and purchasing document must belong to the same company."))
		budgets.add(budget)
		rows.append(
			dict(
				kind=kind,
				row=row.name,
				amount=str(amount),
				qty=str(qty),
				request=request,
				order=order,
				uom=linked["uom"] if linked else row.uom,
				item_code=row.item_code,
				closed=doc.get("status") == "Closed",
				return_against=row.get("purchase_invoice_item") if doc.get("is_return") else None,
			)
		)
	if len(budgets) > 1:
		frappe.throw(_("Use separate purchasing documents for different department budgets."))
	return next(iter(budgets), None), rows


def sync_document(doc, method=None):
	key = f"{doc.doctype}:{doc.name}"
	previous = frappe.db.get_value(POSITION, {"source_key": key}, ["name", "budget", "payload"], as_dict=True)
	# Approval valuations are immutable even when procurement later verifies rates.
	if previous and doc.doctype == "Procurement Request" and doc.docstatus == 1:
		return
	budget_name, rows = build_rows(doc)
	if previous:
		if budget_name and budget_name != previous.budget:
			frappe.throw(
				_(
					"An existing budget commitment cannot move to another department or year. Cancel and amend it."
				)
			)
		budget_name = previous.budget
	if not budget_name:
		return
	budget = lock_budget(budget_name)
	if rows and not budget.ready and method != "register_existing":
		frappe.throw(
			_("Finance must reconcile opening spending and commitments before using this department budget.")
		)
	records = positions(budget_name, lock=True)
	previous = next((r for r in records if r.source_key == key), None)
	before_rows = portfolio(records)
	before = totals(before_rows)
	after_rows = portfolio([r for r in records if r.source_key != key]) + rows
	# Never orphan an active downstream commitment by cancelling its source.
	active_requests = {r["row"] for r in after_rows if r["kind"] == "request"}
	active_orders = {r["row"] for r in after_rows if r["kind"] == "order"}
	active_invoices = {r["row"] for r in after_rows if r["kind"] == "invoice"}
	for row in after_rows:
		if (
			(row.get("request") and row["request"] not in active_requests)
			or (row.get("order") and row["order"] not in active_orders)
			or (row.get("return_against") and row["return_against"] not in active_invoices)
		):
			frappe.throw(_("Cancel downstream budget documents before cancelling their source."))
	after = totals(after_rows)
	available = remaining(budget, before, lock=True)
	increase = sum(after.values()) - sum(before.values())
	if method == "register_existing" and budget.ready:
		frappe.throw(_("Disable approvals on this budget before registering opening documents."))
	if method != "register_existing" and increase > 0 and remaining(budget, after, lock=True) < 0:
		frappe.throw(
			_(
				"Department {0}: this action requires {1} {2} additional budget; {3} is available. Shortfall: {4}."
			).format(
				budget.department,
				budget.currency,
				f"{increase:,.2f}",
				f"{available:,.2f}",
				f"{-remaining(budget, after, lock=True):,.2f}",
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
				budget=budget_name,
				source_type=doc.doctype,
				source_name=doc.name,
				payload=payload,
			)
		).insert(ignore_permissions=True)
	frappe.get_doc(
		dict(
			doctype=MOVEMENT,
			budget=budget_name,
			source_type=doc.doctype,
			source_name=doc.name,
			**{k: str(after[k] - before[k]) for k in after},
			details=json.dumps(
				{"before": json.loads(previous.payload) if previous else [], "after": rows}, sort_keys=True
			),
		)
	).insert(ignore_permissions=True, ignore_links=True)


def request_summary(doc):
	frappe.has_permission(doc.doctype, "read", doc=doc, throw=True)
	# Department-wide financial information is reserved for approvers and Finance.
	if not (
		doc.approver == frappe.session.user and frappe.has_permission(doc.doctype, "submit", doc=doc)
	) and not set(frappe.get_roles()) & {"Accounts Manager", "Purchase Manager", "System Manager"}:
		return None
	position = frappe.db.get_value(
		POSITION, {"source_key": f"Procurement Request:{doc.name}"}, ["budget", "payload"], as_dict=True
	)
	name = (
		position.budget
		if position
		else frappe.db.get_value(
			BUDGET,
			{
				"company": doc.company,
				"department": doc.department,
				"start_date": ["<=", doc.transaction_date],
				"end_date": [">=", doc.transaction_date],
			},
			"name",
		)
	)
	if not name:
		return dict(missing=True, department=doc.department)
	budget = frappe.get_doc(BUDGET, name)
	amounts = totals(portfolio(positions(name)))
	available = remaining(budget, amounts)
	requested = (
		sum((number(r["amount"]) for r in json.loads(position.payload)), number(0))
		if position
		else number(doc.total_estimated_cost)
	)
	return dict(
		missing=False,
		inactive=not bool(budget.ready),
		name=name,
		department=budget.department,
		fiscal_year=budget.fiscal_year,
		currency=budget.currency,
		budget=float(allocation(budget)),
		**{k: float(v) for k, v in amounts.items()},
		available=float(available),
		request_amount=float(requested),
		after_approval=float(available if position else available - requested),
		already_reserved=bool(position),
	)


@frappe.whitelist()
def get_request_budget(name: str) -> dict | None:
	return request_summary(frappe.get_doc("Procurement Request", name))


class BudgetPurchaseOrderMixin:
	def update_status(self, status):
		super().update_status(status)
		sync_document(self)


@frappe.whitelist()
def get_budget_documents(request: str) -> list[dict]:
	"""Only expose supporting documents the current approver can actually read."""
	summary = get_request_budget(request)
	if not summary or summary.get("missing"):
		return []
	result = []
	for position in positions(summary["name"]):
		rows = json.loads(position.payload)
		if not rows:
			continue
		if not frappe.has_permission(position.source_type, "read", doc=position.source_name):
			continue
		result.append(
			dict(
				doctype=position.source_type,
				name=position.source_name,
				amount=float(sum((number(r["amount"]) for r in rows), number(0))),
			)
		)
	return result


def register_existing_documents(documents):
	"""Finance-only, bench execute helper for reviewed historical documents.

	Input: [{"doctype": "Procurement Request", "name": "..."}, ...].
	Call in request/order/invoice/return order. The entire batch is atomic.
	No fabricated estimates or inferred department assignments are introduced.
	"""
	frappe.only_for(["Accounts Manager", "System Manager"])
	affected = set()
	for reference in frappe.parse_json(documents):
		if reference["doctype"] not in ("Procurement Request", "Purchase Order", "Purchase Invoice"):
			frappe.throw(_("Unsupported budget source."))
		doc = frappe.get_doc(reference["doctype"], reference["name"])
		if doc.docstatus != 1:
			frappe.throw(_("Only submitted documents can be registered as opening commitments."))
		sync_document(doc, method="register_existing")
		name = frappe.db.get_value(POSITION, {"source_key": f"{doc.doctype}:{doc.name}"}, "budget")
		if name:
			affected.add(name)
	for name in sorted(affected):
		current = lock_budget(name)
		if remaining(current, totals(portfolio(positions(name, lock=True))), lock=True) < 0:
			frappe.throw(
				_(
					"Opening commitments exceed the allocation for {0}. Review the budget before importing."
				).format(current.department)
			)
	return {"registered": len(frappe.parse_json(documents))}
