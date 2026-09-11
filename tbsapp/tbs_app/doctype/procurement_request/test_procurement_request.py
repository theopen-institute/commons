# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from tbsapp.tbs_app.doctype.procurement_request.procurement_request import make_material_request


class TestProcurementRequest(IntegrationTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.item = make_test_item()

	def make_request(self, items: list[dict], submit: bool = False) -> "frappe.Document":
		request = frappe.get_doc(
			{
				"doctype": "Procurement Request",
				"company": self.company,
				"purpose": "Purchase",
				"transaction_date": today(),
				"schedule_date": add_days(today(), 7),
				"items": items,
			}
		).insert()

		if submit:
			request.submit()

		return request

	def test_item_code_is_optional(self):
		request = self.make_request([{"item_name": "Brass fittings, 12mm", "qty": 4, "uom": "Nos"}])

		self.assertFalse(request.items[0].item_code)
		self.assertEqual(request.status, "Draft")

	def test_row_needs_a_name_of_some_kind(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_request([{"qty": 1, "uom": "Nos"}])

	def test_required_by_falls_back_to_the_parent(self):
		request = self.make_request([{"item_name": "Desk lamp", "qty": 1, "uom": "Nos"}])

		self.assertEqual(str(request.items[0].schedule_date), request.schedule_date)

	def test_required_by_cannot_precede_the_request(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_request(
				[
					{
						"item_name": "Desk lamp",
						"qty": 1,
						"uom": "Nos",
						"schedule_date": add_days(today(), -1),
					}
				]
			)

	def test_estimates_are_totalled(self):
		request = self.make_request(
			[
				{"item_name": "Desk lamp", "qty": 3, "uom": "Nos", "estimated_rate": 20},
				{"item_name": "Cable", "qty": 2, "uom": "Nos", "estimated_rate": 5},
			]
		)

		self.assertEqual(request.items[0].estimated_amount, 60)
		self.assertEqual(request.total_qty, 5)
		self.assertEqual(request.total_estimated_cost, 70)

	def test_submitting_approves_when_no_workflow_is_attached(self):
		request = self.make_request(
			[{"item_name": "Desk lamp", "qty": 1, "uom": "Nos"}], submit=True
		)

		self.assertEqual(request.status, "Approved")

	def test_material_request_needs_an_approved_source(self):
		request = self.make_request([{"item_code": self.item, "qty": 1, "uom": "Nos"}])

		with self.assertRaises(frappe.ValidationError):
			make_material_request(request.name)

	def test_material_request_needs_item_codes(self):
		request = self.make_request(
			[{"item_name": "Something not in the item master", "qty": 1, "uom": "Nos"}], submit=True
		)

		with self.assertRaises(frappe.ValidationError):
			make_material_request(request.name)

	def test_material_request_carries_the_request_over(self):
		request = self.make_request([{"item_code": self.item, "qty": 6, "uom": "Nos"}], submit=True)

		material_request = make_material_request(request.name)
		material_request.warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")
		material_request.schedule_date = add_days(today(), 7)
		for row in material_request.items:
			row.warehouse = material_request.warehouse
		material_request.insert()
		material_request.submit()

		self.assertEqual(material_request.material_request_type, "Purchase")
		self.assertEqual(material_request.procurement_request, request.name)
		self.assertEqual(material_request.items[0].procurement_request_item, request.items[0].name)

		request.reload()
		self.assertEqual(request.items[0].ordered_qty, 6)
		self.assertEqual(request.per_ordered, 100)
		self.assertEqual(request.status, "Ordered")

		# Cancelling the stock document hands the request back to the approver.
		material_request.cancel()
		request.reload()
		self.assertEqual(request.per_ordered, 0)
		self.assertEqual(request.status, "Approved")


def make_test_item() -> str:
	from erpnext.stock.doctype.item.test_item import make_item

	return make_item("_Test Procurement Item", {"is_stock_item": 1, "stock_uom": "Nos"}).name
