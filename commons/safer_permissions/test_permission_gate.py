"""How the gate decides, without a running site.

The interesting logic is the two questions in `commons.safer_permissions.permissions`: does
this user's set of roles put them behind the gate, and have they got past it.
Everything underneath is core's, and is stubbed here.
"""

from unittest import TestCase, addModuleCleanup
from unittest.mock import patch

import frappe

from commons.safer_permissions import permissions
from commons.safer_permissions.permissions import GATE, NOTHING, OWN

DOCTYPE = "Salary Slip"


def perm(role, gated=False, right="read", permlevel=0, if_owner=False):
	return frappe._dict(
		{
			"role": role,
			"permlevel": permlevel,
			right: 1,
			GATE: 1 if gated else 0,
			"if_owner": 1 if if_owner else 0,
		}
	)


def meta(*perms):
	return frappe._dict(permissions=list(perms))


def setUpModule():
	# The site-wide switch reads Commons Settings, and there is no site here.
	# Every class below is about the gate while it is on; `SwitchedOff` is the one
	# that turns it off.
	switch = patch.object(permissions, "gate_switched_on", return_value=True)
	switch.start()
	addModuleCleanup(switch.stop)


class SwitchedOff(TestCase):
	"""The Commons Settings switch stands every part of the gate down."""

	def setUp(self):
		switch = patch.object(permissions, "gate_switched_on", return_value=False)
		switch.start()
		self.addCleanup(switch.stop)

		for name, value in (("get_roles", ["Employee"]), ("get_meta", meta(perm("Employee", gated=True)))):
			stub = patch.object(permissions.frappe, name, return_value=value)
			stub.start()
			self.addCleanup(stub.stop)

	def test_a_gated_role_is_no_longer_held_back(self):
		self.assertIsNone(permissions.gate_scope("employee@example.com", DOCTYPE))

	def test_lists_and_documents_are_left_to_core(self):
		doc = frappe._dict(doctype=DOCTYPE, owner="someone-else@example.com")
		self.assertEqual(permissions.permission_query_conditions("employee@example.com", DOCTYPE), "")
		self.assertTrue(permissions.has_permission(doc=doc, user="employee@example.com"))

	def test_reports_are_no_longer_refused(self):
		with patch.object(permissions.frappe, "get_cached_value", return_value=DOCTYPE):
			self.assertIsNone(permissions.gated_report_doctype("Salary Register", "employee@example.com"))


