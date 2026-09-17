"""What the self-service section derives rather than states, and where each answer comes from.

The section's whole claim is that someone reads a record they own and never
writes it, and that everything shaping the pages around that -- which record is
theirs, which fields may be proposed, which requests are open, which outcomes
exist and how each one reads -- is one answer given in one place. These pin the
derivations, because a derivation that quietly turns into a literal is the
failure that has no symptoms until a site renames something.

The registry gets the most attention, because it is what the generic half rests
on: `Record Change Request` names a doctype and a document, and a policy is the
only thing that turns that pair into "your record, and these are the fields you
may propose".

Site-less by design, the way `test_leave_api` is: nothing here needs a database
to be wrong in an interesting way.
"""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from tbs_commons.self_service import api, registry
from tbs_commons.self_service.doctype.record_change_request.record_change_request import normalized

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. The messages here are the source strings
# either way -- see `test_leave_api`, which does the same.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


def status_field(options="\nPending\nApproved\nRejected\nWithdrawn", default="Pending"):
	return SimpleNamespace(options=options, default=default)


def workflow(states, transitions, state_field="status"):
	return SimpleNamespace(
		name="Changes",
		workflow_state_field=state_field,
		states=[SimpleNamespace(state=state) for state in states],
		transitions=[SimpleNamespace(**row) for row in transitions],
	)


def with_policies(test, policies: dict):
	"""Swap the registry for a fixed set of policies, cache and hook included."""
	test.enterContext(patch.object(registry, "policies", return_value=policies))


def with_db(test, values: dict, exists=True):
	"""Stand in for `frappe.db` with a fixed answer per (doctype, name).

	`frappe.db` is a request-local proxy and there is no request here, so it is
	replaced outright rather than patched attribute by attribute -- patching
	through the proxy would have to bind it first, which is the very thing a
	site-less run cannot do.
	"""
	test.enterContext(
		patch.object(
			registry.frappe,
			"db",
			SimpleNamespace(
				get_value=lambda doctype, name, _field: values.get((doctype, name)),
				exists=lambda _doctype, _filters: exists,
			),
		)
	)


