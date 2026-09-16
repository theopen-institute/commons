"""One field somebody has asked to have changed.

Nothing but storage. Which fieldnames are allowed, what the current value is and
whether the proposal is a change at all are all settled by the parent -- see
`RecordChangeRequest.validate` -- because none of them can be answered from a
row on its own, or without knowing which doctype the request refers to.
"""

from frappe.model.document import Document


class RecordChangeItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		current_value: DF.SmallText | None
		fieldname: DF.Data
		label: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		proposed_value: DF.SmallText | None
	# end: auto-generated types

	pass
