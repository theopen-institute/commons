"""Isolated buying-rate and recoding checks; no running site is required."""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from tbs_commons.procurement.doctype.procurement_request import procurement_request as procurement


class TestBuyingRate(TestCase):
	def setUp(self):
		self.enterContext(patch("frappe.logger", return_value=logging.getLogger(__name__)))
		self.frappe = self.enterContext(patch.object(procurement, "frappe"))
		self.frappe.db.get_single_value.return_value = "Standard Buying"
		self.frappe.get_cached_doc.return_value = SimpleNamespace(
			enabled=1, buying=1, currency="USD", price_not_uom_dependent=0
		)
		self.frappe.get_cached_value.return_value = "Nos"
		self.price = self.frappe.get_all
		self.price.return_value = [SimpleNamespace(price_list_rate=24, uom="Box", valid_from=None, valid_upto=None)]
		self.exchange = self.enterContext(patch("erpnext.setup.utils.get_exchange_rate", return_value=2))

	def test_current_buying_price_uses_uom_and_currency(self):
		self.assertEqual(procurement.get_default_buying_price("ITEM", "NPR"), {"verified_rate": 48, "uom": "Box"})
		self.assertNotIn("uom", self.price.call_args.kwargs["filters"])
		self.exchange.assert_called_once_with("USD", "NPR", "2026-09-12", "for_buying")

	def test_expired_and_future_prices_are_skipped(self):
		valid = self.price.return_value[0]
		self.price.return_value = [
			SimpleNamespace(price_list_rate=99, uom="Case", valid_from="2026-10-01", valid_upto=None),
			SimpleNamespace(price_list_rate=88, uom="Pack", valid_from=None, valid_upto="2026-09-01"),
			valid,
		]
		self.assertEqual(procurement.get_default_buying_price("ITEM", "NPR"), {"verified_rate": 48, "uom": "Box"})

	def test_missing_price_clears_verified_rate(self):
		self.price.return_value = []
		self.assertEqual(procurement.get_default_buying_price("ITEM", "USD"), {"verified_rate": 0, "uom": "Nos"})
		self.exchange.assert_not_called()

	def test_missing_or_disabled_buying_list(self):
		self.frappe.db.get_single_value.return_value = None
		self.assertEqual(procurement.get_default_buying_price("ITEM", "USD"), {"verified_rate": 0, "uom": "Nos"})
		self.frappe.db.get_single_value.return_value = "Standard Buying"
		self.frappe.get_cached_doc.return_value.enabled = 0
		self.assertEqual(procurement.get_default_buying_price("ITEM", "USD"), {"verified_rate": 0, "uom": "Nos"})
		self.price.assert_not_called()

	def test_recoding_refreshes_rate_but_unchanged_item_keeps_manual_rate(self):
		row = SimpleNamespace(name="ROW", item_code="NEW", uom="Nos", qty=1, verified_rate=99)
		doc = object.__new__(procurement.ProcurementRequest)
		doc.__dict__.update(items=[row], currency="USD")
		doc._doc_before_save = SimpleNamespace(items=[SimpleNamespace(name="ROW", item_code="OLD")])
		with patch.object(procurement, "get_default_buying_price", return_value={"verified_rate": 24, "uom": "Box"}) as lookup:
			doc.set_verified_rates_for_changed_items()
			self.assertEqual(row.verified_rate, 24)
			self.assertEqual(row.uom, "Box")
			doc._doc_before_save.items[0].item_code = "NEW"
			row.verified_rate = 30
			doc.set_verified_rates_for_changed_items()
			self.assertEqual(row.verified_rate, 30)
			lookup.assert_called_once()

	def test_clearing_item_resets_verified_rate(self):
		self.assertEqual(procurement.get_default_buying_price(None, "USD"), {"verified_rate": 0, "uom": None})
		self.price.assert_not_called()

	def test_clearing_item_preserves_previous_uom(self):
		row = SimpleNamespace(name="ROW", item_code=None, uom="", qty=1, verified_rate=99)
		doc = object.__new__(procurement.ProcurementRequest)
		doc.__dict__.update(items=[row], currency="USD")
		doc._doc_before_save = SimpleNamespace(items=[SimpleNamespace(name="ROW", item_code="OLD", uom="Box")])
		doc.set_verified_rates_for_changed_items()
		self.assertEqual(row.uom, "Box")
		self.assertEqual(row.verified_rate, 0)

	def test_committed_quantity_is_converted_to_current_request_uom(self):
		query = MagicMock()
		for method in ("join", "on", "select", "where", "groupby"):
			getattr(query, method).return_value = query
		self.frappe.qb.from_.return_value = query
		query.run.return_value = [SimpleNamespace(procurement_request_item="ROW", stock_qty=24)]
		row = SimpleNamespace(name="ROW", item_code="ITEM", uom="Box")
		with patch("erpnext.stock.get_item_details.get_conversion_factor", return_value={"conversion_factor": 12}):
			self.assertEqual(procurement.get_committed_qty_map("PR", [row]), {"ROW": 2})
		row.uom = "Nos"
		with patch("erpnext.stock.get_item_details.get_conversion_factor", return_value={"conversion_factor": 1}):
			self.assertEqual(procurement.get_committed_qty_map("PR", [row]), {"ROW": 24})

	def test_unchanged_item_preserves_manual_uom_and_verified_rate(self):
		row = SimpleNamespace(name="ROW", item_code="ITEM", uom="Box", qty=1, verified_rate=99)
		doc = object.__new__(procurement.ProcurementRequest)
		doc.__dict__.update(items=[row], currency="USD")
		doc._doc_before_save = SimpleNamespace(items=[SimpleNamespace(name="ROW", item_code="ITEM", uom="Nos")])
		doc.set_verified_rates_for_changed_items()
		self.assertEqual((row.uom, row.verified_rate), ("Box", 99))
		self.price.assert_not_called()

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
