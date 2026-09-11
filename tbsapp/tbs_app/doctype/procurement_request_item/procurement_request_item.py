# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

from frappe.model.document import Document


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
		ordered_qty: DF.Float
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		preferred_supplier: DF.Link | None
		qty: DF.Float
		schedule_date: DF.Date | None
		uom: DF.Link
	# end: auto-generated types

	pass
