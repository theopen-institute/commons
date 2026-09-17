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
RECORD_BANK = "Bank Account"


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
		# the note in `policies`. Granted here so the *policy* is what is under
		# test rather than the site's permission configuration.
		self.user.reload()
		self.user.add_roles("Accounts User")

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

	def test_the_policy_offers_no_proposals_and_no_credentials(self):
		"""Read-only by policy, and two fields kept out of `display` entirely."""
		policy = registry.policy(RECORD_BANK)
		self.assertEqual(tuple(policy["proposable"]), ())
		for fieldname in ("statement_password", "integration_id"):
			self.assertNotIn(fieldname, policy["display"])

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
		self.assertFalse(permissions["request"])

	def test_an_account_you_may_not_read_is_forbidden_not_empty(self):
		"""Existence is the discriminator: a row is there and the site is
		withholding it, which is a permissions question rather than an empty
		page."""
		self.new_account("Salary")
		frappe.set_user("Administrator")
		self.user.reload()
		self.user.remove_roles("Accounts User")
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


class TestRequestModes(unittest.TestCase):
	"""Creating and deleting a record through the same request document.

	A `Change` corrects a record that exists. A `New` asks for one to be created
	and creates nothing until it is approved. A `Delete` asks for one to be
	removed. They share the allowlist, the reviewers and the workflow -- what
	these pin is that the two new shapes cannot be used to reach past any of it.
	"""

	def setUp(self):
		frappe.db.savepoint("modes_test")
		self.addCleanup(self.restore)
		frappe.set_user("Administrator")

		self.config = frappe.get_doc("Self Service Record", RECORD_BANK)
		self.config.allow_new = 1
		self.config.allow_delete = 1
		for row in self.config.fields:
			if row.fieldname in ("account_name", "bank"):
				row.proposable = 1
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


def run():
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		suite = unittest.TestSuite(
			unittest.defaultTestLoader.loadTestsFromTestCase(case)
			for case in (TestRecordChangeRequest, TestBankAccountPolicy, TestRequestModes)
		)
		result = unittest.TextTestRunner(verbosity=2).run(suite)
		if not result.wasSuccessful():
			raise RuntimeError("Record change integration tests failed")
		return dict(tests=result.testsRun, success=True)
	finally:
		frappe.db.rollback()
		frappe.set_user(original_user)
