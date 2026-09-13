# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from tbs_commons.install import sync_procurement_workflow
from tbs_commons.procurement.doctype.procurement_request.procurement_request import make_material_request


class ProcurementTestCase(IntegrationTestCase):
	"""Shared fixtures. Not named `Test*`, so it is not collected on its own."""

	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		sync_procurement_workflow()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.department = frappe.db.get_value("Department", {}, "name")
		cls.item = make_test_item()
		cls.requester = make_test_user("requester@procurement.test", "Employee")
		cls.procurement_user = make_test_user("buyer@procurement.test", "Purchase User")
		cls.approver = make_test_user("approver@procurement.test", "Expense Approver")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		super().tearDown()

	def make_request(
		self, items: list[dict], submit: bool = False, approver: str | None = None
	) -> "frappe.Document":
		request = frappe.get_doc(
			{
				"doctype": "Procurement Request",
				"company": self.company,
				"department": self.department,
				"transaction_date": today(),
				"schedule_date": add_days(today(), 7),
				"approver": approver or self.approver,
				"items": items,
			}
		).insert()

		if submit:
			request.submit()

		return request

	def order(self, request, selected_items: list[dict] | None = None) -> "frappe.Document":
		"""Carry a request onto a Material Request and submit it.

		The mapper hands back a draft on purpose -- the warehouse and the dates
		are the stock document's business -- so the fixture fills in what a buyer
		would fill in on the form.
		"""
		material_request = make_material_request(request.name, selected_items=selected_items)
		material_request.warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")
		material_request.schedule_date = add_days(today(), 7)
		for row in material_request.items:
			row.warehouse = material_request.warehouse
		material_request.insert()
		material_request.submit()
		return material_request


