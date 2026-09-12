# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""One line of a request, and how much of it has actually been ordered.

`ordered_qty`, `pending_qty` and `order_status` are virtual: they are counted
from the submitted Material Requests that point back at the row, every time the
row is read, and no column holds them. A stored copy would be one more thing to
keep true across submit, cancel, amend and a Material Request edited after the
fact -- and the moment it drifted, the request would quietly under- or
over-order.

The count is one small indexed query per row, so read a whole request's worth
through `get_ordered_qty_map` (one query for all its rows) rather than looping
over these properties.
"""

from frappe.model.document import Document
from frappe.utils import flt

OPEN = "Open"
PARTIALLY_ORDERED = "Partially Ordered"
ORDERED = "Ordered"


class ProcurementRequestItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.TextEditor | None
		estimated_amount: DF.Currency
		estimated_rate: DF.Currency
		item_code: DF.Link | None
		item_group: DF.Link | None
		item_name: DF.Data | None
		order_status: DF.Data | None
		ordered_qty: DF.Float
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		pending_qty: DF.Float
		preferred_supplier: DF.Link | None
		qty: DF.Float
		reference_url: DF.Data | None
		schedule_date: DF.Date | None
		uom: DF.Link
	# end: auto-generated types

	@property
	def ordered_qty(self) -> float:
		"""How much of this row submitted Material Requests already carry.

		Cached on the instance, not across the request: three virtual fields
		want the same number, and they should all be reading one answer taken
		at the moment the row was loaded.
		"""
		cached = self.__dict__.get("_ordered_qty")
		if cached is None:
			from tbsapp.tbs_app.doctype.procurement_request.procurement_request import (
				get_ordered_qty,
			)

			# An unsaved row has no name a Material Request could point at, so
			# there is nothing to count and nothing to ask the database.
			cached = self.__dict__["_ordered_qty"] = get_ordered_qty(self.name) if self.name else 0.0
		return cached

	@property
	def pending_qty(self) -> float:
		"""What is still to be ordered. Never negative: an over-ordered row is done."""
		return max(flt(self.qty) - self.ordered_qty, 0.0)

	@property
	def order_status(self) -> str:
		if self.ordered_qty <= 0:
			return OPEN
		return ORDERED if self.pending_qty <= 0 else PARTIALLY_ORDERED
