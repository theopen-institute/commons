"""The uninstall hook's checks and warnings: bench --site SITE run-tests --module commons.commons_core.test_uninstall

Nothing here uninstalls. Each test works inside a savepoint it rolls back, on
records it made itself, and calls the hook's parts rather than the hook.
"""

import contextlib
import io
import unittest
from unittest import TestCase
from unittest.mock import patch

import click
import frappe

from commons import testing
from commons.commons_core import uninstall

MARK = "Commons Uninstall Probe"


@testing.site_suite()
class TestUninstall(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("uninstall_test")
		self.modules = frappe.get_all("Module Def", filters={"app_name": "commons"}, pluck="name")
		self.doctypes = frappe.get_all("DocType", filters={"module": ("in", self.modules)}, pluck="name")

	def tearDown(self):
		frappe.db.rollback(save_point="uninstall_test")
		frappe.clear_cache(doctype="ToDo")

	def found(self) -> set[tuple[str, str]]:
		return {(dt, name) for dt, name, _ in uninstall.site_records(self.modules, self.doctypes)}

	def test_what_the_app_ships_is_not_the_sites(self):
		found = self.found()
		self.assertNotIn(("Report", "Open Payables"), found)
		self.assertNotIn(("Page", "commons-banking"), found)
		for record in uninstall.fixture_records():
			self.assertNotIn(record, found)

	def test_a_sites_print_format_in_an_app_module_is_found_and_refused(self):
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": MARK,
				"doc_type": "ToDo",
				"module": "Statement",
				"standard": "No",
				"print_format_type": "Jinja",
				"html": "<p></p>",
			}
		).insert()

		self.assertIn(("Print Format", MARK), self.found())
		with self.assertRaises(click.ClickException) as raised:
			uninstall.refuse_while_site_records(self.modules, self.doctypes)
		self.assertIn(MARK, raised.exception.message)

	def test_sidebars_naming_the_app_lose_the_app_not_the_sidebar(self):
		frappe.get_doc({"doctype": "Workspace Sidebar", "title": MARK, "app": "commons"}).insert()

		with contextlib.redirect_stdout(io.StringIO()):
			uninstall.keep_workspace_sidebars()

		self.assertTrue(frappe.db.exists("Workspace Sidebar", MARK))
		self.assertFalse(frappe.db.get_value("Workspace Sidebar", MARK, "app"))

	def tick(self) -> None:
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "ToDo",
				"role": "Accounts User" if frappe.db.exists("Role", "Accounts User") else "Guest",
				"read": 1,
				"require_user_permission": 1,
			}
		).insert()

	def warning(self, switched_on: bool) -> str:
		printed = io.StringIO()
		with (
			patch("commons.safer_permissions.permissions.gate_switched_on", return_value=switched_on),
			patch.object(click, "secho", side_effect=lambda text, **_: printed.write(text)),
		):
			uninstall.warn_gated_rules(self.doctypes)
		return printed.getvalue()

	def test_a_ticked_rule_is_warned_about_with_the_gate_on(self):
		self.tick()
		text = self.warning(switched_on=True)
		self.assertIn("access widens", text)
		self.assertIn("ToDo:", text)

	def test_a_ticked_rule_is_only_noted_with_the_gate_off(self):
		self.tick()
		text = self.warning(switched_on=False)
		self.assertNotIn("access widens", text)
		self.assertIn("ToDo:", text)

	def test_rules_on_the_apps_own_doctypes_are_not_warned_about(self):
		"""They are dropped with their doctypes, so nothing widens."""
		self.assertFalse(set(uninstall.gated_rules(self.doctypes)) & set(self.doctypes))


if __name__ == "__main__":
	unittest.main()
