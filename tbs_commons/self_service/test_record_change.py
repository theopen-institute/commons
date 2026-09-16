"""Rollback-only integration suite: bench --site SITE execute tbs_commons.self_service.test_record_change.run.

What these pin is the one promise the section makes and the unit tests cannot
check: a record changes when, and only when, somebody approves a change to it.
Everything else -- the read-only page, the diff, the queue -- is a consequence of
that, and would be worth nothing if a proposal could write to the record on its
own.

So each test is a whole round trip through the real doctype, the real Workflow
and real permissions, asserted against the referenced record afterwards. Mocking
any of those would leave exactly the layer that could be wrong untested.

`Employee` is the record under test because it is the one registered policy. The
machinery being tested is not Employee's -- see
`tbs_commons.self_service.registry` -- but a suite that exercised a made-up
doctype would be testing a fixture rather than the thing that ships.
"""

import json
import unittest

import frappe

from tbs_commons.self_service import api, registry

RECORD = "Employee"


class TestRecordChangeRequest(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint("self_service_test")
		self.addCleanup(lambda: frappe.db.rollback(save_point="self_service_test"))
		self.addCleanup(frappe.set_user, "Administrator")

		frappe.set_user("Administrator")
		self.user = self.new_user()
		self.employee = self.new_employee(self.user)

	def new_user(self) -> str:
		"""A fresh login with the Employee role and nothing else.

		Deliberately not one of the site's existing users: Administrator holds
		every role, so a rule that only bites people *without* HR's roles would
		pass against it while being broken for everyone it applies to.
		"""
		user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"self-service-{frappe.generate_hash(length=8)}@example.com",
				first_name="Self",
				last_name="Service",
				send_welcome_email=0,
			)
		).insert(ignore_permissions=True)
		user.add_roles("Employee")
		return user.name

	def new_employee(self, user: str) -> str:
		company = frappe.db.get_value("Company", "_Test Company", "name") or frappe.db.get_value(
			"Company", {}, "name"
		)
		return (
			frappe.get_doc(
				dict(
					doctype="Employee",
					first_name="Self",
					last_name="Service",
					gender=frappe.db.get_value("Gender", {}, "name"),
					date_of_birth="1990-01-01",
					date_of_joining="2020-01-01",
					status="Active",
					company=company,
					user_id=user,
					cell_number="0712 000 000",
				)
			)
			.insert(ignore_permissions=True)
			.name
		)

	def propose(self, **values) -> str:
		frappe.set_user(self.user)
		created = api.request_change(
			RECORD,
			json.dumps(
				{
					"reason": "Integration test",
					"changes": [
						{"fieldname": fieldname, "proposed_value": value}
						for fieldname, value in values.items()
					],
				}
			),
		)
		return created["name"]

	def field(self, fieldname):
		return frappe.db.get_value(RECORD, self.employee, fieldname)

	# -- the registry ------------------------------------------------------

	def test_employee_is_registered_and_resolves_to_this_users_record(self):
		self.assertIn(RECORD, registry.registered())
		frappe.set_user(self.user)
		self.assertEqual(registry.session_record(RECORD).name, self.employee)
		self.assertTrue(registry.session_owns(RECORD, self.employee))

	def test_a_leaver_stops_owning_their_record(self):
		"""The policy's filters, applied where ownership is decided rather than
		remembered separately by each caller."""
		frappe.set_user("Administrator")
		frappe.db.set_value(RECORD, self.employee, "status", "Left")
		frappe.set_user(self.user)
		self.assertFalse(registry.session_owns(RECORD, self.employee))
		self.assertIsNone(api.get_my_record(RECORD))

	def test_an_unregistered_doctype_cannot_be_requested_against(self):
		"""Whatever anyone's permissions say."""
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError):
			api.request_change(
				"Company", json.dumps({"changes": [{"fieldname": "abbr", "proposed_value": "X"}]})
			)

	# -- the promise -------------------------------------------------------

	def test_raising_a_request_changes_nothing_on_the_record(self):
		"""The read-only half. Nothing between the form and an approval writes."""
		self.propose(cell_number="0799 999 999", passport_number="AA1234567")
		self.assertEqual(self.field("cell_number"), "0712 000 000")
		self.assertIsNone(self.field("passport_number"))

	def test_approving_applies_every_row(self):
		name = self.propose(cell_number="0799 999 999", passport_number="AA1234567")
		frappe.set_user("Administrator")
		api.decide_change(name, "Approve")
		self.assertEqual(self.field("cell_number"), "0799 999 999")
		self.assertEqual(self.field("passport_number"), "AA1234567")

	def test_declining_applies_nothing_and_keeps_the_reason(self):
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user("Administrator")
		api.decide_change(name, "Reject", note="Ring the office first.")
		self.assertEqual(self.field("cell_number"), "0712 000 000")
		doc = frappe.get_doc(api.DOCTYPE, name)
		self.assertEqual(doc.status, "Rejected")
		self.assertEqual(doc.review_note, "Ring the office first.")
		# Still amendable, which is what docstatus 0 buys -- a declined request is
		# a conversation, not a dead end.
		self.assertEqual(doc.docstatus, 0)

	def test_the_owner_can_withdraw_their_own_and_nothing_is_applied(self):
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user(self.user)
		api.decide_change(name, "Withdraw")
		self.assertEqual(frappe.db.get_value(api.DOCTYPE, name, "status"), "Withdrawn")
		self.assertEqual(self.field("cell_number"), "0712 000 000")

	def test_the_owner_cannot_approve_their_own(self):
		"""The one thing that would make the whole section decorative."""
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user(self.user)
		with self.assertRaises(Exception):
			api.decide_change(name, "Approve")
		self.assertEqual(self.field("cell_number"), "0712 000 000")

	# -- what may be proposed ----------------------------------------------

	def test_a_field_the_policy_withholds_is_refused(self):
		"""Not enforced by the endpoint but by the document, so the desk is covered too."""
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			api.request_change(
				RECORD, json.dumps({"changes": [{"fieldname": "department", "proposed_value": "X"}]})
			)

	def test_a_request_that_asks_for_nothing_is_refused(self):
		frappe.set_user(self.user)
		with self.assertRaises(frappe.ValidationError):
			api.request_change(
				RECORD,
				json.dumps({"changes": [{"fieldname": "cell_number", "proposed_value": "0712 000 000"}]}),
			)

	def test_a_request_cannot_name_somebody_elses_record(self):
		other = self.new_employee(self.new_user())
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			api.request_change(
				RECORD,
				json.dumps(
					{
						"reference_name": other,
						"changes": [{"fieldname": "cell_number", "proposed_value": "0799 999 999"}],
					}
				),
			)

	def test_a_select_field_only_accepts_its_own_options(self):
		"""Asked while the dropdown that produced it is still on screen, rather
		than days later on the approver's behalf."""
		frappe.set_user(self.user)
		with self.assertRaises(frappe.ValidationError):
			api.request_change(
				RECORD, json.dumps({"changes": [{"fieldname": "blood_group", "proposed_value": "Q+"}]})
			)

	# -- what the request records ------------------------------------------

	def test_the_before_value_is_captured_not_taken_from_the_request(self):
		frappe.set_user(self.user)
		created = api.request_change(
			RECORD,
			json.dumps(
				{
					"changes": [
						{
							"fieldname": "cell_number",
							"current_value": "a number this employee never had",
							"proposed_value": "0799 999 999",
						}
					]
				}
			),
		)
		doc = frappe.get_doc(api.DOCTYPE, created["name"])
		self.assertEqual(doc.changes[0].current_value, "0712 000 000")
		self.assertEqual(doc.changes[0].label, "Mobile")
		# Captured so a queue can read without loading every referenced document.
		self.assertEqual(doc.reference_title, "Self Service")

	def test_the_before_value_is_the_one_replaced_not_the_one_proposed_against(self):
		"""Re-captured on every validate, including the one inside `submit()`, so
		an approved request preserves the change that was actually made."""
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user("Administrator")
		# HR edits the record by hand while the request sits in the queue.
		frappe.db.set_value(RECORD, self.employee, "cell_number", "0733 111 111")
		api.decide_change(name, "Approve")
		row = frappe.get_doc(api.DOCTYPE, name).changes[0]
		self.assertEqual(row.current_value, "0733 111 111")
		self.assertEqual(self.field("cell_number"), "0799 999 999")

	# -- the queues ---------------------------------------------------------

	def test_an_open_request_is_in_the_pending_queue_and_a_settled_one_is_not(self):
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user("Administrator")
		self.assertIn(name, [row["name"] for row in api.get_change_queue()])
		self.assertNotIn(name, [row["name"] for row in api.get_change_queue(decided=1)])

		api.decide_change(name, "Reject", note="No.")
		self.assertNotIn(name, [row["name"] for row in api.get_change_queue()])
		self.assertIn(name, [row["name"] for row in api.get_change_queue(decided=1)])

	def test_the_queue_can_be_narrowed_to_one_record_type(self):
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user("Administrator")
		self.assertIn(name, [row["name"] for row in api.get_change_queue(doctype=RECORD)])
		self.assertNotIn(name, [row["name"] for row in api.get_change_queue(doctype="Company")])

	def test_the_owner_sees_their_own_request_and_its_diff(self):
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user(self.user)
		mine = {row["name"]: row for row in api.get_my_changes()}
		self.assertIn(name, mine)
		self.assertTrue(mine[name]["open"])
		self.assertEqual(
			[
				(row["fieldname"], row["current_value"], row["proposed_value"])
				for row in mine[name]["changes"]
			],
			[("cell_number", "0712 000 000", "0799 999 999")],
		)

	def test_one_persons_requests_are_not_anothers(self):
		"""`get_my_changes` filters on the records this login owns, so a second
		employee's request is invisible to the first."""
		mine = self.propose(cell_number="0799 999 999")
		frappe.set_user("Administrator")
		other_user = self.new_user()
		other_employee = self.new_employee(other_user)
		frappe.set_user(other_user)
		theirs = api.request_change(
			RECORD, json.dumps({"changes": [{"fieldname": "cell_number", "proposed_value": "0700 1"}]})
		)["name"]
		self.assertEqual([row["name"] for row in api.get_my_changes()], [theirs])
		frappe.set_user(self.user)
		self.assertEqual([row["name"] for row in api.get_my_changes()], [mine])
		self.assertTrue(other_employee)

	def test_the_record_is_the_session_users_own_and_carries_no_pay(self):
		frappe.set_user(self.user)
		record = api.get_my_record(RECORD)
		self.assertEqual(record["name"], self.employee)
		for fieldname in ("ctc", "salary_mode", "bank_ac_no"):
			self.assertNotIn(fieldname, record)

	def test_a_login_that_owns_no_record_has_no_profile(self):
		frappe.set_user("Administrator")
		stranger = self.new_user()
		frappe.set_user(stranger)
		self.assertIsNone(api.get_my_record(RECORD))
		self.assertFalse(api.get_change_permissions(RECORD)["read"])
		self.assertEqual(api.get_my_changes(), [])


def run():
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		result = unittest.TextTestRunner(verbosity=2).run(
			unittest.defaultTestLoader.loadTestsFromTestCase(TestRecordChangeRequest)
		)
		if not result.wasSuccessful():
			raise RuntimeError("Record change integration tests failed")
		return dict(tests=result.testsRun, success=True)
	finally:
		frappe.db.rollback()
		frappe.set_user(original_user)
