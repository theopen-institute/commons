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

A request moves Draft -> Pending Approval -> Approved/Rejected. `status` sits
at permlevel 1 for the same reason Leave Application's does: the requester
reads it but cannot write it, so nobody approves their own spending. The two
transitions live in `tbsapp.api` alongside the leave ones, because a decision
is a status change *and* a submit and the pair has to be one transaction.

Once approved, `make_material_request` carries the request -- all of it, or the
rows and quantities the buyer picks -- onto a draft Material Request. That is
where the item master, the warehouse and the stock effects finally enter, and it
is deliberately the only place they do. A request can be converted repeatedly,
so a long list can be bought in instalments.

How much of a row has been ordered is never stored. `ordered_qty`, `pending_qty`
and `order_status` on the rows, and `per_ordered` here, are virtual fields
counted from the submitted Material Requests that point back at them. `status`
is the one derived value that *is* stored, because list views filter and sort on
it; the Material Request hook below refreshes it on submit and cancel, and it
recomputes itself from the same live count.
"""

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.model.workflow import get_workflow_name
from frappe.query_builder.functions import Sum
from frappe.utils import comma_and, flt, get_link_to_form, getdate

DOCTYPE = "Procurement Request"

# Sent, and waiting on the named approver. Still docstatus 0: nothing is
# decided until it is submitted.
PENDING_STATE = "Pending Approval"

# What a decision leaves behind, both submitted. Everything else on the
# `status` field is derived -- see `_derived_status`.
DECIDED_STATES = ("Approved", "Rejected")

# A request has to have cleared approval before it can become a Material
# Request, and a fully ordered one has nothing left to carry over.
ORDERABLE_STATES = ("Approved", "Partially Ordered")

FALLBACK_UOM = "Nos"

# What a row takes from the item master when it is given an Item Code. None of
# them is editable after submission -- they describe what was approved.
FETCHED_FROM_ITEM = ("item_name", "item_group", "description", "uom")


def _with_scheme(url: str) -> str:
	"""Prefix a bare host with https, so a pasted link passes URL validation.

	A `Data` field with options `URL` is validated by Frappe, and that check
	wants a scheme. Requesters paste what the address bar shows them, which
	increasingly hides it. Adding the prefix is kinder than throwing the row
	back over something we can fix ourselves.
	"""
	url = (url or "").strip()
	# Whitespace inside is the mark of something that was never a link. Left
	# alone it fails Frappe's check, which is the answer wanted here -- adding
	# a scheme to it would only turn a plain sentence into a passing "URL".
	if url and not url.startswith("/") and " " not in url and not urlparse(url).scheme:
		url = f"https://{url}"
	return url


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
		approver: DF.Link | None
		approver_name: DF.Data | None
		company: DF.Link
		currency: DF.Link | None
		department: DF.Link | None
		items: DF.Table[ProcurementRequestItem]
		justification: DF.SmallText | None
		letter_head: DF.Link | None
		naming_series: DF.Literal["PRQ-.YYYY.-"]
		per_ordered: DF.Percent
		purpose: DF.Literal["Purchase", "Material Transfer", "Material Issue", "Manufacture"]
		rejection_reason: DF.SmallText | None
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
		self.set_requester_defaults()
		self.validate_items()
		self.validate_schedule_date()
		self.calculate_totals()
		self.set_title()
		self.set_status()

	def before_update_after_submit(self) -> None:
		self.validate_no_rows_added_or_removed()
		self.keep_the_stored_description()
		self.validate_item_code_changes()
		self.validate_schedule_date()

	def on_update_after_submit(self) -> None:
		self.fill_in_from_item()

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

	def set_requester_defaults(self) -> None:
		"""Fill in what the requester's Employee record already knows."""
		if not self.requested_by:
			return

		employee = frappe.db.get_value(
			"Employee",
			{"user_id": self.requested_by, "status": "Active"},
			["department", "expense_approver"],
			as_dict=True,
		)
		if not employee:
			return

		if not self.department:
			self.department = employee.department

		# Procurement spend is approved by whoever approves this person's
		# expenses -- the budget holder either way -- so their existing
		# `expense_approver` is the default. It stays editable: the picker in
		# `tbsapp.api.get_procurement_approvers` offers everyone who could
		# actually decide, for the many employees who have none set.
		if not self.approver:
			self.approver = employee.expense_approver

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

			row.reference_url = _with_scheme(row.reference_url)

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

	def validate_no_rows_added_or_removed(self) -> None:
		"""An approved request is a decision about a list of things. The list is closed.

		`items` carries `allow_on_submit` so a row can still be given its Item
		Code after approval, and Frappe reads that as leave to add and remove
		rows too -- it skips `validate_update_after_submit` for new rows
		entirely. Nothing else in the request would catch a line added after the
		approver said yes, so it is caught here.
		"""
		before = set(self.submitted_rows())
		now = {row.name for row in self.items}

		if added := now - before:
			frappe.throw(
				_("{0} row(s) cannot be added to a request that has already been submitted. Amend it, or raise a new one.").format(
					len(added)
				),
				title=_("Items Are Fixed"),
			)

		if removed := before - now:
			frappe.throw(
				_("{0} row(s) cannot be removed from a request that has already been submitted. Amend it, or raise a new one.").format(
					len(removed)
				),
				title=_("Items Are Fixed"),
			)

	def keep_the_stored_description(self) -> None:
		"""Undo the form's link fetch on the fields that are closed after submit.

		Picking an Item Code in the desk fills `item_name` and the rest from the
		item master. On a submitted request that is the catalogue overwriting the
		requester's own words -- "Bespoke lab bench, 3m" becoming whatever the
		code happens to be called -- and the save would be refused anyway, for
		changing a field that is not editable on submit. So the stored values
		win, and whatever the item master can add to a *blank* one is filled in
		afterwards by `fill_in_from_item`.
		"""
		before = self.submitted_rows()

		for row in self.items:
			stored = before.get(row.name)
			if not stored:
				continue

			for field in FETCHED_FROM_ITEM:
				row.set(field, stored.get(field))

	def validate_item_code_changes(self) -> None:
		"""The Item Code stays editable after approval, up to the point it is ordered.

		Coding a row late is the point of the whole arrangement: a request may
		name something the item master has never heard of, and procurement puts
		the code on it when they get to it. Once a Material Request carries the
		row, though, the code is a statement about what was actually ordered,
		and changing it here would leave the two documents disagreeing.
		"""
		ordered = get_ordered_qty_map(self.name)
		before = self.submitted_rows()

		for row in self.items:
			was = (before.get(row.name) or frappe._dict()).item_code
			if (row.item_code or None) == (was or None):
				continue

			if flt(ordered.get(row.name)):
				frappe.throw(
					_("Row #{0}: {1} is already on a Material Request, so its Item Code cannot be changed. Cancel that Material Request first, or amend this request.").format(
						row.idx, frappe.bold(row.item_name or was)
					),
					title=_("Already Ordered"),
				)

			# Clearing the code is allowed: the row goes back to being something
			# the item master does not carry. It still has to say what it is,
			# which all but guarantees this -- `keep_the_stored_description` has
			# just put back the name the request was saved with, so only a row
			# stored without one at all can fail here.
			if not row.item_code and not row.item_name:
				frappe.throw(
					_("Row #{0}: Enter an Item Name before clearing the Item Code.").format(row.idx)
				)

	def submitted_rows(self) -> dict[str, frappe._dict]:
		"""Each row as the request was last written, straight from the table.

		Not `self.get_doc_before_save()`: that is the document as it was loaded,
		which for a form save is the same object the browser has been editing.
		This is what is actually stored.
		"""
		return {
			row.name: row
			for row in frappe.get_all(
				f"{DOCTYPE} Item",
				filters={"parent": self.name, "parenttype": self.doctype},
				fields=["name", "item_code", *FETCHED_FROM_ITEM],
			)
		}

	def fill_in_from_item(self) -> None:
		"""Fetch what a newly coded row left blank.

		Frappe's own `fetch_from` skips submitted documents unless the fetched
		field is itself editable on submit, and `item_name` and `item_group`
		should not be -- they describe what was approved. Written straight to
		the table for the same reason: these are the item master's answer, not
		an edit anybody made.
		"""
		for row in self.items:
			if not row.item_code:
				continue

			wanted = [field for field in ("item_name", "item_group") if not row.get(field)]
			if not wanted:
				continue

			values = frappe.db.get_value("Item", row.item_code, wanted, as_dict=True)
			for field in wanted:
				if values and values.get(field):
					row.db_set(field, values[field], update_modified=False)

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

		This never *decides* anything -- it only keeps the field consistent with
		the two things that are already true, docstatus and `per_ordered`, and
		otherwise leaves whatever the approval step wrote. If a Workflow is
		attached it owns the approval states outright.
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
			# A request always begins as a draft, whatever the caller sent.
			if self.is_new():
				return "Draft"

			# After that, the draft phase has two legitimate values of its own
			# and two more that pass through it: `decide_procurement_request`
			# writes the decision one save before it submits, so a decided
			# value has to survive here or it would be reset to Draft and the
			# submit would read as an approval nobody gave. What keeps a
			# requester out of all four is permlevel 1 on the field, not this.
			if self.status in (PENDING_STATE, *DECIDED_STATES):
				return None

			return "Draft"

		# Submitted. A decision recorded by `decide_procurement_request` stands;
		# a plain desk submit, with no decision behind it, is the approval.
		return self.status if self.status in DECIDED_STATES else "Approved"

	# -- live ordering state -------------------------------------------------

	def prime_ordered_qty(self) -> None:
		"""Count every row's ordered quantity in one query instead of one each.

		The rows would each answer for themselves -- that is what makes the
		fields virtual -- but a whole request asked row by row is a query per
		line. This fills the same per-row cache from a single grouped read, and
		is called wherever the request is looked at as a whole.
		"""
		ordered = get_ordered_qty_map(self.name) if self.name else {}

		for row in self.items:
			row.__dict__["_ordered_qty"] = flt(ordered.get(row.name))

	@property
	def per_ordered(self) -> float:
		"""How much of the request submitted Material Requests carry, as a percentage.

		Virtual, like the row-level counts it is built from: nothing writes it,
		so nothing can leave it stale.
		"""
		requested = sum(flt(row.qty) for row in self.items)
		if not requested:
			return 0.0

		self.prime_ordered_qty()
		# Capped per row: over-ordering one line does not cover another.
		covered = sum(min(row.ordered_qty, flt(row.qty)) for row in self.items)
		return flt(covered / requested * 100, 2)

	@property
	def open_rows(self) -> list["ProcurementRequestItem"]:
		"""The rows with something still to order."""
		self.prime_ordered_qty()
		return [row for row in self.items if row.pending_qty > 0]

	def update_order_status(self) -> None:
		"""Refresh the stored `status` after a Material Request moved.

		Only `status` is written: the quantities behind it are counted live, so
		there is nothing else left to keep in step.
		"""
		self.set_status(update=True)