class GateApplies(TestCase):
	"""Which users the gate holds back."""

	def check(self, roles, perms):
		with (
			patch.object(permissions.frappe, "get_roles", return_value=roles),
			patch.object(permissions.frappe, "get_meta", return_value=meta(*perms)),
		):
			return permissions.gate_scope("employee@example.com", DOCTYPE)

	def test_doctype_nobody_ticked_is_never_gated(self):
		"""The fast path, and the safety: gating is opt-in per role row."""
		self.assertIsNone(self.check(["Employee"], [perm("Employee"), perm("HR Manager")]))

	def test_gated_role_is_held_back(self):
		self.assertEqual(self.check(["Employee"], [perm("Employee", gated=True)]), NOTHING)

	def test_ungated_role_is_not(self):
		self.assertIsNone(self.check(["Employee"], [perm("Employee")]))

	def test_one_ungated_role_beats_a_gated_one(self):
		"""An HR Manager who also holds Employee is an HR Manager."""
		self.assertIsNone(
			self.check(
				["Employee", "HR Manager"],
				[perm("Employee", gated=True), perm("HR Manager")],
			)
		)

	def test_every_granting_role_must_be_gated(self):
		self.assertEqual(
			self.check(
				["Employee", "Intern"],
				[perm("Employee", gated=True), perm("Intern", gated=True)],
			),
			NOTHING,
		)

	def test_roles_the_user_does_not_hold_are_ignored(self):
		self.assertEqual(
			self.check(["Employee"], [perm("Employee", gated=True), perm("HR Manager")]),
			NOTHING,
		)

	def test_no_read_access_at_all_is_core_business_not_ours(self):
		self.assertIsNone(self.check(["Sales User"], [perm("Employee", gated=True)]))

	def test_select_only_access_is_still_gated(self):
		self.assertEqual(
			self.check(["Employee"], [perm("Employee", gated=True, right="select")]), NOTHING
		)

	def test_higher_permlevel_rows_do_not_open_the_gate(self):
		"""Permlevel > 0 governs fields, not rows, so core skips those rows too."""
		self.assertEqual(
			self.check(
				["Employee"],
				[perm("Employee", gated=True), perm("Employee", permlevel=1)],
			),
			NOTHING,
		)

	def test_an_ungated_only_if_creator_role_does_not_beat_the_gate(self):
		"""The failure this module was reported for.

		`Employee` grants read on `Procurement Request` with "Only if Creator"
		ticked, so it reaches the holder's own requests and nobody else's. Read
		as an unrestricted grant it switched the gate off and showed an approver
		every request on the site -- including, as it happened, all of the ones
		she had not raised herself.
		"""
		self.assertEqual(
			self.check(
				["Employee", "Expense Approver"],
				[perm("Employee", if_owner=True), perm("Expense Approver", gated=True)],
			),
			OWN,
		)

	def test_an_only_if_creator_role_still_keeps_its_own_documents(self):
		"""It is not read as nothing either: the gate withholds all but the user's own."""
		self.assertNotEqual(
			self.check(
				["Employee", "Expense Approver"],
				[perm("Employee", if_owner=True), perm("Expense Approver", gated=True)],
			),
			NOTHING,
		)

	def test_an_unrestricted_role_alongside_an_only_if_creator_one_still_wins(self):
		self.assertIsNone(
			self.check(
				["Employee", "Expense Approver", "HR Manager"],
				[
					perm("Employee", if_owner=True),
					perm("Expense Approver", gated=True),
					perm("HR Manager"),
				],
			)
		)

	def test_an_only_if_creator_role_with_nothing_gated_is_left_alone(self):
		"""No tick among the roles held: not this module's business at all."""
		self.assertIsNone(self.check(["Employee"], [perm("Employee", if_owner=True)]))

	def test_administrator_is_never_gated(self):
		with patch.object(
			permissions.frappe, "get_meta", return_value=meta(perm("Employee", gated=True))
		):
			self.assertFalse(permissions.gate_applies("Administrator", DOCTYPE))


class GateSatisfied(TestCase):
	"""What gets a gated user through: a permission aimed at this doctype."""

	def check(self, user_permissions, constraining=("Employee", "Company")):
		with (
			patch.object(permissions.frappe.permissions, "get_user_permissions", return_value=user_permissions),
			patch.object(permissions, "constraining_doctypes", return_value=set(constraining)),
		):
			return permissions.gate_satisfied("employee@example.com", DOCTYPE)

	def held(self, allow, applicable_for):
		return {allow: [frappe._dict(doc="SOME-DOC", applicable_for=applicable_for)]}

	def test_no_user_permissions_at_all_fails_closed(self):
		self.assertFalse(self.check({}))

	def test_a_permission_aimed_at_this_doctype_opens_the_gate(self):
		self.assertTrue(self.check(self.held("Employee", DOCTYPE)))

	def test_a_blanket_permission_does_not_open_the_gate(self):
		"""The hole this closes. `apply_to_all_doctypes` -- an absent
		`applicable_for` -- is the default, and core honours it everywhere. One
		Company restriction created for an unrelated reason would otherwise
		satisfy every gate on the site."""
		self.assertFalse(self.check(self.held("Company", None)))

	def test_a_permission_scoped_to_another_doctype_does_not(self):
		self.assertFalse(self.check(self.held("Employee", "Leave Application")))

	def test_a_permission_that_cannot_reach_the_doctype_does_not(self):
		self.assertFalse(self.check(self.held("Language", DOCTYPE), constraining=("Employee",)))

	def test_the_wrong_dimension_still_opens_it_if_aimed_here(self):
		"""What the checkbox still cannot express. A Company permission pointed at
		this doctype opens the gate and shows every row in that company; closing
		this would need the gate to name which link it wants, and a checkbox has
		nowhere to say so."""
		self.assertTrue(self.check(self.held("Company", DOCTYPE)))


