"""Rollback-only integration suite: bench --site SITE execute tbs_commons.procurement.test_budget_integration.run."""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from tbs_commons.procurement import budget


class TestDepartmentBudget(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint("budget_test")
		self.company = frappe.db.get_value("Company", {}, "name")
		self.department = self.new_department()
		self.year = frappe.db.get_value(
			"Fiscal Year",
			{"year_start_date": ["<=", today()], "year_end_date": [">=", today()], "disabled": 0},
			"name",
		)
		self.budget = self.allocation()
		self.item = (
			frappe.get_doc(
				dict(
					doctype="Item",
					item_code="Budget-" + frappe.generate_hash(length=8),
					item_name="Budget test item",
					item_group=frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
					stock_uom="Nos",
					is_stock_item=1,
					is_purchase_item=1,
				)
			)
			.insert()
			.name
		)
		self.warehouse = frappe.db.get_value("Warehouse", {"company": self.company, "is_group": 0}, "name")
		self.enterContext(patch("frappe.model.document.Document.validate_workflow"))

	def tearDown(self):
		frappe.db.rollback(save_point="budget_test")

	def new_department(self):
		return (
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

	def allocation(self, amount=1000, department=None, submit=True, save=True):
		doc = frappe.get_doc(
			dict(
				doctype=budget.BUDGET,
				company=self.company,
				department=department or self.department,
				fiscal_year=self.year,
				budget_owner="Administrator",
				annual_amount=amount,
			)
		)
		if not save:
			return doc
		doc.insert()
		return doc.submit() if submit else doc

	def amendment(self, amount, **overrides):
		"""Cancel the active allocation and open its replacement as a draft."""
		self.budget.reload()
		if self.budget.docstatus == 1:
			self.budget.cancel()
		draft = frappe.copy_doc(self.budget)
		draft.amended_from = self.budget.name
		draft.annual_amount = amount
		draft.update(overrides)
		return draft

	def used(self):
		return budget.used_amount(self.budget)

	def request(self, amount=400, approve=True):
		doc = frappe.get_doc(
			dict(
				doctype="Procurement Request",
				company=self.company,
				department=self.department,
				transaction_date=today(),
				schedule_date=add_days(today(), 7),
				approver="Administrator",
				items=[dict(item_code=self.item, qty=4, uom="Nos", estimated_rate=amount / 4)],
			)
		).insert()
		if approve:
			doc.status = "Approved"
			doc.submit()
		return doc

	def mr(self, rate=100, qty=1, kind="Purchase", request=None, submit=True, department=True):
		if request:
			from tbs_commons.procurement.doctype.procurement_request.procurement_request import (
				make_material_request,
			)

			doc = make_material_request(
				request.name, selected_items=[{"name": request.items[0].name, "qty": qty}]
			)
			doc.material_request_type = kind
			doc.items[0].rate = rate
		else:
			doc = frappe.get_doc(
				dict(
					doctype="Material Request",
					material_request_type=kind,
					company=self.company,
					transaction_date=today(),
					schedule_date=add_days(today(), 7),
					items=[dict(item_code=self.item, qty=qty, uom="Nos", rate=rate)],
				)
			)
		if department:
			doc.department = self.department
		doc.set_warehouse = self.warehouse
		for row in doc.items:
			row.warehouse = self.warehouse
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def refuses(self, doc, method="submit"):
		"""Assert the call is rejected, and leave no partial write behind."""
		frappe.db.savepoint("refused")
		with self.assertRaises(frappe.ValidationError):
			getattr(doc, method)()
		frappe.db.rollback(save_point="refused")

	# --- the tally ----------------------------------------------------------

	def test_both_material_request_types_are_actual_usage(self):
		self.mr(rate=125, qty=2)
		self.mr(rate=75, qty=2, kind="Material Issue")
		self.assertEqual(self.used(), 400)

	def test_draft_material_request_does_not_count(self):
		self.mr(rate=2000, submit=False)
		self.assertEqual(self.used(), 0)

	def test_mr_submission_checks_live_remaining_balance_and_rolls_back(self):
		self.mr(rate=700)
		second = self.mr(rate=400, submit=False)
		self.refuses(second)
		self.assertEqual(frappe.db.get_value("Material Request", second.name, "docstatus"), 0)
		self.assertEqual(self.used(), 700)

	def test_cancellation_releases_usage_without_a_stored_reversal(self):
		doc = self.mr(rate=700)
		self.assertEqual(self.used(), 700)
		doc.cancel()
		self.assertEqual(self.used(), 0)
		# The request keeps its department, so the release stays attributable.
		self.assertEqual(
			frappe.db.get_value("Material Request", doc.name, "department"), self.department
		)

	def test_replaying_the_submit_hook_cannot_double_charge(self):
		doc = self.mr(rate=250)
		budget.charge_material_request(doc)
		doc.db_set("status", "Stopped")
		budget.charge_material_request(doc)
		self.assertEqual(self.used(), 250)
		doc.db_set("status", "Issued")
		budget.charge_material_request(doc)
		self.assertEqual(self.used(), 250)

	def test_submitted_rates_cannot_be_changed_or_refreshed(self):
		doc = self.mr(rate=250)
		doc.update_item_rates()
		self.assertEqual(self.used(), 250)
		doc.items[0].rate = 300
		self.refuses(doc, "save")

	def test_missing_department_and_zero_rate_block_mr_only(self):
		for kwargs in ({"department": False}, {"rate": 0}):
			self.refuses(self.mr(submit=False, **kwargs))

	# --- the allocation -----------------------------------------------------

	def test_draft_and_cancelled_allocations_do_not_authorize_requests(self):
		other = self.new_department()
		self.allocation(department=other, submit=False)
		doc = self.mr(submit=False)
		doc.department = other
		self.refuses(doc)
		self.budget.reload().cancel()
		self.refuses(self.mr(submit=False))

	def test_only_one_submitted_allocation_may_cover_a_period(self):
		self.refuses(self.allocation(save=False), "insert")

	def test_allocation_cannot_be_cut_below_what_is_already_charged(self):
		self.mr(rate=700)
		self.refuses(self.amendment(500), "insert")

	def test_amendment_keeps_usage_without_touching_the_requests(self):
		doc = self.mr(rate=700)
		modified = frappe.db.get_value("Material Request", doc.name, "modified")
		new = self.amendment(2000).insert()
		new.submit()
		# Attribution is derived, so the requests are neither rewritten nor stranded.
		self.assertEqual(budget.used_amount(new), 700)
		self.assertEqual(frappe.db.get_value("Material Request", doc.name, "modified"), modified)
		# The restated allocation is what the next request is measured against.
		self.mr(rate=1200)
		self.assertEqual(budget.used_amount(new), 1900)

	def test_a_fresh_allocation_inherits_the_periods_existing_usage(self):
		"""A budget declares an amount for a department and period; it does not own
		the requests. A replacement therefore sees what the period already carries."""
		self.mr(rate=700)
		self.budget.reload().cancel()
		replacement = self.allocation(2000)
		self.assertEqual(budget.used_amount(replacement), 700)

	def test_amendment_cannot_move_the_budget_to_another_department(self):
		self.refuses(self.amendment(2000, department=self.new_department()), "insert")

	def test_amendment_chain_records_the_supersession(self):
		new = self.amendment(2000).insert()
		new.submit()
		self.assertEqual(new.amended_from, self.budget.name)
		self.assertEqual(frappe.db.get_value(budget.BUDGET, self.budget.name, "docstatus"), 2)

	# --- provisional procurement -------------------------------------------

	def test_procurement_approval_is_provisional_even_over_budget(self):
		doc = self.request(1400)
		self.assertEqual(self.used(), 0)
		summary = budget.request_summary(doc)
		self.assertEqual(summary["provisional"], 1400)
		self.assertEqual(summary["available"], 1000)
		self.assertEqual(summary["projected_available"], -400)

	def test_procurement_approval_does_not_need_an_allocation_or_estimate(self):
		self.request(0)
		self.budget.reload().cancel()
		frappe.db.delete(budget.BUDGET, {"name": self.budget.name})
		self.assertTrue(budget.request_summary(self.request(400))["missing"])

	def test_draft_allocation_is_reported_as_inactive_not_missing(self):
		self.budget.reload().cancel()
		frappe.db.delete(budget.BUDGET, {"name": self.budget.name})
		self.allocation(submit=False)
		summary = budget.request_summary(self.request(400))
		self.assertFalse(summary["missing"])
		self.assertTrue(summary["inactive"])

	def test_mr_rate_replaces_only_covered_provisional_quantities(self):
		doc = self.request(400)
		mr = self.mr(rate=150, qty=2, request=doc, department=False)
		summary = budget.request_summary(doc.reload())
		self.assertEqual(mr.department, self.department)
		self.assertEqual(summary["used"], 300)
		self.assertEqual(summary["provisional"], 200)
		self.assertEqual(summary["projected_available"], 500)
		mr.cancel()
		summary = budget.request_summary(doc.reload())
		self.assertEqual(summary["used"], 0)
		self.assertEqual(summary["provisional"], 400)

	def test_drafts_rejections_and_cancellations_stay_out_of_the_projection(self):
		active = self.request(400)
		self.request(500, approve=False)
		rejected = self.request(600, approve=False)
		rejected.status = "Rejected"
		rejected.submit()
		self.request(700).cancel()
		self.assertEqual(budget.request_summary(active)["provisional"], 400)

	def test_uom_conversion_reduces_correct_provisional_quantity(self):
		item = frappe.get_doc("Item", self.item)
		item.append("uoms", {"uom": "Box", "conversion_factor": 2})
		item.save()
		doc = self.request(400)
		mr = self.mr(rate=150, qty=2, request=doc, submit=False)
		mr.items[0].update({"uom": "Box", "qty": 1, "conversion_factor": 2})
		mr.save().submit()
		self.assertEqual(self.used(), 150)
		self.assertEqual(budget.request_summary(doc.reload())["provisional"], 200)

	# --- historical attribution ---------------------------------------------

	def test_historical_attribution_is_idempotent(self):
		doc = self.mr(rate=400, department=False, submit=False)
		doc.db_set("docstatus", 1)
		self.assertEqual(self.used(), 0)
		refs = [{"doctype": "Material Request", "name": doc.name, "department": self.department}]
		budget.register_existing_documents(refs)
		budget.register_existing_documents(refs)
		self.assertEqual(self.used(), 400)

	def test_historical_attribution_cannot_overrun_the_allocation(self):
		doc = self.mr(rate=4000, department=False, submit=False)
		doc.db_set("docstatus", 1)
		with self.assertRaises(frappe.ValidationError):
			budget.register_existing_documents(
				[{"doctype": "Material Request", "name": doc.name, "department": self.department}]
			)

	# --- purchasing independence -------------------------------------------

	def test_po_and_pi_cannot_change_budget(self):
		from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
		from erpnext.stock.doctype.material_request.material_request import make_purchase_order

		# Non-stock item permits invoice testing without a receipt or stock movement.
		frappe.db.set_value("Item", self.item, "is_stock_item", 0)
		frappe.clear_document_cache("Item", self.item)
		doc = self.mr(rate=100, qty=2)
		supplier = frappe.get_doc(
			dict(
				doctype="Supplier",
				supplier_name="Budget-" + frappe.generate_hash(length=8),
				supplier_group=frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
				supplier_type="Company",
			)
		).insert()
		po = make_purchase_order(doc.name)
		po.supplier = supplier.name
		po.items[0].rate = 600
		po.insert().submit()
		invoice = make_purchase_invoice(po.name)
		invoice.insert().submit()
		self.assertEqual(self.used(), 200)
		invoice.cancel()
		po.reload().cancel()
		self.assertEqual(self.used(), 200)


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
