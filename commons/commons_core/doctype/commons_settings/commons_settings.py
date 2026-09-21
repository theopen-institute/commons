"""What this app calls itself on the site that runs it.

One field, because one thing was hard-coded: the sidebar said `Commons` under
the workspace whatever the site was, and the browser tab said it too. That is a
name, and a name is the site's to choose -- an organisation running this app
does not necessarily call the thing its staff open "Commons".

The default lives in two places on purpose. Here as the field's default, so the
form opens filled in rather than blank; and in
`commons.commons_core.settings.DEFAULT_TITLE`, which is what answers for a site
whose Single has never been saved and therefore has no row to read at all.
"""

from frappe.model.document import Document


class CommonsSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		title: DF.Data | None
	# end: auto-generated types

	pass
