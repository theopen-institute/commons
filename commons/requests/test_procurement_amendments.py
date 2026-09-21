"""Request-list amendment handling without a running site."""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.commons_core import workflow as wf
from commons.requests import procurement as api

# Every test below is about a site that *has* ERPNext, which is the only site
# these endpoints have anything to say on. Availability is otherwise an
# installed-apps lookup on every call -- see `approvals.RequestType.available`
# -- and `TestProcurementUnavailable` is where the other answer is pinned.
_available = patch.object(api.PROCUREMENT, "available", return_value=True)

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. The messages here are the source strings
# either way -- see `test_procurement_helpers`, which does the same.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_available.start()
	_logger.start()


def tearDownModule():
	_available.stop()
	_logger.stop()


def request(name, docstatus=0, amended_from=None):
	return api.frappe._dict(name=name, docstatus=docstatus, amended_from=amended_from)


class TestProcurementAmendments(TestCase):
	def test_duplicate_role_transitions_render_one_action(self):
		transitions = [
			SimpleNamespace(action="Decide", next_state="Done", allowed="Role A"),
			SimpleNamespace(action="Decide", next_state="Done", allowed="Role B"),
			SimpleNamespace(action="Return", next_state="Draft", allowed="Role B"),
		]
		self.assertEqual(
			wf.unique_actions(transitions),
			[
				{"action": "Decide", "next_state": "Done"},
				{"action": "Return", "next_state": "Draft"},
			],
		)

	def test_workflow_allow_edit_role_controls_draft_editing(self):
		workflow = SimpleNamespace(
			workflow_state_field="workflow_state",
			states=[
				SimpleNamespace(state="Current", doc_status="0", allow_edit="Current Role")
			],
		)
		doc = SimpleNamespace(
			docstatus=0,
			has_permission=lambda permission: permission == "write",
			get=lambda fieldname: "Current" if fieldname == "workflow_state" else None,
		)

		with patch.object(api.frappe, "get_roles", return_value=["Current Role"]):
			self.assertTrue(api._can_edit_procurement_request(doc, workflow))
		with patch.object(api.frappe, "get_roles", return_value=["Other Role"]):
			self.assertFalse(api._can_edit_procurement_request(doc, workflow))

	def test_submitted_request_is_not_editable_in_request_dialog(self):
		doc = SimpleNamespace(docstatus=1, has_permission=lambda _permission: True)
		self.assertFalse(api._can_edit_procurement_request(doc, workflow=None))

	def test_frontend_save_preserves_catalogue_fields(self):
		stored = SimpleNamespace(
			items=[api.frappe._dict(name="ROW-1", item_code="ITEM-1", verified_rate=25)]
		)
		items = [{"name": "ROW-1", "item_code": "ITEM-2", "verified_rate": 100}]
		api._preserve_non_frontend_line_fields(items, stored)
		self.assertEqual(items[0]["item_code"], "ITEM-1")
		self.assertEqual(items[0]["verified_rate"], 25)

	def test_frontend_save_strips_catalogue_fields_from_new_lines(self):
		items = [{"item_code": "ITEM-1", "verified_rate": 25}]
		api._preserve_non_frontend_line_fields(items)
		self.assertNotIn("item_code", items[0])
		self.assertNotIn("verified_rate", items[0])

	def test_initial_actions_follow_the_workflow_and_current_roles(self):
		workflow = SimpleNamespace(
			states=[SimpleNamespace(state="First")],
			transitions=[
				SimpleNamespace(
					state="First",
					action="Continue",
					next_state="Second",
					allowed="Current Role",
					allow_self_approval=1,
				),
				SimpleNamespace(
					state="First",
					action="Other role",
					next_state="Second",
					allowed="Other Role",
					allow_self_approval=1,
				),
			],
		)
		with patch.object(wf.frappe, "get_roles", return_value=["Current Role"]):
			self.assertEqual(
				wf.initial_actions(workflow),
				[{"action": "Continue", "next_state": "Second"}],
			)

	def test_no_workflow_means_no_available_actions(self):
		with (
			patch.object(api.PROCUREMENT, "workflow", return_value=None),
			patch.object(api.frappe, "parse_json", return_value=["PR-1"]),
			patch.object(api.frappe, "get_list") as get_list,
		):
			self.assertEqual(api.get_procurement_request_transitions('["PR-1"]'), {})
			get_list.assert_not_called()

	def test_amendment_replaces_original_at_original_position(self):
		amended = request("PR-1-1", amended_from="PR-1")
		unrelated = request("PR-2")
		rows = [amended, unrelated, request("PR-1", 2)]
		self.assertEqual(api._replace_cancelled_requests(rows), [unrelated, amended])

	def test_multiple_amendments_resolve_to_latest_descendant(self):
		latest = request("PR-1-2", amended_from="PR-1-1")
		rows = [latest, request("PR-1-1", 2, "PR-1"), request("PR-1", 2)]
		self.assertEqual(api._replace_cancelled_requests(rows), [latest])

	def test_cancelled_without_amendment_is_retained(self):
		rows = [request("PR-1", 2)]
		self.assertEqual(api._replace_cancelled_requests(rows), rows)

	def test_amendment_without_readable_ancestor_is_retained(self):
		rows = [request("PR-1-1", amended_from="PR-1")]
		self.assertEqual(api._replace_cancelled_requests(rows), rows)

	def test_latest_sibling_amendment_wins(self):
		latest = request("PR-1-2", amended_from="PR-1")
		rows = [latest, request("PR-1-1", 2, "PR-1"), request("PR-1", 2)]
		self.assertEqual(api._replace_cancelled_requests(rows), [latest])

	def test_endpoint_checks_owner_and_permissions_before_collapsing(self):
		with (
			patch.object(api, "frappe") as frappe,
			patch.object(api.PROCUREMENT, "workflow", return_value=None),
			patch.object(api, "_add_procurement_costs"),
		):
			frappe.session.user = "requester@example.com"
			amended = request("PR-1-1", amended_from="PR-1")
			frappe.get_list.return_value = [amended, request("PR-1", 2)]
			self.assertEqual(api.get_my_procurement_requests(), [amended])
			self.assertEqual(
				frappe.get_list.call_args.kwargs["filters"],
				{"requested_by": "requester@example.com"},
			)
			frappe.get_all.assert_not_called()

	def test_list_rows_carry_the_virtual_total_the_list_query_drops(self):
		"""`get_list` omits a virtual field silently, so the row is filled in after."""
		row = api.frappe._dict(name="PR-1")
		doc = SimpleNamespace(
			as_dict=lambda: {
				"approver_name": "Ann Approver",
				"requester_name": "Bob Buyer",
				"total_estimated_cost": 70.0,
			}
		)
		with (
			patch.object(api.frappe, "get_doc", return_value=doc),
			patch.object(api.PROCUREMENT, "workflow", return_value=None),
			patch.object(api, "_can_edit_procurement_request", return_value=True),
			patch("commons.requests.budget.request_summary", return_value=None),
		):
			api._add_procurement_costs([row])

		self.assertEqual(row.total_estimated_cost, 70.0)
		self.assertEqual(row.approver_name, "Ann Approver")
		self.assertEqual(row.requester_name, "Bob Buyer")


