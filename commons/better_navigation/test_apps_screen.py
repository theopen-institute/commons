# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The Apps screen's arrangement, over plain data: `arrange` rewrites `app_data` in place."""

from unittest import TestCase

from commons.better_navigation.apps_screen import HIDDEN, PER_MODULE, arrange


def rail_app(key, app_name, title, modules=(), mode=None, logo=None, frontend=None):
	return {
		"key": key,
		"app_name": app_name,
		"title": title,
		"logo": logo,
		"apps_screen": mode,
		"frontend": frontend,
		"modules": [{"shell": m, "label": m} for m in modules],
	}


def app_data():
	return [
		{
			"app_name": "erpnext",
			"app_title": "ERPNext",
			"app_logo_url": "/e.svg",
			"on_apps_screen": True,
			"sequence_id": 1,
			"dock": [{"link_type": "Sidebar", "link_to": "Stock"}],
		},
		{
			"app_name": "hrms",
			"app_title": "Frappe HR",
			"app_logo_url": None,
			"on_apps_screen": True,
			"sequence_id": 2,
			"dock": [],
		},
		{
			"app_name": "telephony",
			"app_title": "Telephony",
			"app_logo_url": None,
			"on_apps_screen": False,
			"sequence_id": 3,
			"dock": [],
		},
	]


def shown(data):
	return [
		(e["app_name"], e["app_title"])
		for e in sorted((e for e in data if e["on_apps_screen"]), key=lambda e: e["sequence_id"])
	]


class TestArrange(TestCase):
	def test_rail_order_one_icon_each_and_everything_else_off(self):
		data = app_data()
		arrange(data, [rail_app("app:hrms", "hrms", "People"), rail_app("app:erpnext", "erpnext", "ERPNext")])
		self.assertEqual(shown(data), [("hrms", "People"), ("erpnext", "ERPNext")])

	def test_hidden_has_no_tile(self):
		data = app_data()
		arrange(
			data,
			[
				rail_app("app:hrms", "hrms", "Frappe HR", mode=HIDDEN),
				rail_app("app:erpnext", "erpnext", "ERPNext"),
			],
		)
		self.assertEqual(shown(data), [("erpnext", "ERPNext")])

	def test_icon_per_module_with_frontend_first_and_pictures(self):
		data = app_data()
		oi = rail_app(
			"navigation-app:OI",
			"navigation-app:OI",
			"OI",
			modules=("Members", "Student Accounts"),
			mode=PER_MODULE,
			frontend={"label": "OI app", "url": "/commons"},
		)
		oi["modules"][0]["desktop_image"] = "/files/members.png"
		arrange(data, [oi])
		tiles = sorted((e for e in data if e["on_apps_screen"]), key=lambda e: e["sequence_id"])
		self.assertEqual([t["app_title"] for t in tiles], ["OI app", "Members", "Student Accounts"])
		self.assertEqual(tiles[0]["app_route"], "/commons")
		self.assertEqual(tiles[1]["app_logo_url"], "/files/members.png")
		# No Apps Screen Image: Frappe draws its letter.
		self.assertIsNone(tiles[2]["app_logo_url"])
		self.assertEqual(tiles[2]["dock"], [{"link_type": "Sidebar", "link_to": "Student Accounts"}])

	def test_an_app_frappe_does_not_know_gets_a_tile_opening_its_modules(self):
		data = app_data()
		arrange(
			data,
			[rail_app("navigation-app:OI", "navigation-app:OI", "OI", modules=("Members",), logo="/oi.svg")],
		)
		entry = next(e for e in data if e["app_name"] == "navigation-app:OI")
		self.assertEqual((entry["app_logo_url"], entry["on_apps_screen"]), ("/oi.svg", True))
		self.assertEqual(entry["dock"], [{"link_type": "Sidebar", "link_to": "Members"}])

	def test_a_known_apps_own_dock_is_left_alone(self):
		data = app_data()
		arrange(data, [rail_app("app:erpnext", "erpnext", "ERPNext", modules=("Accounts",))])
		self.assertEqual(data[0]["dock"], [{"link_type": "Sidebar", "link_to": "Stock"}])
