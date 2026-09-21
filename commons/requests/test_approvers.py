"""One invariant, in the two places this module used to break it.

A name that arrives from the caller must not decide what gets read. Both
halves of this file are that rule:

* `get_approvers` is handed an `employee` in its `filters`, and HRMS's query
  behind it asks no permission of any kind -- so whoever chose the employee
  chose whose name, department and approver chain came back. The employee is
  now the session's, and `TestApproversAreScopedToTheSession` is what says so.
* `get_procurement_request_lines` and `get_expense_claim_lines` are handed
  parent names, and used to vet them here before reading the children with
  `frappe.get_all`, which is `ignore_permissions=True`. They now read through
  `get_list` with `parent_doctype`, where `frappe.database.query` joins the
  child to its parent and applies the parent's own conditions.
  `TestChildRowsAreReadThroughGetList` is what says so.

These run with a site connected: `frappe.validate_and_sanitize_search_inputs`
reaches the database to check the link target exists before the body runs, so
`get_approvers` cannot be called site-less at all -- which is why
`test_procurement_amendments` leaves its sibling out of the site-less sweep.
Nothing here writes anything.
"""

import json
import unittest
from unittest.mock import patch

import frappe

from commons.requests import approvers
from commons.requests import expense as expense_api
from commons.requests import procurement as procurement_api

# The link field's target, which is what the first argument always is -- never
# the request being raised. That one arrives in `filters`.
LINK_TARGET = "User"

# Where HRMS's query actually lives, so the patch catches the late import
# `get_approvers` does inside its body.
HRMS_QUERY = "hrms.hr.doctype.department_approver.department_approver.get_approvers"


@unittest.skipUnless(
	frappe.db.exists("DocType", "Department Approver", cache=True),
	"HRMS is not on this site, so there is no approver query to scope.",
)
class TestApproversAreScopedToTheSession(unittest.TestCase):
	"""What `get_approvers` asks HRMS, given what a caller asked it."""

	def _filters_handed_to_hrms(self, sent: dict | str | list | None) -> dict | None:
		"""Call the endpoint and return the `filters` HRMS was given, or None.

		None means HRMS was never reached, which is the answer for every input
		that names no request this app draws a picker for.
		"""
		with patch(HRMS_QUERY, return_value=[]) as hrms:
			approvers.get_approvers(LINK_TARGET, "", "name", 0, 10, sent)
		if not hrms.called:
			return None
		return hrms.call_args.args[5]

	def test_the_employee_is_the_sessions_not_the_payloads(self):
		"""The whole of the fix: a payload naming somebody else is overruled."""
		with patch.object(approvers, "session_employee_name", return_value="HR-EMP-MINE"):
			handed = self._filters_handed_to_hrms(
				{"employee": "HR-EMP-SOMEBODY-ELSE", "doctype": "Leave Application"}
			)
		self.assertEqual(handed["employee"], "HR-EMP-MINE")

	def test_a_department_in_the_payload_is_dropped(self):
		"""HRMS prefers a `department` in the filters over the employee's own.

		Left in, it would put the scoping back in the caller's hands one field
		over: the employee would be theirs and the tree walked would not be.
		"""
		with patch.object(approvers, "session_employee_name", return_value="HR-EMP-MINE"):
			handed = self._filters_handed_to_hrms(
				{
					"employee": "HR-EMP-MINE",
					"department": "Somebody Else's Department",
					"doctype": "Expense Claim",
				}
			)
		self.assertNotIn("department", handed)

	def test_the_callers_filters_are_not_mutated(self):
		"""A copy, so a caller holding the dict does not see it rewritten."""
		sent = {"employee": "HR-EMP-SOMEBODY-ELSE", "doctype": "Leave Application"}
		with patch.object(approvers, "session_employee_name", return_value="HR-EMP-MINE"):
			self._filters_handed_to_hrms(sent)
		self.assertEqual(sent["employee"], "HR-EMP-SOMEBODY-ELSE")

	def test_a_login_with_no_employee_record_gets_no_picker(self):
		"""Nothing to raise, so nobody to pick -- and HRMS is never asked."""
		with patch.object(approvers, "session_employee_name", return_value=None):
			self.assertIsNone(
				self._filters_handed_to_hrms(
					{"employee": "HR-EMP-SOMEBODY-ELSE", "doctype": "Leave Application"}
				)
			)

	def test_a_request_this_app_draws_no_picker_for_is_refused(self):
		"""`Shift Request` is HRMS's to answer for and not this app's."""
		with patch.object(approvers, "session_employee_name", return_value="HR-EMP-MINE"):
			self.assertIsNone(
				self._filters_handed_to_hrms(
					{"employee": "HR-EMP-MINE", "doctype": "Shift Request"}
				)
			)

	def test_filters_that_name_no_request_are_refused(self):
		"""Every shape a direct caller can send that a picker never would.

		A GET's `filters` arrives as a JSON string, and nothing stops it being a
		list or absent -- so "not a dict" and "a dict naming no request" have to
		answer the same way as `Shift Request` above.
		"""
		for label, sent in (
			("none", None),
			("a list of filter triples", [["employee", "=", "HR-EMP-MINE"]]),
			("a JSON list", "[]"),
			("a dict with no doctype", {"employee": "HR-EMP-MINE"}),
			("a JSON string naming no request", json.dumps({"employee": "HR-EMP-MINE"})),
		):
			with self.subTest(filters=label):
				with patch.object(approvers, "session_employee_name", return_value="HR-EMP-MINE"):
					self.assertIsNone(self._filters_handed_to_hrms(sent))

	def test_a_json_string_naming_a_request_is_honoured_and_still_scoped(self):
		"""Parsed rather than refused -- but the employee is still overruled."""
		sent = json.dumps({"employee": "HR-EMP-SOMEBODY-ELSE", "doctype": "Leave Application"})
		with patch.object(approvers, "session_employee_name", return_value="HR-EMP-MINE"):
			handed = self._filters_handed_to_hrms(sent)
		self.assertEqual(handed["employee"], "HR-EMP-MINE")


