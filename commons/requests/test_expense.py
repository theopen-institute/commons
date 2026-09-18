"""The expense queue's predicate, who may settle a claim, and what a claim carries.

The shape is shared -- `requests.approvals` -- and `commons.requests.test_leave`
pins the same invariants through it for the same reasons: one predicate behind
the page and the badge, a decision vocabulary that is derived rather than spelled
out, and a request whose field list and employee are the server's.

What is worth reading here is where the two differ, because each difference is
something HRMS does to expense claims and not to leave:

* preventing self-approval takes away *every* outcome, not just the affirmative
  one, and takes the row out of the queue and the badge along with it;
* the backstop is a claim naming nobody rather than a role, because the
  doctype's permission rows cannot tell an approver from an owner;
* a claim carries money, so the rate it is priced at, the cost centre it is
  charged to and the amount that opens as sanctioned are all settled server-side.
"""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.requests import expense as api

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. The messages here are the source strings
# either way -- see `test_leave`, which does the same.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


def approval_status_field(options="Draft\nApproved\nRejected\nCancelled"):
	return SimpleNamespace(options=options)


def workflow(transitions, state_field="workflow_state"):
	return SimpleNamespace(
		name="Expense",
		workflow_state_field=state_field,
		states=[],
		transitions=[SimpleNamespace(**row) for row in transitions],
	)


class TestQueuePredicate(TestCase):
	"""One predicate behind the page and the badge, so the two cannot disagree."""

	def setUp(self):
		self.session = patch.object(
			api.frappe, "session", SimpleNamespace(user="approver@example.com")
		)
		self.session.start()
		self.addCleanup(self.session.stop)
		# Nothing in this class is about self-approval; the case that is patches
		# over this.
		self.db = patch.object(
			api.frappe,
			"db",
			SimpleNamespace(get_single_value=lambda *a, **k: 0, get_value=lambda *a, **k: None),
		)
		self.db.start()
		self.addCleanup(self.db.stop)

	def test_pending_is_undecided_and_draft_not_merely_undecided(self):
		"""An approval status set from the desk without a submit settles nothing."""
		filters, _or_filters = api.EXPENSES.queue_predicate(decided=False, admin=False)
		self.assertEqual(filters, {"docstatus": 0, "approval_status": "Draft"})

	def test_pending_is_the_claims_naming_you_and_the_ones_naming_nobody(self):
		"""The backstop `may_decide` describes, as a filter."""
		_filters, or_filters = api.EXPENSES.queue_predicate(decided=False, admin=False)
		self.assertEqual(
			or_filters,
			[
				["expense_approver", "=", "approver@example.com"],
				["expense_approver", "is", "not set"],
			],
		)

	def test_decided_is_submitted_whatever_the_decision_was(self):
		filters, or_filters = api.EXPENSES.queue_predicate(decided=True, admin=False)
		self.assertEqual(
			filters, {"docstatus": 1, "expense_approver": "approver@example.com"}
		)
		# History needs no second clause: a claim that named nobody has the
		# decider written onto it as it is settled.
		self.assertIsNone(or_filters)

	def test_your_own_claims_leave_the_queue_where_the_site_forbids_settling_them(self):
		"""HRMS refuses the submit itself, so such a row has no action at all."""
		db = SimpleNamespace(
			get_single_value=lambda *a, **k: 1,
			get_value=lambda *a, **k: "EMP-ME",
		)
		with patch.object(api.frappe, "db", db):
			filters, _or_filters = api.EXPENSES.queue_predicate(decided=False, admin=False)
		self.assertEqual(filters["employee"], ["!=", "EMP-ME"])

	def test_they_stay_in_history_even_then(self):
		"""Somebody else settled it; it is still a claim they were part of."""
		db = SimpleNamespace(
			get_single_value=lambda *a, **k: 1,
			get_value=lambda *a, **k: "EMP-ME",
		)
		with patch.object(api.frappe, "db", db):
			filters, _or_filters = api.EXPENSES.queue_predicate(decided=True, admin=False)
		self.assertNotIn("employee", filters)

	def test_the_badge_counts_exactly_what_the_page_would_list(self):
		"""One predicate, one ceiling -- the two cannot promise different numbers."""
		with patch.object(api.frappe, "get_list", return_value=["a", "b"]) as get_list:
			self.assertEqual(api.EXPENSES.pending_count(None, admin=False), 2)

		filters, or_filters = api.EXPENSES.queue_predicate(decided=False, admin=False)
		self.assertEqual(get_list.call_args.kwargs["filters"], filters)
		self.assertEqual(get_list.call_args.kwargs["or_filters"], or_filters)
		self.assertEqual(get_list.call_args.kwargs["limit_page_length"], api.EXPENSES.page_length)

	def test_a_workflow_badge_counts_rows_the_workflow_would_let_this_user_move(self):
		"""Not the rows in a movable state -- the ones with an action on them."""
		active = workflow([])
		with (
			patch.object(api.approvals.wf, "names_in_movable_states", return_value=["a", "b", "c"]),
			patch.object(
				api.approvals.wf,
				"permitted_transitions",
				return_value={"a": [{"action": "Approve"}], "b": [], "c": [{"action": "Reject"}]},
			),
		):
			self.assertEqual(api.EXPENSES.pending_count(active, admin=False), 2)


