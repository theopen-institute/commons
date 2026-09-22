"""Rollback-only integration suite: bench --site SITE execute commons.self_service.test_record_change.run.

What these pin is the one promise the section makes and the unit tests cannot
check: a record changes when, and only when, somebody approves a change to it.
Everything else -- the read-only page, the diff, the queue -- is a consequence of
that, and would be worth nothing if a proposal could write to the record on its
own.

So each test is a whole round trip through the real doctype, the real Workflow
and real permissions, asserted against the referenced record afterwards. Mocking
any of those would leave exactly the layer that could be wrong untested.

`Employee` is the record under test because it is the shape the machinery was
built for: a record named by a login. The machinery is not Employee's -- see
`commons.self_service.registry` -- but a suite that exercised a made-up
doctype would be testing its own invention rather than the thing that ships.

Nothing installs a configuration or an approval chain, so the fixtures at the
foot of this file put both on the site for the run and the rollback takes them
back. They are this suite's, not a configuration the app suggests.
"""

import json
import unittest

import frappe

from commons import testing
from commons.safer_permissions.permissions import gate_applies, gate_satisfied
from commons.self_service import api, registry

RECORD = "Employee"
RECORD_BANK = "Bank Account"


def satisfy_permission_gate(user: str, employee: str) -> None:
	"""Give `user` whatever User Permission this site's gate demands on `Employee`.

	`commons.safer_permissions` adds a third state to Frappe's two permission
	systems: a Role Permission row marked `require_user_permission` grants
	nothing at all until a User Permission aimed at that doctype narrows it. On
	a site that has ticked it for `Employee`/`Employee` -- which is the feature
	working, and the configuration it exists for -- a fresh login with only the
	`Employee` role sees none of its own record, and every test here that reads
	one failed with "You have no Employee record for this request".

	What was missing was this fixture declaring the dependency. The suite
	creates a User and an Employee and lets ERPNext grant the role, but no
	User Permission -- so it only ever passed on a site with the gate switched
	off, and said nothing about the one where it is on. A correctly configured
	gated site gives each employee exactly this row, and the gate's own module
	docstring is where that is prescribed: `applicable_for` the doctype being
	gated, never a blanket permission, which the gate ignores by design.

	In the same spirit as `add_roles("Accounts User")` in the fixtures below:
	granted so that the *policy* is what these tests are about rather than the
	site's permission configuration. Written inside each test's savepoint, so
	the rollback takes it back like everything else.

	Asked of the gate rather than assumed, so nothing is written on a site that
	gates nothing -- there the suite runs exactly as it did before.

	`Bank Account` needs no equivalent, though the fixtures below grant a role
	that is gated on it: ERPNext's `Employee` role also holds read there and is
	*not* gated, and one unrestricted ungated grant stands the gate down. See
	`gate_scope`.
	"""
	# The role arrives with the Employee record -- ERPNext's `validate_employee_role`
	# grants it on insert -- and `gate_applies` reads the user's roles, so the
	# cache has to be dropped or this asks about a user who still holds nothing.
	frappe.clear_cache(user=user)
	if not gate_applies(user, RECORD) or gate_satisfied(user, RECORD):
		return

	frappe.get_doc(
		dict(
			doctype="User Permission",
			user=user,
			allow=RECORD,
			for_value=employee,
			applicable_for=RECORD,
		)
	).insert(ignore_permissions=True)
	frappe.clear_cache(user=user)


