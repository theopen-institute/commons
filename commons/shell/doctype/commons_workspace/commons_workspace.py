"""One named section of this app's navigation, and the rows in it.

The sidebar used to be a list written into `AppSidebar.vue` under a name written
into `data/apps.ts`: one workspace, called Staff Member, holding announcements,
the profile pages and the three request sections in that order. All of that is
this document now, and a site may have as many as it likes.

What a workspace is made of is deliberately narrow. A row points either at a
page this app ships -- the four in `commons.shell.pages` -- or at a
`Self Service Record`, which is itself configuration and already says what it is
called. Nothing else can be put in the sidebar, because nothing else is a page
this app has.

Two rules are enforced here, and both are about the sidebar being able to answer
a question it is asked constantly.

*A page or a record type sits in one workspace.* The header names the workspace
the page you are looking at belongs to, and the switcher takes you elsewhere; a
page in two workspaces has no answer to "which one am I in", and picking one
would make the answer depend on the order rows happened to come back in. So the
second workspace to claim a row is refused, and told which one has it.

*An icon has to be one this app can draw.* Same reason `Self Service Record`
holds its icon to a list: the classes are compiled from the names written down
in `commons.self_service.icons`, so anything outside it renders as an empty
square. Saying so on save is the only place anyone finds out before the sidebar
does.

Emptiness is not an error, though. A workspace whose every row has been dropped
-- because the record types it named were disabled -- resolves to nothing and is
simply not offered; see `workspaces._configured`. That is a state a site can
arrive at without doing anything wrong, and refusing to save it would not be.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from commons.shell import workspaces
from commons.shell.pages import PAGES


class CommonsWorkspace(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commons.shell.doctype.commons_workspace_item.commons_workspace_item import (
			CommonsWorkspaceItem,
		)

		enabled: DF.Check
		icon: DF.Data | None
		items: DF.Table[CommonsWorkspaceItem]
		logo: DF.Data | None
		nav_order: DF.Int
		title: DF.Data
	# end: auto-generated types

	def validate(self) -> None:
		self.validate_icon(self.icon)
		self.validate_rows()

	def validate_icon(self, icon: str | None, row: int | None = None) -> None:
		"""An icon the frontend cannot draw is refused, not stored."""
		from commons.self_service.icons import NAV_ICONS

		if not icon or icon in NAV_ICONS:
			return
		message = _("{0} is not an icon this sidebar can draw. Choose one of: {1}.").format(
			frappe.bold(icon), ", ".join(sorted(NAV_ICONS))
		)
		frappe.throw(_("Row {0}: {1}").format(row, message) if row else message)

	def validate_rows(self) -> None:
		"""Every row names something real, once, and nowhere else.

		"Nowhere else" is checked against the other enabled workspaces rather
		than against every workspace: a row in a workspace nobody is offered is
		not in the sidebar, so it is not claimed. Turning that workspace back on
		is where the clash actually appears, and that save is refused.
		"""
		taken = workspaces.claimed_elsewhere(self.name) if self.enabled else {}
		seen: dict[tuple[str, str], int] = {}

		for row in self.items:
			target = row.page if row.item_type == "Page" else row.self_service_record
			if not target:
				# `mandatory_depends_on` catches this on the form; a row built by
				# an import or a script gets the same answer here.
				frappe.throw(
					_("Row {0}: choose the {1} this row opens.").format(row.idx, _(row.item_type))
				)
			if row.item_type == "Page" and target not in PAGES:
				frappe.throw(
					_("Row {0}: {1} is not a page this app has. Choose one of: {2}.").format(
						row.idx, frappe.bold(target), ", ".join(PAGES)
					)
				)

			self.validate_icon(row.icon, row.idx)

			key = (row.item_type, target)
			if key in seen:
				frappe.throw(
					_("Row {0}: {1} is already row {2} of this workspace.").format(
						row.idx, frappe.bold(target), seen[key]
					)
				)
			seen[key] = row.idx

			holder = taken.get(key)
			if holder:
				frappe.throw(
					_(
						"Row {0}: {1} is already in the {2} workspace. A page belongs to one "
						"workspace, so that the sidebar can say which one you are in -- take it "
						"out of {2} first."
					).format(row.idx, frappe.bold(target), frappe.bold(holder))
				)
