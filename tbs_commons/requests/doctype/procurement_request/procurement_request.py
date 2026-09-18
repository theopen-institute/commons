"""A request to buy something, raised and approved before any stock document exists.

A Material Request is a stock document. Submitting one moves `requested_qty` on
the bin, and every row has to name an `Item` that the item master already
carries. Neither suits the step that comes first, where someone says what they
need in their own words and an approver decides whether it is worth buying at
all.

So this doctype keeps the shape of a Material Request -- series, company, dated
item rows, submit and cancel -- and drops the consequences. It writes no stock
ledger entries, no bin quantities and no GL entries, and `item_code` is
optional: a row may carry nothing but a name, a quantity and a UOM. The
estimated cost fields exist for the approver and are posted nowhere.

Very little of that is enforced here, because very little of it has to be. The
DocType JSON carries the defaults, the `fetch_from` links into the item master
and the mandatory and non-negative checks. Whatever Workflow a site has built
carries who may do what and when -- including, if it is set up that way, the rule
that every row must have an `item_code` before a request can go for review.
Nothing here assumes one: a site with no Workflow, or one shaped differently, is
read rather than corrected -- see `tbs_commons.requests.procurement_workflow`.
Frappe itself
refuses every edit to an approved request's items, because no field on that
table is `allow_on_submit`, and refuses any cancellation that would orphan a
submitted Material Request. What is left in this file is arithmetic, and the
few rules none of them can state.

A request moves through the active Frappe Workflow: staff draft it, procurement
checks and codes it, its expense approver reviews it, and procurement fulfills
it. The `status` field is also the workflow state field.

Approval is what submits a request: every state before a decision is a draft,
and so is `Rejected`. `docstatus` 1 therefore means approved, and nothing has to
consult the name of a state to know it. A rejection is not the end of the road
either -- procurement can `Reopen` a turned-down request, which hands it back to
them at `Pending` with the old reason cleared off it.

Because approval is the spending decision, it is also where the department's
allocation has to hold: `on_submit` refuses a request whose outstanding estimate
no longer fits what the department has left. The arithmetic is the same one the
approver's budget banner shows, so the refusal never contradicts the readout it
sits next to. It lives in `tbs_commons.requests.budget` with everything else
that knows about allocations -- all this file decides is when to ask.

Once approved, `make_material_request` carries the request -- all of it, or the
rows and quantities the buyer picks -- onto a draft Material Request. That is
where the item master, the warehouse and the stock effects finally enter, and it
is deliberately the only place they do. A request can be converted repeatedly,
so a long list can be bought in instalments.

How much of a row has been ordered is never stored. `committed_qty` and
`uncommitted_qty` on the rows are virtual fields counted from the submitted
Material Requests that point back at them: they depend on other documents, so a
stored copy could drift. `total_estimated_cost` is virtual as well, for the
opposite reason -- it depends on nothing but this request's own rows, so summing
it on read is cheaper than keeping a column in step with them. Being virtual, it
answers to `as_dict()` and not to attribute access, and a list query drops it.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate

from tbs_commons.requests.budget import enforce_request_allocation

DOCTYPE = "Procurement Request"


class ProcurementRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from tbs_commons.requests.doctype.procurement_request_item.procurement_request_item import (
			ProcurementRequestItem,
		)

		amended_from: DF.Link | None
		approver: DF.Link
		approver_name: DF.Data | None
		company: DF.Link
		currency: DF.Link | None
		department: DF.Link
		item_summary: DF.Data | None
		items: DF.Table[ProcurementRequestItem]
		justification: DF.SmallText | None
		naming_series: DF.Literal["PRQ-.YYYY.-"]
		rejection_reason: DF.SmallText | None
		requested_by: DF.Link
		requester_name: DF.Data | None
		schedule_date: DF.Date
		status: DF.Data
		title: DF.Data | None
		total_estimated_cost: DF.Currency
		transaction_date: DF.Date
	# end: auto-generated types

	def validate(self) -> None:
		self.validate_quantities()
		self.validate_schedule_date()

	def on_submit(self) -> None:
		"""Refuse an approval the department's allocation cannot hold.

		Here rather than in `validate` because the check counts this request
		among the approved ones, which it only is once the submit has been
		written -- and because a draft is free to exceed a budget it has not yet
		asked anyone to spend.
		"""
		enforce_request_allocation(self)

	def validate_quantities(self) -> None:
		"""Refuse a row that asks for nothing.

		The DocField covers the rest: `reqd` stops an empty quantity and
		`non_negative` stops a negative one. Neither catches zero -- Frappe reads a
		Float's content as the string "0.0", which is truthy, and zero is not
		negative. Tested for equality rather than `<= 0` so a negative quantity
		still falls through to `non_negative` and raises `NonNegativeError`,
		which is the doctype's answer and not this one.
		"""
		for row in self.items:
			if flt(row.qty) == 0:
				frappe.throw(
					_("Row {0}: quantity must be greater than zero.").format(row.idx),
					frappe.ValidationError,
				)

	def validate_schedule_date(self) -> None:
		"""Refuse a required-by date that precedes the request itself.

		A cross-field comparison, so there is nowhere in the DocType JSON to
		declare it.
		"""
		if not self.schedule_date or not self.transaction_date:
			return
		if getdate(self.schedule_date) < getdate(self.transaction_date):
			frappe.throw(
				_("Required by cannot be before the request date {0}.").format(
					frappe.utils.formatdate(self.transaction_date)
				),
				frappe.ValidationError,
			)

	def onload(self) -> None:
		# `committed_qty` and `uncommitted_qty` are virtual, and Frappe resolves a
		# virtual field by calling its property once per row while serialising the
		# document. Left to itself that is one aggregate query per row every time
		# the form is opened, so fill them all from one query first.
		self.prime_committed_qty()

	def prime_committed_qty(self) -> None:
		"""Fill every row's committed quantity from one query instead of one each."""
		committed = get_committed_qty_map(self.name, self.items) if self.name else {}
		for row in self.items:
			row._committed_qty = flt(committed.get(row.name))

	@property
	def open_rows(self) -> list["ProcurementRequestItem"]:
		"""The rows with something still to order.

		Primed afresh on every call rather than reused: the cache lives on the row
		instance, so a request still in memory after a Material Request was
		submitted against it would otherwise report a balance that has already
		been spent, and let the same quantity be ordered twice.
		"""
		self.prime_committed_qty()
		return [row for row in self.items if row.uncommitted_qty > 0]