@testing.site_suite()
class TestRecordChangeRequest(unittest.TestCase):
	def setUp(self):
		frappe.db.savepoint("self_service_test")
		self.addCleanup(lambda: frappe.db.rollback(save_point="self_service_test"))
		self.addCleanup(frappe.set_user, "Administrator")

		frappe.set_user("Administrator")
		self.user = self.new_user()
		self.employee = self.new_employee(self.user)

	def new_user(self) -> str:
		"""A fresh login with no roles of its own.

		Deliberately not one of the site's existing users: Administrator holds
		every role, so a rule that only bites people *without* HR's roles would
		pass against it while being broken for everyone it applies to.

		No `add_roles("Employee")` here, because it would be a no-op that read
		like a precondition. ERPNext owns that role: `validate_employee_role`
		strips it from any login with no employee record behind it, and creating
		the record grants it back. So a user made here holds it only after
		`new_employee` links them -- which is the real sequence, and the reason
		`test_a_login_with_no_employee_record_is_not_offered_the_section` gets the
		answer it does.
		"""
		return (
			frappe.get_doc(
				dict(
					doctype="User",
					email=f"self-service-{frappe.generate_hash(length=8)}@example.com",
					first_name="Self",
					last_name="Service",
					send_welcome_email=0,
				)
			)
			.insert(ignore_permissions=True)
			.name
		)

	def new_employee(self, user: str) -> str:
		"""An active Employee for `user`, reachable by them.

		The gate fixture is applied here rather than in `setUp` because this is
		also how the second employee in `test_one_persons_requests_are_not_anothers`
		is made, and that one needs it for the same reason: without it, on a site
		that gates `Employee`, the other login cannot see the record this just
		created for it and the test fails raising its own request rather than
		asserting anything about whose it is.
		"""
		company = frappe.db.get_value("Company", "_Test Company", "name") or frappe.db.get_value(
			"Company", {}, "name"
		)
		employee = (
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
		satisfy_permission_gate(user, employee)
		return employee

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
		self.assertIsNone(registry.session_record(RECORD))

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
		than days later on the approver's behalf.

		The field is taken from the policy rather than named here. It used to be
		`blood_group`, which is proposable on some sites and not on others -- and
		where it is not, `validate_rows` refuses the row for being withheld
		before it ever looks at the value, so this passed while asserting nothing
		about select options. Any proposable Select does the job, and a site whose
		policy offers none has no dropdown for this to be about.
		"""
		meta = frappe.get_meta(RECORD)
		selects = [
			fieldname
			for fieldname in registry.proposable_fields(RECORD)
			if meta.get_field(fieldname).fieldtype == "Select"
		]
		if not selects:
			self.skipTest(f"No proposable Select field on this site's {RECORD} policy.")

		fieldname = selects[0]
		options = meta.get_field(fieldname).options or ""
		self.assertNotIn("Q+", options.split("\n"), "the value below has to be an impossible one")

		frappe.set_user(self.user)
		with self.assertRaises(frappe.ValidationError):
			api.request_change(
				RECORD, json.dumps({"changes": [{"fieldname": fieldname, "proposed_value": "Q+"}]})
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

	def test_a_settled_request_leaves_the_owner_s_list(self):
		"""The profile shows what is still waiting, not what was decided.

		An approved request is already the record above it and a refused one is
		raised again rather than revisited, so neither is something the owner can
		act on. The reviewer's own history is `get_change_queue(decided=1)`,
		which is where who decided what still matters.

		Each outcome separately, because they settle differently: approving
		submits the request (docstatus 1) while rejecting and withdrawing leave
		it at 0, so a predicate reading `docstatus` would have caught only one of
		the three.
		"""
		# A distinct number per outcome: approving *applies* the change, so a
		# second request proposing the same value is refused by the controller
		# as proposing nothing.
		for outcome, number in (
			("Approve", "0799 000 001"),
			("Reject", "0799 000 002"),
			("Withdraw", "0799 000 003"),
		):
			with self.subTest(outcome=outcome):
				name = self.propose(cell_number=number)
				frappe.set_user(self.user)
				self.assertIn(name, [row["name"] for row in api.get_my_changes()])

				frappe.set_user("Administrator")
				api.decide_change(name, outcome)
				frappe.set_user(self.user)
				self.assertNotIn(name, [row["name"] for row in api.get_my_changes()])

	def test_a_settled_request_is_in_the_owners_history(self):
		"""The other half of the split: gone from the list, not gone.

		The owner's own history, which is not the reviewer's -- `get_change_queue`
		needs submit on the doctype, and this needs nothing but owning the record.
		A refused request and the reason it was refused are the requester's to
		read.
		"""
		name = self.propose(cell_number="0799 000 004")
		frappe.set_user("Administrator")
		api.decide_change(name, "Reject", note="Ring the office first.")

		frappe.set_user(self.user)
		self.assertNotIn(name, [row["name"] for row in api.get_my_changes()])
		settled = {row["name"]: row for row in api.get_my_changes(decided=1)}
		self.assertIn(name, settled)
		self.assertFalse(settled[name]["open"])
		self.assertEqual(settled[name]["review_note"], "Ring the office first.")

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

	def test_the_policy_never_offers_pay_fields_to_the_page(self):
		"""The page reads the record itself, so what the server still controls is
		which fields it may ask for."""
		frappe.set_user(self.user)
		display = api.get_change_permissions(RECORD)["display"]
		# The header needs these; they are added by `display_fields`, not
		# configured as rows, because they are not facts the page lists.
		self.assertIn("employee_name", display)
		self.assertIn("name", display)
		for fieldname in ("ctc", "salary_mode", "bank_ac_no"):
			self.assertNotIn(fieldname, display)

	def test_a_visible_record_says_so(self):
		frappe.set_user(self.user)
		self.assertEqual(api.get_change_permissions(RECORD)["record_access"], "visible")

	def test_a_leaver_reads_as_missing_rather_than_forbidden(self):
		"""Nothing is withholding it -- it has stopped being theirs, which is why
		the policy's filters apply to the existence test too."""
		frappe.set_user("Administrator")
		frappe.db.set_value(RECORD, self.employee, "status", "Left")
		frappe.set_user(self.user)
		self.assertEqual(api.get_change_permissions(RECORD)["record_access"], "missing")

	def test_a_login_with_no_employee_record_is_not_offered_the_section(self):
		"""And that is ERPNext's answer, not this app's.

		`validate_employee_role` removes the `Employee` role from any login with
		no employee record behind it, so such a user holds no permission on the
		request doctype either. `read` follows that rather than second-guessing
		it: the site has already said this login is not an employee, and offering
		them a profile section would be this app disagreeing.
		"""
		frappe.set_user("Administrator")
		stranger = self.new_user()
		frappe.set_user(stranger)
		permissions = api.get_change_permissions(RECORD)
		self.assertFalse(permissions["read"])
		self.assertFalse(permissions["has_record"])
		self.assertFalse(permissions["request"])
		self.assertEqual(permissions["record_access"], "missing")
		self.assertEqual(api.get_my_changes(), [])

	def test_a_leaver_keeps_the_section_and_is_told_why_it_is_empty(self):
		"""The case the "your login isn't linked" notice actually exists for.

		A leaver keeps the `Employee` role -- the record still exists -- so `read`
		stays true and the section stays in the sidebar, while `has_record` goes
		false because the policy's filters no longer claim the record for them.
		That split is what lets the page explain itself instead of vanishing.
		"""
		frappe.set_user("Administrator")
		frappe.db.set_value(RECORD, self.employee, "status", "Left")
		frappe.set_user(self.user)
		permissions = api.get_change_permissions(RECORD)
		self.assertTrue(permissions["read"])
		self.assertFalse(permissions["has_record"])
		self.assertFalse(permissions["request"])
		self.assertIsNone(registry.session_record(RECORD))

	def test_a_reviewer_who_owns_no_record_keeps_their_queue(self):
		"""The bug the split above fixes: HR staff who are not themselves
		employees were losing the review queue with the section."""
		name = self.propose(cell_number="0799 999 999")
		frappe.set_user("Administrator")
		permissions = api.get_change_permissions(RECORD)
		self.assertFalse(permissions["has_record"])
		self.assertTrue(permissions["review"])
		self.assertIn(name, [row["name"] for row in api.get_change_queue()])


@testing.site_suite()
class TestBankAccountPolicy(unittest.TestCase):
	"""The registry's second shape: many records per owner, owned through a chain.

	`Employee` is one record named by a login. A bank account is one of several,
	and it names no login at all -- it names its employee, and whoever owns that
	employee owns it. Those are the two cases the registry was built to tell
	apart, and only one of them had ever been exercised.
	"""

	def setUp(self):
		frappe.db.savepoint("bank_test")
		self.addCleanup(lambda: frappe.db.rollback(save_point="bank_test"))
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user("Administrator")

		self.user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"bank-{frappe.generate_hash(length=8)}@example.com",
				first_name="Bank",
				last_name="Tester",
				send_welcome_email=0,
			)
		).insert(ignore_permissions=True)
		company = frappe.db.get_value("Company", "_Test Company", "name") or frappe.db.get_value(
			"Company", {}, "name"
		)
		self.company = company
		self.employee = (
			frappe.get_doc(
				dict(
					doctype="Employee",
					first_name="Bank",
					last_name="Tester",
					gender=frappe.db.get_value("Gender", {}, "name"),
					date_of_birth="1990-01-01",
					date_of_joining="2020-01-01",
					status="Active",
					company=company,
					user_id=self.user.name,
				)
			)
			.insert(ignore_permissions=True)
			.name
		)
		# Reading bank accounts is an accounts right, not an employee one -- see
		# the fixture note below. Granted here so the *policy* is what is under
		# test rather than the site's permission configuration.
		self.user.reload()
		self.user.add_roles("Accounts User")
		satisfy_permission_gate(self.user.name, self.employee)

	def new_account(self, name: str, **extra) -> str:
		bank = (
			frappe.db.get_value("Bank", {}, "name")
			or frappe.get_doc(dict(doctype="Bank", bank_name=f"Bank {frappe.generate_hash(length=6)}"))
			.insert(ignore_permissions=True)
			.name
		)
		return (
			frappe.get_doc(
				dict(
					doctype="Bank Account",
					account_name=name,
					bank=bank,
					party_type="Employee",
					party=self.employee,
					**extra,
				)
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_ownership_chains_from_the_account_to_the_login(self):
		"""The account names its employee; the employee names the login."""
		account = self.new_account("Salary")
		self.assertEqual(registry.owner_of(RECORD_BANK, account), self.user.name)
		frappe.set_user(self.user.name)
		self.assertTrue(registry.session_owns(RECORD_BANK, account))

	def test_every_account_is_listed_not_just_one(self):
		"""The whole reason this policy is not `singular`."""
		self.new_account("Salary", is_default=1)
		self.new_account("Expenses")
		frappe.set_user(self.user.name)
		rows = registry.session_records(RECORD_BANK, ["name", "account_name"])
		self.assertEqual(sorted(r.account_name for r in rows), ["Expenses", "Salary"])

	def test_there_is_no_single_bank_account_for_a_user(self):
		"""Asking for one is a caller with a bug, and gets told so rather than
		handed whichever row the database offered first."""
		self.new_account("Salary")
		frappe.set_user(self.user.name)
		with self.assertRaises(frappe.ValidationError):
			registry.session_record(RECORD_BANK)

	def test_somebody_elses_accounts_are_not_mine(self):
		self.new_account("Salary")
		frappe.set_user("Administrator")
		other_user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"other-{frappe.generate_hash(length=8)}@example.com",
				first_name="Other",
				send_welcome_email=0,
			)
		).insert(ignore_permissions=True)
		frappe.get_doc(
			dict(
				doctype="Employee",
				first_name="Other",
				gender=frappe.db.get_value("Gender", {}, "name"),
				date_of_birth="1990-01-01",
				date_of_joining="2020-01-01",
				status="Active",
				company=self.company,
				user_id=other_user.name,
			)
		).insert(ignore_permissions=True)
		other_user.reload()
		other_user.add_roles("Accounts User")
		frappe.set_user(other_user.name)
		self.assertEqual(registry.session_records(RECORD_BANK), [])

	def test_a_non_employee_party_is_not_claimed_by_this_policy(self):
		"""`party` is a Dynamic Link, so `party_type` has to be pinned or the
		policy would claim any party whose id happened to match an employee's."""
		self.assertEqual(registry.policy(RECORD_BANK)["filters"]["party_type"], "Employee")

	# The two fields that must never reach a self-service page for a bank
	# account, whatever else the policy is configured to offer: one is a
	# credential and the other addresses somebody else's system.
	BANK_CREDENTIALS = ("statement_password", "integration_id")

	def test_the_policy_never_offers_credentials(self):
		"""Neither to read nor to propose, whatever the site has configured.

		This used to assert `proposable == ()` as well -- that the policy is
		read-only outright. That is how `make_test_configuration` seeds it, but
		the seed only applies to a record type the site has none for, and this
		suite deliberately runs against whatever configuration it finds (see the
		fixture note at the foot of this file). A site that has opened one field
		for proposal is configured, not broken, so asserting the seed here made
		the test a claim about the site rather than about the policy machinery.

		What holds either way is the part worth pinning: these two fields are
		absent from both lists, so no configuration reaches them.
		"""
		policy = registry.policy(RECORD_BANK)
		for fieldname in self.BANK_CREDENTIALS:
			self.assertNotIn(fieldname, policy["display"])
			self.assertNotIn(fieldname, policy["proposable"])

	def test_permissions_report_the_list_shape(self):
		self.new_account("Salary")
		frappe.set_user(self.user.name)
		permissions = api.get_change_permissions(RECORD_BANK)
		self.assertFalse(permissions["singular"])
		self.assertTrue(permissions["can_read_records"])
		self.assertTrue(permissions["has_record"])
		self.assertEqual(permissions["record_access"], "visible")
		self.assertEqual(permissions["owner_field"], "party")
		self.assertEqual(permissions["owner_value"], self.employee)
		self.assertEqual(permissions["record_filters"], {"party_type": "Employee"})
		# Derived from the policy rather than asserted flat. `request` is "may
		# this user raise one here", and the endpoint answers it from three
		# things: owning a record, holding `create`, and the policy having a
		# field to propose at all. Only the last varies between sites, so it is
		# read rather than assumed -- the invariant is that the payload agrees
		# with the configuration, not that this site's is read-only.
		self.assertEqual(
			permissions["request"], bool(registry.proposable_fields(RECORD_BANK))
		)

	def test_an_account_you_may_not_read_is_forbidden_not_empty(self):
		"""Existence is the discriminator: a row is there and the site is
		withholding it, which is a permissions question rather than an empty
		page.

		Every role that grants read is taken away, not just `Accounts User`.
		Dropping the one this fixture granted was enough on a site where it is
		the only route to a `Bank Account`, and silently not enough on one where
		another role also holds read -- ERPNext's `Employee` does on some sites,
		and there this user kept reading accounts after the removal and the
		assertion below failed. Read off the doctype's own permissions instead,
		so whatever this site's routes are, they all go.

		Taking `Employee` away can take the *parent* record's read with it, which
		is what `registry.record_exists` has to survive to still answer
		`forbidden` here rather than `missing` -- see `_owner_value_raw`.
		"""
		self.new_account("Salary")
		frappe.set_user("Administrator")
		self.user.reload()
		readers = {
			perm.role
			for perm in frappe.get_meta(RECORD_BANK).permissions
			if not frappe.utils.cint(perm.permlevel) and (perm.read or perm.select)
		}
		self.user.remove_roles(*readers)
		frappe.clear_cache(user=self.user.name)
		frappe.set_user(self.user.name)
		permissions = api.get_change_permissions(RECORD_BANK)
		self.assertFalse(permissions["can_read_records"])
		self.assertEqual(permissions["record_access"], "forbidden")
		self.assertEqual(registry.session_records(RECORD_BANK), [])

	def test_no_accounts_at_all_reads_as_missing(self):
		"""Nothing is being withheld -- there is nothing. Said this way round so
		the page sends the reader to payroll rather than to a System Manager."""
		frappe.set_user(self.user.name)
		permissions = api.get_change_permissions(RECORD_BANK)
		self.assertEqual(permissions["record_access"], "missing")
		self.assertFalse(permissions["has_record"])


