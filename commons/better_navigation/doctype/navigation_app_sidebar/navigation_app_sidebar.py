# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""One module in a Navigation App's top menu: a Workspace Sidebar, and what to call it."""

from frappe.model.document import Document


class NavigationAppSidebar(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		label: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		sidebar: DF.Link
	# end: auto-generated types

	pass
