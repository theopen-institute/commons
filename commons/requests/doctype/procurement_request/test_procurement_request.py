# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from commons.requests.doctype.procurement_request.procurement_request import (
	DOCTYPE,
	make_material_request,
)
from commons.requests.procurement_workflow import PROCUREMENT_REQUEST

# This suite's own approval chain. Nothing installs one -- a site builds whatever
# it needs, and `commons.requests.procurement_workflow` reads that rather
# than assuming any particular shape -- so a suite that exercises transitions has
# to bring a workflow with it. The shape below is a conventional one: the buyer
# sends a request on, procurement costs it, a named approver decides, and a
# rejection can be reworked. It is a fixture, not a recommendation.
#
# Order is load-bearing twice over. `Draft` is first, so it is the state Frappe
# assigns a document that arrives without one, and `Approved` is the first
# `doc_status` 1 row, so it is the state `set_workflow_state_on_action` picks
# when something submits a request without going through the workflow.
PROCUREMENT_WORKFLOW = "Procurement Request Workflow"

# Approval is the submission. Everything before a decision is a draft, a
# rejection leaves it one, and only `Approved` carries the request to docstatus
# 1 -- which is what lets `make_material_request` gate on `docstatus` alone
# rather than on the name of a state. `Completed` and `Canceled` are the two
# ways out of it afterwards.
#
# Order is load-bearing twice over. `Draft` is first, so it is the state Frappe
# assigns a document that arrives without one, and `Approved` is the first
# `doc_status` 1 row, so it is the state `set_workflow_state_on_action` picks
# when something submits a request without going through the workflow.
WORKFLOW_STATES = (
	{"state": "Draft", "style": "Primary", "doc_status": "0", "allow_edit": "Employee"},
	{
		"state": "Pending",
		"style": "Warning",
		"doc_status": "0",
		"allow_edit": "Purchase User",
		# Reopening brings a rejected request back here, so this is also where a
		# rejection stops standing. Left alone, last time's reason would still be
		# on the request the next time an approver turned it down. An empty
		# `update_value` clears the field: `evaluate_workflow_value` reads any
		# falsy value as None.
		"update_field": "rejection_reason",
		"update_value": "",
	},
	{"state": "Under Review", "style": "Info", "doc_status": "0", "allow_edit": "Expense Approver"},
	{"state": "Approved", "style": "Success", "doc_status": "1", "allow_edit": "Purchase User"},
	{"state": "Rejected", "style": "Danger", "doc_status": "0", "allow_edit": "Expense Approver"},
	{"state": "Completed", "style": "Success", "doc_status": "1", "allow_edit": "Purchase User"},
	{"state": "Canceled", "style": "Inverse", "doc_status": "2", "allow_edit": "Purchase User"},
)

WORKFLOW_ACTIONS = ("Send to Procurement", "Send for Review", "Approve", "Reject", "Cancel", "Reopen")

WORKFLOW_TRANSITIONS = (
	{"state": "Draft", "action": "Send to Procurement", "next_state": "Pending", "allowed": "Employee", "allow_self_approval": 1},
	{
		"state": "Pending",
		"action": "Send for Review",
		"next_state": "Under Review",
		"allowed": "Purchase User",
		"condition": 'not frappe.db.get_value("Procurement Request Item", {"parent": doc.name, "item_code": ["is", "not set"]}, "name")',
	},
	{
		"state": "Under Review",
		"action": "Approve",
		"next_state": "Approved",
		"allowed": "Expense Approver",
		"condition": "doc.approver == frappe.session.user",
	},
	{
		"state": "Under Review",
		"action": "Reject",
		"next_state": "Rejected",
		"allowed": "Expense Approver",
		"condition": "doc.approver == frappe.session.user",
	},
	{"state": "Under Review", "action": "Approve", "next_state": "Approved", "allowed": "Purchase User"},
	{"state": "Under Review", "action": "Reject", "next_state": "Rejected", "allowed": "Purchase User"},
	{"state": "Approved", "action": "Cancel", "next_state": "Canceled", "allowed": "Purchase User"},
	# A rejection is a decision, not a shredder. Procurement owns the queue, so
	# they are the ones who decide whether a turned-down request is worth
	# reworking, and reopening puts it back in their hands at `Pending` -- where
	# it is theirs to edit again, which `Rejected` deliberately is not.
	{
		"state": "Rejected",
		"action": "Reopen",
		"next_state": "Pending",
		"allowed": "Purchase User",
		# Reopening decides nothing, so a buyer may reopen their own request.
		"allow_self_approval": 1,
	},
)

