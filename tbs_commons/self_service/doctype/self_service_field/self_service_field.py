"""One field a self-service record type exposes, and on what terms.

Nothing but storage. Whether the fieldname exists, whether it may be proposed
and what it is called are all settled by the parent -- see
`SelfServiceRecord.validate` -- because none of them can be answered from a row
that does not know which doctype it belongs to.
"""

from frappe.model.document import Document


class SelfServiceField(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		fieldname: DF.Data
		free_text: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		proposable: DF.Check
		section: DF.Data
		viewable: DF.Check
	# end: auto-generated types

	pass