class Hooks(TestCase):
	"""What core is handed once the two questions are answered."""

	# No site is bound here, so `frappe.db` is an unbound proxy and the escaping
	# the owner condition needs cannot be patched onto it. The module's whole
	# view of frappe is stood in for instead; with `blocked_scope` mocked out,
	# these two are all either hook still reaches for.
	stub = frappe._dict(
		db=frappe._dict(escape=lambda value, **kwargs: f"'{value}'"),
		session=frappe._dict(user="employee@example.com"),
	)

	def check(self, blocked, owner="someone-else@example.com"):
		with (
			patch.object(permissions, "blocked_scope", return_value=blocked),
			patch.object(permissions, "frappe", self.stub),
		):
			return (
				permissions.permission_query_conditions("employee@example.com", doctype=DOCTYPE),
				permissions.has_permission(
					doc=frappe._dict(doctype=DOCTYPE, owner=owner), user="employee@example.com"
				),
			)

	def test_a_blocked_user_gets_an_empty_list_and_no_document(self):
		self.assertEqual(self.check(blocked=NOTHING), ("1=0", False))

	def test_everyone_else_is_left_alone(self):
		"""An empty condition, not a permissive one: the hook only ever denies."""
		self.assertEqual(self.check(blocked=None), ("", True))

	def test_an_only_if_creator_grant_survives_the_gate(self):
		"""Narrowed to the user's own rows rather than emptied: the ungated role
		granted those, and the gate was never asked to take them back."""
		self.assertEqual(
			self.check(blocked=OWN),
			("`tabSalary Slip`.`owner` = 'employee@example.com'", False),
		)

	def test_and_the_document_they_own_is_still_readable(self):
		self.assertEqual(
			self.check(blocked=OWN, owner="employee@example.com")[1],
			True,
		)

	def test_owning_it_under_a_different_case_still_counts(self):
		"""Core lowercases both sides, and the owner condition above is compared
		by the database under a case-insensitive collation. An exact compare here
		would list a row and then refuse to open it."""
		self.assertEqual(
			self.check(blocked=OWN, owner="Employee@Example.com")[1],
			True,
		)

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


class PreparedReports(TestCase):
	"""A report's results, sitting in a file once the report has run."""

	def readable(self, gate_applies, report_name="Salary Register"):
		with (
			patch.object(permissions.frappe, "get_cached_value", return_value=DOCTYPE),
			patch.object(permissions, "gate_applies", return_value=gate_applies),
		):
			return permissions.has_prepared_report_permission(
				doc=frappe._dict(doctype="Prepared Report", report_name=report_name),
				user="employee@example.com",
			)

	def test_a_gated_role_cannot_read_one(self):
		"""Refusing the run and then serving the file would be no refusal at all:
		core reaches a finished Prepared Report without going near the wrappers
		above, and lets anyone who may access the report read it."""
		self.assertFalse(self.readable(gate_applies=True))

	def test_an_ungated_role_can(self):
		self.assertTrue(self.readable(gate_applies=False))

	def test_one_naming_no_report_is_left_to_core(self):
		self.assertTrue(self.readable(gate_applies=True, report_name=None))

	def test_a_doctype_level_check_has_nothing_to_refuse(self):
		self.assertTrue(permissions.has_prepared_report_permission(doc=None, user="employee@example.com"))


class Forwarding(TestCase):
	"""The report wrappers hand core whatever core asks for, and nothing else."""

	def call(self, wrapper, core, **request):
		with (
			patch.object(permissions, "_refuse_gated_report"),
			patch.object(permissions, "_core", return_value=core),
			patch.object(permissions.frappe, "form_dict", frappe._dict(request)),
		):
			return wrapper(**request)

	def test_an_argument_core_adds_later_still_reaches_it(self):
		def run(report_name, filters=None, argument_from_a_later_frappe=None):
			return (report_name, filters, argument_from_a_later_frappe)

		self.assertEqual(
			self.call(
				permissions.run_query_report,
				run,
				report_name="Salary Register",
				filters="{}",
				argument_from_a_later_frappe=1,
			),
			("Salary Register", "{}", 1),
		)

	def test_an_argument_core_no_longer_takes_is_dropped_not_fatal(self):
		def make(report_name):
			return report_name

		self.assertEqual(
			self.call(permissions.make_prepared_report, make, report_name="Salary Register", filters="{}", cmd="x"),
			"Salary Register",
		)

	def test_export_is_refused_by_the_name_core_reads(self):
		with (
			patch.object(permissions, "_refuse_gated_report") as refuse,
			patch.object(permissions, "_core", return_value=lambda: None),
			patch.object(permissions.frappe, "form_dict", frappe._dict(report_name="Salary Register")),
		):
			permissions.export_query_report(report_name="Salary Register")
		refuse.assert_called_once_with("Salary Register")