class TestChildRowsAreReadThroughGetList(unittest.TestCase):
	"""That the child-table reads go through the permission-checked query.

	Asserted as "which function was called, with `parent_doctype` set" rather
	than by counting rows, because the rows depend on what a site happens to
	hold. What must not rot is the choice between `get_list` and `get_all`:
	the second is `ignore_permissions=True`, and the whole of the parent's
	permissions -- including this app's gate -- rides on the first.
	"""

	def _read_through(self, call) -> dict:
		"""Run `call` with both query functions watched; report what it used."""
		with (
			patch.object(frappe, "get_list", return_value=[]) as get_list,
			patch.object(frappe, "get_all", return_value=[]) as get_all,
		):
			call()
			return {
				"get_list": get_list.call_args_list,
				"get_all": get_all.call_args_list,
			}

	def _assert_permission_checked(self, used: dict, child: str, parent: str):
		self.assertEqual(
			[call.args[0] for call in used["get_all"]],
			[],
			f"{child} was read with get_all, which ignores permissions",
		)
		reads = [call for call in used["get_list"] if call.args and call.args[0] == child]
		self.assertTrue(reads, f"{child} was not read with get_list at all")
		self.assertEqual(reads[0].kwargs.get("parent_doctype"), parent)

	@unittest.skipUnless(
		frappe.db.exists("DocType", "Procurement Request Item", cache=True),
		"Procurement is not set up on this site.",
	)
	def test_procurement_lines_are_read_with_the_parents_permissions(self):
		used = self._read_through(
			lambda: procurement_api.get_procurement_request_lines(json.dumps(["PRQ-DOES-NOT-EXIST"]))
		)
		self._assert_permission_checked(
			used, "Procurement Request Item", "Procurement Request"
		)

	@unittest.skipUnless(
		frappe.db.exists("DocType", "Expense Claim Detail", cache=True),
		"HRMS is not on this site.",
	)
	def test_expense_lines_are_read_with_the_parents_permissions(self):
		used = self._read_through(
			lambda: expense_api.get_expense_claim_lines(json.dumps(["HR-EXP-DOES-NOT-EXIST"]))
		)
		self._assert_permission_checked(used, "Expense Claim Detail", "Expense Claim")

	def test_asking_about_nothing_reads_nothing(self):
		"""An empty list short-circuits, so no query is issued at all."""
		for label, call in (
			("procurement", lambda: procurement_api.get_procurement_request_lines("[]")),
			("expense", lambda: expense_api.get_expense_claim_lines("[]")),
		):
			with self.subTest(section=label):
				used = self._read_through(call)
				self.assertEqual(used["get_list"], [])
				self.assertEqual(used["get_all"], [])
