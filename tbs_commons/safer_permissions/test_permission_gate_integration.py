"""The gate against a real site: bench --site SITE execute tbs_commons.test_permission_gate_integration.run

Not purely rollback-only, unlike the budget suite. The `Custom DocPerm` rows are
committed so other connections see them, and `_register_gate` and `_retire_gate`
bracket the run to put them back; everything within it rolls back. The gate
column itself is created once by `sync_gate_field` and left alone.

`Branch` stands in for a payslip. It has one field, it autonames from it, no
role outside HR can read it, and this app's are the only permission hooks
registered against it -- so an assertion that fails here failed because of the
gate. The fixture matters: on a doctype readable by `Desk User` or `All`, every
System User holds an ungated role and the gate correctly stands down.
"""

import unittest

import frappe

from tbs_commons.safer_permissions.install import sync_gate_field
from tbs_commons.safer_permissions.permissions import GATE, clear_gated_doctypes

DOCTYPE = "Branch"
REQUIRED = "Branch"
REPORT = "TBS Gate Test Report"

MINE = "TBS Gate Test Mine"
THEIRS = "TBS Gate Test Theirs"
# Owned by the gated user, so an "Only if Creator" role has something to reach.
OWNED = "TBS Gate Test Owned"

GATED_ROLE = "TBS Gate Test Gated"
OPEN_ROLE = "TBS Gate Test Open"
OWNER_ROLE = "TBS Gate Test Owner"
GATED_USER = "tbs-gate-gated@example.com"
OPEN_USER = "tbs-gate-open@example.com"


class TestPermissionGate(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		"""Stand the gate up once for the class, and take it down after.

		These fixtures cannot live in `setUp`: the `Custom DocPerm` rows have to
		be committed so that permission lookups on other connections see them,
		which a per-test savepoint would undo. Bracketing the class is also what
		lets `bench run-tests` run this suite at all -- it was previously only
		reachable through `run()` below, which did the bracketing itself, so
		under the standard runner every fixture was missing.
		"""
		super().setUpClass()
		cls._original_user = frappe.session.user
		frappe.set_user("Administrator")
		# `add_permission` copies a doctype's standard `DocPerm` rows into
		# `Custom DocPerm` the first time it is customised, and core reads
		# `Custom DocPerm` from then on. Noted before anything runs, so the
		# teardown knows whether to hand the doctype back to its own app -- and
		# so that a failure during setup still tears down.
		cls._had_custom_perms = bool(frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}))
		try:
			_register_gate()
		except Exception:
			_retire_gate(cls._had_custom_perms)
			raise

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		_retire_gate(cls._had_custom_perms)
		frappe.set_user(cls._original_user)
		super().tearDownClass()

	def setUp(self):
		frappe.db.savepoint("permission_gate_test")
		frappe.set_user("Administrator")
		# `gated_doctypes` memoises onto `frappe.local`, which is a per-request
		# store everywhere but here: one test process serves every module, so a
		# memo taken before `setUpClass` ticked the gate would say this doctype is
		# ungated and the first test would see rows the gate exists to withhold.
		clear_gated_doctypes()

	def tearDown(self):
		frappe.set_user("Administrator")
		_drop_user_permissions()
		frappe.db.rollback(save_point="permission_gate_test")
		frappe.clear_cache()
		# The gate is retired after this class, so leave no memo asserting it.
		clear_gated_doctypes()

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

	def test_a_blanket_user_permission_does_not_open_the_gate(self):
		"""`apply_to_all_doctypes` is what a User Permission gets by default, so
		counting it would let one restriction created for an unrelated reason
		satisfy every gate on the site."""
		_user_permission(GATED_USER, MINE, applicable_for=None)
		self.assertEqual(self.visible(GATED_USER), set())

	def test_the_same_permission_aimed_at_this_doctype_does_open_it(self):
		_user_permission(GATED_USER, MINE, applicable_for=DOCTYPE)
		self.assertEqual(self.visible(GATED_USER), {MINE})

	def test_a_user_permission_on_something_else_does_not_open_it(self):
		_user_permission(GATED_USER, frappe.db.get_value("Language", {}, "name"), allow="Language")
		self.assertEqual(self.visible(GATED_USER), set())

	def test_holding_an_ungated_role_as_well_beats_the_gate(self):
		"""An HR Manager who also holds Employee is an HR Manager."""
		frappe.get_doc("User", GATED_USER).add_roles(OPEN_ROLE)
		frappe.clear_cache(user=GATED_USER)
		self.assertEqual(self.visible(GATED_USER), {MINE, THEIRS})

	def test_an_ungated_only_if_creator_role_does_not_beat_the_gate(self):
		"""The failure this module was reported for.

		`Employee` grants read on `Procurement Request` with "Only if Creator"
		ticked. Counted as an unrestricted grant it switched the gate off and
		showed an approver every request on the site, most of which she had not
		raised. It reaches her own and nothing else, and that is all it leaves.
		"""
		frappe.get_doc("User", GATED_USER).add_roles(OWNER_ROLE)
		frappe.clear_cache(user=GATED_USER)

		frappe.set_user(GATED_USER)
		visible = set(
			frappe.get_list(DOCTYPE, filters={"name": ["in", (MINE, THEIRS, OWNED)]}, pluck="name")
		)
		self.assertEqual(visible, {OWNED})
		self.assertTrue(self.readable(GATED_USER, OWNED))
		self.assertFalse(self.readable(GATED_USER, THEIRS))

	def test_the_gate_is_configured_entirely_from_the_permission_row(self):
		"""No second document: the tick on the role is the whole configuration."""
		from tbs_commons.safer_permissions.permissions import gated_doctypes

		clear_gated_doctypes()
		self.assertIn(DOCTYPE, gated_doctypes())
		self.assertFalse(frappe.db.exists("DocType", "Permission Gate Settings"))

	def test_a_doctype_nobody_ticked_is_untouched(self):
		"""The fast path, and the safety: gating is opt-in per role row."""
		from tbs_commons.safer_permissions.permissions import blocked_scope

		clear_gated_doctypes()
		self.assertIsNone(blocked_scope(GATED_USER, "ToDo"))

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

	sync_gate_field()

	frappe.permissions.add_permission(DOCTYPE, GATED_ROLE, 0)
	frappe.permissions.update_permission_property(DOCTYPE, GATED_ROLE, 0, GATE, 1)
	frappe.permissions.add_permission(DOCTYPE, OPEN_ROLE, 0)

	# Ungated, but restricted to its holder's own documents -- the shape that
	# used to switch the gate off wholesale.
	frappe.permissions.add_permission(DOCTYPE, OWNER_ROLE, 0)
	frappe.permissions.update_permission_property(DOCTYPE, OWNER_ROLE, 0, "if_owner", 1)

	# Written straight to the column: `owner` is set from the session at insert
	# and the fixtures are created by Administrator.
	frappe.db.set_value(DOCTYPE, OWNED, "owner", GATED_USER, update_modified=False)

	frappe.db.commit()
	frappe.clear_cache()


