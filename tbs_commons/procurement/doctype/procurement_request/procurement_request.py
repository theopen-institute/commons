# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""A request to buy something, raised and approved before any stock document exists.

A Material Request is a stock document. Submitting one moves `requested_qty` on
the bin, and every row has to name an `Item` that the item master already
carries. Neither suits the step that comes first, where someone says what they
need in their own words and an approver decides whether it is worth buying at
all.

So this doctype keeps the shape of a Material Request -- series,
company, dated item rows, submit and cancel -- and drops the consequences. It
writes no stock ledger entries, no bin quantities and no GL entries, and
`item_code` is optional: a row may carry nothing but a name, a quantity and a
UOM. The estimated cost fields exist for the approver and are posted nowhere.

A request moves through the active Frappe Workflow: staff draft it, procurement
checks and codes it, its expense approver reviews it, and procurement fulfills
it. The `status` field is also the workflow state field.

Approval is what submits a request: every state before a decision is a draft,
and so is `Rejected`. `docstatus` 1 therefore means approved, and nothing has to
consult the name of a state to know it. A rejection is not the end of the road
either -- procurement can `Reopen` a turned-down request, which hands it back to
them at `Pending` with the old reason cleared off it.

Once approved, `make_material_request` carries the request -- all of it, or the
rows and quantities the buyer picks -- onto a draft Material Request. That is
where the item master, the warehouse and the stock effects finally enter, and it
is deliberately the only place they do. A request can be converted repeatedly,
so a long list can be bought in instalments.

How much of a row has been ordered is never stored. `committed_qty`,
`uncommitted_qty` on the rows, and `per_ordered` here, are virtual fields counted
from the submitted Material Requests that point back at them. `status` is not
derived here either: the Workflow owns it outright, and how much of a request has
actually been ordered is read from `per_ordered` rather than mirrored into a
state.
"""

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import Sum
from frappe.utils import comma_and, flt, get_link_to_form, getdate, today

DOCTYPE = "Procurement Request"

FALLBACK_UOM = "Nos"

# What a row takes from the item master when it is given an Item Code. None of
# them is editable after submission -- they describe what was approved.
FETCHED_FROM_ITEM = ("item_name", "item_group", "description")


# def _with_scheme(url: str) -> str:
# 	"""Prefix a bare host with https, so a pasted link passes URL validation.

# 	A `Data` field with options `URL` is validated by Frappe, and that check
# 	wants a scheme. Requesters paste what the address bar shows them, which
# 	increasingly hides it. Adding the prefix is kinder than throwing the row
# 	back over something we can fix ourselves.
# 	"""
# 	url = (url or "").strip()
# 	# Whitespace inside is the mark of something that was never a link. Left
# 	# alone it fails Frappe's check, which is the answer wanted here -- adding
# 	# a scheme to it would only turn a plain sentence into a passing "URL".
# 	if url and not url.startswith("/") and " " not in url and not urlparse(url).scheme:
# 		url = f"https://{url}"
# 	return url


class ProcurementRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from tbs_commons.procurement.doctype.procurement_request_item.procurement_request_item import ProcurementRequestItem

		amended_from: DF.Link | None
		approver: DF.Link
		approver_name: DF.Data | None
		company: DF.Link
		currency: DF.Link | None
		department: DF.Link
		items: DF.Table[ProcurementRequestItem]
		justification: DF.SmallText | None
		naming_series: DF.Literal["PRQ-.YYYY.-"]
		rejection_reason: DF.SmallText | None
		requested_by: DF.Link
		requester_name: DF.Data | None
		schedule_date: DF.Date
		status: DF.Literal["", "Draft", "Pending", "Under Review", "Rejected", "Approved", "Completed", "Canceled"]
		title: DF.Data | None
		total_estimated_cost: DF.Currency
		total_qty: DF.Float
		transaction_date: DF.Date
	# end: auto-generated types

	def validate(self) -> None:
		self.set_requester_defaults()
		self.validate_items()
		self.set_verified_rates_for_changed_items()
		self.validate_schedule_date()
		self.calculate_totals()
		self.set_title()

	def before_update_after_submit(self) -> None:
		self.validate_no_rows_added_or_removed()
		self.keep_the_stored_description()
		self.validate_item_code_changes()
		self.set_verified_rates_for_changed_items()
		self.validate_schedule_date()

	def on_update_after_submit(self) -> None:
		self.fill_in_from_item()

	def before_cancel(self) -> None:
		# Before, not `on_cancel`: post-save hooks fire after the row has already
		# been written, so a refusal there leaves docstatus 2 behind for anything
		# that does not roll the transaction back.
		self.validate_no_submitted_material_requests()

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
		# `tbs_commons.api.get_procurement_approvers` offers everyone who could
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

			# row.reference_url = _with_scheme(row.reference_url)

			if flt(row.qty) <= 0:
				frappe.throw(_("Row #{0}: Quantity must be greater than zero.").format(row.idx))

			if not row.uom:
				row.uom = (
					frappe.db.get_value("Item", row.item_code, "stock_uom")
					if row.item_code
					else default_uom
				)

	def validate_schedule_date(self) -> None:
		if self.schedule_date and getdate(self.schedule_date) < getdate(self.transaction_date):
			frappe.throw(_("Required By cannot be earlier than the Request Date."))

	def set_verified_rates_for_changed_items(self) -> None:
		"""Refresh defaults only on recoding; subsequent manual rate edits survive."""
		before = self.get_doc_before_save()
		previous = {row.name: row for row in before.items} if before else {}
		for row in self.items:
			old = previous.get(row.name)
			if (old.item_code if old else None) != (row.item_code or None):
				price = get_default_buying_price(row.item_code, self.currency)
				row.verified_rate = price["verified_rate"]
				if row.item_code and price["uom"]:
					row.uom = price["uom"]
				elif not row.item_code and old:
					row.uom = old.uom

	def validate_no_rows_added_or_removed(self) -> None:
		"""An approved request is a decision about a list of things. The list is closed.

		Frappe's metadata enforces this too. Keep the server check as protection
		for sites whose cached DocType has not yet been migrated.
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
		"""Defensively reject recoding a submitted row once it has been committed.

		The DocField is not editable after submit. This also protects existing
		sites whose metadata has not yet been migrated.
		"""
		ordered = get_committed_qty_map(self.name)
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
		self.total_qty = flt(sum(flt(row.qty) for row in self.items), self.precision("total_qty"))

	@property
	def total_estimated_cost(self) -> float:
		"""Current line costs, preferring a nonzero verified rate over the estimate."""
		return flt(
			sum(
				flt(row.qty) * (flt(row.verified_rate) or flt(row.estimated_rate))
				for row in self.get("items", [])
			),
			self.precision("total_estimated_cost"),
		)

	def set_title(self) -> None:
		if self.title:
			return

		named = [row.item_name or row.item_code for row in self.items[:3]]
		self.title = _("Request for {0}").format(", ".join(named))[:140]
	# -- live ordering state -------------------------------------------------

	def prime_committed_qty(self) -> None:
		"""Count every row's ordered quantity in one query instead of one each.

		The rows would each answer for themselves -- that is what makes the
		fields virtual -- but a whole request asked row by row is a query per
		line. This fills the same per-row cache from a single grouped read, and
		is called wherever the request is looked at as a whole.
		"""
		ordered = get_committed_qty_map(self.name, self.items) if self.name else {}

		for row in self.items:
			row.__dict__["_committed_qty"] = flt(ordered.get(row.name))

	@property
	def per_ordered(self) -> float:
		"""How much of the request submitted Material Requests carry, as a percentage.

		Virtual, like the row-level counts it is built from: nothing writes it,
		so nothing can leave it stale.
		"""
		requested = sum(flt(row.qty) for row in self.items)
		if not requested:
			return 0.0

		self.prime_committed_qty()
		# Capped per row: over-ordering one line does not cover another.
		covered = sum(min(row.committed_qty, flt(row.qty)) for row in self.items)
		return flt(covered / requested * 100, 2)

	@property
	def open_rows(self) -> list["ProcurementRequestItem"]:
		"""The rows with something still to order."""
		self.prime_committed_qty()
		return [row for row in self.items if row.uncommitted_qty > 0]
def get_default_buying_price(item_code: str | None, currency: str | None) -> dict:
	"""Return rate and UOM from the same current general buying Item Price."""
	from erpnext.setup.utils import get_exchange_rate

	result = {"verified_rate": 0.0, "uom": None}
	if not item_code:
		return result
	result["uom"] = frappe.get_cached_value("Item", item_code, "stock_uom")
	price_list = frappe.db.get_single_value("Buying Settings", "buying_price_list")
	if not price_list:
		return result
	price_list_doc = frappe.get_cached_doc("Price List", price_list)
	if not price_list_doc.enabled or not price_list_doc.buying:
		return result

	# Do not filter by the previous item's UOM: the selected price supplies it.
	prices = frappe.get_all(
		"Item Price",
		filters={
			"item_code": item_code,
			"price_list": price_list,
			"supplier": ["is", "not set"],
			"customer": ["is", "not set"],
			"batch_no": ["is", "not set"],
		},
		fields=["price_list_rate", "uom", "valid_from", "valid_upto"],
		order_by="valid_from desc, creation desc",
	)
	current_date = getdate(today())
	price = next(
		(p for p in prices if (not p.valid_from or getdate(p.valid_from) <= current_date)
		 and (not p.valid_upto or getdate(p.valid_upto) >= current_date)),
		None,
	)
	if price is None:
		return result
	result["uom"] = price.uom or result["uom"]
	if not price.price_list_rate:
		return result
	if not currency:
		frappe.throw(_("Select a request currency before fetching the buying price."))
	exchange_rate = get_exchange_rate(price_list_doc.currency, currency, today(), "for_buying")
	if not exchange_rate:
		frappe.throw(
			_("No buying exchange rate is available from {0} to {1}.").format(price_list_doc.currency, currency)
		)
	result["verified_rate"] = flt(price.price_list_rate) * flt(exchange_rate)
	return result


@frappe.whitelist()
def get_verified_buying_price(
	item_code: str,
	currency: str | None = None,
	request: str | None = None,
) -> dict:
	"""Rate and UOM preview for users creating or editing a procurement request."""
	if request:
		frappe.get_doc(DOCTYPE, request).check_permission("write")
	else:
		frappe.has_permission(DOCTYPE, "create", throw=True)
	frappe.has_permission("Item", "read", doc=item_code, throw=True)
	return get_default_buying_price(item_code, currency)


def get_committed_qty_map(procurement_requests: str | list[str], items=None) -> dict[str, float]:
	"""Committed stock quantities expressed in each request line's current UOM."""
	from erpnext.stock.get_item_details import get_conversion_factor

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

	committed = {}
	factors = {}
	for row in items:
		if row.name not in stock_quantities:
			continue
		key = (row.item_code, row.uom)
		if key not in factors:
			factors[key] = flt(get_conversion_factor(*key).get("conversion_factor"))
		factor = factors[key]
		if factor <= 0:
			frappe.throw(_("No UOM conversion is available for {0} in {1}.").format(*key))
		committed[row.name] = stock_quantities[row.name] / factor
	return committed


