# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""One line of a request, and how much of it has been committed.

`committed_qty` and `uncommitted_qty` are virtual: they are counted
from the submitted Material Requests that point back at the row, every time the
row is read, and no column holds them. A stored copy would be one more thing to
keep true across submit, cancel, amend and a Material Request edited after the
fact -- and the moment it drifted, the request would quietly under- or
over-order.

The count is one small indexed query per row, so read a whole request's worth
through `ProcurementRequest.prime_committed_qty`, which fills every row from one
query, rather than looping over these properties. A request loaded in the desk
primes itself in `onload`.
"""

from frappe.model.document import Document
from frappe.utils import flt


class ProcurementRequestItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.TextEditor | None
		estimated_rate: DF.Currency
		item_code: DF.Link | None
		item_name: DF.Data
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		qty: DF.Float
		reference_url: DF.Data | None
		uom: DF.Link
		verified_rate: DF.Currency
	# end: auto-generated types

	@property
	def committed_qty(self) -> float:
		"""How much Resources has committed through submitted Material Requests.

		Cached on the instance, not across the request: two virtual fields
		want the same number, and they should all be reading one answer taken
		at the moment the row was loaded.
		"""
		cached = getattr(self, "_committed_qty", None)
		if cached is None:
			from commons.requests.doctype.procurement_request.procurement_request import (
				get_committed_qty_map,
			)

			# An unsaved row has no name a Material Request could point at, so
			# there is nothing to count and nothing to ask the database.
			cached = self._committed_qty = (
				flt(get_committed_qty_map(self.parent, [self]).get(self.name)) if self.name else 0.0
			)
		return cached

	@property
	def uncommitted_qty(self) -> float:
		"""What is still to be committed, capped at zero."""
		return max(flt(self.qty) - self.committed_qty, 0.0)