class TestDecisionVocabulary(TestCase):
	"""What an approver may be offered is derived, never spelled out here."""

	def test_without_a_workflow_the_outcomes_are_the_decision_fields_own_options(self):
		meta = SimpleNamespace(get_field=lambda _name: approval_status_field())
		with patch.object(api.frappe, "get_meta", return_value=meta):
			offered = api.EXPENSES.decision_vocabulary(None)
		self.assertEqual([row["value"] for row in offered], ["Approved", "Rejected"])

	def test_the_vocabulary_is_read_off_approval_status_not_status(self):
		"""`status` is HRMS's derived readout and carries Paid, Unpaid and Draft."""
		asked = []

		def get_field(name):
			asked.append(name)
			return approval_status_field()

		with patch.object(api.frappe, "get_meta", return_value=SimpleNamespace(get_field=get_field)):
			api.EXPENSES.decision_vocabulary(None)
		self.assertEqual(asked, ["approval_status"])

	def test_an_outcome_a_site_adds_by_property_setter_is_offered(self):
		meta = SimpleNamespace(
			get_field=lambda _name: approval_status_field(
				"Draft\nApproved\nRejected\nQueried\nCancelled"
			)
		)
		with patch.object(api.frappe, "get_meta", return_value=meta):
			offered = api.EXPENSES.decision_vocabulary(None)
		self.assertEqual([row["value"] for row in offered], ["Approved", "Rejected", "Queried"])
		# Unknown to this app, so unstyled -- and confirmed, because only the
		# affirmative outcome is applied without asking twice.
		queried = offered[-1]
		self.assertIsNone(queried["style"])
		self.assertTrue(queried["confirm"])

	def test_the_affirmative_outcome_is_the_one_a_page_may_apply_outright(self):
		meta = SimpleNamespace(get_field=lambda _name: approval_status_field())
		with patch.object(api.frappe, "get_meta", return_value=meta):
			offered = {row["value"]: row for row in api.EXPENSES.decision_vocabulary(None)}
		self.assertFalse(offered["Approved"]["confirm"])
		self.assertTrue(offered["Rejected"]["confirm"])

	def test_with_a_workflow_the_outcomes_are_its_actions_styled_by_the_site(self):
		active = workflow(
			[
				{"action": "Approve", "next_state": "Approved"},
				{"action": "Approve", "next_state": "Approved"},
				{"action": "Query", "next_state": "Draft"},
			]
		)
		with patch.object(
			api.approvals.wf, "state_styles", return_value={"Approved": "Success", "Draft": "Warning"}
		):
			offered = api.EXPENSES.decision_vocabulary(active)
		# Parallel rows granting one action to two roles are one button.
		self.assertEqual([row["value"] for row in offered], ["Approve", "Query"])
		self.assertEqual(offered[0]["style"], "Success")
		self.assertFalse(offered[0]["confirm"])
		self.assertTrue(offered[1]["confirm"])


