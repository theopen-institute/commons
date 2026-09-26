# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""An entry on the navigation rail: a named group of sidebars.

What the rail makes of these, and of the sidebars none of them claims, is
`commons.better_navigation.navigation_apps`. This controller only refuses the
three shapes that resolver could not give a stable answer for:

- the same sidebar twice in one app, which would put it in the top menu twice;
- a personal sidebar (`for_user`), which is one person's and not the site's;
- a sidebar another enabled app already holds. The header has to say which app
  the page you are on belongs to, so the second claim is refused and told which
  app has it. A disabled app claims nothing, so this is checked only while
  enabled -- and again when a disabled one is switched back on.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from commons.better_navigation.navigation_apps import APP, APP_SIDEBAR, SIDEBAR


class NavigationApp(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.core.doctype.has_role.has_role import HasRole
		from frappe.types import DF

		from commons.better_navigation.doctype.navigation_app_sidebar.navigation_app_sidebar import (
			NavigationAppSidebar,
		)

		enabled: DF.Check
		frontend_label: DF.Data | None
		frontend_url: DF.Data | None
		icon: DF.Icon | None
		logo: DF.AttachImage | None
		rail_order: DF.Int
		roles: DF.Table[HasRole]
		sidebars: DF.Table[NavigationAppSidebar]
		title: DF.Data
	# end: auto-generated types

	def validate(self):
		self.validate_sidebars()

	def validate_sidebars(self):
		seen = set()
		for row in self.sidebars:
			if row.sidebar in seen:
				frappe.throw(
					_("Row {0}: {1} is already in this app.").format(row.idx, frappe.bold(row.sidebar))
				)
			seen.add(row.sidebar)

		personal = set()
		if seen:
			personal = set(
				frappe.get_all(
					SIDEBAR,
					filters={"name": ["in", list(seen)], "for_user": ["is", "set"]},
					pluck="name",
				)
			)
		for row in self.sidebars:
			if row.sidebar in personal:
				frappe.throw(
					_("Row {0}: {1} is a personal sidebar and cannot be put on the rail.").format(
						row.idx, frappe.bold(row.sidebar)
					)
				)

		if not self.enabled:
			return
		held = claimed_elsewhere(self.name)
		for row in self.sidebars:
			if row.sidebar in held:
				frappe.throw(
					_("Row {0}: {1} is already in {2}. A sidebar can belong to only one app.").format(
						row.idx, frappe.bold(row.sidebar), frappe.bold(held[row.sidebar])
					)
				)


def claimed_elsewhere(app: str | None) -> dict[str, str]:
	"""Every sidebar an enabled app other than `app` holds, and which app holds it."""
	others = frappe.get_all(APP, filters={"enabled": 1, "name": ["!=", app or ""]}, pluck="name")
	if not others:
		return {}
	rows = frappe.get_all(
		APP_SIDEBAR,
		filters={"parent": ["in", others], "parenttype": APP},
		fields=["parent", "sidebar"],
		parent_doctype=APP,
	)
	return {row.sidebar: row.parent for row in rows}
