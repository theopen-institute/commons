# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from tbsapp.api import decide_procurement_request, send_procurement_request
from tbsapp.tbs_app.doctype.procurement_request.procurement_request import make_material_request


class ProcurementTestCase(IntegrationTestCase):
	"""Shared fixtures. Not named `Test*`, so it is not collected on its own."""

	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.item = make_test_item()
		cls.requester = make_test_user("requester@procurement.test", "Employee")
		cls.approver = make_test_user("approver@procurement.test", "Purchase Manager")

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
				"purpose": "Purchase",
				"transaction_date": today(),
				"schedule_date": add_days(today(), 7),
				"approver": approver,
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

		material_request = self.order(request)

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
		self.assertEqual(request.items[0].ordered_qty, 0)
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
		self.assertEqual(request.items[0].order_status, "Open")
		self.assertEqual(request.items[0].pending_qty, 2)
		self.assertEqual(request.items[1].order_status, "Ordered")
		self.assertEqual(request.items[1].pending_qty, 0)
		self.assertEqual(request.status, "Partially Ordered")

	def test_part_of_a_row_can_be_ordered_now_and_the_rest_later(self):
		request = self.make_request([{"item_code": self.item, "qty": 10, "uom": "Nos"}], submit=True)

		self.order(request, [{"name": request.items[0].name, "qty": 4}])

		request.reload()
		self.assertEqual(request.items[0].ordered_qty, 4)
		self.assertEqual(request.items[0].pending_qty, 6)
		self.assertEqual(request.items[0].order_status, "Partially Ordered")
		self.assertEqual(request.per_ordered, 40)
		self.assertEqual(request.status, "Partially Ordered")

		# The second instalment carries the remainder, and nothing more.
		self.assertEqual(request.open_rows[0].pending_qty, 6)

		self.order(request)

		request.reload()
		self.assertEqual(request.items[0].pending_qty, 0)
		self.assertEqual(request.status, "Ordered")

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
		self.assertEqual(request.items[1].order_status, "Open")
		self.assertEqual(request.status, "Partially Ordered")

	def test_an_item_code_can_be_set_after_submission(self):
		request = self.make_request(
			[{"item_name": "Bespoke lab bench, 3m", "qty": 1, "uom": "Nos"}], submit=True
		)

		# Nothing could be ordered while the row named no item.
		with self.assertRaises(frappe.ValidationError):
			make_material_request(request.name)

		request.items[0].item_code = self.item
		request.save()
		request.reload()

		self.assertEqual(request.items[0].item_code, self.item)
		self.assertEqual(len(request.open_rows), 1)

		material_request = self.order(request)
		self.assertEqual(material_request.items[0].item_code, self.item)

	def test_the_requesters_own_words_survive_a_late_item_code(self):
		request = self.make_request(
			[{"item_name": "Bespoke lab bench, 3m", "qty": 1, "uom": "Nos"}], submit=True
		)

		# What the desk sends when an Item Code is picked: its link fetch has
		# already overwritten the name with the catalogue's.
		request.items[0].item_code = self.item
		request.items[0].item_name = "_Test Procurement Item"
		request.save()
		request.reload()

		self.assertEqual(request.items[0].item_code, self.item)
		self.assertEqual(request.items[0].item_name, "Bespoke lab bench, 3m")

	def test_an_item_code_can_be_cleared_again(self):
		request = self.make_request([{"item_code": self.item, "qty": 1, "uom": "Nos"}], submit=True)

		request.items[0].item_code = None
		request.save()
		request.reload()

		self.assertFalse(request.items[0].item_code)
		# The row still says what it is, so it is a request for something the
		# item master does not carry -- exactly as if it had been raised that way.
		self.assertTrue(request.items[0].item_name)

	def test_an_item_code_cannot_be_changed_once_the_row_is_ordered(self):
		request = self.make_request([{"item_code": self.item, "qty": 2, "uom": "Nos"}], submit=True)
		self.order(request)

		request.reload()
		request.items[0].item_code = make_test_item("_Test Procurement Recode")
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
	"""The request/approval loop the SPA drives, via the same endpoints it calls."""

	def make_sent_request(self) -> "frappe.Document":
		frappe.set_user(self.requester)
		request = self.make_request(
			[{"item_name": "Lab tripods", "qty": 4, "uom": "Nos", "estimated_rate": 50}],
			approver=self.approver,
		)
		send_procurement_request(request.name)
		request.reload()
		return request

	def test_sending_needs_an_approver(self):
		frappe.set_user(self.requester)
		request = self.make_request([{"item_name": "Lab tripods", "qty": 1, "uom": "Nos"}])

		with self.assertRaises(frappe.ValidationError):
			send_procurement_request(request.name)

	def test_sending_hands_the_request_over(self):
		request = self.make_sent_request()

		self.assertEqual(request.status, "Pending Approval")
		self.assertEqual(request.docstatus, 0)

	def test_a_requester_cannot_approve_their_own(self):
		request = self.make_sent_request()

		# permlevel 1 on `status`: the write is reverted rather than refused,
		# which is what makes the explicit check in the endpoint necessary.
		request.status = "Approved"
		request.save()
		request.reload()
		self.assertEqual(request.status, "Pending Approval")

	def test_only_the_named_approver_decides(self):
		request = self.make_sent_request()
		stranger = make_test_user("stranger@procurement.test", "Purchase Manager")

		frappe.set_user(stranger)
		with self.assertRaises(frappe.PermissionError):
			decide_procurement_request(request.name, "Approved")

	def test_an_undecided_request_must_have_been_sent(self):
		frappe.set_user(self.requester)
		request = self.make_request(
			[{"item_name": "Lab tripods", "qty": 1, "uom": "Nos"}], approver=self.approver
		)

		frappe.set_user(self.approver)
		with self.assertRaises(frappe.ValidationError):
			decide_procurement_request(request.name, "Approved")

	def test_approving_submits(self):
		request = self.make_sent_request()

		frappe.set_user(self.approver)
		decide_procurement_request(request.name, "Approved")

		request.reload()
		self.assertEqual(request.status, "Approved")
		self.assertEqual(request.docstatus, 1)

	def test_turning_down_records_the_reason(self):
		request = self.make_sent_request()

		frappe.set_user(self.approver)
		decide_procurement_request(request.name, "Rejected", reason="Over budget.")

		request.reload()
		self.assertEqual(request.status, "Rejected")
		self.assertEqual(request.docstatus, 1)
		self.assertEqual(request.rejection_reason, "Over budget.")

	def test_a_decided_request_cannot_be_decided_again(self):
		request = self.make_sent_request()

		frappe.set_user(self.approver)
		decide_procurement_request(request.name, "Approved")

		with self.assertRaises(frappe.ValidationError):
			decide_procurement_request(request.name, "Rejected")


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
