"""Install/migrate hooks: the app's icons on the desk.

The desk renders `Desktop Icon` *documents*, not the `add_to_apps_screen` hook.
Frappe seeds one icon per installed app at site install
(`create_desktop_icons_from_installed_apps`), taking only the first hook entry
and never revisiting it — so an app that wants two icons, or that changes its
title or route later, has to maintain those records itself.
"""

import frappe

APP = "tbsapp"

# The stale single icon Frappe seeds from the `app_title` hook. Replaced by the
# two below on the first migrate after this app grew a second section.
LEGACY_ICON_LABEL = "TBS App"

DESKTOP_ICONS = (
	{
		"label": "TBS Employees",
		"link": "/tbsapp/employees",
		"logo_url": "/assets/tbsapp/images/tbsapp-employees-logo.svg",
	},
	{
		"label": "TBS Leave",
		"link": "/tbsapp/leave",
		"logo_url": "/assets/tbsapp/images/tbsapp-leave-logo.svg",
	},
)


def after_install() -> None:
	sync_desktop_icons()


def after_migrate() -> None:
	sync_desktop_icons()


def sync_desktop_icons() -> None:
	"""Create or refresh this app's desk icons. Safe to run repeatedly."""
	_remove_legacy_icon()

	for index, spec in enumerate(DESKTOP_ICONS):
		existing = frappe.db.exists("Desktop Icon", spec["label"])
		if existing:
			icon = frappe.get_doc("Desktop Icon", existing)
		else:
			icon = frappe.new_doc("Desktop Icon")
			icon.label = spec["label"]
			# Only on create: a user who hid or reordered the icon keeps that.
			icon.idx = index
			icon.hidden = 0

		icon.link = spec["link"]
		icon.logo_url = spec["logo_url"]
		icon.link_type = "External"
		icon.icon_type = "App"
		icon.app = APP
		# Shipped by the app rather than owned by whoever ran the migrate, so
		# every user sees it — `get_desktop_icons` loads non-standard icons
		# only for their owner.
		icon.standard = 1
		icon.save(ignore_permissions=True)

	frappe.db.commit()
	_clear_icon_caches()


def _remove_legacy_icon() -> None:
	if not frappe.db.exists("Desktop Icon", LEGACY_ICON_LABEL):
		return

	# Only if it is the one Frappe made for this app — a user-made icon that
	# happens to share the label is theirs, not ours to delete.
	if frappe.db.get_value("Desktop Icon", LEGACY_ICON_LABEL, "app") != APP:
		return

	frappe.delete_doc("Desktop Icon", LEGACY_ICON_LABEL, ignore_permissions=True, force=True)


def _clear_icon_caches() -> None:
	"""Icons are cached per user, so a changed set is invisible until cleared."""
	from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache

	for user in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
		clear_desktop_icons_cache(user)
	frappe.clear_cache()
