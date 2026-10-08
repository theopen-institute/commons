# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""One row of a Navigation App's module list: a module (a Module Def), or a Category
heading or a Spacer between them.

A module row carries no name of its own: the rail calls a module what its sidebar
does, which a site changes with a `Custom Sidebar` (Edit Sidebar), so the module
reads the same on the rail, in the header and in the switcher."""

from frappe.model.document import Document


class NavigationAppModule(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		desktop_image: DF.AttachImage | None
		label: DF.Data | None
		module: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		type: DF.Literal["Module", "Category", "Spacer"]
	# end: auto-generated types

	pass