def get_conversion_factor(item_code: str, uom: str) -> float:
	"""Stock units per `uom`, refusing the zero a missing conversion returns."""
	from erpnext.stock.get_item_details import get_conversion_factor as erpnext_conversion_factor

	factor = flt(erpnext_conversion_factor(item_code, uom).get("conversion_factor"))
	if factor <= 0:
		frappe.throw(_("No UOM conversion is available for {0} in {1}.").format(item_code, uom))
	return factor


def get_committed_qty_map(procurement_requests: str | list[str], items=None) -> dict[str, float]:
	"""Committed stock quantities expressed in each request line's current UOM.

	Material Requests are counted in stock UOM, because the buyer may order a
	line in a different one than it was requested in. `items` is the rows to
	convert back, for a caller that is holding them already.
	"""
	names = [procurement_requests] if isinstance(procurement_requests, str) else list(procurement_requests)
	if not names:
		return {}

	mr_item = frappe.qb.DocType("Material Request Item")
	mr = frappe.qb.DocType("Material Request")
	rows = (
		frappe.qb.from_(mr_item)
		.join(mr)
		.on(mr_item.parent == mr.name)
		.select(mr_item.procurement_request_item, Sum(mr_item.stock_qty).as_("stock_qty"))
		.where((mr.docstatus == 1) & (mr_item.procurement_request.isin(names)))
		.groupby(mr_item.procurement_request_item)
	).run(as_dict=True)
	stock_quantities = {row.procurement_request_item: flt(row.stock_qty) for row in rows}
	if not stock_quantities:
		return {}

	if items is None:
		items = frappe.get_all(
			"Procurement Request Item",
			filters={"parent": ["in", names], "parenttype": DOCTYPE},
			fields=["name", "item_code", "uom"],
		)

	factors: dict[tuple[str, str], float] = {}
	committed = {}
	for row in items:
		if row.name not in stock_quantities:
			continue
		key = (row.item_code, row.uom)
		if key not in factors:
			factors[key] = get_conversion_factor(*key)
		committed[row.name] = stock_quantities[row.name] / factors[key]
	return committed