# Frappe builds test records for a doctype by following its Link fields, then
# theirs, and so on. From `Procurement Request` that walk is 24 hops long --
# Company, Warehouse, Customer, Loyalty Program, Project, Sales Order ... all
# the way to `Payment Gateway`, which lives in the `payments` app and is not
# installed, so the walk dies there. Even where it completes it seeds thousands
# of ERPNext fixture records for a suite that uses none of them.
#
# Nothing here wants them. ERPNext's `before_tests` hook has already run the
# setup wizard, which is where `_Test Company`, its chart of accounts, its
# warehouses and its departments come from, and the fixtures below make their
# own items and users. So the walk is cut off at this doctype's own links.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Company", "Currency", "Department", "User", "Item", "UOM"]


class ProcurementTestCase(IntegrationTestCase):
	"""Shared fixtures. Not named `Test*`, so it is not collected on its own."""

	def require_transition(self, state: str, action: str) -> None:
		"""Skip unless the site's active chain offers this move.

		These tests run against whatever Workflow the site has -- see
		`make_test_workflow` -- so a transition the site's chain does not define
		is a configuration this suite cannot exercise rather than a failure. Said
		here so the skip names the missing move instead of surfacing as Frappe's
		`WorkflowTransitionError` from somewhere in the middle of a test.
		"""
		workflow = frappe.db.get_value(
			"Workflow", {"document_type": PROCUREMENT_REQUEST, "is_active": 1}, "name"
		)
		if workflow and frappe.db.exists(
			"Workflow Transition",
			{"parent": workflow, "parenttype": "Workflow", "state": state, "action": action},
		):
			return
		self.skipTest(
			f"This site's {PROCUREMENT_REQUEST} workflow has no {action!r} from {state!r}."
		)

	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		make_test_workflow()
		# `_Test Company` by name, not whichever company comes back first: it is
		# the one ERPNext's `before_tests` hook sets up, so its currency matches
		# the buying price list and its warehouses and departments exist. A site
		# carrying other companies would otherwise hand back an arbitrary one.
		cls.company = frappe.db.get_value("Company", "_Test Company", "name") or frappe.db.get_value(
			"Company", {}, "name"
		)
		# Of that company: `Material Request` refuses a department belonging to
		# another one, and a site with more than one company will otherwise hand
		# back an unrelated pair.
		cls.department = make_test_department(cls.company)
		# Submitting a Material Request charges a department budget, and
		# `commons.requests.budget` refuses one with no submitted
		# allocation behind it. Generous on purpose: what the budget tests
		# measure is elsewhere, and these should never fail for want of funds.
		make_test_budget(cls.company, cls.department)
		cls.item = make_test_item()
		cls.requester = make_test_user("requester@procurement.test", "Employee", cls.company)
		cls.procurement_user = make_test_user("buyer@procurement.test", "Purchase User")
		cls.approver = make_test_user("approver@procurement.test", "Expense Approver")
		# Each of these holds exactly one role, which is the point -- and on a
		# site that has gated one of them, holding it grants nothing until a User
		# Permission narrows it. `Expense Approver` is the one that bites here:
		# gated on `Procurement Request`, the approver could not read the request
		# they were named on, and every workflow test failed in `get_transitions`
		# with a permission error rather than asserting anything about the
		# transition. See `satisfy_permission_gate`.
		for user in (cls.requester, cls.procurement_user, cls.approver):
			for doctype in (PROCUREMENT_REQUEST, "Material Request"):
				satisfy_permission_gate(user, doctype, "Department", cls.department)

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
		would fill in on the form. That includes a rate: the budget charges
		against one, and `commons.requests.budget` will not let a request
		be submitted without it, whatever the source request estimated.
		"""
		material_request = make_material_request(request.name, selected_items=selected_items)
		material_request.warehouse = frappe.db.get_value(
			"Warehouse", {"is_group": 0, "company": self.company}, "name"
		)
		material_request.schedule_date = add_days(today(), 7)
		for row in material_request.items:
			row.warehouse = material_request.warehouse
			if not flt(row.rate):
				row.rate = 10
		material_request.insert()
		material_request.submit()
		return material_request


class TestProcurementRequest(ProcurementTestCase):
	def test_item_code_is_optional(self):
		request = self.make_request([{"item_name": "Brass fittings, 12mm", "qty": 4, "uom": "Nos"}])

		self.assertFalse(request.items[0].item_code)
		self.assertEqual(request.status, "Draft")

	def test_reference_link_is_optional_and_kept_as_given(self):
		request = self.make_request(
			[
				{"item_name": "Desk lamp", "qty": 1, "uom": "Nos"},
				{
					"item_name": "Cable ties",
					"qty": 10,
					"uom": "Nos",
					"reference_url": "https://example.com/ties",
				},
			]
		)

		self.assertFalse(request.items[0].reference_url)
		self.assertEqual(request.items[1].reference_url, "https://example.com/ties")

	def test_a_link_without_a_scheme_is_refused(self):
		# Frappe's own `Data(URL)` check, left to do its job. Supplying the
		# missing scheme is the collecting form's business -- the requester app
		# and the desk grid both do it before they post -- and no longer
		# something the document quietly does on their behalf.
		with self.assertRaises(frappe.ValidationError):
			self.make_request(
				[
					{
						"item_name": "Brass fittings, 12mm",
						"qty": 4,
						"uom": "Nos",
						"reference_url": "example.com/fittings?size=12",
					}
				]
			)

	def test_row_needs_a_name_of_some_kind(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_request([{"qty": 1, "uom": "Nos"}])

	def test_a_negative_quantity_is_refused_by_the_doctype(self):
		with self.assertRaises(frappe.NonNegativeError):
			self.make_request([{"item_name": "Desk lamp", "qty": -1, "uom": "Nos"}])

	def test_a_zero_quantity_is_refused(self):
		"""`reqd` does not cover it: Frappe reads a Float's content as `"0.0"`."""
		with self.assertRaises(frappe.ValidationError):
			self.make_request([{"item_name": "Desk lamp", "qty": 0, "uom": "Nos"}])

	def test_uom_is_fetched_from_the_item(self):
		"""Declared on the child DocType, not filled in by the controller."""
		request = self.make_request([{"item_code": self.item, "qty": 1}])
		self.assertEqual(request.items[0].uom, frappe.db.get_value("Item", self.item, "stock_uom"))

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

		# `total_estimated_cost` is a virtual field backed by an `options` expression,
		# which `get_valid_dict` evaluates -- so it answers to `as_dict` and not to
		# attribute access, where the DocField reads back as an empty column.
		self.assertEqual(request.as_dict().total_estimated_cost, 70)

	def test_a_verified_rate_takes_over_from_the_estimate_in_the_total(self):
		"""The total is computed on read, so a changed rate shows up without a resave."""
		request = self.make_request(
			[
				{"item_name": "Desk lamp", "qty": 3, "uom": "Nos", "estimated_rate": 20},
				{"item_name": "Cable", "qty": 2, "uom": "Nos", "estimated_rate": 5},
			],
		)
		request.items[0].verified_rate = 25
		request.save()
		request.reload()
		self.assertEqual(request.as_dict().total_estimated_cost, 85)

		request.items[0].verified_rate = 0
		request.save()
		request.reload()
		self.assertEqual(request.as_dict().total_estimated_cost, 70)

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

		# Cancelling the stock document hands the request back to the approver.
		material_request.cancel()
		request.reload()
		self.assertEqual(request.items[0].committed_qty, 0)
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
		self.assertEqual(request.status, "Approved")

		# The second instalment carries the remainder, and nothing more.
		self.assertEqual(request.open_rows[0].uncommitted_qty, 6)

		self.order(request)

		request.reload()
		self.assertEqual(request.items[0].uncommitted_qty, 0)

	def test_ordering_more_than_is_left_takes_what_is_left(self):
		"""Trimmed, not refused: the buyer sees the quantity on the form anyway."""
		request = self.make_request([{"item_code": self.item, "qty": 5, "uom": "Nos"}], submit=True)
		self.order(request, [{"name": request.items[0].name, "qty": 4}])

		material_request = make_material_request(
			request.name, selected_items=[{"name": request.items[0].name, "qty": 2}]
		)
		self.assertEqual(len(material_request.items), 1)
		self.assertEqual(material_request.items[0].qty, 1)

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
		"""Frappe's own rule, because no field on the table is `allow_on_submit`.

		Asserting the specific exception rather than `ValidationError`: that is
		what says the metadata is still doing the work, rather than some other
		check happening to fail first.
		"""
		request = self.make_request([{"item_code": self.item, "qty": 2, "uom": "Nos"}], submit=True)

		for fieldname, value in (
			("item_code", make_test_item("_Test Procurement Recode")),
			("uom", "Unit"),
			("verified_rate", 25),
			("item_name", "Overwritten by the catalogue"),
			("qty", 9),
		):
			request.reload()
			request.items[0].set(fieldname, value)
			with self.assertRaises(frappe.exceptions.UpdateAfterSubmitError):
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
		with self.assertRaises(frappe.exceptions.UpdateAfterSubmitError):
			request.save()

		request.reload()
		request.items.pop()
		with self.assertRaises(frappe.exceptions.UpdateAfterSubmitError):
			request.save()

	def test_an_approved_request_cannot_be_cancelled_out_from_under_a_material_request(self):
		"""Also Frappe's own rule: `check_no_back_links_exist` on cancel."""
		request = self.make_request([{"item_code": self.item, "qty": 2, "uom": "Nos"}], submit=True)
		self.order(request)

		request.reload()
		with self.assertRaises(frappe.LinkExistsError):
			request.cancel()

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
		# Holding the approving role and nothing else is the whole point of this
		# stranger, so on a gated site they have to be given the User Permission
		# that role needs -- otherwise the refusal below is the gate declining to
		# show them the request at all, which is a `PermissionError` and not what
		# this test is about. Refused for not being the named approver is.
		satisfy_permission_gate(stranger, PROCUREMENT_REQUEST, "Department", self.department)

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

	def test_rejecting_leaves_the_request_a_draft(self):
		request = self.make_review_request()

		frappe.set_user(self.approver)
		apply_workflow(request, "Reject")

		request.reload()
		self.assertEqual(request.status, "Rejected")
		# Approval is the submission, so a turned-down request never reaches
		# docstatus 1 -- which is what `make_material_request` gates on.
		self.assertEqual(request.docstatus, 0)

	def test_a_rejected_request_cannot_become_a_material_request(self):
		request = self.make_review_request()

		frappe.set_user(self.approver)
		apply_workflow(request, "Reject")

		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			make_material_request(request.name)

	def test_a_rejected_request_can_be_reopened(self):
		"""Reopening clears the rejection, and the request is editable again.

		Skipped where the site's own chain has no such transition. This suite
		runs against whatever workflow it finds -- `make_test_workflow` installs
		its own only on a site with none, deliberately -- and a chain that offers
		no way back from `Rejected` cannot be asked what reopening leaves
		behind. Before this, the test failed there with Frappe's
		`WorkflowTransitionError`, which reads as a bug in the app rather than as
		a transition nobody configured.
		"""
		self.require_transition("Rejected", "Reopen")
		request = self.make_review_request()
		frappe.set_user(self.approver)
		request.db_set("rejection_reason", "Too expensive this quarter")
		apply_workflow(request, "Reject")

		frappe.set_user(self.procurement_user)
		apply_workflow(request.reload(), "Reopen")

		request.reload()
		self.assertEqual(request.status, "Pending")
		self.assertEqual(request.docstatus, 0)
		# The rejection does not outlive the state it belongs to.
		self.assertFalse(request.rejection_reason)

		# And it can go round again.
		apply_workflow(request, "Send for Review")
		request.reload()
		self.assertEqual(request.status, "Under Review")

	def test_a_decided_request_cannot_be_decided_again(self):
		request = self.make_review_request()

		frappe.set_user(self.approver)
		apply_workflow(request, "Approve")

		with self.assertRaises(frappe.ValidationError):
			apply_workflow(request, "Reject")


