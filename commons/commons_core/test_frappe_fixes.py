# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The stand-ins for broken Frappe endpoints hand Frappe's own function what it expects."""

from unittest import TestCase
from unittest.mock import patch


class SavePage(TestCase):
	def call(self, new_widgets):
		from commons.commons_core import frappe_fixes

		with patch("frappe.desk.doctype.workspace.workspace.save_page") as frappe_save_page:
			frappe_fixes.save_page(name="Stock", public="1", new_widgets=new_widgets, blocks="[]")
		return frappe_save_page.call_args.kwargs

	def test_json_text_becomes_a_dict(self):
		kwargs = self.call('{"chart": [{"name": "x"}]}')
		self.assertEqual(kwargs["new_widgets"], {"chart": [{"name": "x"}]})
		self.assertEqual((kwargs["name"], kwargs["public"], kwargs["blocks"]), ("Stock", "1", "[]"))

	def test_empty_text_becomes_an_empty_dict(self):
		self.assertEqual(self.call("{}")["new_widgets"], {})
		self.assertEqual(self.call("")["new_widgets"], {})

	def test_a_dict_passes_through(self):
		self.assertEqual(self.call({"card": []})["new_widgets"], {"card": []})