class TestRegistry(TestCase):
	"""A doctype means nothing here until a policy says what it is."""

	def test_an_unregistered_doctype_is_refused_rather_than_defaulted(self):
		"""The default for a doctype nobody thought about is that its fields are
		not anyone's to propose -- a permissive fallback would turn every doctype
		on the site into a self-service form."""
		with_policies(self, {})
		with self.assertRaises(Exception):
			registry.policy("Sales Invoice")

	def test_a_policys_proposable_list_is_filtered_by_what_the_doctype_still_has(self):
		"""A field renamed upstream, or hidden by a Property Setter, is not
		proposable -- answered here rather than as a save that throws."""
		with_policies(self, {"Thing": {"doctype": "Thing", "proposable": ("kept", "gone")}})
		meta = SimpleNamespace(has_field=lambda field: field == "kept")
		with patch.object(registry.frappe, "get_meta", return_value=meta):
			self.assertEqual(registry.proposable_fields("Thing"), ["kept"])

	def test_display_carries_what_the_page_needs_beyond_the_configured_fields(self):
		"""The id and the modified stamp are the header's and the footer's, not
		rows anyone configured -- so a page never asks for a field an
		administrator would have had to know to add."""
		with_policies(self, {"Thing": {"doctype": "Thing", "display": ("label",)}})
		meta = SimpleNamespace(has_field=lambda _field: True)
		with patch.object(registry.frappe, "get_meta", return_value=meta):
			self.assertEqual(registry.display_fields("Thing"), ["name", "modified", "label"])

	def test_display_never_repeats_a_field(self):
		"""A title field that is also a configured row is asked for once."""
		with_policies(
			self,
			{"Thing": {"doctype": "Thing", "title_field": "label", "display": ("label",)}},
		)
		meta = SimpleNamespace(has_field=lambda _field: True)
		with patch.object(registry.frappe, "get_meta", return_value=meta):
			self.assertEqual(registry.display_fields("Thing"), ["name", "label", "modified"])

	def test_a_direct_owner_field_names_the_user(self):
		with_policies(self, {"Employee": {"doctype": "Employee", "owner_field": "user_id"}})
		with_db(self, {("Employee", "HR-EMP-1"): "kim@example.com"})
		self.assertEqual(registry.owner_of("Employee", "HR-EMP-1"), "kim@example.com")

	def test_ownership_chains_through_another_registered_doctype(self):
		"""How a record that hangs off the employee rather than off the login is
		meant to be added: it names its Employee, and whoever owns that owns it."""
		with_policies(
			self,
			{
				"Employee": {"doctype": "Employee", "owner_field": "user_id"},
				"Employee Education": {
					"doctype": "Employee Education",
					"owner_field": "employee",
					"owner_doctype": "Employee",
				},
			},
		)
		with_db(
			self,
			{
				("Employee Education", "EDU-1"): "HR-EMP-1",
				("Employee", "HR-EMP-1"): "kim@example.com",
			},
		)
		self.assertEqual(registry.owner_of("Employee Education", "EDU-1"), "kim@example.com")

	def test_a_blank_owner_field_means_nobody_owns_it(self):
		"""An employee with no login yet belongs to nobody -- which the callers
		read as "not yours", not as a failure."""
		with_policies(self, {"Employee": {"doctype": "Employee", "owner_field": "user_id"}})
		with_db(self, {})
		self.assertIsNone(registry.owner_of("Employee", "HR-EMP-1"))

	def test_a_record_that_fails_its_policys_filters_belongs_to_nobody(self):
		"""A leaver's record stops being theirs to correct the day they leave,
		rather than on the day somebody remembers."""
		with_policies(
			self,
			{
				"Employee": {
					"doctype": "Employee",
					"owner_field": "user_id",
					"filters": {"status": "Active"},
				}
			},
		)
		with_db(self, {("Employee", "HR-EMP-1"): "kim@example.com"}, exists=None)
		self.assertIsNone(registry.owner_of("Employee", "HR-EMP-1"))

	def test_a_circular_chain_is_answered_rather_than_looped(self):
		"""Chains are configuration, so a mistake in one has to end somewhere."""
		with_policies(
			self,
			{
				"A": {"doctype": "A", "owner_field": "b", "owner_doctype": "B"},
				"B": {"doctype": "B", "owner_field": "a", "owner_doctype": "A"},
			},
		)
		with_db(self, {("A", "1"): "1", ("B", "1"): "1"})
		self.assertIsNone(registry.owner_of("A", "1"))

	def test_a_non_singular_policy_has_no_my_record(self):
		"""Many rows is not one answer, and returning whichever came first would
		be worse than saying so."""
		with_policies(self, {"Skill": {"doctype": "Skill", "owner_field": "employee"}})
		with self.assertRaises(Exception):
			registry.session_record("Skill")


class TestInitialState(TestCase):
	"""Which state counts as "not decided yet" is derived, never spelled."""

	def test_comes_from_the_workflows_first_state(self):
		"""Frappe assigns a document its workflow's first state, so that is the one."""
		self.assertEqual(api.initial_state(workflow(["Awaiting HR", "Approved"], [])), "Awaiting HR")

	def test_falls_back_to_the_status_fields_own_default(self):
		"""Without a workflow the field's default is what a new request carries."""
		meta = SimpleNamespace(get_field=lambda _: status_field(default="Raised"))
		with patch.object(api.frappe, "get_meta", return_value=meta):
			self.assertEqual(api.initial_state(None), "Raised")


class TestQueueFilters(TestCase):
	"""The badge and the page ask one question, and it is this one."""

	def setUp(self):
		meta = SimpleNamespace(get_field=lambda _: status_field())
		self.enterContext(patch.object(api.frappe, "get_meta", return_value=meta))
		self.enterContext(patch.object(api, "change_workflow", return_value=None))

	def test_open_is_the_initial_state_not_a_docstatus(self):
		"""`docstatus` cannot answer it: a declined request stays at 0 to stay amendable."""
		self.assertEqual(api._queue_filters(decided=False), {"status": "Pending"})

	def test_settled_is_everything_else(self):
		"""One predicate, negated -- so nothing can be in neither queue."""
		self.assertEqual(api._queue_filters(decided=True), {"status": ["!=", "Pending"]})

	def test_a_queue_can_be_narrowed_to_one_record_type(self):
		"""The reviewer's page asks for all of them; a per-record page could not."""
		self.assertEqual(
			api._queue_filters(decided=False, doctype="Employee"),
			{"status": "Pending", "reference_doctype": "Employee"},
		)

	def test_a_renamed_initial_state_moves_both_queues_together(self):
		meta = SimpleNamespace(get_field=lambda _: status_field(default="Raised"))
		with patch.object(api.frappe, "get_meta", return_value=meta):
			self.assertEqual(api._queue_filters(decided=False), {"status": "Raised"})
			self.assertEqual(api._queue_filters(decided=True), {"status": ["!=", "Raised"]})