def get_ordered_qty_map(procurement_requests: str | list[str]) -> dict[str, float]:
	"""Quantity per source row that submitted Material Requests already carry.

	One query for however many requests are asked about, keyed by the source row
	name. Rows nothing has ordered are absent rather than zero.
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
		.select(mr_item.procurement_request_item, Sum(mr_item.qty).as_("qty"))
		.where((mr.docstatus == 1) & (mr_item.procurement_request.isin(names)))
		.groupby(mr_item.procurement_request_item)
	).run(as_dict=True)

	return {row.procurement_request_item: flt(row.qty) for row in rows if row.procurement_request_item}


def get_ordered_qty(procurement_request_item: str) -> float:
	"""How much of one source row submitted Material Requests already carry.

	Behind `ProcurementRequestItem.ordered_qty`. Reading many rows this way is a
	query each -- use `get_ordered_qty_map` for a whole request.
	"""
	mr_item = frappe.qb.DocType("Material Request Item")
	mr = frappe.qb.DocType("Material Request")

	ordered = (
		frappe.qb.from_(mr_item)
		.join(mr)
		.on(mr_item.parent == mr.name)
		.select(Sum(mr_item.qty))
		.where((mr.docstatus == 1) & (mr_item.procurement_request_item == procurement_request_item))
	).run()

	return flt(ordered[0][0]) if ordered else 0.0


def update_linked_procurement_requests(doc, method: str | None = None) -> None:
	"""`Material Request` hook: keep the source request's ordered quantities honest.

	Registered in hooks.py for submit and cancel, the two events that change
	whether a Material Request counts. Drafts deliberately do not.
	"""
	names = {row.procurement_request for row in doc.get("items", []) if row.get("procurement_request")}

	for name in names:
		frappe.get_doc(DOCTYPE, name).update_order_status()


def _selection(source, selected_items: str | list | None) -> dict[str, float]:
	"""How much of which row to carry over, checked against what is open *now*.

	Returns row name -> quantity. With nothing selected the whole outstanding
	balance is taken, which is what the plain "Create > Material Request" button
	on a fresh request should do.
	"""
	open_qty = {row.name: row.pending_qty for row in source.open_rows}
	if not open_qty:
		frappe.throw(_("Every item on this request has already been ordered."))

	if isinstance(selected_items, str):
		selected_items = frappe.parse_json(selected_items)

	# The desk grid's own tick boxes, when the button was pressed with rows
	# selected and no explicit quantities given.
	if not selected_items and (ticked := (frappe.flags.selected_children or {}).get("items")):
		selected_items = [{"name": name} for name in ticked]

	if not selected_items:
		return open_qty

	wanted: dict[str, float] = {}
	for entry in selected_items:
		name = entry.get("name") if isinstance(entry, dict) else entry
		row = next((row for row in source.items if row.name == name), None)
		if not row:
			frappe.throw(_("{0} is not a row of this request.").format(frappe.bold(name)))

		qty = flt(entry.get("qty")) if isinstance(entry, dict) and entry.get("qty") is not None else None
		if qty == 0:
			# An explicit "not this time", not an error.
			continue

		remaining = flt(open_qty.get(name))
		if not remaining:
			frappe.throw(
				_("Row #{0} ({1}) has already been ordered in full.").format(row.idx, row.item_name or row.item_code)
			)

		if qty is None:
			qty = remaining
		elif qty < 0:
			frappe.throw(_("Row #{0}: Quantity to order cannot be negative.").format(row.idx))
		elif qty > remaining:
			frappe.throw(
				_("Row #{0}: only {1} of {2} is still to be ordered.").format(
					row.idx, frappe.bold(remaining), row.item_name or row.item_code
				)
			)

		wanted[name] = qty

	if not wanted:
		frappe.throw(_("Choose at least one item to order."))

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
	is a list of `{"name": <request row>, "qty": <how many>}`, and the desk's own
	row tick boxes arrive the same way. Either is checked against a live count of
	what submitted Material Requests already carry, so two buyers working at once
	cannot order the same line twice.
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

	wanted = _selection(source, selected_items)

	# The one thing a Procurement Request is allowed to omit is the one thing a
	# Material Request insists on. Only the rows actually being carried over
	# have to answer for it -- the rest can stay uncoded until their turn.
	uncoded = [str(row.idx) for row in source.items if row.name in wanted and not row.item_code]
	if uncoded:
		frappe.throw(
			_("A Material Request needs an Item Code on every row. Set one on row {0} -- it can be set on a submitted request -- or tick just the rows you want to order.").format(
				comma_and(uncoded)
			),
			title=_("Item Code Missing"),
		)

	def update_item(source_row, target_row, source_parent) -> None:
		from erpnext.stock.get_item_details import get_conversion_factor

		target_row.qty = wanted[source_row.name]
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
				"condition": lambda row: row.name in wanted,
			},
		},
		target_doc,
	)
