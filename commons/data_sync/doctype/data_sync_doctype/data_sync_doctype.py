# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""One doctype that Data Sync compares, and how. See `commons.data_sync.rules`."""

from frappe.model.document import Document


class DataSyncDoctype(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		document_type: DF.Link
		filters: DF.Code | None
		ignored_fields: DF.SmallText | None
		key_fields: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