def _retire_gate(had_custom_perms: bool):
	stale = {"parent": DOCTYPE} if not had_custom_perms else {"parent": DOCTYPE, "role": ["in", (GATED_ROLE, OPEN_ROLE, OWNER_ROLE)]}
	for name in frappe.get_all("Custom DocPerm", filters=stale, pluck="name"):
		frappe.delete_doc("Custom DocPerm", name, force=True, ignore_permissions=True)

	_drop_user_permissions()
	for doctype, names in (("Report", (REPORT,)), (DOCTYPE, (MINE, THEIRS, OWNED)), ("User", (GATED_USER, OPEN_USER)), ("Role", (GATED_ROLE, OPEN_ROLE, OWNER_ROLE))):
		for name in names:
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache()


def _fixtures():
	for branch in (MINE, THEIRS, OWNED):
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
	for role in (GATED_ROLE, OPEN_ROLE, OWNER_ROLE):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()

	for user, role in ((GATED_USER, GATED_ROLE), (OPEN_USER, OPEN_ROLE)):
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Gate Test",
					"user_type": "System User",
					# A site with no Email Account configured -- a fresh test
					# site, say -- refuses the welcome email and so the insert.
					"send_welcome_email": 0,
				}
			).insert()
		frappe.get_doc("User", user).add_roles(role)


def _user_permission(user, for_value, allow=REQUIRED, applicable_for=DOCTYPE):
	"""Aimed at a doctype by default. `applicable_for=None` makes it blanket,
	which is what core creates when nobody names one -- and what a gate ignores."""
	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": allow,
			"for_value": for_value,
			"apply_to_all_doctypes": 0 if applicable_for else 1,
			"applicable_for": applicable_for,
		}
	).insert(ignore_permissions=True)
	frappe.cache.hdel("user_permissions", user)


def _drop_user_permissions():
	names = frappe.get_all("User Permission", filters={"user": ["in", (GATED_USER, OPEN_USER)]}, pluck="name")
	for name in names:
		frappe.delete_doc("User Permission", name, force=True, ignore_permissions=True)
	for user in (GATED_USER, OPEN_USER):
		frappe.cache.hdel("user_permissions", user)


def run():
	"""Run this suite against a site by hand, verbosely.

	`bench --site SITE execute tbs_commons.safer_permissions.test_permission_gate_integration.run`

	Standing the gate up and taking it down again is `setUpClass`/`tearDownClass`
	business now, so this only chooses a runner -- and `bench run-tests` gets the
	same fixtures without going through here.
	"""
	result = unittest.TextTestRunner(verbosity=2).run(
		unittest.defaultTestLoader.loadTestsFromTestCase(TestPermissionGate)
	)
	if not result.wasSuccessful():
		raise RuntimeError("Permission gate integration tests failed")
	return dict(tests=result.testsRun, success=True)
