# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""A request to buy something, raised and approved before any stock document exists.

A Material Request is a stock document. Submitting one moves `requested_qty` on
the bin, and every row has to name an `Item` that the item master already
carries. Neither suits the step that comes first, where someone says what they
need in their own words and an approver decides whether it is worth buying at
all.

So this doctype keeps the shape of a Material Request -- series, purpose,
company, dated item rows, submit and cancel -- and drops the consequences. It
writes no stock ledger entries, no bin quantities and no GL entries, and
`item_code` is optional: a row may carry nothing but a name, a quantity and a
UOM. The estimated cost fields exist for the approver and are posted nowhere.

Once approved, `make_material_request` carries the request onto a draft Material
Request. That is where the item master, the warehouse and the stock effects
finally enter, and it is deliberately the only place they do.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.model.workflow import get_workflow_name
from frappe.query_builder.functions import Sum
from frappe.utils import comma_and, flt, get_link_to_form, getdate

DOCTYPE = "Procurement Request"

# The states an approval step leaves behind. Everything else on the `status`
# field is derived -- see `_derived_status`.
APPROVAL_STATES = ("Pending Approval", "Approved", "Rejected")

# A request has to have cleared approval before it can become a Material
# Request, and a fully ordered one has nothing left to carry over.
ORDERABLE_STATES = ("Approved", "Partially Ordered")

FALLBACK_UOM = "Nos"


class ProcurementRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from tbsapp.tbs_app.doctype.procurement_request_item.procurement_request_item import (
			ProcurementRequestItem,
		)

		amended_from: DF.Link | None
		company: DF.Link
		department: DF.Link | None
		items: DF.Table[ProcurementRequestItem]
		justification: DF.SmallText | None
		letter_head: DF.Link | None
		naming_series: DF.Literal["PRQ-.YYYY.-"]
		per_ordered: DF.Percent
		purpose: DF.Literal["Purchase", "Material Transfer", "Material Issue", "Manufacture"]
		requested_by: DF.Link | None
		schedule_date: DF.Date | None
		select_print_heading: DF.Link | None
		status: DF.Literal[
			"",
			"Draft",
			"Pending Approval",
			"Approved",
			"Rejected",
			"Partially Ordered",
			"Ordered",
			"Cancelled",
		]
		title: DF.Data | None
		total_estimated_cost: DF.Currency
		total_qty: DF.Float
		transaction_date: DF.Date
	# end: auto-generated types

	def validate(self) -> None:
		self.validate_items()
		self.validate_schedule_date()
		self.calculate_totals()
		self.set_title()
		self.set_status()

	def before_update_after_submit(self) -> None:
		self.validate_schedule_date()

	def on_submit(self) -> None:
		self.set_status(update=True)

	def before_cancel(self) -> None:
		# Before, not `on_cancel`: post-save hooks fire after the row has already
		# been written, so a refusal there leaves docstatus 2 behind for anything
		# that does not roll the transaction back.
		self.validate_no_submitted_material_requests()

	def on_cancel(self) -> None:
		# `validate` does not run on cancel, and this fires after the write, so
		# the status has to be pushed down on its own.
		self.set_status(update=True)

	# -- validation ----------------------------------------------------------

	def validate_items(self) -> None:
		default_uom = frappe.db.get_single_value("Stock Settings", "stock_uom") or FALLBACK_UOM

		for row in self.items:
			if row.item_code and not row.item_name:
				row.item_name = frappe.db.get_value("Item", row.item_code, "item_name")

			# The whole point of the doctype: a row may describe something the
			# item master has never heard of. It still has to say *what*.
			if not (row.item_code or row.item_name):
				frappe.throw(
					_("Row #{0}: Enter an Item Code, or an Item Name for something not in the item master.").format(
						row.idx
					)
				)

			if flt(row.qty) <= 0:
				frappe.throw(_("Row #{0}: Quantity must be greater than zero.").format(row.idx))

			if not row.uom:
				row.uom = (
					frappe.db.get_value("Item", row.item_code, "stock_uom")
					if row.item_code
					else default_uom
				)

	def validate_schedule_date(self) -> None:
		for row in self.items:
			if not row.schedule_date:
				row.schedule_date = self.schedule_date

			if row.schedule_date and getdate(row.schedule_date) < getdate(self.transaction_date):
				frappe.throw(
					_("Row #{0}: Required By cannot be earlier than the Request Date.").format(row.idx)
				)

		if not self.schedule_date:
			dates = [row.schedule_date for row in self.items if row.schedule_date]
			self.schedule_date = min(dates) if dates else None

	def validate_no_submitted_material_requests(self) -> None:
		linked = frappe.get_all(
			"Material Request",
			filters={"procurement_request": self.name, "docstatus": 1},
			pluck="name",
		)
		if linked:
			frappe.throw(
				_("Cancel the Material Requests raised from this request first: {0}").format(
					comma_and([get_link_to_form("Material Request", name) for name in linked])
				),
				title=_("Linked Material Requests"),
			)

	# -- derived values ------------------------------------------------------

	def calculate_totals(self) -> None:
		for row in self.items:
			row.estimated_amount = flt(
				flt(row.qty) * flt(row.estimated_rate), row.precision("estimated_amount")
			)

		self.total_qty = flt(sum(flt(row.qty) for row in self.items), self.precision("total_qty"))
		self.total_estimated_cost = flt(
			sum(flt(row.estimated_amount) for row in self.items),
			self.precision("total_estimated_cost"),
		)

	def set_title(self) -> None:
		if self.title:
			return

		named = [row.item_name or row.item_code for row in self.items[:3]]
		self.title = _("{0} Request for {1}").format(_(self.purpose), ", ".join(named))[:140]

	def set_status(self, update: bool = False) -> None:
		status = self._derived_status()
		if not status or status == self.status:
			return

		if update:
			self.db_set("status", status, update_modified=False)
		else:
			self.status = status

	def _derived_status(self) -> str | None:
		"""The status this request should carry, or `None` to leave it alone.

		Approval is not this doctype's job. If a Workflow is attached it owns
		the states in `APPROVAL_STATES` and we only write the ordering ones on
		top; if none is, there is no approval step to speak of and submitting
		the document is the approval.
		"""
		if self.docstatus == 2:
			return "Cancelled"

		if flt(self.per_ordered) >= 100:
			return "Ordered"

		if flt(self.per_ordered) > 0:
			return "Partially Ordered"

		if get_workflow_name(self.doctype):
			# Nothing ordered any more (the Material Request was cancelled), so
			# hand the document back to the Workflow's own last approval state.
			return "Approved" if self.status in ("Ordered", "Partially Ordered") else None

		if self.docstatus == 0:
			return "Draft"

		return self.status if self.status in APPROVAL_STATES else "Approved"

	def update_ordered_qty(self) -> None:
		"""Recount how much of this request has reached a submitted Material Request."""
		ordered = get_ordered_qty_map(self.name)

		for row in self.items:
			qty = flt(ordered.get(row.name))
			if qty != flt(row.ordered_qty):
				row.db_set("ordered_qty", qty, update_modified=False)

		requested = sum(flt(row.qty) for row in self.items)
		# Capped per row: over-ordering one line does not cover another.
		covered = sum(min(flt(row.ordered_qty), flt(row.qty)) for row in self.items)

		self.db_set(
			"per_ordered",
			flt(covered / requested * 100, 2) if requested else 0,
			update_modified=False,
		)
		self.set_status(update=True)


