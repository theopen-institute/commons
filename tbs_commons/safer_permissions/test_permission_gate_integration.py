"""The gate against a real site: bench --site SITE execute tbs_commons.test_permission_gate_integration.run

Not purely rollback-only, unlike the budget suite. Registering the gate creates
a `Permission Type`, which adds Custom Fields to `DocPerm`, `Custom DocPerm`
and `DocShare` -- DDL, which MariaDB commits whatever this suite does
afterwards. `_register_gate` and `_retire_gate` bracket the run to put that
back; everything within it rolls back.

`Branch` stands in for a payslip. It has one field, it autonames from it, no
role outside HR can read it, and this app's are the only permission hooks
registered against it -- so an assertion that fails here failed because of the
gate. The fixture matters: on a doctype readable by `Desk User` or `All`, every
System User holds an ungated role and the gate correctly stands down.
"""

import unittest

import frappe

from tbs_commons.safer_permissions.install import sync_permission_gates
from tbs_commons.safer_permissions.permissions import GATE, SETTINGS

DOCTYPE = "Branch"
REQUIRED = "Branch"
REPORT = "TBS Gate Test Report"

MINE = "TBS Gate Test Mine"
THEIRS = "TBS Gate Test Theirs"

GATED_ROLE = "TBS Gate Test Gated"
OPEN_ROLE = "TBS Gate Test Open"
GATED_USER = "tbs-gate-gated@example.com"
OPEN_USER = "tbs-gate-open@example.com"


class TestPermissionGate(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint("permission_gate_test")
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		_drop_user_permissions()
		frappe.db.rollback(save_point="permission_gate_test")
		frappe.clear_cache()

	def visible(self, user):
		"""Which of the two fixtures this user can list."""
		frappe.set_user(user)
		return set(frappe.get_list(DOCTYPE, filters={"name": ["in", (MINE, THEIRS)]}, pluck="name"))

	def readable(self, user, name):
		frappe.set_user(user)
		return frappe.permissions.has_permission(DOCTYPE, "read", doc=name, user=user, print_logs=False)

	def test_the_checkbox_exists_after_registration(self):
		"""Without this the gate is inert, so everything below is meaningless."""
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Custom DocPerm", "fieldname": GATE}))
		gated = [p for p in frappe.get_meta(DOCTYPE).permissions if p.role == GATED_ROLE]
		self.assertTrue(gated and gated[0].get(GATE))

	def test_a_gated_role_with_no_user_permission_sees_nothing(self):
		"""The whole point: the role grants read, and read yields no rows."""
		self.assertTrue(frappe.permissions.has_permission(DOCTYPE, "read", user=GATED_USER))
		self.assertEqual(self.visible(GATED_USER), set())

	def test_a_gated_role_cannot_open_a_document_either(self):
		self.assertFalse(self.readable(GATED_USER, MINE))

	def test_an_ungated_role_is_untouched(self):
		self.assertEqual(self.visible(OPEN_USER), {MINE, THEIRS})
		self.assertTrue(self.readable(OPEN_USER, MINE))

	def test_the_user_permission_opens_the_gate_and_narrows_it(self):
		_user_permission(GATED_USER, MINE)
		self.assertEqual(self.visible(GATED_USER), {MINE})
		self.assertTrue(self.readable(GATED_USER, MINE))
		self.assertFalse(self.readable(GATED_USER, THEIRS))

	def test_a_user_permission_on_something_else_does_not_open_it(self):
		_user_permission(GATED_USER, frappe.db.get_value("Language", {}, "name"), allow="Language")
		self.assertEqual(self.visible(GATED_USER), set())

	def test_holding_an_ungated_role_as_well_beats_the_gate(self):
		"""An HR Manager who also holds Employee is an HR Manager."""
		frappe.get_doc("User", GATED_USER).add_roles(OPEN_ROLE)
		frappe.clear_cache(user=GATED_USER)
		self.assertEqual(self.visible(GATED_USER), {MINE, THEIRS})

	def test_a_gated_role_is_refused_reports(self):
		from tbs_commons.safer_permissions.permissions import _refuse_gated_report

		# Even with the gate satisfied: report SQL never consults a User Permission.
		_user_permission(GATED_USER, MINE)

		frappe.set_user(GATED_USER)
		self.assertRaises(frappe.PermissionError, _refuse_gated_report, REPORT)

		frappe.set_user(OPEN_USER)
		_refuse_gated_report(REPORT)


def _register_gate():
	_fixtures()
	_roles_and_users()

	settings = frappe.get_single(SETTINGS)
	# Idempotent: a run killed between setup and teardown leaves its rule, and
	# appending a second would only trip the settings' own duplicate check.
	settings.rules = [rule for rule in settings.rules if rule.document_type != DOCTYPE]
	settings.append("rules", {"document_type": DOCTYPE, "required_user_permission": REQUIRED})
	settings.save()
	sync_permission_gates()

	frappe.permissions.add_permission(DOCTYPE, GATED_ROLE, 0)
	frappe.permissions.update_permission_property(DOCTYPE, GATED_ROLE, 0, GATE, 1)
	frappe.permissions.add_permission(DOCTYPE, OPEN_ROLE, 0)

	frappe.db.commit()
	frappe.clear_cache()


def _retire_gate(had_custom_perms: bool):
	stale = {"parent": DOCTYPE} if not had_custom_perms else {"parent": DOCTYPE, "role": ["in", (GATED_ROLE, OPEN_ROLE)]}
	for name in frappe.get_all("Custom DocPerm", filters=stale, pluck="name"):
		frappe.delete_doc("Custom DocPerm", name, force=True, ignore_permissions=True)

	if permission_type := frappe.db.get_value("Permission Type", {"perm_type": GATE, "doc_type": DOCTYPE}):
		frappe.delete_doc("Permission Type", permission_type, force=True, ignore_permissions=True)

	settings = frappe.get_single(SETTINGS)
	settings.rules = [rule for rule in settings.rules if rule.document_type != DOCTYPE]
	settings.save()

	_drop_user_permissions()
	for doctype, names in (("Report", (REPORT,)), (DOCTYPE, (MINE, THEIRS)), ("User", (GATED_USER, OPEN_USER)), ("Role", (GATED_ROLE, OPEN_ROLE))):
		for name in names:
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache()


def _fixtures():
	for branch in (MINE, THEIRS):
		if not frappe.db.exists(DOCTYPE, branch):
			frappe.get_doc({"doctype": DOCTYPE, "branch": branch}).insert(ignore_permissions=True)

	if not frappe.db.exists("Report", REPORT):
		frappe.get_doc(
			{
				"doctype": "Report",
				"report_name": REPORT,
				"ref_doctype": DOCTYPE,
				"report_type": "Report Builder",
				"is_standard": "No",
			}
		).insert(ignore_permissions=True)


def _roles_and_users():
	for role in (GATED_ROLE, OPEN_ROLE):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()

	for user, role in ((GATED_USER, GATED_ROLE), (OPEN_USER, OPEN_ROLE)):
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "Gate Test", "user_type": "System User"}
			).insert()
		frappe.get_doc("User", user).add_roles(role)