class TestProcurementUnavailable(TestCase):
	"""A site that does not run ERPNext.

	The section's own doctype is still here -- `Procurement Request` is this
	app's -- which is what makes this different from leave and expenses and why
	`Procurement.requires_apps` names the app rather than a doctype. What is
	missing is everything a request is *about*: the Company it is raised in, the
	Items it orders, the Department Budget it is charged to and the Material
	Request it becomes.

	The permissions endpoint answers, because every page asks it before drawing
	anything. Everything else refuses, and says which app is missing rather than
	claiming a doctype that is plainly there is not.
	"""

	def setUp(self):
		# Two patches for one fact, because `require_available` asks twice: once
		# for the answer and once, when it is no, for which app to name. The
		# module-level patch above says every site has ERPNext, so the first has
		# to be overridden rather than merely re-derived from the second.
		for stand_in in (
			patch.object(api.PROCUREMENT, "available", return_value=False),
			patch.object(api.approvals.apps, "installed", side_effect=lambda app: app != "erpnext"),
		):
			stand_in.start()
			self.addCleanup(stand_in.stop)

	def test_the_permissions_payload_says_there_is_nothing_here(self):
		payload = api.get_procurement_permissions()
		self.assertFalse(payload["read"])
		self.assertFalse(payload["request"])
		self.assertFalse(payload["workflow_access"])
		self.assertIsNone(payload["workflow"])
		self.assertEqual(payload["pending_workflow_actions"], 0)

	def test_the_permissions_payload_asks_the_database_nothing(self):
		with (
			patch.object(api.PROCUREMENT, "workflow", side_effect=AssertionError),
			patch.object(api.frappe, "has_permission", side_effect=AssertionError),
		):
			api.get_procurement_permissions()

	def test_the_refusal_names_the_missing_app(self):
		"""'Procurement Request is not available' would be a puzzle here."""
		with patch.object(api.frappe, "throw", side_effect=ValueError) as throw:
			with self.assertRaises(ValueError):
				api.get_my_procurement_requests()
		self.assertIn("erpnext", throw.call_args.args[0])

	def test_every_other_endpoint_refuses(self):
		calls = (
			("defaults", lambda: api.get_procurement_request_defaults()),
			("save", lambda: api.save_procurement_request({"title": "X"})),
			("mine", lambda: api.get_my_procurement_requests()),
			("transitions", lambda: api.get_procurement_request_transitions('["PR-1"]')),
			("queue", lambda: api.get_procurement_workflow_queue()),
			("lines", lambda: api.get_procurement_request_lines('["PR-1"]')),
		)
		# `get_procurement_approvers` is gated the same way and is deliberately
		# not here: `frappe.validate_and_sanitize_search_inputs` wraps it and
		# reaches the database before the body runs, so site-less it cannot be
		# called at all. Its guard is the same one line as the six above.
		for label, call in calls:
			with self.subTest(endpoint=label):
				with patch.object(api.frappe, "throw", side_effect=ValueError):
					with self.assertRaises(ValueError):
						call()