class TestStatusDisplay(TestCase):
	"""How a row reads is the server's answer, so the page holds no status names."""

	def row(self, **fields):
		return api.frappe._dict({"approval_status": "Draft", "docstatus": 0, **fields})

	def test_an_unsubmitted_claim_is_pending_whatever_its_approval_status_says(self):
		label, _style = api.EXPENSES.status_display(self.row(approval_status="Approved"), None, {})
		self.assertEqual(label, "Pending")

	def test_a_cancelled_claim_reads_as_cancelled_not_as_its_decision(self):
		label, _style = api.EXPENSES.status_display(
			self.row(approval_status="Approved", docstatus=2), None, {}
		)
		self.assertEqual(label, "Cancelled")

	def test_a_decided_claim_reads_as_its_outcome(self):
		label, style = api.EXPENSES.status_display(
			self.row(approval_status="Rejected", docstatus=1), None, {}
		)
		self.assertEqual((label, style), ("Rejected", "Danger"))

	def test_whether_it_has_been_paid_is_a_separate_answer(self):
		"""`status` rides along beside the decision rather than replacing it."""
		label, _style = api.EXPENSES.status_display(
			self.row(approval_status="Approved", status="Unpaid", docstatus=1), None, {}
		)
		self.assertEqual(label, "Approved")

	def test_with_a_workflow_the_state_is_the_answer_and_the_site_styles_it(self):
		active = workflow([])
		row = self.row(workflow_state="With Finance")
		label, style = api.EXPENSES.status_display(row, active, {"With Finance": "Warning"})
		self.assertEqual((label, style), ("With Finance", "Warning"))


# What `get_expense_permissions` would have sent for a site running no workflow.
VOCABULARY = [
	{"value": "Approved", "style": "Success", "confirm": False},
	{"value": "Rejected", "style": "Danger", "confirm": True},
]


class TestPermittedDecisions(TestCase):
	"""Which outcomes a *row* accepts, which is narrower than who may decide."""

	def decisions(self, row, *, can_submit=True, blocked=False):
		with (
			patch.object(api.frappe, "session", SimpleNamespace(user="me@example.com")),
			patch.object(api.EXPENSES, "self_approval_blocked", return_value=blocked),
		):
			return api.EXPENSES.permitted_decisions(row, None, VOCABULARY, False, can_submit)

	def row(self, approver, docstatus=0):
		return api.frappe._dict(
			name="HR-EXP-1", employee="EMP-1", expense_approver=approver, docstatus=docstatus
		)

	def test_the_named_approver_gets_the_whole_vocabulary(self):
		self.assertEqual(self.decisions(self.row("me@example.com")), ["Approved", "Rejected"])

	def test_somebody_elses_claim_is_not_this_users_to_decide(self):
		self.assertEqual(self.decisions(self.row("someone@example.com")), [])

	def test_a_claim_naming_nobody_is_the_backstop(self):
		"""Not a role -- see `may_decide` for why there is no role to name."""
		self.assertTrue(self.decisions(self.row(None)))

	def test_an_already_settled_claim_offers_nothing(self):
		self.assertEqual(self.decisions(self.row("me@example.com", docstatus=1)), [])

	def test_a_reader_without_submit_is_offered_nothing(self):
		self.assertEqual(self.decisions(self.row("me@example.com"), can_submit=False), [])

	def test_self_approval_withholds_every_outcome_not_merely_the_approval(self):
		"""The one place this must not copy leave.

		`LeaveApplication` tests the outcome, so an approver may still turn their
		own application down. `ExpenseClaim` tests the submit, in `before_submit`,
		whatever the claim was settled at -- so offering a rejection here would
		draw a button the write throws on.
		"""
		self.assertEqual(self.decisions(self.row("me@example.com"), blocked=True), [])

	def test_with_a_workflow_the_transitions_are_the_answer(self):
		row = api.frappe._dict(
			name="HR-EXP-1", _transitions=[{"action": "Approve", "next_state": "Approved"}]
		)
		self.assertEqual(
			api.EXPENSES.permitted_decisions(row, workflow([]), VOCABULARY, False, True), ["Approve"]
		)


