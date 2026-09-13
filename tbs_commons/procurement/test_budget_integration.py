"""Rollback-only integration suite: bench --site SITE execute tbs_commons.test_budget_integration.run."""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from tbs_commons.procurement import budget
from tbs_commons.procurement.budget_math import totals


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
		self.budget = (
			frappe.get_doc(
				dict(
					doctype=budget.BUDGET,
					company=self.company,
					department=self.department,
					budget_mode="Cumulative Material Requests",
					from_fiscal_year=year,
					to_fiscal_year=year,
					budget_owner="Administrator",
					budget_amount=1000,
					ready=1,
				)
			)
			.insert()
			.submit()
		)
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
			doc.budget_department = self.department
		doc.set_warehouse = self.warehouse
		for row in doc.items:
			row.warehouse = self.warehouse
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def used(self):
		return totals(budget.portfolio(budget.positions(self.budget.name)))["used"]

	def test_procurement_approval_is_provisional_even_over_budget(self):
		doc = self.request(1400)
		self.assertEqual(self.used(), 0)
		self.assertEqual(frappe.db.count(budget.POSITION, {"budget": self.budget.name}), 0)
		summary = budget.request_summary(doc)
		self.assertEqual(summary["provisional"], 1400)
		self.assertEqual(summary["available"], 1000)
		self.assertEqual(summary["projected_available"], -400)

	def test_procurement_approval_does_not_need_ready_budget_or_estimate(self):
		self.budget.ready = 0
		self.budget.save()
		self.request(0)
		frappe.db.delete(budget.BUDGET, {"name": self.budget.name})
		doc = self.request(400)
		self.assertTrue(budget.request_summary(doc)["missing"])

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
		frappe.db.savepoint("refused_mr")
		with self.assertRaises(frappe.ValidationError):
			second.submit()
		frappe.db.rollback(save_point="refused_mr")
		self.assertEqual(frappe.db.get_value("Material Request", second.name, "docstatus"), 0)
		self.assertEqual(self.used(), 700)

	def test_mr_rate_replaces_only_covered_provisional_quantities(self):
		doc = self.request(400)
		mr = self.mr(rate=150, qty=2, request=doc, department=False)
		summary = budget.request_summary(doc.reload())
		self.assertEqual(mr.budget_department, self.department)
		self.assertEqual(summary["used"], 300)
		self.assertEqual(summary["provisional"], 200)
		self.assertEqual(summary["projected_available"], 500)
		mr.cancel()
		summary = budget.request_summary(doc.reload())
		self.assertEqual(summary["used"], 0)
		self.assertEqual(summary["provisional"], 400)
		self.assertEqual(frappe.db.count(budget.MOVEMENT, {"budget": self.budget.name}), 2)

	def test_duplicate_sync_and_fulfillment_status_cannot_revalue_mr(self):
		doc = self.mr(rate=250)
		budget.sync_document(doc)
		doc.db_set("status", "Stopped")
		budget.sync_document(doc)
		self.assertEqual(self.used(), 250)
		self.assertEqual(frappe.db.count(budget.MOVEMENT, {"budget": self.budget.name}), 1)
		doc.db_set("status", "Issued")
		budget.sync_document(doc)
		self.assertEqual(self.used(), 250)

	def test_submitted_rates_cannot_be_changed_or_refreshed(self):
		doc = self.mr(rate=250)
		doc.update_item_rates()
		self.assertEqual(self.used(), 250)
		doc.items[0].rate = 300
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_missing_department_budget_and_zero_rate_block_mr_only(self):
		for kwargs in ({"department": False}, {"rate": 0}):
			doc = self.mr(submit=False, **kwargs)
			frappe.db.savepoint("invalid_mr")
			with self.assertRaises(frappe.ValidationError):
				doc.submit()
			frappe.db.rollback(save_point="invalid_mr")
		self.budget.ready = 0
		self.budget.save()
		doc = self.mr(submit=False)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()

	def test_adjustments_ignore_provisional_but_protect_mr_usage(self):
		self.request(2000)
		self.budget.append("adjustments", dict(amount=-100, reason="Reduce allocation"))
		self.budget.save()
		self.mr(rate=700)
		self.budget.append("adjustments", dict(amount=-300, reason="Too much"))
		with self.assertRaises(frappe.ValidationError):
			self.budget.save()

	def test_historical_mr_registration_is_idempotent_and_required_for_readiness(self):
		doc = self.mr(rate=400)
		frappe.db.delete(budget.POSITION, {"budget": self.budget.name})
		frappe.db.delete(budget.MOVEMENT, {"budget": self.budget.name})
		self.budget.ready = 0
		self.budget.save()
		self.budget.ready = 1
		with self.assertRaises(frappe.ValidationError):
			self.budget.save()
		self.budget.reload()
		self.budget.ready = 0
		refs = [{"doctype": "Material Request", "name": doc.name}]
		budget.register_existing_documents(refs)
		budget.register_existing_documents(refs)
		self.budget.ready = 1
		self.budget.save()
		self.assertEqual(self.used(), 400)
		self.assertEqual(frappe.db.count(budget.MOVEMENT, {"budget": self.budget.name}), 1)

	def test_drafts_rejections_and_cancellations_do_not_add_to_other_requests_projection(self):
		active = self.request(400)
		self.request(500, approve=False)
		rejected = self.request(600, approve=False)
		rejected.status = "Rejected"
		rejected.submit()
		cancelled = self.request(700)
		cancelled.cancel()
		self.assertEqual(budget.request_summary(active)["provisional"], 400)

	def test_uom_conversion_reduces_correct_provisional_quantity(self):
		item = frappe.get_doc("Item", self.item)
		item.append("uoms", {"uom": "Box", "conversion_factor": 2})
		item.save()
		doc = self.request(400)
		mr = self.mr(rate=150, qty=2, request=doc, submit=False)
		mr.items[0].uom = "Box"
		mr.items[0].qty = 1
		mr.items[0].conversion_factor = 2
		mr.save().submit()
		self.assertEqual(self.used(), 150)
		self.assertEqual(budget.request_summary(doc.reload())["provisional"], 200)

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

	def account_budget(self, amount=1000):
		account = frappe.db.get_value(
			"Account", {"company": self.company, "is_group": 0, "root_type": "Expense"}, "name"
		)
		return (
			frappe.get_doc(
				dict(
					doctype="Budget",
					company=self.company,
					budget_mode="Account",
					budget_against="Department",
					department=self.department,
					account=account,
					from_fiscal_year=self.budget.from_fiscal_year,
					to_fiscal_year=self.budget.to_fiscal_year,
					budget_amount=amount,
					distribute_equally=1,
				)
			)
			.insert()
			.submit()
		)

	def test_account_mode_retains_native_validation_and_distribution(self):
		account = self.account_budget()
		self.assertTrue(account.budget_distribution)
		self.assertAlmostEqual(sum(row.amount for row in account.budget_distribution), 1000, places=1)
		self.assertTrue(account.applicable_on_booking_actual_expenses)
		group = frappe.db.get_value(
			"Account", {"company": self.company, "is_group": 1, "root_type": "Expense"}, "name"
		)
		invalid = frappe.copy_doc(account)
		invalid.account = group
		with self.assertRaises(frappe.ValidationError):
			invalid.insert()
		invalid = frappe.copy_doc(account)
		invalid.account = None
		with self.assertRaises(frappe.ValidationError):
			invalid.insert()

	def test_account_mode_does_not_require_mr_allocation(self):
		self.budget.cancel()
		self.account_budget()
		request = self.request()
		self.assertEqual(budget.request_summary(request)["mode"], "Account")
		doc = self.mr(rate=2000)
		self.assertFalse(doc.department_budget)
		self.assertFalse(frappe.db.exists(budget.POSITION, {"source_name": doc.name}))
		self.assertEqual(budget.get_material_request_budget(doc.name)["mode"], "Account")

	def test_cumulative_mode_clears_native_controls_and_survives_native_controller(self):
		from erpnext.controllers.budget_controller import BudgetValidation

		self.assertFalse(self.budget.account)
		self.assertFalse(self.budget.budget_distribution)
		for field in (
			"applicable_on_material_request",
			"applicable_on_purchase_order",
			"applicable_on_booking_actual_expenses",
			"applicable_on_cumulative_expense",
		):
			self.assertFalse(self.budget.get(field))
		doc = self.mr(rate=100)
		doc.items[0].department = self.department
		# Null account is also safe when a native item key overlaps the MR budget.
		doc.items[0].expense_account = None
		BudgetValidation(doc=doc).validate()
		self.assertEqual(self.used(), 100)

	def test_modes_are_immutable_and_draft_mr_budget_is_not_active(self):
		self.budget.budget_mode = "Account"
		with self.assertRaises(frappe.ValidationError):
			self.budget.save()
		self.budget.reload().cancel()
		draft = frappe.copy_doc(self.budget)
		draft.ready = 0
		draft.insert()
		self.account_budget()
		with self.assertRaises(frappe.ValidationError):
			self.mr()

	def test_mr_audit_prevents_budget_cancellation_and_revising(self):
		from erpnext.accounts.doctype.budget.budget import revise_budget

		doc = self.mr()
		doc.cancel()
		with self.assertRaises(frappe.ValidationError):
			self.budget.cancel()
		with self.assertRaises(frappe.ValidationError):
			revise_budget(self.budget.name)

	def test_submitted_allocation_and_adjustments_cannot_be_rewritten(self):
		self.budget.append("adjustments", dict(amount=100, reason="Additional allocation"))
		self.budget.save()
		self.budget.adjustments[0].reason = "Changed history"
		with self.assertRaises(frappe.ValidationError):
			self.budget.save()
		self.budget.reload()
		self.budget.budget_amount = 2000
		with self.assertRaises(frappe.ValidationError):
			self.budget.save()

	def test_native_variance_report_excludes_cumulative_budget(self):
		account = self.account_budget()
		# Native report rounds periods to month starts. Keep this fixture within
		# a full fiscal month (the site's Nepal fiscal year starts mid-July).
		frappe.db.delete("Budget Distribution", {"parent": account.name})
		frappe.get_doc(
			dict(
				doctype="Budget Distribution",
				parent=account.name,
				parenttype="Budget",
				parentfield="budget_distribution",
				start_date=today(),
				end_date=today(),
				amount=1000,
				percent=100,
			)
		).db_insert()
		filters = dict(
			company=self.company,
			budget_against="Department",
			budget_against_filter=[self.department],
			from_fiscal_year=self.budget.from_fiscal_year,
			to_fiscal_year=self.budget.to_fiscal_year,
			period="Yearly",
		)
		result = frappe.get_doc("Report", "Budget Variance Report").execute_module(filters)
		self.assertEqual(len(result[1]), 1)
		self.assertEqual(result[1][0]["account"], account.account)

	def test_legacy_migration_preserves_links_adjustments_and_is_idempotent(self):
		from tbs_commons.procurement.budget_setup import migrate_legacy_budgets

		mr = self.mr(rate=300)
		old_name = "legacy-" + frappe.generate_hash(length=8)
		# Historical fixtures bypass the intentionally retired archive controller.
		old = frappe.get_doc(
			dict(
				doctype="Department Budget",
				name=old_name,
				company=self.company,
				department=self.department,
				fiscal_year=self.budget.from_fiscal_year,
				annual_amount=1000,
				budget_owner="Administrator",
				ready=1,
			)
		)
		old.db_insert()
		frappe.get_doc(
			dict(
				doctype="Department Budget Adjustment",
				parent=old_name,
				parenttype="Department Budget",
				parentfield="adjustments",
				amount=100,
				reason="Legacy increase",
			)
		).db_insert()
		for doctype in (budget.POSITION, budget.MOVEMENT):
			frappe.db.sql(
				f"update `tab{doctype}` set budget=%s where budget=%s", (old_name, self.budget.name)
			)
		frappe.db.set_value("Material Request", mr.name, "department_budget", old_name)
		frappe.db.delete("Budget", {"name": self.budget.name})
		migrate_legacy_budgets()
		new_name = frappe.db.get_value("Budget", {"legacy_department_budget": old_name}, "name")
		self.assertTrue(new_name)
		new = frappe.get_doc("Budget", new_name)
		self.assertEqual(new.docstatus, 1)
		self.assertTrue(new.ready)
		self.assertEqual(budget.allocation(new), 1100)
		self.assertEqual(frappe.db.get_value("Material Request", mr.name, "department_budget"), new_name)
		self.assertEqual(totals(budget.portfolio(budget.positions(new_name)))["used"], 300)
		self.assertEqual(frappe.db.count(budget.MOVEMENT, {"budget": new_name}), 1)
		migrate_legacy_budgets()
		self.assertEqual(frappe.db.count("Budget", {"legacy_department_budget": old_name}), 1)


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