class TestDecisionVocabulary(TestCase):
	"""Which outcomes exist, and how each one reads."""

	def test_without_a_workflow_they_are_the_status_options_less_the_initial_one(self):
		meta = SimpleNamespace(get_field=lambda _: status_field())
		with patch.object(api.frappe, "get_meta", return_value=meta):
			offered = api.decision_vocabulary(None)
		self.assertEqual([row["value"] for row in offered], ["Approved", "Rejected", "Withdrawn"])

	def test_the_affirmative_outcome_is_the_only_one_not_confirmed(self):
		"""Read off the style, so a workflow that renames approval still gets one solid button."""
		meta = SimpleNamespace(get_field=lambda _: status_field())
		with patch.object(api.frappe, "get_meta", return_value=meta):
			confirm = {row["value"]: row["confirm"] for row in api.decision_vocabulary(None)}
		self.assertEqual(confirm, {"Approved": False, "Rejected": True, "Withdrawn": True})

	def test_with_a_workflow_the_outcomes_are_its_actions(self):
		"""And the styling is the site's -- an action reads as the state it leads to."""
		active = workflow(
			["Pending"],
			[
				{"state": "Pending", "action": "Apply", "next_state": "Applied"},
				{"state": "Pending", "action": "Turn down", "next_state": "Declined"},
			],
		)
		with patch.object(api.wf, "state_styles", return_value={"Applied": "Success", "Declined": "Danger"}):
			offered = api.decision_vocabulary(active)
		self.assertEqual(
			offered,
			[
				{"value": "Apply", "style": "Success", "confirm": False},
				{"value": "Turn down", "style": "Danger", "confirm": True},
			],
		)

	def test_one_button_per_action_however_many_roles_it_is_granted_to(self):
		"""Parallel transition rows are how a Workflow grants one action to several
		roles; `apply_workflow` takes only the name, so they are one choice."""
		active = workflow(
			["Pending"],
			[
				{"state": "Pending", "action": "Approve", "next_state": "Approved"},
				{"state": "Pending", "action": "Approve", "next_state": "Approved"},
			],
		)
		with patch.object(api.wf, "state_styles", return_value={"Approved": "Success"}):
			self.assertEqual([row["value"] for row in api.decision_vocabulary(active)], ["Approve"])


class TestRecordAccess(TestCase):
	"""Why there is nothing to show, which decides who the reader is sent to.

	Unit-tested rather than driven through a real gate: `Custom DocPerm` rows
	cannot live inside a rollback-only suite (see
	`safer_permissions.test_permission_gate_integration`), and what matters here
	is the decision, not the mechanism that produces it.
	"""

	def test_a_readable_record_is_visible(self):
		with patch.object(api.registry, "session_records", return_value=[{"name": "HR-EMP-1"}]):
			self.assertEqual(api._record_access("Employee"), "visible")

	def test_a_withheld_record_is_forbidden_not_missing(self):
		"""The one worth having. Telling someone their record does not exist, when
		it does and the site is withholding it, sends them to HR to fix something
		HR has already done."""
		with (
			patch.object(api.registry, "session_records", return_value=[]),
			patch.object(api.registry, "record_exists", return_value=True),
		):
			self.assertEqual(api._record_access("Employee"), "forbidden")

	def test_no_row_at_all_is_missing(self):
		with (
			patch.object(api.registry, "session_records", return_value=[]),
			patch.object(api.registry, "record_exists", return_value=False),
		):
			self.assertEqual(api._record_access("Employee"), "missing")