class FailingGracefully(TestCase):
	"""What a report request gets when an upgrade has moved something."""

	def setUp(self):
		def throw(message, exc=frappe.ValidationError, **kwargs):
			raise exc(message)

		# `frappe.throw` and `log_error` both reach for `frappe.local`, which only a
		# request or a site has. What is under test is which one is raised, and why.
		for stub in (
			patch.object(permissions, "_", lambda text: text),
			patch.object(permissions.frappe, "throw", throw),
			patch.object(permissions.frappe, "log_error"),
			patch.object(permissions.frappe, "get_traceback", return_value=""),
		):
			stub.start()
			self.addCleanup(stub.stop)

	def test_a_core_function_that_has_moved_is_a_clear_error(self):
		with patch.object(permissions.frappe, "get_attr", side_effect=AttributeError("gone")):
			with self.assertRaises(frappe.ValidationError) as raised:
				permissions._core(permissions.CORE_RUN)
		self.assertIn("Error Log", str(raised.exception))
		permissions.frappe.log_error.assert_called_once()

	def test_a_gate_check_that_breaks_refuses_rather_than_waving_through(self):
		with patch.object(permissions, "gated_report_doctype", side_effect=KeyError("ref_doctype")):
			with self.assertRaises(frappe.PermissionError) as raised:
				permissions._refuse_gated_report("Salary Register")
		self.assertIn("Commons Settings", str(raised.exception))

	def test_with_the_gate_off_the_check_is_never_made(self):
		"""So unticking it is a way out even when the check itself is what broke."""
		with (
			patch.object(permissions, "gate_switched_on", return_value=False),
			patch.object(permissions.frappe, "get_cached_value", side_effect=AssertionError("asked")),
		):
			permissions._refuse_gated_report("Salary Register")


class CoreStillLooksTheSame(TestCase):
	"""Run after every Frappe upgrade: what the report overrides assume of core.

	The one failure nothing at run time can notice is core no longer calling one
	of these paths -- the override is then simply never reached, and a gated role
	gets the report. So this checks the installed Frappe itself.
	"""

	OVERRIDES = {
		permissions.CORE_RUN: "commons.safer_permissions.permissions.run_query_report",
		permissions.CORE_EXPORT: "commons.safer_permissions.permissions.export_query_report",
		permissions.CORE_MAKE_PREPARED: "commons.safer_permissions.permissions.make_prepared_report",
	}

	def test_hooks_override_exactly_these_paths(self):
		from commons import hooks

		self.assertEqual(hooks.override_whitelisted_methods, self.OVERRIDES)

	def core_function(self, path):
		"""The definition at `path`, read from core's source rather than imported.

		Importing `frappe.desk.query_report` sets up a file logger relative to the
		working directory, which a site-less run from anywhere but `sites/` does not
		have. Reading the source asks the same question without running any of it.
		"""
		import ast
		import importlib.util

		module, _, name = path.rpartition(".")
		with open(importlib.util.find_spec(module).origin, encoding="utf-8") as file:
			tree = ast.parse(file.read())
		return next(
			(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name),
			None,
		)

	def test_each_core_function_still_exists_where_it_did(self):
		for path in self.OVERRIDES:
			with self.subTest(path=path):
				self.assertIsNotNone(self.core_function(path))

	def test_core_still_names_the_report_the_way_the_gate_reads_it(self):
		for path in (permissions.CORE_RUN, permissions.CORE_MAKE_PREPARED):
			with self.subTest(path=path):
				arguments = self.core_function(path).args
				self.assertIn("report_name", [arg.arg for arg in arguments.args + arguments.kwonlyargs])

	def test_the_desk_still_calls_each_path(self):
		import os

		root = os.path.join(os.path.dirname(frappe.__file__), "public", "js")
		source = ""
		for directory, _, files in os.walk(root):
			if "dist" in directory or "node_modules" in directory:
				continue
			for name in files:
				if name.endswith((".js", ".vue", ".ts")):
					with open(os.path.join(directory, name), encoding="utf-8", errors="ignore") as file:
						source += file.read()

		for path in self.OVERRIDES:
			with self.subTest(path=path):
				self.assertIn(path, source)