class TestSelfApprovalBlocked(TestCase):
	"""Mirrors `ExpenseClaim.validate_for_self_approval`, down to its escape."""

	def blocked(self, *, setting, user_id, active=None):
		db = SimpleNamespace(
			get_single_value=lambda *a, **k: setting,
			get_value=lambda *a, **k: user_id,
		)
		with (
			patch.object(api.frappe, "session", SimpleNamespace(user="me@example.com")),
			patch.object(api.frappe, "db", db),
		):
			return api.EXPENSES.self_approval_blocked("EMP-1", active)

	def test_blocked_when_the_setting_is_on_and_it_is_your_own_claim(self):
		self.assertTrue(self.blocked(setting=1, user_id="me@example.com"))

	def test_not_blocked_when_the_site_allows_it(self):
		self.assertFalse(self.blocked(setting=0, user_id="me@example.com"))

	def test_not_blocked_for_somebody_elses_claim(self):
		self.assertFalse(self.blocked(setting=1, user_id="someone@example.com"))

	def test_a_workflow_decides_it_instead(self):
		"""HRMS steps aside for one, so this must not second-guess the workflow."""
		self.assertFalse(self.blocked(setting=1, user_id="me@example.com", active=workflow([])))


class TestMayDecide(TestCase):
	"""The backstop, which is a claim without an approver rather than a role."""

	def may(self, approver, *, permitted=True):
		doc = api.frappe._dict(name="HR-EXP-1", expense_approver=approver)
		with (
			patch.object(api.frappe, "session", SimpleNamespace(user="me@example.com")),
			patch.object(api.frappe, "has_permission", return_value=permitted),
		):
			return api.EXPENSES.may_decide(doc)

	def test_the_named_approver_may(self):
		self.assertTrue(self.may("me@example.com"))

	def test_somebody_elses_claim_may_not_be_settled_by_role_alone(self):
		"""`Expense Approver` holds submit over every claim on the site.

		Which is the over-reach this narrows: HRMS ships that role and `HR User`
		with identical rows, so no derivation off the doctype can tell an approver
		from an owner, and taking submit at face value would hand every approver
		everyone else's claims.
		"""
		self.assertFalse(self.may("someone@example.com"))

	def test_a_claim_naming_nobody_is_anybodys_who_may_submit_it(self):
		self.assertTrue(self.may(None))

	def test_the_doctype_right_is_still_the_first_question(self):
		self.assertFalse(self.may("me@example.com", permitted=False))


