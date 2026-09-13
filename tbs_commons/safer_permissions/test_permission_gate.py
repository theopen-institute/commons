"""How the gate decides, without a running site.

The interesting logic is the two questions in `tbs_commons.safer_permissions.permissions`: does
this user's set of roles put them behind the gate, and have they got past it.
Everything underneath is core's, and is stubbed here.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from tbs_commons.safer_permissions import permissions
from tbs_commons.safer_permissions.permissions import GATE

DOCTYPE = "Salary Slip"


def perm(role, gated=False, right="read", permlevel=0):
	return frappe._dict({"role": role, "permlevel": permlevel, right: 1, GATE: 1 if gated else 0})


def meta(*perms):
	return frappe._dict(permissions=list(perms))


class GateApplies(TestCase):
	"""Which users the gate holds back."""

	def check(self, roles, perms, gateable=True):
		with (
			patch.object(
				permissions, "get_doctype_ptype_map", return_value={DOCTYPE: [GATE]} if gateable else {}
			),
			patch.object(permissions.frappe, "get_roles", return_value=roles),
			patch.object(permissions.frappe, "get_meta", return_value=meta(*perms)),
		):
			return permissions.gate_applies("employee@example.com", DOCTYPE)

	def test_doctype_without_the_checkbox_is_never_gated(self):
		self.assertFalse(self.check(["Employee"], [perm("Employee", gated=True)], gateable=False))

	def test_gated_role_is_held_back(self):
		self.assertTrue(self.check(["Employee"], [perm("Employee", gated=True)]))

	def test_ungated_role_is_not(self):
		self.assertFalse(self.check(["Employee"], [perm("Employee")]))

	def test_one_ungated_role_beats_a_gated_one(self):
		"""An HR Manager who also holds Employee is an HR Manager."""
		self.assertFalse(
			self.check(
				["Employee", "HR Manager"],
				[perm("Employee", gated=True), perm("HR Manager")],
			)
		)

	def test_every_granting_role_must_be_gated(self):
		self.assertTrue(
			self.check(
				["Employee", "Intern"],
				[perm("Employee", gated=True), perm("Intern", gated=True)],
			)
		)

	def test_roles_the_user_does_not_hold_are_ignored(self):
		self.assertTrue(
			self.check(["Employee"], [perm("Employee", gated=True), perm("HR Manager")])
		)

	def test_no_read_access_at_all_is_core_business_not_ours(self):
		self.assertFalse(self.check(["Sales User"], [perm("Employee", gated=True)]))

	def test_select_only_access_is_still_gated(self):
		self.assertTrue(self.check(["Employee"], [perm("Employee", gated=True, right="select")]))

	def test_higher_permlevel_rows_do_not_open_the_gate(self):
		"""Permlevel > 0 governs fields, not rows, so core skips those rows too."""
		self.assertTrue(
			self.check(
				["Employee"],
				[perm("Employee", gated=True), perm("Employee", permlevel=1)],
			)
		)

	def test_administrator_is_never_gated(self):
		with (
			patch.object(permissions, "get_doctype_ptype_map", return_value={DOCTYPE: [GATE]}),
			patch.object(permissions.frappe, "get_meta", return_value=meta(perm("Employee", gated=True))),
		):
			self.assertFalse(permissions.gate_applies("Administrator", DOCTYPE))


class GateSatisfied(TestCase):
	"""What gets a gated user through."""

	def check(self, user_permissions, required):
		with (
			patch.object(permissions.frappe.permissions, "get_user_permissions", return_value=user_permissions),
			patch.object(permissions, "required_user_permissions", return_value=required),
		):
			return permissions.gate_satisfied("employee@example.com", DOCTYPE)

	def test_no_user_permissions_at_all_fails_closed(self):
		self.assertFalse(self.check({}, ["Employee"]))

	def test_the_required_user_permission_opens_the_gate(self):
		self.assertTrue(
			self.check({"Employee": [frappe._dict(doc="HR-EMP-0001", applicable_for=None)]}, ["Employee"])
		)

	def test_a_user_permission_for_something_else_does_not(self):
		self.assertFalse(
			self.check({"Company": [frappe._dict(doc="TBS", applicable_for=None)]}, ["Employee"])
		)

	def test_a_permission_scoped_to_another_doctype_does_not(self):
		"""`applicable_for` elsewhere means it never restricts this doctype."""
		self.assertFalse(
			self.check(
				{"Employee": [frappe._dict(doc="HR-EMP-0001", applicable_for="Leave Application")]},
				["Employee"],
			)
		)

	def test_every_configured_rule_must_be_met(self):
		held = {"Employee": [frappe._dict(doc="HR-EMP-0001", applicable_for=None)]}
		self.assertFalse(self.check(held, ["Employee", "Company"]))


class Hooks(TestCase):
	"""What core is handed once the two questions are answered."""

	def check(self, blocked):
		with patch.object(permissions, "is_blocked", return_value=blocked):
			return (
				permissions.permission_query_conditions("employee@example.com", doctype=DOCTYPE),
				permissions.has_permission(doc=frappe._dict(doctype=DOCTYPE), user="employee@example.com"),
			)

	def test_a_blocked_user_gets_an_empty_list_and_no_document(self):
		self.assertEqual(self.check(blocked=True), ("1=0", False))

	def test_everyone_else_is_left_alone(self):
		"""An empty condition, not a permissive one: the hook only ever denies."""
		self.assertEqual(self.check(blocked=False), ("", True))

	def test_a_doctype_level_check_has_nothing_to_gate(self):
		self.assertTrue(permissions.has_permission(doc=None, user="employee@example.com"))


class Reports(TestCase):
	"""Query and Script Reports, which honour neither hook."""

	def refuse(self, gate_applies):
		def throw(message, exc=Exception, **kwargs):
			raise exc(message)

		with (
			# `frappe.throw` logs the message through `frappe.local`, which
			# only a request or a site has. The decision is what is under test.
			patch.object(permissions, "_", lambda text: text),
			patch.object(permissions.frappe, "throw", throw),
			patch.object(permissions.frappe, "get_cached_value", return_value=DOCTYPE),
			patch.object(permissions.frappe, "session", frappe._dict(user="employee@example.com")),
			patch.object(permissions, "gate_applies", return_value=gate_applies),
		):
			permissions._refuse_gated_report("Salary Register")

	def test_a_gated_role_is_refused_even_with_its_user_permission(self):
		"""Report SQL never consults a User Permission, so holding one changes nothing."""
		with self.assertRaises(frappe.PermissionError):
			self.refuse(gate_applies=True)

	def test_an_ungated_role_runs_the_report(self):
		self.refuse(gate_applies=False)

	def test_a_report_without_a_name_is_left_to_core(self):
		permissions._refuse_gated_report(None)