def make_test_workflow() -> None:
	"""Put this suite's chain on the site, unless the site already has one.

	An existing workflow is left exactly as it is: on a real site this suite is
	being run against somebody's own chain, and overwriting it to test against a
	fixture would be both rude and dishonest about what passed.

	The alert is off. Frappe's workflow alert attaches the request as a PDF, which
	needs `wkhtmltopdf` on the machine running the suite, and it is sent inline
	rather than queued when `frappe.in_test` -- so leaving it on would make every
	test here depend on a binary that need not be installed. What is under test is
	which transitions are allowed and what they leave behind, not delivery.
	"""
	if frappe.db.exists("Workflow", {"document_type": PROCUREMENT_REQUEST}):
		return

	for state in WORKFLOW_STATES:
		name = state["state"]
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": state["style"]}
			).insert(ignore_permissions=True)

	for action in WORKFLOW_ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	workflow = frappe.new_doc("Workflow")
	workflow.update(
		{
			"workflow_name": PROCUREMENT_WORKFLOW,
			"document_type": PROCUREMENT_REQUEST,
			"workflow_state_field": "status",
			"is_active": 1,
			"send_email_alert": 0,
		}
	)
	workflow.set("states", [{k: v for k, v in state.items() if k != "style"} for state in WORKFLOW_STATES])
	workflow.set("transitions", list(WORKFLOW_TRANSITIONS))
	workflow.save(ignore_permissions=True)


