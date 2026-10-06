# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""One row of a Navigation App's top menu: a module (a Workspace Sidebar, and what to call
it), or a Category heading or a Spacer between them."""

from frappe.model.document import Document


class NavigationAppSidebar(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		desktop_image: DF.AttachImage | None
		label: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		sidebar: DF.Link | None
		type: DF.Literal["Sidebar", "Category", "Spacer"]
	# end: auto-generated types

	pass
