# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The rail's rules, over plain data.

`resolve` takes everything it reads as arguments, so each rule in the module
docstring is one small table here: the fallback, the one-app rule, roles that
hide without releasing, and personal sidebars.
"""

from unittest import TestCase

from commons.better_navigation.navigation_apps import OTHER, installed_app_of, resolve

INSTALLED = ["frappe", "erpnext", "education", "commons"]
META = {
	"frappe": {"title": "Frappe Framework"},
	"erpnext": {"title": "ERPNext", "logo": "/erpnext.svg"},
	"education": {"title": "Education"},
	"commons": {"title": "Commons"},
}


def sidebar(name, app=None, module=None, for_user=None, header_icon=None):
	return {"name": name, "app": app, "module": module, "for_user": for_user, "header_icon": header_icon}


SIDEBARS = [
	sidebar("Users", app="frappe"),
	sidebar("Stock", app="erpnext", header_icon="package"),
	sidebar("Accounting", app="erpnext"),
	sidebar("Education", app="education"),
	# Made on the site: no app, so its module or a Desktop Icon has to say.
	sidebar("Students", module="Education"),
	sidebar("Assessments", module="Education Extensions"),
	sidebar("Helpdesk"),
	sidebar("Mine", for_user="peter@example.com"),
]
MODULES = {"Education": "education", "Education Extensions": "commons"}
ICONS = {"Helpdesk": "helpdesk"}


def rail(configured=(), user="someone@example.com", roles=("Desk User",), sidebars=SIDEBARS):
	return resolve(
		configured=list(configured),
		sidebars=sidebars,
		installed_apps=INSTALLED,
		app_meta=META,
		module_apps=MODULES,
		icon_apps=ICONS,
		user=user,
		user_roles=set(roles),
	)


def app(name, *sidebars, roles=(), icon=None, labels=None):
	labels = labels or {}
	return {
		"name": name,
		"title": name,
		"icon": icon,
		"logo": None,
		"roles": list(roles),
		"sidebars": [{"sidebar": s, "label": labels.get(s)} for s in sidebars],
	}


def shape(result):
	return [(entry["title"], [s["sidebar"] for s in entry["sidebars"]]) for entry in result]


class TestFallback(TestCase):
	def test_nothing_configured_is_one_entry_per_installed_app(self):
		self.assertEqual(
			shape(rail()),
			[
				("Frappe Framework", ["Users"]),
				("ERPNext", ["Accounting", "Stock"]),
				("Education", ["Education", "Students"]),
				("Commons", ["Assessments"]),
				# Helpdesk's icon names an app this site does not run.
				(OTHER, ["Helpdesk"]),
			],
		)

	def test_installed_apps_are_marked_and_keyed_apart_from_configured_ones(self):
		entry = rail()[1]
		self.assertEqual(entry["key"], "app:erpnext")
		self.assertFalse(entry["configured"])
		self.assertEqual(entry["logo"], "/erpnext.svg")

	def test_which_app_a_sidebar_belongs_to(self):
		self.assertEqual(installed_app_of(sidebar("A", app="erpnext", module="Education"), MODULES, ICONS), "erpnext")
		self.assertEqual(installed_app_of(sidebar("A", module=" Education "), MODULES, ICONS), "education")
		self.assertEqual(installed_app_of(sidebar("Helpdesk"), MODULES, ICONS), "helpdesk")
		self.assertIsNone(installed_app_of(sidebar("Nowhere"), MODULES, ICONS))


class TestConfigured(TestCase):
	def test_configured_apps_come_first_and_keep_their_order(self):
		result = rail([app("Finance", "Accounting", "Stock"), app("School", "Students", "Assessments")])
		self.assertEqual(
			shape(result),
			[
				("Finance", ["Accounting", "Stock"]),
				("School", ["Students", "Assessments"]),
				("Frappe Framework", ["Users"]),
				# Emptied by the claims above, so gone rather than drawn empty.
				("Education", ["Education"]),
				(OTHER, ["Helpdesk"]),
			],
		)
		self.assertEqual(result[0]["key"], "navigation-app:Finance")
		self.assertTrue(result[0]["configured"])

	def test_label_overrides_the_sidebar_title(self):
		entry = rail([app("Finance", "Accounting", labels={"Accounting": "Books"})])[0]
		self.assertEqual(entry["sidebars"][0], {"sidebar": "Accounting", "label": "Books", "icon": None})

	def test_first_claim_wins(self):
		result = rail([app("Finance", "Stock"), app("Warehouse", "Stock", "Accounting")])
		self.assertEqual(shape(result)[:2], [("Finance", ["Stock"]), ("Warehouse", ["Accounting"])])

	def test_an_app_with_nothing_left_is_dropped(self):
		result = rail([app("Gone", "Deleted Sidebar")])
		self.assertNotIn("Gone", [entry["title"] for entry in result])

	def test_roles_hide_the_app_without_releasing_its_sidebars(self):
		result = rail([app("Finance", "Accounting", "Stock", roles=["Accounts User"])])
		self.assertNotIn("Finance", [entry["title"] for entry in result])
		# Not back under ERPNext either: the restriction would only have moved them.
		self.assertNotIn("ERPNext", [entry["title"] for entry in result])

		allowed = rail([app("Finance", "Accounting", roles=["Accounts User"])], roles=["Accounts User"])
		self.assertEqual(allowed[0]["title"], "Finance")


class TestPersonal(TestCase):
	def test_personal_sidebar_only_for_its_owner(self):
		def other_entry(result):
			return next(entry for entry in result if entry["title"] == OTHER)["sidebars"]

		self.assertEqual([s["sidebar"] for s in other_entry(rail())], ["Helpdesk"])
		self.assertEqual(
			[s["sidebar"] for s in other_entry(rail(user="peter@example.com"))], ["Helpdesk", "Mine"]
		)

	def test_personal_sidebar_cannot_be_claimed(self):
		result = rail([app("Mine Too", "Mine")], user="peter@example.com")
		self.assertNotIn("Mine Too", [entry["title"] for entry in result])