def get_committed_qty(procurement_request_item: str) -> float:
	"""Committed quantity of a saved line, in that line's UOM."""
	parent = frappe.db.get_value("Procurement Request Item", procurement_request_item, "parent")
	return get_committed_qty_map(parent).get(procurement_request_item, 0.0) if parent else 0.0
def _selection(source, selected_items: str | list | None) -> dict[str, float]:
	"""How much of which row to carry over, checked against what is open *now*.

	Returns row name -> quantity. With nothing selected the whole outstanding
	balance is taken, which is what the plain "Create > Material Request" button
	on a fresh request should do.
	"""
	open_qty = {row.name: row.uncommitted_qty for row in source.open_rows}
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

	# Approval is the submission, so `docstatus` is the whole test: the states
	# before a decision and `Rejected` are all drafts, and `Canceled` is 2. The
	# state name is read here only to say which one it is. A request that has
	# been ordered in full is turned away further down, by `_selection`.
	if source.docstatus != 1:
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
			_("A Material Request needs an Item Code on every row. Amend this request to set one on row {0}, or tick just the coded rows you want to order.").format(
				comma_and(uncoded)
			),
			title=_("Item Code Missing"),
		)

	def update_item(source_row, target_row, source_parent) -> None:
		from erpnext.stock.get_item_details import get_conversion_factor

		target_row.qty = wanted[source_row.name]
		target_row.schedule_date = source_parent.schedule_date
		target_row.stock_uom = frappe.db.get_value("Item", source_row.item_code, "stock_uom")
		target_row.conversion_factor = flt(
			get_conversion_factor(source_row.item_code, source_row.uom).get("conversion_factor")
		)
		if target_row.conversion_factor <= 0:
			frappe.throw(_("No UOM conversion is available for {0} in {1}.").format(source_row.item_code, source_row.uom))
		target_row.rate = flt(source_row.verified_rate) or flt(source_row.estimated_rate)
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