def get_ordered_qty_map(procurement_request: str) -> dict[str, float]:
	"""Quantity per source row that submitted Material Requests already carry."""
	mr_item = frappe.qb.DocType("Material Request Item")
	mr = frappe.qb.DocType("Material Request")

	rows = (
		frappe.qb.from_(mr_item)
		.join(mr)
		.on(mr_item.parent == mr.name)
		.select(mr_item.procurement_request_item, Sum(mr_item.qty).as_("qty"))
		.where((mr.docstatus == 1) & (mr_item.procurement_request == procurement_request))
		.groupby(mr_item.procurement_request_item)
	).run(as_dict=True)

	return {row.procurement_request_item: flt(row.qty) for row in rows if row.procurement_request_item}


def update_linked_procurement_requests(doc, method: str | None = None) -> None:
	"""`Material Request` hook: keep the source request's ordered quantities honest.

	Registered in hooks.py for submit and cancel, the two events that change
	whether a Material Request counts. Drafts deliberately do not.
	"""
	names = {row.procurement_request for row in doc.get("items", []) if row.get("procurement_request")}

	for name in names:
		frappe.get_doc(DOCTYPE, name).update_ordered_qty()


@frappe.whitelist()
def make_material_request(source_name: str, target_doc: str | None = None) -> Document:
	"""Carry an approved Procurement Request onto a draft Material Request.

	Returned unsaved on purpose. This is where the stock rules start applying --
	a stock item needs a warehouse, a UOM needs a conversion factor -- and those
	belong on the Material Request form, so the original requester never had to
	know about them.
	"""
	source = frappe.get_doc(DOCTYPE, source_name)
	frappe.has_permission(DOCTYPE, "read", doc=source, throw=True)

	if source.docstatus != 1:
		frappe.throw(_("Submit the Procurement Request before raising a Material Request from it."))

	if source.status not in ORDERABLE_STATES:
		frappe.throw(
			_("Only an approved Procurement Request can become a Material Request. This one is {0}.").format(
				frappe.bold(_(source.status))
			)
		)

	# The one thing a Procurement Request is allowed to omit is the one thing a
	# Material Request insists on, so it has to be filled in before the handover.
	without_item_code = [str(row.idx) for row in source.items if not row.item_code]
	if without_item_code:
		frappe.throw(
			_("A Material Request needs an Item Code on every row. Set one on row {0}, or remove the row.").format(
				comma_and(without_item_code)
			),
			title=_("Item Code Missing"),
		)

	if not any(flt(row.qty) > flt(row.ordered_qty) for row in source.items):
		frappe.throw(_("Every item on this request has already been ordered."))

	def update_item(source_row, target_row, source_parent) -> None:
		from erpnext.stock.get_item_details import get_conversion_factor

		target_row.qty = flt(source_row.qty) - flt(source_row.ordered_qty)
		target_row.schedule_date = source_row.schedule_date or source_parent.schedule_date
		target_row.stock_uom = frappe.db.get_value("Item", source_row.item_code, "stock_uom")
		target_row.conversion_factor = (
			flt(get_conversion_factor(source_row.item_code, source_row.uom).get("conversion_factor")) or 1
		)
		target_row.stock_qty = flt(target_row.qty) * flt(target_row.conversion_factor)
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
					"purpose": "material_request_type",
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
					"estimated_rate": "rate",
				},
				"postprocess": update_item,
				"condition": lambda row: flt(row.qty) > flt(row.ordered_qty),
			},
		},
		target_doc,
	)