class TestDecideGuard(TestCase):
	def test_an_outcome_the_server_does_not_accept_is_refused(self):
		with (
			patch.object(api.EXPENSES, "workflow", return_value=None),
			patch.object(api.EXPENSES, "decision_vocabulary", return_value=[{"value": "Approved"}]),
			patch.object(api.frappe, "throw", side_effect=ValueError) as throw,
		):
			with self.assertRaises(ValueError):
				api.decide_expense_claim("HR-EXP-1", "Maybe")
		self.assertTrue(throw.called)

	def test_a_sanctioned_figure_for_a_row_the_claim_does_not_have_is_refused(self):
		"""Skipping it would read on screen as an approval of the full amount."""
		doc = SimpleNamespace(name="HR-EXP-1", expenses=[SimpleNamespace(name="row-1")])
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				api._apply_sanctioned_amounts(doc, {"row-9": 10.0})

	def test_a_sanctioned_figure_is_written_by_row_name_not_by_position(self):
		rows = [
			SimpleNamespace(name="row-1", sanctioned_amount=5.0),
			SimpleNamespace(name="row-2", sanctioned_amount=7.0),
		]
		claim = SimpleNamespace(name="HR-EXP-1", expenses=rows)
		api._apply_sanctioned_amounts(claim, {"row-2": 3.0})
		self.assertEqual([row.sanctioned_amount for row in rows], [5.0, 3.0])

	def test_a_negative_sanctioned_amount_is_refused(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				api._sanctioned_amounts({"row-1": -1})

	def test_nothing_sent_is_nothing_changed(self):
		self.assertEqual(api._sanctioned_amounts(None), {})


class TestPermissionsPayload(TestCase):
	"""What the page is told, and where each answer comes from."""

	def permissions(self, *, setting=1, access="visible"):
		meta = SimpleNamespace(get_field=lambda _name: approval_status_field())
		with (
			patch.object(api.EXPENSES, "workflow", return_value=None),
			patch.object(api.frappe, "get_meta", return_value=meta),
			patch.object(api.frappe, "has_permission", return_value=False),
			patch.object(api.frappe, "db", SimpleNamespace(get_single_value=lambda *a: setting)),
			# Not what these pin, and they reach the database of their own accord.
			patch.object(api.approvals, "session_employee_access", return_value=access),
			patch.object(api.approvals, "session_employee_filters", return_value={}),
			patch.object(api.frappe, "get_roles", return_value=[]),
		):
			return api.get_expense_permissions()

	def test_the_offered_decisions_are_the_ones_decide_accepts(self):
		"""The page's buttons come from here, so they match what is validated."""
		meta = SimpleNamespace(get_field=lambda _name: approval_status_field())
		with patch.object(api.frappe, "get_meta", return_value=meta):
			accepted = [row["value"] for row in api.EXPENSES.decision_vocabulary(None)]
		self.assertEqual([row["value"] for row in self.permissions()["decisions"]], accepted)

	def test_the_form_is_told_what_hr_settings_says_about_the_approver(self):
		"""Mandatory is the site's answer, not the request form's assumption."""
		self.assertIs(self.permissions(setting=1)["approver_mandatory"], True)
		self.assertIs(self.permissions(setting=0)["approver_mandatory"], False)

	def test_the_page_is_told_why_there_is_no_employee_record(self):
		"""`missing` sends the reader to HR and `forbidden` to permissions."""
		for access in ("visible", "forbidden", "missing"):
			self.assertEqual(self.permissions(access=access)["employee_access"], access)


class TestApprovalsQueueGate(TestCase):
	"""Who is shown an approvals page at all, which a workflow changes."""

	def gate(self, active, *, can_submit=False, roles=()):
		with (
			patch.object(api.frappe, "has_permission", return_value=can_submit),
			patch.object(api.frappe, "get_roles", return_value=list(roles)),
		):
			return api.EXPENSES.has_approvals_queue(active, can_read=True)

	def test_without_a_workflow_it_is_the_submit_right(self):
		self.assertTrue(self.gate(None, can_submit=True))
		self.assertFalse(self.gate(None, can_submit=False))

	def test_with_a_workflow_a_transition_of_your_own_is_enough(self):
		"""A state that routes a claim back to its author submits nothing."""
		active = workflow([{"allowed": "Line Manager", "action": "Query", "next_state": "Draft"}])
		self.assertTrue(self.gate(active, can_submit=False, roles=["Line Manager"]))

	def test_with_a_workflow_holding_none_of_its_roles_is_no_queue(self):
		active = workflow([{"allowed": "Line Manager", "action": "Query", "next_state": "Draft"}])
		self.assertFalse(self.gate(active, can_submit=True, roles=["Employee"]))

	def test_a_reader_who_cannot_read_has_no_queue_either(self):
		active = workflow([{"allowed": "Line Manager", "action": "Approve", "next_state": "Done"}])
		with (
			patch.object(api.frappe, "has_permission", return_value=True),
			patch.object(api.frappe, "get_roles", return_value=["Line Manager"]),
		):
			self.assertFalse(api.EXPENSES.has_approvals_queue(active, can_read=False))


class TestRequestExpenseClaim(TestCase):
	"""The field list a claim may set is the server's, and so is the money."""

	def request(self, payload, employee="EMP-1"):
		inserted = {}

		def get_doc(values):
			inserted.update(values)
			return SimpleNamespace(insert=lambda: SimpleNamespace(as_dict=lambda: values))

		context = api.frappe._dict(
			company="Acme",
			company_currency="NPR",
			currency="NPR",
			cost_center="Main - A",
		)
		with (
			patch.object(
				api.approvals,
				"session_employee",
				return_value=api.frappe._dict(name=employee, company="Acme", salary_currency="NPR"),
			),
			patch.object(api, "_claim_context", return_value=context),
			patch.object(api, "_exchange_rate", return_value=1.0),
			patch.object(api.frappe, "parse_json", side_effect=lambda value: value),
			patch.object(api.frappe, "get_doc", side_effect=get_doc),
		):
			api.request_expense_claim(payload)
		return inserted

	def expenses(self, **overrides):
		return [{"expense_date": "2026-09-17", "expense_type": "Travel", "amount": 120, **overrides}]

	def test_the_employee_comes_from_the_session_not_from_the_payload(self):
		values = self.request({"expenses": self.expenses()})
		self.assertEqual(values["employee"], "EMP-1")

	def test_a_field_outside_the_request_form_is_dropped(self):
		"""`approval_status` sits at permlevel 1; the series is the doctype's."""
		values = self.request(
			{
				"expenses": self.expenses(),
				"approval_status": "Approved",
				"naming_series": "X-",
				"docstatus": 1,
				"total_sanctioned_amount": 9999,
			}
		)
		for field in ("approval_status", "naming_series", "docstatus", "total_sanctioned_amount"):
			self.assertNotIn(field, values)

	def test_the_money_the_claim_is_priced_at_is_the_servers(self):
		"""What the desk collects with four round trips of JavaScript."""
		values = self.request({"expenses": self.expenses()})
		self.assertEqual(values["company"], "Acme")
		self.assertEqual(values["currency"], "NPR")
		self.assertEqual(values["cost_center"], "Main - A")
		self.assertEqual(values["exchange_rate"], 1.0)

	def test_a_row_opens_sanctioned_at_what_was_claimed(self):
		"""A claim that reached submission sanctioning nothing would book nothing."""
		values = self.request({"expenses": self.expenses()})
		row = values["expenses"][0]
		self.assertEqual((row["amount"], row["sanctioned_amount"]), (120.0, 120.0))

	def test_a_row_cannot_sanction_itself(self):
		values = self.request({"expenses": self.expenses(sanctioned_amount=500)})
		self.assertEqual(values["expenses"][0]["sanctioned_amount"], 120.0)

	def test_a_row_carries_the_cost_centre_the_desk_copies_down(self):
		"""Without it `validate_account_details` refuses to book the claim."""
		values = self.request({"expenses": self.expenses()})
		self.assertEqual(values["expenses"][0]["cost_center"], "Main - A")

	def test_a_claim_with_nothing_on_it_is_refused(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				self.request({"expenses": []})

	def test_an_expense_without_an_amount_is_refused(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				self.request({"expenses": self.expenses(amount=0)})

	def test_expenses_cannot_be_claimed_for_somebody_else(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				self.request({"employee": "EMP-2", "expenses": self.expenses()})


class TestClaimTypes(TestCase):
	"""A type the company cannot book to is not a choice, it is a failed save."""

	def types(self, parents, catalogue=()):
		def get_all(doctype, **kwargs):
			if doctype == "Expense Claim Account":
				return list(parents)
			return list(catalogue)

		with patch.object(api.frappe, "get_all", side_effect=get_all):
			return api.claim_types("Acme")

	def test_only_types_with_an_account_for_this_company_are_offered(self):
		"""`set_expense_account` throws on save for any other, so offering it lies."""
		self.types(["Travel"], [{"name": "Travel", "description": None}])

		def get_all(doctype, **kwargs):
			if doctype == "Expense Claim Account":
				self.assertEqual(kwargs["filters"]["company"], "Acme")
				self.assertEqual(kwargs["filters"]["default_account"], ["is", "set"])
				return ["Travel"]
			self.assertEqual(kwargs["filters"], {"name": ["in", ["Travel"]]})
			return [{"name": "Travel", "description": None}]

		with patch.object(api.frappe, "get_all", side_effect=get_all):
			self.assertEqual(api.claim_types("Acme"), [{"name": "Travel", "description": None}])

	def test_a_company_with_nothing_configured_offers_nothing(self):
		"""The form then says so, which sends the reader to Accounts."""
		self.assertEqual(self.types([]), [])

	def test_no_company_is_no_answer_rather_than_every_type(self):
		self.assertEqual(api.claim_types(None), [])
