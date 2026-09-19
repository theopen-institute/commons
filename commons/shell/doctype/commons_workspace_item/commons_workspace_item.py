"""One row of one workspace's sidebar.

Nothing is validated here. A row only means something in the order and the
company of the rest of its table -- whether the page it names is already in
another workspace, whether the heading above it groups it with the row before --
so every check is on the parent, in `CommonsWorkspace.validate_rows`.
"""

from frappe.model.document import Document


class CommonsWorkspaceItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		icon: DF.Data | None
		item_group: DF.Data | None
		item_type: DF.Literal["Page", "Self Service Record"]
		label: DF.Data | None
		page: DF.Literal["", "Announcements", "Leave Request", "Expense Claim", "Procurement"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		self_service_record: DF.Link | None
	# end: auto-generated types

	pass