def _selection(source, selected_items: str | list | None) -> dict[str, float]:
	"""How much of which row to carry over, checked against what is open *now*.

	Returns row name -> quantity, the whole outstanding balance by default,
	which is what the plain "Create > Material Request" button should do. A
	quantity larger than what is left is trimmed rather than refused, and a row
	that is already fully ordered is dropped: two buyers working at once cannot
	order the same line twice either way, and the buyer adjusts the quantities
	on the Material Request form regardless.

	Which rows the desk's own tick boxes chose is not read here -- every open
	row is priced, and `get_mapped_doc` drops the unticked ones itself, from
	`frappe.flags.selected_children`.
	"""
	open_qty = {row.name: row.uncommitted_qty for row in source.open_rows}
	if not open_qty:
		frappe.throw(_("Every item on this request has already been ordered."))

	if isinstance(selected_items, str):
		selected_items = frappe.parse_json(selected_items)
	if not selected_items:
		return open_qty

	wanted: dict[str, float] = {}
	for entry in selected_items:
		remaining = flt(open_qty.get(entry.get("name")))
		qty = flt(entry.get("qty")) if entry.get("qty") is not None else remaining
		if remaining and qty > 0:
			wanted[entry["name"]] = min(qty, remaining)

	if not wanted:
		frappe.throw(_("Choose at least one item that still has something to order."))

	return wanted


@frappe.whitelist()
def make_material_request(
	source_name: str, target_doc: str | None = None, selected_items: str | list | None = None
) -> Document:
	"""Carry an approved Procurement Request onto a draft Material Request.

	Everything still outstanding comes over by default. Returned unsaved on
	purpose: this is where the stock rules start applying -- a stock item needs a
	warehouse, a UOM needs a conversion factor -- and the buyer trims the
	quantities and drops the rows they are not ordering yet on that form, before
	submitting it. Whatever they leave behind stays open here, because what has
	been ordered is counted from the Material Requests themselves.

	A caller that already knows what it wants can say so instead: `selected_items`
	is a list of `{"name": <request row>, "qty": <how many>}`. The desk's own row
	tick boxes arrive separately, in `frappe.flags.selected_children`. Either is
	checked against a live count of what submitted Material Requests carry.
	"""
	source = frappe.get_doc(DOCTYPE, source_name)
	frappe.has_permission(DOCTYPE, "read", doc=source, throw=True)

	if source.docstatus != 1:
		frappe.throw(
			_("Only an approved Procurement Request can become a Material Request. This one is {0}.").format(
				frappe.bold(_(source.status))
			)
		)

	wanted = _selection(source, selected_items)

	def update_item(source_row, target_row, source_parent) -> None:
		if not source_row.item_code:
			frappe.throw(
				_("Row {0} has no Item Code, which a Material Request needs on every row. Amend this request to set one, or tick just the coded rows you want to order.").format(
					source_row.idx
				),
				title=_("Item Code Missing"),
			)

		target_row.qty = wanted[source_row.name]
		target_row.schedule_date = source_parent.schedule_date
		target_row.stock_uom = frappe.db.get_value("Item", source_row.item_code, "stock_uom")
		target_row.conversion_factor = get_conversion_factor(source_row.item_code, source_row.uom)
		target_row.rate = flt(source_row.verified_rate) or flt(source_row.estimated_rate)
		target_row.stock_qty = flt(target_row.qty) * target_row.conversion_factor
		# A hint, not a decision: the item's own default warehouse if it has one,
		# otherwise the Material Request form asks.
		target_row.warehouse = frappe.db.get_value(
			"Item Default",
			{"parent": source_row.item_code, "company": source_parent.company},
			"default_warehouse",
		)

	return get_mapped_doc(
		DOCTYPE,
		source_name,
		{
			DOCTYPE: {
				"doctype": "Material Request",
				"field_map": {
					"name": "procurement_request",
				},
				# The Material Request is raised today, whenever the request was made.
				"field_no_map": ["transaction_date"],
				"validation": {"docstatus": ["=", 1]},
			},
			f"{DOCTYPE} Item": {
				"doctype": "Material Request Item",
				"field_map": {
					"name": "procurement_request_item",
					"parent": "procurement_request",
				},
				"postprocess": update_item,
				"condition": lambda row: row.name in wanted,
			},
		},
		target_doc,
	)
