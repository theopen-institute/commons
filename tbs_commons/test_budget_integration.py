"""Run with bench --site SITE execute tbs_commons.test_budget_integration.run.

All fixtures and accounting mutations are rolled back; no test-site setting is changed.
"""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from tbs_commons import budget
from tbs_commons.budget_math import totals


class TestDepartmentBudget(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint("budget_test")
		self.company = frappe.db.get_value("Company", {}, "name")
		self.department = (
			frappe.get_doc(
				dict(
					doctype="Department",
					department_name="Budget test " + frappe.generate_hash(length=8),
					company=self.company,
				)
			)
			.insert()
			.name
		)
		year = frappe.db.get_value(
			"Fiscal Year",
			{"year_start_date": ["<=", today()], "year_end_date": [">=", today()], "disabled": 0},
			"name",
		)
		self.budget = frappe.get_doc(
			dict(
				doctype=budget.BUDGET,
				company=self.company,
				department=self.department,
				fiscal_year=year,
				budget_owner="Administrator",
				annual_amount=1000,
				ready=1,
			)
		).insert()
		self.enterContext(patch("frappe.model.document.Document.validate_workflow"))

	def tearDown(self):
		frappe.db.rollback(save_point="budget_test")

	def request(self, amount=400):
		return frappe.get_doc(
			dict(
				doctype="Procurement Request",
				company=self.company,
				department=self.department,
				transaction_date=today(),
				schedule_date=add_days(today(), 7),
				approver="Administrator",
				items=[dict(item_name="Budget test service", qty=4, uom="Nos", estimated_rate=amount / 4)],
			)
		).insert()

	def approve(self, request):
		request.status = "Approved"
		request.submit()
		return request

	def amounts(self):
		return totals(budget.portfolio(budget.positions(self.budget.name)))

	def test_approval_is_reserved_and_retry_is_idempotent(self):
		request = self.approve(self.request())
		self.assertEqual(self.amounts()["reserved"], 400)
		budget.sync_document(request)
		self.assertEqual(frappe.db.count(budget.MOVEMENT, {"budget": self.budget.name}), 1)
		self.assertEqual(budget.request_summary(request)["after_approval"], 600)

	def test_second_approval_cannot_exceed_remaining_balance(self):
		self.approve(self.request(700))
		second = self.request(400)
		frappe.db.savepoint("refused_approval")
		with self.assertRaises(frappe.ValidationError):
			self.approve(second)
		frappe.db.rollback(save_point="refused_approval")
		self.assertEqual(frappe.db.get_value("Procurement Request", second.name, "docstatus"), 0)
		self.assertEqual(self.amounts()["reserved"], 700)

	def test_historical_registration_requires_review_and_is_idempotent(self):
		request = self.approve(self.request())
		frappe.db.delete(budget.MOVEMENT, {"budget": self.budget.name})
		frappe.db.delete(budget.POSITION, {"budget": self.budget.name})
		self.budget.ready = 0
		self.budget.save()
		references = [{"doctype": request.doctype, "name": request.name}]
		budget.register_existing_documents(references)
		budget.register_existing_documents(references)
		self.assertEqual(self.amounts()["reserved"], 400)
		self.assertEqual(frappe.db.count(budget.MOVEMENT, {"budget": self.budget.name}), 1)

	def test_unreconciled_budget_blocks_new_approval(self):
		self.budget.ready = 0
		self.budget.save()
		with self.assertRaises(frappe.ValidationError):
			self.approve(self.request())

	def test_missing_budget_and_zero_estimate_block_approval(self):
		request = self.request(0)
		with self.assertRaises(frappe.ValidationError):
			self.approve(request)
		with self.assertRaises(frappe.ValidationError):
			budget.find_budget(self.company, "Unknown department", today())

	def test_cancellation_releases_reservation_and_writes_reversal(self):
		request = self.approve(self.request())
		request.cancel()
		self.assertEqual(self.amounts()["reserved"], 0)
		self.assertEqual(frappe.db.count(budget.MOVEMENT, {"budget": self.budget.name}), 2)

	def test_adjustments_cannot_reduce_below_commitments(self):
		self.approve(self.request(700))
		self.budget.append("adjustments", dict(amount=-400, reason="Too much"))
		with self.assertRaises(frappe.ValidationError):
			self.budget.save()

	def test_adjustments_are_append_only(self):
		self.budget.append("adjustments", dict(amount=100, reason="Additional allocation"))
		self.budget.save()
		self.budget.adjustments[0].amount = 200
		with self.assertRaises(frappe.ValidationError):
			self.budget.save()

	def test_rejection_does_not_reserve_budget(self):
		request = self.request()
		request.status = "Rejected"
		request.submit()
		self.assertEqual(self.amounts()["reserved"], 0)

	def test_approval_amount_does_not_change_with_verified_rate(self):
		request = self.approve(self.request())
		request.items[0].verified_rate = 200
		budget.sync_document(request)
		self.assertEqual(self.amounts()["reserved"], 400)

	def purchasing_fixture(self):
		item = frappe.get_doc(
			dict(
				doctype="Item",
				item_code="Budget-" + frappe.generate_hash(length=8),
				item_name="Budget test service",
				item_group=frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				stock_uom="Nos",
				is_stock_item=0,
				is_purchase_item=1,
			)
		).insert()
		supplier = frappe.get_doc(
			dict(
				doctype="Supplier",
				supplier_name="Budget-" + frappe.generate_hash(length=8),
				supplier_group=frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
				supplier_type="Company",
			)
		).insert()
		return item, supplier

	def test_real_partial_order_invoice_and_cancellations(self):
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
		from erpnext.stock.doctype.material_request.material_request import make_purchase_order

		from tbs_commons.tbs_commons.doctype.procurement_request.procurement_request import (
			make_material_request,
		)

		item, supplier = self.purchasing_fixture()
		request = self.request()
		request.items[0].item_code = item.name
		request.save()
		self.approve(request)
		mr = make_material_request(request.name)
		mr.insert().submit()
		po = make_purchase_order(mr.name)
		po.supplier = supplier.name
		po.items[0].qty = 2
		po.items[0].rate = 90
		po.insert().submit()
		self.assertEqual(self.amounts(), dict(reserved=200, committed=180, spent=0))
		invoice = make_purchase_invoice(po.name)
		invoice.items[0].qty = 1
		invoice.items[0].rate = 90
		invoice.insert().submit()
		self.assertEqual(self.amounts(), dict(reserved=200, committed=90, spent=90))
		po.reload()
		po.update_status("Closed")
		self.assertEqual(self.amounts(), dict(reserved=300, committed=0, spent=90))
		po.reload()
		po.update_status("Submitted")
		self.assertEqual(self.amounts(), dict(reserved=200, committed=90, spent=90))
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit = make_return_doc("Purchase Invoice", invoice.name)
		credit.insert().submit()
		self.assertEqual(self.amounts(), dict(reserved=200, committed=180, spent=0))
		credit.cancel()
		self.assertEqual(self.amounts(), dict(reserved=200, committed=90, spent=90))
		invoice.reload().cancel()
		self.assertEqual(self.amounts(), dict(reserved=200, committed=180, spent=0))
		po.reload().cancel()
		self.assertEqual(self.amounts(), dict(reserved=400, committed=0, spent=0))

	def test_direct_order_requires_department_and_enforces_limit(self):
		item, supplier = self.purchasing_fixture()
		po = frappe.get_doc(
			dict(
				doctype="Purchase Order",
				company=self.company,
				supplier=supplier.name,
				transaction_date=today(),
				schedule_date=add_days(today(), 7),
				items=[dict(item_code=item.name, qty=1, rate=1100, budget_department=self.department)],
			)
		).insert()
		frappe.db.savepoint("over_budget_order")
		with self.assertRaises(frappe.ValidationError):
			po.submit()
		frappe.db.rollback(save_point="over_budget_order")
		po.reload()
		po.items[0].rate = 500
		po.items[0].budget_department = None
		po.save()
		frappe.db.savepoint("missing_department_order")
		with self.assertRaises(frappe.ValidationError):
			po.submit()
		frappe.db.rollback(save_point="missing_department_order")
		po.reload()
		po.items[0].budget_department = self.department
		po.save().submit()
		self.assertEqual(self.amounts()["committed"], 500)

	def test_purchase_order_class_covers_close_reopen(self):
		from frappe.model.base_document import get_controller

		self.assertTrue(issubclass(get_controller("Purchase Order"), budget.BudgetPurchaseOrderMixin))


def run():
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		result = unittest.TextTestRunner(verbosity=2).run(
			unittest.defaultTestLoader.loadTestsFromTestCase(TestDepartmentBudget)
		)
		if not result.wasSuccessful():
			raise RuntimeError("Department budget integration tests failed")
		return dict(tests=result.testsRun, success=True)
	finally:
		frappe.db.rollback()
		frappe.set_user(original_user)
