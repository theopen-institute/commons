# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The Desktop laid out from the rail, over plain data."""

from unittest import TestCase

from commons.better_navigation.desktop import desktop_icons


def entry(key, title, sidebars=(), configured=False, frontend=None, logo=None):
	return {
		"key": key,
		"title": title,
		"logo": logo,
		"configured": configured,
		"frontend": frontend,
		"sidebars": [{"sidebar": name, "label": name, "icon": None} for name in sidebars],
	}


RAIL = [
	entry("navigation-app:OI", "OI", ["Members", "Courses"], configured=True),
	entry("app:frappe", "Frappe Framework", ["Users", "Build"], logo="/frappe.svg"),
	entry("app:education", "Education", ["Education"], logo="/edu.svg"),
	entry("app:helpdesk", "Helpdesk", ["Helpdesk"], frontend={"label": "Helpdesk app", "url": "/helpdesk"}),
	entry("app:Other", "Other", ["Actions", "Locked"]),
]
OPEN = {"items": [{"type": "Link"}]}
SIDEBAR_ITEMS = {
	name.lower(): OPEN
	for name in ("Members", "Courses", "Users", "Build", "Education", "Helpdesk", "Actions")
}
APP_LOOKS = {"frappe": {"label": "Framework", "logo_url": "/framework.svg"}}


def icons(rail=RAIL, **kwargs):
	kwargs.setdefault("looks", {"Members": {"bg_color": "blue"}})
	kwargs.setdefault("app_looks", APP_LOOKS)
	kwargs.setdefault("sidebar_items", SIDEBAR_ITEMS)
	return {icon.label: icon for icon in desktop_icons(rail, **kwargs)}


class TestDesktop(TestCase):
	def test_own_navigation_app_spreads_its_modules(self):
		result = icons()
		self.assertIsNone(result["Members"].parent_icon)
		self.assertEqual(result["Members"].link_to, "Members")
		self.assertEqual(result["Members"].bg_color, "blue")
		self.assertNotIn("OI", result)

	def test_installed_app_is_one_icon_over_its_modules(self):
		result = icons()
		self.assertEqual(result["Framework"].icon_type, "App")
		self.assertEqual(result["Framework"].logo_url, "/framework.svg")
		self.assertEqual(result["Users"].parent_icon, "Framework")
		self.assertEqual(result["Build"].parent_icon, "Framework")

	def test_one_destination_is_the_icon_itself(self):
		education = icons()["Education"]
		self.assertIsNone(education.parent_icon)
		self.assertEqual(education.icon_type, "App")
		self.assertEqual((education.link_type, education.link_to), ("Workspace Sidebar", "Education"))
		self.assertEqual(education.logo_url, "/edu.svg")

	def test_app_named_like_its_module_is_renamed(self):
		result = icons()
		self.assertEqual(result["Helpdesk"].parent_icon, "Helpdesk Modules")
		self.assertEqual(result["Helpdesk app"].parent_icon, "Helpdesk Modules")
		self.assertEqual(result["Helpdesk app"].link, "/helpdesk")

	def test_modules_the_user_cannot_open_are_left_out(self):
		result = icons()
		self.assertNotIn("Locked", result)
		# Other has one module left, so it goes straight there.
		self.assertIsNone(result["Actions"].parent_icon)

	def test_sidebar_opening_on_a_disabled_report_is_left_out(self):
		broken = {"items": [{"type": "Link", "link_type": "Report", "link_to": "Gone"}]}
		result = icons(sidebar_items={**SIDEBAR_ITEMS, "courses": broken})
		self.assertNotIn("Courses", result)
		self.assertIn("Members", result)

	def test_forbidden_frontend_is_left_out(self):
		result = icons(frontend_permitted=lambda app_name: app_name != "helpdesk")
		self.assertNotIn("Helpdesk app", result)
		self.assertIsNone(result["Helpdesk"].parent_icon)

	def test_labels_are_unique_and_order_follows_the_rail(self):
		rows = desktop_icons(RAIL, looks={}, app_looks=APP_LOOKS, sidebar_items=SIDEBAR_ITEMS)
		labels = [row.label for row in rows]
		self.assertEqual(len(labels), len(set(labels)))
		self.assertEqual(labels[:3], ["Members", "Courses", "Framework"])
		self.assertEqual([row.idx for row in rows], list(range(len(rows))))

	def test_bound_navigation_app_uses_its_own_title_and_logo(self):
		rail = [entry("app:frappe", "Admin", ["Users", "Build"], configured=True, logo="/mine.svg")]
		result = icons(rail)
		self.assertEqual(result["Users"].parent_icon, "Admin")
		self.assertEqual(result["Admin"].logo_url, "/mine.svg")
