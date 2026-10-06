# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""An entry on the navigation rail: a named group of sidebars, or the stand-in
for an installed app.

What the rail makes of these, and of the sidebars none of them claims, is
`commons.better_navigation.navigation_apps`. This controller only refuses the
shapes that resolver could not give a stable answer for:

- an installed app that is not installed, or one another enabled record
  already stands for. The rail has one place for each app, so the second is
  refused and told which record has it;

- a module row with no sidebar, or a Category with no heading. A Category or
  Spacer row names no sidebar; one picked before the type was changed is
  dropped rather than left to claim it unseen;
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

from commons.better_navigation.navigation_apps import (
	APP,
	APP_SIDEBAR,
	MODULE,
	OTHER,
	SIDEBAR,
	SPACER,
	row_type,
)


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

		desktop_display: DF.Literal["Default", "Separate Icons", "One Icon"]
		enabled: DF.Check
		frontend_label: DF.Data | None
		frontend_url: DF.Data | None
		hidden: DF.Check
		icon: DF.Icon | None
		installed_app: DF.Autocomplete | None
		logo: DF.AttachImage | None
		rail_order: DF.Int
		roles: DF.Table[HasRole]
		sidebar_mode: DF.Literal["Add", "Replace"]
		sidebars: DF.Table[NavigationAppSidebar]
		title: DF.Data
	# end: auto-generated types

	def validate(self):
		self.validate_installed_app()
		self.validate_sidebars()
		self.warn_private_images()

	def validate_installed_app(self):
		self.installed_app = (self.installed_app or "").strip() or None
		if not self.installed_app:
			return
		# Checked only when it changes, so a record for an app since uninstalled
		# can still be saved (the rail ignores it until the app is back).
		if self.has_value_changed("installed_app") and self.installed_app not in installed_app_names():
			frappe.throw(_("{0} is not an installed app.").format(frappe.bold(self.installed_app)))
		if not self.enabled:
			return
		held = frappe.get_all(
			APP,
			filters={"enabled": 1, "installed_app": self.installed_app, "name": ["!=", self.name or ""]},
			pluck="name",
			limit=1,
		)
		if held:
			frappe.throw(
				_("{0} already stands for {1}. An installed app can have only one enabled record.").format(
					frappe.bold(held[0]), frappe.bold(self.installed_app)
				)
			)

	def validate_sidebars(self):
		for row in self.sidebars:
			row.type = row_type(row)
			if row.type == MODULE:
				if not row.sidebar:
					frappe.throw(_("Row {0}: pick a sidebar.").format(row.idx))
				continue
			row.sidebar = None
			row.desktop_image = None
			if row.type == SPACER:
				row.label = None
			elif not (row.label or "").strip():
				frappe.throw(_("Row {0}: a Category needs a label.").format(row.idx))

		seen = set()
		for row in self.modules():
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
		for row in self.modules():
			if row.sidebar in personal:
				frappe.throw(
					_("Row {0}: {1} is a personal sidebar and cannot be put on the rail.").format(
						row.idx, frappe.bold(row.sidebar)
					)
				)

		if not self.enabled:
			return
		held = claimed_elsewhere(self.name)
		for row in self.modules():
			if row.sidebar in held:
				frappe.throw(
					_("Row {0}: {1} is already in {2}. A sidebar can belong to only one app.").format(
						row.idx, frappe.bold(row.sidebar), frappe.bold(held[row.sidebar])
					)
				)

	def warn_private_images(self):
		"""Say so when a picture is a private file, which the rail and the Desktop cannot load.

		A warning, not a refusal: the record is still right, only its picture
		is missing until the file is made public.
		"""
		private = [
			_("Logo") if (self.logo or "").startswith("/private/") else None,
			*(
				_("Row {0}: Desktop Image").format(row.idx)
				for row in self.sidebars
				if (row.desktop_image or "").startswith("/private/")
			),
		]
		if private := [p for p in private if p]:
			frappe.msgprint(
				_("These are private files, so they will not show: {0}. Make each file public.").format(
					", ".join(private)
				),
				indicator="orange",
				alert=True,
			)

	def modules(self):
		"""The rows that are modules, not Categories or Spacers."""
		return [row for row in self.sidebars if row.sidebar]


def claimed_elsewhere(app: str | None) -> dict[str, str]:
	"""Every sidebar an enabled app other than `app` holds, and which app holds it."""
	others = frappe.get_all(APP, filters={"enabled": 1, "name": ["!=", app or ""]}, pluck="name")
	if not others:
		return {}
	rows = frappe.get_all(
		APP_SIDEBAR,
		filters={"parent": ["in", others], "parenttype": APP, "sidebar": ["is", "set"]},
		fields=["parent", "sidebar"],
		parent_doctype=APP,
	)
	return {row.sidebar: row.parent for row in rows}


def installed_app_names() -> list[str]:
	return [*frappe.get_installed_apps(), OTHER]


@frappe.whitelist()
def installed_app_options() -> list[dict]:
	"""What the Installed App field offers: each installed app by title, then Other."""
	frappe.has_permission(APP, "read", throw=True)
	from commons.better_navigation.navigation_apps import _app_meta

	meta = _app_meta()
	return [
		{"value": name, "label": (meta.get(name) or {}).get("title") or name}
		for name in installed_app_names()
	]
