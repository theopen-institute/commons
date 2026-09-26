"""Isolated checks for the two helpers that do arithmetic; no running site needed.

`get_committed_qty_map` converts what has been ordered back into the unit the
request asked in, and `make_material_request` decides which rate carries over.
Both are pure enough to drive with mocks, which is why they are tested here
rather than against a site.
"""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.requests.doctype.procurement_request import procurement_request as procurement


class TestProcurementHelpers(TestCase):
	def setUp(self):
		self.enterContext(patch("frappe.logger", return_value=logging.getLogger(__name__)))
		self.frappe = self.enterContext(patch.object(procurement, "frappe"))
		self.frappe.get_cached_value.return_value = "Nos"

	def test_committed_quantity_is_converted_to_current_request_uom(self):
		# What has been ordered is the budget's answer (`budget.ordered_stock_qty`);
		# converting it back into the request's unit is this helper's.
		self.enterContext(patch.object(procurement, "ordered_stock_qty", return_value={"ROW": 24}))
		row = SimpleNamespace(name="ROW", item_code="ITEM", uom="Box")
		with patch("erpnext.stock.get_item_details.get_conversion_factor", return_value={"conversion_factor": 12}):
			self.assertEqual(procurement.get_committed_qty_map("PR", [row]), {"ROW": 2})
		row.uom = "Nos"
		with patch("erpnext.stock.get_item_details.get_conversion_factor", return_value={"conversion_factor": 1}):
			self.assertEqual(procurement.get_committed_qty_map("PR", [row]), {"ROW": 24})

	def test_material_request_uses_effective_rate_and_parent_date(self):
		row = SimpleNamespace(name="ROW", item_code="ITEM", uom="Box", estimated_rate=10, verified_rate=24)
		source = SimpleNamespace(docstatus=1, status="Approved", items=[row], schedule_date="2026-09-20", company="Company")
		self.frappe.get_doc.return_value = source
		target = SimpleNamespace()
		def map_document(doctype, name, mapping, target_doc):
			mapping["Procurement Request Item"]["postprocess"](row, target, source)
			return target
		with (
			patch.object(procurement, "_selection", return_value={"ROW": 2}),
			patch.object(procurement, "get_mapped_doc", side_effect=map_document),
			patch("erpnext.stock.get_item_details.get_conversion_factor", return_value={"conversion_factor": 12}),
		):
			procurement.make_material_request("PR")
			self.assertEqual((target.rate, target.stock_qty, target.schedule_date), (24, 24, "2026-09-20"))
			row.verified_rate = 0
			procurement.make_material_request("PR")
			self.assertEqual(target.rate, 10)