class TestProcurementRequest(ProcurementTestCase):
	def test_item_code_is_optional(self):
		request = self.make_request([{"item_name": "Brass fittings, 12mm", "qty": 4, "uom": "Nos"}])

		self.assertFalse(request.items[0].item_code)
		self.assertEqual(request.status, "Draft")

	def test_reference_link_is_optional_and_gains_a_scheme(self):
		request = self.make_request(
			[
				{"item_name": "Desk lamp", "qty": 1, "uom": "Nos"},
				{
					"item_name": "Brass fittings, 12mm",
					"qty": 4,
					"uom": "Nos",
					"reference_url": "  example.com/fittings?size=12  ",
				},
				{
					"item_name": "Cable ties",
					"qty": 10,
					"uom": "Nos",
					"reference_url": "https://example.com/ties",
				},
			]
		)

		self.assertFalse(request.items[0].reference_url)
		# Pasted without a scheme, which `Data(URL)` would otherwise reject.
		self.assertEqual(request.items[1].reference_url, "https://example.com/fittings?size=12")
		# One that already has a scheme is left exactly as it was given.
		self.assertEqual(request.items[2].reference_url, "https://example.com/ties")

	def test_row_needs_a_name_of_some_kind(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_request([{"qty": 1, "uom": "Nos"}])

	def test_material_request_uses_parent_required_by(self):
		request = self.make_request([{"item_code": self.item, "qty": 1, "uom": "Nos"}], submit=True)
		material_request = make_material_request(request.name)
		self.assertEqual(str(material_request.items[0].schedule_date), str(request.schedule_date))

	def test_required_by_cannot_precede_the_request(self):
		request = self.make_request([{"item_name": "Desk lamp", "qty": 1, "uom": "Nos"}])
		request.schedule_date = add_days(today(), -1)
		with self.assertRaises(frappe.ValidationError):
			request.save()

	def test_estimates_are_totalled(self):
		request = self.make_request(
			[
				{"item_name": "Desk lamp", "qty": 3, "uom": "Nos", "estimated_rate": 20},
				{"item_name": "Cable", "qty": 2, "uom": "Nos", "estimated_rate": 5},
			]
		)

		self.assertEqual(request.total_qty, 5)
		self.assertEqual(request.total_estimated_cost, 70)

	def test_verified_rate_updates_virtual_total(self):
		request = self.make_request(
			[
				{"item_name": "Desk lamp", "qty": 3, "uom": "Nos", "estimated_rate": 20},
				{"item_name": "Cable", "qty": 2, "uom": "Nos", "estimated_rate": 5},
			],
		)
		request.items[0].verified_rate = 25
		self.assertEqual(request.total_estimated_cost, 85)
		request.save()
		request.reload()
		self.assertEqual(request.total_estimated_cost, 85)
		self.assertEqual(request.as_dict().total_estimated_cost, 85)
		request.items[0].verified_rate = 0
		request.save()
		request.reload()
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

		material_request = self.order(request)

		self.assertEqual(material_request.material_request_type, "Purchase")
		self.assertEqual(material_request.procurement_request, request.name)
		self.assertEqual(material_request.items[0].procurement_request_item, request.items[0].name)

		request.reload()
		self.assertEqual(request.items[0].committed_qty, 6)
		self.assertEqual(request.per_ordered, 100)
		self.assertEqual(request.status, "Completed")

		# Cancelling the stock document hands the request back to the approver.
		material_request.cancel()
		request.reload()
		self.assertEqual(request.items[0].committed_qty, 0)
		self.assertEqual(request.per_ordered, 0)
		self.assertEqual(request.status, "Approved")

	def test_only_the_chosen_rows_are_carried_over(self):
		request = self.make_request(
			[
				{"item_code": self.item, "qty": 2, "uom": "Nos"},
				{"item_code": self.item, "qty": 3, "uom": "Nos"},
			],
			submit=True,
		)

		material_request = self.order(request, [{"name": request.items[1].name, "qty": 3}])

		self.assertEqual(len(material_request.items), 1)
		self.assertEqual(material_request.items[0].procurement_request_item, request.items[1].name)

		request.reload()
		self.assertEqual(request.items[0].uncommitted_qty, 2)
		self.assertEqual(request.items[1].uncommitted_qty, 0)
		self.assertEqual(request.status, "Approved")

	def test_part_of_a_row_can_be_ordered_now_and_the_rest_later(self):
		request = self.make_request([{"item_code": self.item, "qty": 10, "uom": "Nos"}], submit=True)

		self.order(request, [{"name": request.items[0].name, "qty": 4}])

		request.reload()
		self.assertEqual(request.items[0].committed_qty, 4)
		self.assertEqual(request.items[0].uncommitted_qty, 6)
		self.assertEqual(request.per_ordered, 40)
		self.assertEqual(request.status, "Approved")

		# The second instalment carries the remainder, and nothing more.
		self.assertEqual(request.open_rows[0].uncommitted_qty, 6)

		self.order(request)

		request.reload()
		self.assertEqual(request.items[0].uncommitted_qty, 0)
		self.assertEqual(request.status, "Completed")

	def test_ordering_more_than_is_left_is_refused(self):
		request = self.make_request([{"item_code": self.item, "qty": 5, "uom": "Nos"}], submit=True)
		self.order(request, [{"name": request.items[0].name, "qty": 4}])

		with self.assertRaises(frappe.ValidationError):
			make_material_request(request.name, selected_items=[{"name": request.items[0].name, "qty": 2}])

	def test_a_row_without_an_item_code_can_be_left_out(self):
		request = self.make_request(
			[
				{"item_code": self.item, "qty": 1, "uom": "Nos"},
				{"item_name": "Something not in the item master", "qty": 1, "uom": "Nos"},
			],
			submit=True,
		)

		# The whole request cannot go over -- the second row has no item code --
		# but the row that does is not held hostage by it.
		with self.assertRaises(frappe.ValidationError):
			make_material_request(request.name)

		material_request = self.order(request, [{"name": request.items[0].name, "qty": 1}])
		self.assertEqual(len(material_request.items), 1)

		request.reload()
		self.assertEqual(request.status, "Approved")

	def test_item_fields_cannot_be_changed_after_submission(self):
		request = self.make_request([{"item_code": self.item, "qty": 2, "uom": "Nos"}], submit=True)

		for fieldname, value in (
			("item_code", make_test_item("_Test Procurement Recode")),
			("uom", "Unit"),
			("verified_rate", 25),
		):
			request.reload()
			request.items[0].set(fieldname, value)
			with self.assertRaises(frappe.ValidationError):
				request.save()

	def test_rows_cannot_be_added_or_removed_after_submission(self):
		request = self.make_request(
			[
				{"item_code": self.item, "qty": 1, "uom": "Nos"},
				{"item_code": self.item, "qty": 2, "uom": "Nos"},
			],
			submit=True,
		)

		request.append("items", {"item_name": "Slipped in later", "qty": 1, "uom": "Nos"})
		with self.assertRaises(frappe.ValidationError):
			request.save()

		request.reload()
		request.items.pop()
		with self.assertRaises(frappe.ValidationError):
			request.save()

	def test_nothing_is_left_to_order_once_it_all_has_been(self):
		request = self.make_request([{"item_code": self.item, "qty": 2, "uom": "Nos"}], submit=True)
		self.order(request)

		self.assertEqual(request.open_rows, [])
		with self.assertRaises(frappe.ValidationError):
			make_material_request(request.name)


class TestProcurementApproval(ProcurementTestCase):
	"""The configured Frappe Workflow, using Frappe's standard action API."""

	def make_pending_request(self) -> "frappe.Document":
		frappe.set_user(self.requester)
		request = self.make_request(
			[{"item_code": self.item, "qty": 4, "uom": "Nos", "estimated_rate": 50}],
			approver=self.approver,
		)
		apply_workflow(request, "Send to Procurement")
		request.reload()
		return request

	def make_review_request(self) -> "frappe.Document":
		request = self.make_pending_request()
		frappe.set_user(self.procurement_user)
		apply_workflow(request, "Send for Review")
		request.reload()
		return request

	def test_sending_hands_the_request_over(self):
		request = self.make_pending_request()

		self.assertEqual(request.status, "Pending")
		self.assertEqual(request.docstatus, 0)

	def test_a_requester_cannot_approve_their_own(self):
		request = self.make_review_request()
		frappe.set_user(self.requester)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(request, "Approve")

	def test_only_the_named_approver_decides(self):
		request = self.make_review_request()
		stranger = make_test_user("stranger@procurement.test", "Expense Approver")

		frappe.set_user(stranger)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(request, "Approve")

	def test_an_undecided_request_must_have_been_sent(self):
		frappe.set_user(self.requester)
		request = self.make_request(
			[{"item_code": self.item, "qty": 1, "uom": "Nos"}], approver=self.approver
		)

		frappe.set_user(self.approver)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(request, "Approve")

	def test_approving_submits(self):
		request = self.make_review_request()

		frappe.set_user(self.approver)
		apply_workflow(request, "Approve")

		request.reload()
		self.assertEqual(request.status, "Approved")
		self.assertEqual(request.docstatus, 1)

	def test_rejecting_submits(self):
		request = self.make_review_request()

		frappe.set_user(self.approver)
		apply_workflow(request, "Reject")

		request.reload()
		self.assertEqual(request.status, "Rejected")
		self.assertEqual(request.docstatus, 1)

	def test_a_decided_request_cannot_be_decided_again(self):
		request = self.make_review_request()

		frappe.set_user(self.approver)
		apply_workflow(request, "Approve")

		with self.assertRaises(frappe.ValidationError):
			apply_workflow(request, "Reject")


def make_test_item(code: str = "_Test Procurement Item") -> str:
	from erpnext.stock.doctype.item.test_item import make_item

	return make_item(code, {"is_stock_item": 1, "stock_uom": "Nos"}).name


def make_test_user(email: str, role: str) -> str:
	"""A user with exactly one role, so permissions prove something.

	The roles a real login accumulates — System Manager most of all — sail past
	every check these tests are about.
	"""
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Has Role", {"parent": email, "role": role, "parenttype": "User"}):
		frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": email,
				"parenttype": "User",
				"parentfield": "roles",
				"role": role,
			}
		).insert(ignore_permissions=True)

	return email