class TestStatusDisplay(TestCase):
	"""How a row reads -- which `status` alone does not answer."""

	def test_a_reversed_request_does_not_go_on_reading_as_approved(self):
		"""`on_cancel` deliberately leaves `status` alone, so docstatus is read first."""
		row = SimpleNamespace(status="Approved", docstatus=2, get=lambda _field: None)
		self.assertEqual(api.status_display(row, None, {}), ("Reversed", None))

	def test_without_a_workflow_the_status_is_styled_from_the_default_map(self):
		row = SimpleNamespace(status="Rejected", docstatus=0, get=lambda _field: None)
		self.assertEqual(api.status_display(row, None, {}), ("Rejected", "Danger"))

	def test_with_a_workflow_the_state_and_the_sites_own_style_win(self):
		active = workflow(["Awaiting HR"], [], state_field="workflow_state")
		row = SimpleNamespace(
			status="Pending", docstatus=0, get=lambda field: {"workflow_state": "Awaiting HR"}[field]
		)
		self.assertEqual(
			api.status_display(row, active, {"Awaiting HR": "Warning"}), ("Awaiting HR", "Warning")
		)


class TestNormalized(TestCase):
	"""Frappe's two ways of storing an empty field, reduced to one."""

	def test_blank_and_null_are_the_same_answer(self):
		"""Otherwise clearing a field and leaving it blank read as a change."""
		self.assertIsNone(normalized(None))
		self.assertIsNone(normalized(""))
		self.assertIsNone(normalized("   "))

	def test_surrounding_whitespace_is_not_a_change(self):
		self.assertEqual(normalized("  0712 345 678  "), "0712 345 678")


class TestRequestFields(TestCase):
	"""What a request is allowed to state about itself."""

	def test_a_row_may_not_state_the_value_it_is_replacing(self):
		"""`current_value` is captured from the record, so a request cannot claim a
		"before" that was never true."""
		self.assertNotIn("current_value", api.CHANGE_ROW_FIELDS)

	def test_a_request_may_not_name_its_own_record_or_status(self):
		"""The record comes from the session and the status from the doctype."""
		for fieldname in ("reference_doctype", "reference_name", "reference_title", "status"):
			self.assertNotIn(fieldname, api.REQUEST_FIELDS)


class TestSeededConfiguration(TestCase):
	"""The configuration this app ships, checked as policy rather than as code.

	These are assertions about the seed -- what a fresh site starts with. A site
	that has since edited its `Self Service Record` documents is not bound by
	them, which is the point of holding the configuration as documents.
	"""

	def setUp(self):
		from tbs_commons.self_service.policies import SEED

		self.seed = {entry["document_type"]: entry for entry in SEED}

	def viewable(self, doctype):
		return {row[1] for row in self.seed[doctype]["fields"]}

	def proposable(self, doctype):
		return {row[1] for row in self.seed[doctype]["fields"] if row[2]}

	def test_pay_is_not_in_the_employee_profile_at_all(self):
		"""Not merely un-proposable: never sent."""
		for fieldname in ("ctc", "salary_mode", "bank_ac_no", "salary_currency"):
			self.assertNotIn(fieldname, self.viewable("Employee"))

	def test_employment_and_identity_are_shown_but_not_proposable(self):
		"""They are decisions the organisation made, or documents-in-hand facts --
		and you cannot check your own record without seeing them."""
		for fieldname in (
			"company",
			"status",
			"department",
			"designation",
			"date_of_joining",
			"user_id",
			"leave_approver",
			"first_name",
			"date_of_birth",
		):
			self.assertIn(fieldname, self.viewable("Employee"))
			self.assertNotIn(fieldname, self.proposable("Employee"))

	def test_the_details_an_employee_is_the_authority_on_are_proposable(self):
		for fieldname in ("cell_number", "current_address", "person_to_be_contacted"):
			self.assertIn(fieldname, self.proposable("Employee"))

	def test_a_leavers_record_stops_being_theirs(self):
		self.assertEqual(self.seed["Employee"]["record_filters"], '{"status": "Active"}')

	def test_bank_accounts_are_read_only_and_carry_no_credentials(self):
		self.assertEqual(self.proposable("Bank Account"), set())
		for fieldname in ("statement_password", "integration_id"):
			self.assertNotIn(fieldname, self.viewable("Bank Account"))

	def test_bank_accounts_chain_ownership_and_pin_the_party_type(self):
		"""`party` is a Dynamic Link, so without the filter this would claim any
		party whose id happened to match an employee's."""
		entry = self.seed["Bank Account"]
		self.assertEqual(entry["owner_field"], "party")
		self.assertEqual(entry["owner_doctype"], "Employee")
		self.assertEqual(entry["record_filters"], '{"party_type": "Employee"}')
		self.assertFalse(entry["is_singular"])
