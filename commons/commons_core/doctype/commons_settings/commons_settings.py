"""What this app calls itself on the site that runs it, and which of Frappe's
own behaviours it is allowed to change.

The second half is `commons.commons_core.settings.feature_enabled`. Each of
those is opt-in: a site gets core's behaviour until somebody ticks the box.

The title came first, because one thing was hard-coded: the sidebar said `Commons` under
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

		enable_bikram_sambat: DF.Check
		enable_home_page_priority: DF.Check
		enable_sidebar_memory: DF.Check
		enable_unencoded_at_in_routes: DF.Check
		enable_user_permission_gate: DF.Check
		title: DF.Data | None
	# end: auto-generated types

	pass