@testing.site_suite()
class TestRequestModes(unittest.TestCase):
	"""Creating and deleting a record through the same request document.

	A `Change` corrects a record that exists. A `New` asks for one to be created
	and creates nothing until it is approved. A `Delete` asks for one to be
	removed. They share the allowlist, the reviewers and the workflow -- what
	these pin is that the two new shapes cannot be used to reach past any of it.
	"""

	#: The fields this class's configuration offers for proposal, and so the
	#: whole of what a request here may set. Everything else on the doctype is
	#: withheld, which is what the refusals below are about.
	PROPOSABLE = ("account_name", "bank")

	def setUp(self):
		frappe.db.savepoint("modes_test")
		self.addCleanup(self.restore)
		frappe.set_user("Administrator")

		self.config = frappe.get_doc("Self Service Record", RECORD_BANK)
		self.config.allow_new = 1
		self.config.allow_delete = 1
		# Exactly these two proposable and the rest not. This used to only switch
		# the two on and leave every other row as the site had it, which on a site
		# whose policy already offers all of them meant
		# `test_a_new_request_may_not_set_a_field_that_is_not_proposable` had no
		# withheld field left to be refused for. The class mutates this
		# configuration and rolls it back either way, so pinning the whole set is
		# no more intrusive than pinning half of it -- and it is what makes the
		# tests below about the allowlist rather than about the site.
		for row in self.config.fields:
			row.proposable = 1 if row.fieldname in self.PROPOSABLE else 0
		self.config.save()
		registry.clear_cache()

		self.user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"modes-{frappe.generate_hash(length=8)}@example.com",
				first_name="Modes",
				send_welcome_email=0,
			)
		).insert(ignore_permissions=True)
		company = frappe.db.get_value("Company", "_Test Company", "name") or frappe.db.get_value(
			"Company", {}, "name"
		)
		self.employee = (
			frappe.get_doc(
				dict(
					doctype="Employee",
					first_name="Modes",
					gender=frappe.db.get_value("Gender", {}, "name"),
					date_of_birth="1990-01-01",
					date_of_joining="2020-01-01",
					status="Active",
					company=company,
					user_id=self.user.name,
				)
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.user.reload()
		self.user.add_roles("Accounts User")
		satisfy_permission_gate(self.user.name, self.employee)
		self.bank = (
			frappe.db.get_value("Bank", {}, "name")
			or frappe.get_doc(dict(doctype="Bank", bank_name=f"Bank {frappe.generate_hash(length=6)}"))
			.insert(ignore_permissions=True)
			.name
		)

	def restore(self):
		"""A savepoint rollback does not run the cache callbacks, so the
		configuration this suite saved has to be dropped by hand -- see
		`SelfServiceRecord.clear_registry_cache`."""
		frappe.db.rollback(save_point="modes_test")
		registry.clear_cache()
		frappe.set_user("Administrator")

	def raise_request(self, **values):
		frappe.set_user(self.user.name)
		return api.request_change(RECORD_BANK, json.dumps(values))["name"]

	def accounts(self):
		return frappe.get_all("Bank Account", filters={"party": self.employee}, pluck="name")

	# -- new ---------------------------------------------------------------

	def test_a_new_request_creates_nothing_until_it_is_approved(self):
		self.raise_request(
			request_type="New",
			changes=[
				{"fieldname": "account_name", "proposed_value": "Fresh"},
				{"fieldname": "bank", "proposed_value": self.bank},
			],
		)
		self.assertEqual(self.accounts(), [])

	def test_approving_a_new_request_creates_it_owned_by_whoever_asked(self):
		"""The owner comes from the requester, not the approver -- resolving it at
		approval would attach the record to the wrong person, silently."""
		name = self.raise_request(
			request_type="New",
			changes=[
				{"fieldname": "account_name", "proposed_value": "Fresh"},
				{"fieldname": "bank", "proposed_value": self.bank},
			],
		)
		self.assertEqual(frappe.db.get_value(api.DOCTYPE, name, "record_owner"), self.employee)
		frappe.set_user("Administrator")
		api.decide_change(name, "Approve")
		created = self.accounts()
		self.assertEqual(len(created), 1)
		row = frappe.db.get_value(
			"Bank Account", created[0], ["party", "party_type", "account_name"], as_dict=True
		)
		self.assertEqual(row.party, self.employee)
		# The policy's filters are applied too, or the record would not be one this
		# policy ever claims back.
		self.assertEqual(row.party_type, "Employee")
		self.assertEqual(row.account_name, "Fresh")
		# The request stops being about a hypothetical record.
		self.assertEqual(frappe.db.get_value(api.DOCTYPE, name, "reference_name"), created[0])

	def test_a_new_request_may_not_set_a_field_that_is_not_proposable(self):
		"""The creation form is not a way around the allowlist."""
		with self.assertRaises(frappe.PermissionError):
			self.raise_request(
				request_type="New",
				changes=[{"fieldname": "iban", "proposed_value": "GB00"}],
			)

	def test_a_new_request_with_nothing_filled_in_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.raise_request(request_type="New", changes=[])

	# -- delete ------------------------------------------------------------

	def test_a_delete_request_removes_nothing_until_it_is_approved(self):
		account = self.new_account()
		self.raise_request(request_type="Delete", reference_name=account)
		self.assertEqual(self.accounts(), [account])

	def test_approving_a_delete_request_removes_the_record(self):
		account = self.new_account()
		name = self.raise_request(request_type="Delete", reference_name=account)
		# A deletion proposes no values; naming the record is the request.
		self.assertEqual(frappe.get_doc(api.DOCTYPE, name).changes, [])
		frappe.set_user("Administrator")
		api.decide_change(name, "Approve")
		self.assertEqual(self.accounts(), [])
		# The settled request still says what it was about, which is why the title
		# is captured rather than looked up.
		self.assertTrue(frappe.db.get_value(api.DOCTYPE, name, "reference_title"))

	def test_a_delete_request_cannot_name_somebody_elses_record(self):
		frappe.set_user("Administrator")
		other = (
			frappe.get_doc(
				dict(
					doctype="Bank Account",
					account_name="Not Yours",
					bank=self.bank,
					party_type="Employee",
					party=frappe.db.get_value("Employee", {"name": ["!=", self.employee]}, "name"),
				)
			)
			.insert(ignore_permissions=True)
			.name
		)
		with self.assertRaises(frappe.PermissionError):
			self.raise_request(request_type="Delete", reference_name=other)

	# -- the switches ------------------------------------------------------

	def test_both_shapes_are_refused_when_the_configuration_says_so(self):
		frappe.set_user("Administrator")
		self.config.reload()
		self.config.allow_new = 0
		self.config.allow_delete = 0
		self.config.save()
		registry.clear_cache()
		account = self.new_account()
		with self.assertRaises(frappe.PermissionError):
			self.raise_request(
				request_type="New",
				changes=[{"fieldname": "account_name", "proposed_value": "Nope"}],
			)
		with self.assertRaises(frappe.PermissionError):
			self.raise_request(request_type="Delete", reference_name=account)

	def test_permissions_report_both_switches(self):
		frappe.set_user(self.user.name)
		permissions = api.get_change_permissions(RECORD_BANK)
		self.assertTrue(permissions["allow_new"])
		self.assertTrue(permissions["allow_delete"])

	def test_a_pending_deletion_is_visible_to_whoever_asked(self):
		"""The page marks the record somebody wants removed, so it has to come back.

		Both halves were missing: a many-per-owner record type resolved no
		ownership at all, so its requests were invisible, and `request_type` was
		not carried on a list row, so nothing could tell a deletion from a
		correction.
		"""
		account = self.new_account()
		name = self.raise_request(request_type="Delete", reference_name=account)
		mine = {row["name"]: row for row in api.get_my_changes(RECORD_BANK)}
		self.assertIn(name, mine)
		self.assertEqual(mine[name]["request_type"], "Delete")
		self.assertEqual(mine[name]["reference_name"], account)
		self.assertTrue(mine[name]["open"])

	def test_a_pending_new_request_is_visible_before_it_names_anything(self):
		"""It names no record until approval, so ownership cannot find it -- it is
		theirs because they raised it."""
		frappe.set_user(self.user.name)
		name = self.raise_request(
			request_type="New",
			changes=[{"fieldname": "account_name", "proposed_value": "Pending"}],
		)
		mine = {row["name"]: row for row in api.get_my_changes(RECORD_BANK)}
		self.assertIn(name, mine)
		self.assertIsNone(mine[name]["reference_name"])

	def test_every_owned_record_contributes_its_requests(self):
		"""An owner with several has several histories, not the first one's."""
		first = self.new_account("First")
		second = self.new_account("Second")
		a = self.raise_request(request_type="Delete", reference_name=first)
		b = self.raise_request(request_type="Delete", reference_name=second)
		names = {row["name"] for row in api.get_my_changes(RECORD_BANK)}
		self.assertEqual({a, b} - names, set())

	def new_account(self, name="Existing"):
		frappe.set_user("Administrator")
		return (
			frappe.get_doc(
				dict(
					doctype="Bank Account",
					account_name=name,
					bank=self.bank,
					party_type="Employee",
					party=self.employee,
				)
			)
			.insert(ignore_permissions=True)
			.name
		)


@testing.site_suite()
class TestFreeFormFields(unittest.TestCase):
	"""A Link field whose target may not exist yet.

	The case this exists for: an employee has to name something the site does not
	have on file, or does not let them see. They type it, the request carries the
	text, and whoever reviews it creates the document. Nothing is applied until
	that document exists -- which is the line between "free form" and "unchecked".
	"""

	def setUp(self):
		frappe.db.savepoint("free_text_test")
		self.addCleanup(self.restore)
		frappe.set_user("Administrator")

		self.config = frappe.get_doc("Self Service Record", RECORD_BANK)
		self.config.allow_new = 0
		self.config.allow_delete = 0
		for row in self.config.fields:
			if row.fieldname == "bank":
				row.proposable = 1
				row.free_text = 1
		self.config.save()
		registry.clear_cache()

		self.user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"freetext-{frappe.generate_hash(length=8)}@example.com",
				first_name="Free",
				send_welcome_email=0,
			)
		).insert(ignore_permissions=True)
		company = frappe.db.get_value("Company", "_Test Company", "name") or frappe.db.get_value(
			"Company", {}, "name"
		)
		self.employee = (
			frappe.get_doc(
				dict(
					doctype="Employee",
					first_name="Free",
					gender=frappe.db.get_value("Gender", {}, "name"),
					date_of_birth="1990-01-01",
					date_of_joining="2020-01-01",
					status="Active",
					company=company,
					user_id=self.user.name,
				)
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.user.reload()
		self.user.add_roles("Accounts User")
		satisfy_permission_gate(self.user.name, self.employee)
		bank = (
			frappe.db.get_value("Bank", {}, "name")
			or frappe.get_doc(dict(doctype="Bank", bank_name=f"Base {frappe.generate_hash(length=6)}"))
			.insert(ignore_permissions=True)
			.name
		)
		self.account = (
			frappe.get_doc(
				dict(
					doctype="Bank Account",
					account_name="Existing",
					bank=bank,
					party_type="Employee",
					party=self.employee,
				)
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.unknown = f"Bank Of Nowhere {frappe.generate_hash(length=6)}"

	def restore(self):
		"""A savepoint rollback does not run the cache callbacks, so configuration
		saved here has to be dropped by hand."""
		frappe.db.rollback(save_point="free_text_test")
		registry.clear_cache()
		frappe.set_user("Administrator")

	def propose_unknown_bank(self, value: str | None = None) -> str:
		frappe.set_user(self.user.name)
		return api.request_change(
			RECORD_BANK,
			json.dumps(
				{
					"request_type": "Change",
					"reference_name": self.account,
					"changes": [{"fieldname": "bank", "proposed_value": value or self.unknown}],
				}
			),
		)["name"]

	def onloaded(self, name: str) -> list[dict]:
		"""What the desk form is told when it opens this request."""
		doc = frappe.get_doc(api.DOCTYPE, name)
		doc.run_method("onload")
		return doc.get_onload("missing_links")

	def test_the_field_is_offered_as_text_with_nothing_to_search(self):
		"""The page draws a text box because there is no document to find yet."""
		field = next(
			f
			for section in registry.field_definitions(RECORD_BANK)
			for f in section["fields"]
			if f["fieldname"] == "bank"
		)
		self.assertTrue(field["free_text"])
		self.assertEqual(field["type"], "text")
		self.assertIsNone(field["doctype"])

	def test_a_value_that_names_nothing_is_accepted_when_raised(self):
		"""The whole point: the document does not exist yet."""
		name = self.propose_unknown_bank()
		row = frappe.get_doc(api.DOCTYPE, name).changes[0]
		self.assertEqual(row.proposed_value, self.unknown)
		self.assertFalse(frappe.db.exists("Bank", self.unknown))

	def test_approval_is_refused_while_the_document_is_missing(self):
		"""Free form is not unchecked. Approving is the moment somebody decided the
		value is right, and the link has to exist for the save to take it."""
		name = self.propose_unknown_bank()
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.LinkValidationError):
			api.decide_change(name, "Approve")
		# Nothing was written to the record on the way to refusing.
		self.assertNotEqual(frappe.db.get_value("Bank Account", self.account, "bank"), self.unknown)

	def test_approval_succeeds_once_the_reviewer_creates_it(self):
		name = self.propose_unknown_bank()
		frappe.set_user("Administrator")
		frappe.db.savepoint("attempt")
		try:
			api.decide_change(name, "Approve")
		except frappe.LinkValidationError:
			# A web request rolls back when a whitelisted method throws; the test
			# runner has no such boundary, so the refused attempt is undone here.
			frappe.db.rollback(save_point="attempt")
		frappe.get_doc(dict(doctype="Bank", bank_name=self.unknown)).insert(ignore_permissions=True)
		api.decide_change(name, "Approve")
		self.assertEqual(frappe.db.get_value("Bank Account", self.account, "bank"), self.unknown)

	def test_a_refused_approval_leaves_the_request_decidable(self):
		"""Otherwise the reviewer creates the document and has nothing to approve."""
		name = self.propose_unknown_bank()
		frappe.set_user("Administrator")
		frappe.db.savepoint("attempt")
		try:
			api.decide_change(name, "Approve")
		except frappe.LinkValidationError:
			frappe.db.rollback(save_point="attempt")
		row = frappe.db.get_value(api.DOCTYPE, name, ["status", "docstatus"], as_dict=True)
		self.assertEqual(row.status, "Pending")
		self.assertEqual(row.docstatus, 0)

	# -- what the desk form is told ---------------------------------------

	def test_the_form_says_what_is_missing_before_anybody_approves(self):
		"""The refusal is the guard, not the notice.

		An approver who only finds out by pressing Approve reads an error where
		they could have read a sentence. The same answer arrives with the
		document, so the form can say it and offer the popup against it.
		"""
		name = self.propose_unknown_bank()
		frappe.set_user("Administrator")
		gaps = self.onloaded(name)
		self.assertEqual(len(gaps), 1)
		self.assertEqual(gaps[0]["target"], "Bank")
		self.assertEqual(gaps[0]["value"], self.unknown)
		self.assertEqual(gaps[0]["label"], "Bank")
		# A Bank is named after `bank_name`, so the typed value becomes the name
		# the Link will resolve to -- which is what makes the popup worth offering.
		self.assertEqual(gaps[0]["name_field"], "bank_name")
		self.assertTrue(gaps[0]["creatable"])

	def test_the_notice_goes_once_the_document_exists(self):
		"""Paired with the approval test below: one answer behind both, so the
		form cannot go on asking for something that is already there."""
		name = self.propose_unknown_bank()
		frappe.set_user("Administrator")
		frappe.get_doc(dict(doctype="Bank", bank_name=self.unknown)).insert(ignore_permissions=True)
		self.assertEqual(self.onloaded(name), [])

	def test_a_near_match_already_on_file_is_offered(self):
		"""Against duplicates: a typed value that matches nothing may still be
		something the site holds under a slightly different name, and the
		approver is the only person placed to notice."""
		frappe.set_user("Administrator")
		existing = frappe.get_doc(
			dict(doctype="Bank", bank_name=f"Chartered Bank {frappe.generate_hash(length=6)}")
		).insert(ignore_permissions=True)
		name = self.propose_unknown_bank("Chartered")
		frappe.set_user("Administrator")
		self.assertIn(existing.name, self.onloaded(name)[0]["suggestions"])

	def test_nothing_is_offered_to_create_to_somebody_who_may_not(self):
		"""The employee who raised it can read their own request in the desk.
		Creating the bank it names is not theirs to do, and the form is told so
		rather than offering a popup that would be refused on insert."""
		name = self.propose_unknown_bank()
		frappe.set_user(self.user.name)
		gaps = self.onloaded(name)
		self.assertEqual(len(gaps), 1)
		self.assertFalse(gaps[0]["creatable"])

	def test_a_record_type_taken_out_of_self_service_still_opens(self):
		"""A form that cannot be opened is a worse answer to a configuration
		change than a form with no notice on it. The approval still refuses."""
		name = self.propose_unknown_bank()
		frappe.set_user("Administrator")
		self.config.reload()
		self.config.enabled = 0
		self.config.save()
		registry.clear_cache()
		self.assertEqual(self.onloaded(name), [])

	# -- what the configuration refuses -----------------------------------

	def test_free_form_needs_something_to_link_to(self):
		"""A Select's options are the point of the field; typing past them would
		propose a value the doctype refuses."""
		frappe.set_user("Administrator")
		self.config.reload()
		for row in self.config.fields:
			if row.fieldname == "account_name":
				row.proposable = 1
				row.free_text = 1
		with self.assertRaises(frappe.ValidationError):
			self.config.save()

	def test_free_form_needs_the_field_to_be_proposable(self):
		frappe.set_user("Administrator")
		self.config.reload()
		for row in self.config.fields:
			if row.fieldname == "bank":
				row.proposable = 0
				row.free_text = 1
		with self.assertRaises(frappe.ValidationError):
			self.config.save()


# --- fixtures -------------------------------------------------------------
#
# The configuration and the approval chain this suite runs against. Nothing
# installs either: which record types are self-service, which of their fields
# staff may see and propose corrections to, and who decides a proposal are a
# site's decisions, made by a System Manager on a new site. So a suite that
# exercises the whole round trip has to bring its own, and what follows is a
# fixture rather than a recommendation.
#
# `Employee` is the record under test because the machinery needs one that is
# named by a login, and `Bank Account` because it is the other shape -- several
# records per owner, owned through a chain. The split between viewable and
# proposable is the one the tests assert on: employment facts and identity are
# shown but not proposable, pay and bank details are never proposable at all.

# (section, fieldname, proposable)
EMPLOYEE_FIELDS = (
	("Basic information", "salutation", False),
	("Basic information", "first_name", False),
	("Basic information", "middle_name", False),
	("Basic information", "last_name", False),
	("Basic information", "gender", False),
	("Basic information", "date_of_birth", False),
	("Employment", "company", False),
	("Employment", "status", False),
	("Employment", "date_of_joining", False),
	("Employment", "employee_number", False),
	("Employment", "designation", False),
	("Employment", "department", False),
	("Employment", "branch", False),
	("Employment", "reports_to", False),
	("Employment", "holiday_list", False),
	("Access & approvals", "user_id", False),
	("Access & approvals", "leave_approver", False),
	("Contact", "cell_number", True),
	("Contact", "company_email", False),
	("Contact", "personal_email", True),
	("Contact", "prefered_contact_email", True),
	("Contact", "current_address", True),
	("Contact", "permanent_address", True),
	("Emergency contact", "person_to_be_contacted", True),
	("Emergency contact", "relation", True),
	("Emergency contact", "emergency_phone_number", True),
	("Personal details", "marital_status", True),
	("Personal details", "blood_group", True),
	("Personal details", "passport_number", True),
)

BANK_ACCOUNT_FIELDS = (
	("Account", "account_name", False),
	("Account", "bank", False),
	("Account", "account_type", False),
	("Account", "account_subtype", False),
	("Account", "is_default", False),
	("Account", "disabled", False),
	("Details", "bank_account_no", False),
	("Details", "iban", False),
	("Details", "branch_code", False),
)

SEED = (
	{
		"document_type": "Employee",
		"label": "My profile",
		"route_slug": "employee",
		"icon": "lucide-id-card",
		"nav_order": 10,
		"read_only_notice": (
			"Your details are held by HR. Fields you can correct have a pencil beside "
			"them — your change goes to HR as a proposal."
		),
		"empty_notice": ("There's no profile to show until HR links an employee record to your login."),
		# `user_id` is a Link to User, so it names the owner outright.
		"owner_field": "user_id",
		"title_field": "employee_name",
		# One employee record per login, so "my record" has a single answer.
		"is_singular": 1,
		# A leaver's record stops being theirs to correct.
		"record_filters": '{"status": "Active"}',
		"fields": EMPLOYEE_FIELDS,
	},
	{
		"document_type": "Bank Account",
		"label": "Bank accounts",
		"route_slug": "bank-accounts",
		"icon": "lucide-landmark",
		"nav_order": 20,
		"read_only_notice": (
			"Bank details are held by payroll. To change where you're paid, talk to "
			"them directly — this isn't something to send through a form."
		),
		"empty_notice": (
			"This is where the accounts payroll pays you into would appear. Ask "
			"whoever runs payroll if you expected one here."
		),
		# `party` is a Dynamic Link, so the doctype it points at is a field on the
		# row rather than a property of the schema -- which is why the filters pin
		# `party_type` as well. Without it this would claim every bank account
		# whose party id happened to match an employee id.
		"owner_field": "party",
		"owner_doctype": "Employee",
		"title_field": "account_name",
		# One employee, several accounts: the page lists them.
		"is_singular": 0,
		"record_filters": '{"party_type": "Employee"}',
		"fields": BANK_ACCOUNT_FIELDS,
	},
)

CHANGE_WORKFLOW = "Record Change Request Workflow"
DOCTYPE = "Record Change Request"

# Approval is the submission, as it is for `Procurement Request`: everything
# before a decision is docstatus 0, and only `Approved` reaches 1 -- which is
# what lets `RecordChangeRequest.on_submit` apply the change without consulting
# the name of a state.
#
# Order is load-bearing. `Pending` is first, so it is the state Frappe assigns a
# request that arrives without one -- and this section has no draft step, because
# a proposal nobody has sent is just a form nobody has pressed Send on.
# `Approved` is the first `doc_status` 1 row, so it is what
# `set_workflow_state_on_action` picks if something submits a request outside the
# workflow.
WORKFLOW_STATES = (
	{"state": "Pending", "style": "Warning", "doc_status": "0", "allow_edit": "Employee"},
	{
		"state": "Approved",
		"style": "Success",
		"doc_status": "1",
		"allow_edit": "HR Manager",
	},
	{
		"state": "Rejected",
		"style": "Danger",
		"doc_status": "0",
		"allow_edit": "HR Manager",
	},
	# The requester's own way out, and the reason it is not `Cancel`: a request
	# that was never decided should not read as one somebody turned down.
	{"state": "Withdrawn", "style": "Inverse", "doc_status": "0", "allow_edit": "HR Manager"},
	# Cancelling an *approved* request. It does not put the old values back --
	# see `RecordChangeRequest.on_cancel` -- so the state says what happened to
	# the request, not to the record.
	{"state": "Reversed", "style": "Inverse", "doc_status": "2", "allow_edit": "HR Manager"},
)

WORKFLOW_ACTIONS = ("Approve", "Reject", "Withdraw", "Reverse")

WORKFLOW_TRANSITIONS = (
	{"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR Manager"},
	{"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR Manager"},
	{"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR User"},
	{"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR User"},
	# Withdrawing decides nothing, so a requester may do it to their own
	# request -- which is the only kind they can see. Without `allow_self_approval`
	# Frappe would refuse it as approving your own document.
	{
		"state": "Pending",
		"action": "Withdraw",
		"next_state": "Withdrawn",
		"allowed": "Employee",
		"allow_self_approval": 1,
	},
	{"state": "Approved", "action": "Reverse", "next_state": "Reversed", "allowed": "HR Manager"},
)


def make_test_configuration() -> None:
	"""Put this suite's configuration on the site, for record types with none.

	An existing `Self Service Record` is left exactly as it is: on a real site
	this suite is being run against somebody's own configuration, and overwriting
	it to test against a fixture would be both rude and dishonest about what
	passed. A record whose doctype is not installed is skipped rather than
	raising, because `Bank Account` is ERPNext's.
	"""
	for entry in SEED:
		doctype = entry["document_type"]
		if frappe.db.exists(registry.CONFIG, doctype):
			continue
		if not frappe.db.exists("DocType", doctype):
			continue
		record = frappe.new_doc(registry.CONFIG)
		record.update({key: value for key, value in entry.items() if key != "fields"})
		meta = frappe.get_meta(doctype)
		for section, fieldname, proposable in entry["fields"]:
			# A field the site's version of the doctype does not have is dropped
			# rather than seeded, so the first save does not fail validation on
			# something upstream renamed.
			if not meta.has_field(fieldname):
				continue
			record.append(
				"fields",
				{
					"section": section,
					"fieldname": fieldname,
					"viewable": 1,
					"proposable": 1 if proposable else 0,
				},
			)
		if record.fields:
			record.insert(ignore_permissions=True)


def make_test_workflow() -> None:
	"""Put this suite's approval chain on the site, unless the site has one.

	An existing workflow, active or not, is left alone -- the same rule
	`make_test_configuration` follows and for the same reason.

	A `Workflow State` is a site-wide record shared with every other workflow
	that names it, so an existing one is never restyled here.
	"""
	if frappe.db.exists("Workflow", {"document_type": DOCTYPE}):
		return

	for state in WORKFLOW_STATES:
		name = state["state"]
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": name, "style": state["style"]}
			).insert(ignore_permissions=True)

	for action in WORKFLOW_ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	workflow = frappe.new_doc("Workflow")
	workflow.update(
		{
			"workflow_name": CHANGE_WORKFLOW,
			"document_type": DOCTYPE,
			"workflow_state_field": "status",
			# Off. Frappe's workflow alert calls `attach_print` unconditionally, so
			# turning it on mails every reviewer a PDF of the request -- which under
			# the bank-account fixture means an account number and an IBAN.
			"send_email_alert": 0,
		}
	)
	workflow.set("states", [{k: v for k, v in state.items() if k != "style"} for state in WORKFLOW_STATES])
	workflow.set("transitions", list(WORKFLOW_TRANSITIONS))
	workflow.save(ignore_permissions=True)


def run():
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		# Nothing installs the self-service configuration or its approval chain, so
		# the suite puts its own fixture on the site. Both leave an existing
		# configuration alone, and the rollback below takes back whatever is written.
		make_test_configuration()
		make_test_workflow()
		suite = unittest.TestSuite(
			unittest.defaultTestLoader.loadTestsFromTestCase(case)
			for case in (
				TestRecordChangeRequest,
				TestBankAccountPolicy,
				TestRequestModes,
				TestFreeFormFields,
			)
		)
		result = unittest.TextTestRunner(verbosity=2).run(suite)
		if not result.wasSuccessful():
			raise RuntimeError("Record change integration tests failed")
		return dict(tests=result.testsRun, success=True)
	finally:
		frappe.db.rollback()
		frappe.set_user(original_user)