def make_test_item(code: str = "_Test Procurement Item") -> str:
	"""A stock item to put on a request line, made if the site has none.

	Written here rather than through `erpnext.stock.doctype.item.test_item`'s
	`make_item`. That module imports `erpnext.tests.utils`, which instantiates
	`BootStrapTestData()` at module level -- so the import alone writes
	erpnext's entire test master data to whatever site is connected: the India
	preset records, UOMs, companies, accounts, and a company-less `Fiscal Year`
	for every calendar year from 2012 to twenty-five years out.

	On a site that keeps its own company-less fiscal year -- one running an
	April-to-March book, say -- ERPNext's own `Fiscal Year.validate_overlap`
	then refuses one of the two and the *import* raises `frappe.NameError`.
	That happened in `setUpClass`, so both classes in this file reported an
	error and none of their tests ran at all.

	An item is three mandatory fields and nothing this suite needs is in the
	rest, so importing a test module to get one was never a good trade. The
	group and the UOM are read off the site rather than named: `_Test Item
	Group` and the preset UOMs are exactly the master data this no longer
	installs.
	"""
	if frappe.db.exists("Item", code):
		return code

	group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or frappe.db.get_value(
		"Item Group", {}, "name"
	)
	uom = frappe.db.get_value("UOM", "Nos", "name") or frappe.db.get_value("UOM", {}, "name")
	return (
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": group,
				"stock_uom": uom,
				"is_stock_item": 1,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def make_test_budget(company: str, department: str) -> str | None:
	"""A submitted allocation covering today, so Material Requests can be raised."""
	from erpnext.accounts.utils import get_fiscal_year

	fiscal_year = get_fiscal_year(today(), company=company, boolean=True)
	if not fiscal_year:
		return None
	fiscal_year = fiscal_year[0]

	existing = frappe.db.get_value(
		"Department Budget",
		{"company": company, "department": department, "fiscal_year": fiscal_year, "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	budget = frappe.get_doc(
		{
			"doctype": "Department Budget",
			"company": company,
			"department": department,
			"fiscal_year": fiscal_year,
			"budget_owner": "Administrator",
			"annual_amount": 10_000_000,
		}
	).insert(ignore_permissions=True)
	budget.submit()
	return budget.name


#: The department this suite raises every request against. Its own, by name.
TEST_DEPARTMENT = "Procurement Test"


def make_test_department(company: str) -> str:
	"""This suite's own leaf department of the given company.

	Its own, rather than whichever leaf department the site happens to list
	first. That is what this did, and on a site with real departments it picked
	a real one -- `Fine Arts` here -- whose budget carries real committed spend.
	`make_test_budget` then found that department's existing allocation and
	reused it, so the four approval tests charged a live overspent budget and
	failed with a shortfall rather than on anything they were written to check.
	The comment beside `make_test_budget` in `setUpClass` says these should
	never fail for want of funds; this is what makes that true.

	Matched on `department_name` rather than on the full name, because ERPNext
	autonames a Department by appending the company abbreviation and a site
	renaming its company would otherwise get a second one every run.
	"""
	existing = frappe.db.get_value(
		"Department", {"company": company, "department_name": TEST_DEPARTMENT}, "name"
	)
	if existing:
		return existing

	return (
		frappe.get_doc(
			{
				"doctype": "Department",
				"department_name": TEST_DEPARTMENT,
				"company": company,
				"is_group": 0,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def satisfy_permission_gate(user: str, doctype: str, allow: str, for_value: str) -> None:
	"""Give `user` the User Permission this site's gate demands on `doctype`.

	`commons.safer_permissions` lets a Role Permission row be marked
	`require_user_permission`, and a role marked that way grants nothing at all
	until a User Permission aimed at that doctype narrows it. These fixtures give
	each login exactly one role so that permissions prove something -- which
	means that on a gated site each login has only the gated grant, and so no
	access, and the tests fail on the way in rather than on what they assert.

	`applicable_for` the doctype being gated, never a blanket permission: the
	gate ignores blanket ones by design, because that is the default and
	counting them would let one unrelated restriction open every gate on the
	site. `allow`/`for_value` name the link to narrow by, which is why this takes
	them -- a `Department` is the realistic one for both doctypes here, and it is
	what a real gated site grants an approver.

	Asked of the gate rather than assumed, so nothing is written on a site that
	gates nothing and these suites run there exactly as they did before.
	"""
	from commons.safer_permissions.permissions import gate_applies, gate_satisfied

	if not gate_applies(user, doctype) or gate_satisfied(user, doctype):
		return

	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": allow,
			"for_value": for_value,
			"applicable_for": doctype,
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(user=user)


def make_test_user(email: str, role: str, company: str | None = None) -> str:
	"""A user with exactly one role, so permissions prove something.

	The roles a real login accumulates — System Manager most of all — sail past
	every check these tests are about.

	Through `add_roles` rather than by inserting a `Has Role` row: a role only
	takes effect once `User.validate` has seen it, because that is what promotes
	the account to `System User`. Added straight to the child table the row is
	stored, shows on the form, and grants nothing -- `frappe.get_roles` returns
	`All` and `Guest`, and every permission check says no.

	`Employee` needs more than that. ERPNext hooks `validate_employee_role` onto
	`User.validate`, and it takes the role straight back off any account that no
	`Employee` record points at -- silently, as a `msgprint`. So the requester
	gets an employee record before the role goes on.
	"""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

	if role in ("Employee", "Employee Self Service") and not frappe.db.exists("Employee", {"user_id": email}):
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": email.split("@")[0],
				"user_id": email,
				"company": company,
				"gender": frappe.db.get_value("Gender", {}, "name"),
				"date_of_birth": add_days(today(), -365 * 30),
				"date_of_joining": add_days(today(), -365),
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		# Creating the employee writes to the user, so the handle above is stale.
		user.reload()

	if role not in {row.role for row in user.roles}:
		user.add_roles(role)

	return email