def _user_permission(user, for_value, allow=REQUIRED):
	frappe.get_doc(
		{"doctype": "User Permission", "user": user, "allow": allow, "for_value": for_value}
	).insert(ignore_permissions=True)
	frappe.cache.hdel("user_permissions", user)


def _drop_user_permissions():
	names = frappe.get_all("User Permission", filters={"user": ["in", (GATED_USER, OPEN_USER)]}, pluck="name")
	for name in names:
		frappe.delete_doc("User Permission", name, force=True, ignore_permissions=True)
	for user in (GATED_USER, OPEN_USER):
		frappe.cache.hdel("user_permissions", user)


def run():
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	# `Permission Type` is writable during install, migrate, developer mode or
	# tests; saying which this is also stops core exporting it as a fixture
	# into whichever app happens to own the gated doctype.
	frappe.flags.in_test = True
	# `add_permission` copies a doctype's standard `DocPerm` rows into `Custom
	# DocPerm` the first time it is customised, and core reads `Custom DocPerm`
	# from then on. Noted before anything runs, so the teardown knows whether
	# to hand the doctype back to its own app -- and so that a failure during
	# setup still tears down.
	had_custom_perms = bool(frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}))
	try:
		_register_gate()
		result = unittest.TextTestRunner(verbosity=2).run(
			unittest.defaultTestLoader.loadTestsFromTestCase(TestPermissionGate)
		)
		if not result.wasSuccessful():
			raise RuntimeError("Permission gate integration tests failed")
		return dict(tests=result.testsRun, success=True)
	finally:
		frappe.db.rollback()
		_retire_gate(had_custom_perms)
		frappe.flags.in_test = False
		frappe.set_user(original_user)
