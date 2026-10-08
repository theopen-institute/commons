# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The save-time warning about labels the rail will not use; no site records needed."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.better_navigation.doctype.navigation_app import navigation_app as controller


def row(idx, module, label=None):
	return SimpleNamespace(idx=idx, module=module, label=label)


class TestUnusedLabels(TestCase):
	def setUp(self):
		self.enterContext(
			patch.object(controller, "multi_shell_modules", return_value={"Quality Management"})
		)
		self.msgprint = self.enterContext(patch.object(controller.frappe, "msgprint"))

	def warn(self, *rows):
		doc = SimpleNamespace(sidebars=list(rows))
		doc.modules = lambda: controller.NavigationApp.modules(doc)
		controller.NavigationApp.warn_unused_labels(doc)

	def test_a_label_on_a_module_of_several_sidebars_is_warned_about(self):
		self.warn(row(1, "Stock", "Inventory"), row(2, "Quality Management", "QA"))
		self.msgprint.assert_called_once()
		message = self.msgprint.call_args.args[0]
		self.assertIn("Row 2", message)
		self.assertNotIn("Row 1", message)
		self.assertEqual(self.msgprint.call_args.kwargs["indicator"], "orange")

	def test_no_label_or_one_sidebar_says_nothing(self):
		self.warn(row(1, "Stock", "Inventory"), row(2, "Quality Management"), row(3, None, "Heading"))
		self.msgprint.assert_not_called()
