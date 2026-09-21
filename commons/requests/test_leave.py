"""Leave's half of the shared request shape, and where each answer comes from.

What is pinned here is leave's own configuration of `requests.approvals` --
its queue predicate, its backstop role, the outcome self-approval costs -- run
through the shared implementation. `test_expense` pins the same invariants for
expenses, and where the two assertions differ is exactly where the two sections
differ.

The predicate used to be stated twice -- once here and once in a list query the
frontend built for itself -- and the two drifted: the badge counted
`status = "Open"` and the page did not, the badge was uncapped and the page
stopped at twenty. What these pin is that there is now one predicate, and that
the count and the list are the same question asked twice.

The rest is newer. The outcomes an approver is offered, how each one reads, and
which of them a given row accepts are all derived -- from the active Workflow
where a site runs one, and from the `status` field's own options where it does
not. None of them is a literal in the frontend or, for the vocabulary, in this
app at all, and these are what say so.
"""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.requests import leave as api

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. The messages here are the source strings
# either way -- see `test_procurement_helpers`, which does the same.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


# Every test below is about a site that *has* HRMS, which is the only site
# these endpoints have anything to say on. Availability is otherwise a database
# lookup on every call -- see `approvals.RequestType.available` -- and
# `TestLeaveUnavailable` is where the other answer is pinned.
_available = patch.object(api.LEAVE, "available", return_value=True)


def setUpModule():
	_logger.start()
	_available.start()


def tearDownModule():
	_logger.stop()
	_available.stop()


def status_field(options="Open\nApproved\nRejected\nCancelled"):
	return SimpleNamespace(options=options)


def workflow(transitions, state_field="workflow_state"):
	return SimpleNamespace(
		name="Leave",
		workflow_state_field=state_field,
		states=[],
		transitions=[SimpleNamespace(**row) for row in transitions],
	)


class TestQueueFilters(TestCase):
	def setUp(self):
		self.session = patch.object(
			api.frappe, "session", SimpleNamespace(user="approver@example.com")
		)
		self.session.start()
		self.addCleanup(self.session.stop)

	def predicate(self, *, decided, admin):
		return api.LEAVE.queue_predicate(decided=decided, admin=admin)

	def test_pending_is_undecided_and_open_not_merely_undecided(self):
		"""A status set from the desk without a submit is not waiting on anyone."""
		self.assertEqual(
			self.predicate(decided=False, admin=False),
			({"docstatus": 0, "status": "Open", "leave_approver": "approver@example.com"}, None),
		)

	def test_decided_is_submitted_whatever_the_decision_was(self):
		self.assertEqual(
			self.predicate(decided=True, admin=False),
			({"docstatus": 1, "leave_approver": "approver@example.com"}, None),
		)

	def test_an_admin_sees_the_queue_they_are_the_backstop_for(self):
		self.assertEqual(
			self.predicate(decided=False, admin=True),
			({"docstatus": 0, "status": "Open"}, None),
		)

	def test_the_badge_counts_exactly_what_the_page_would_list(self):
		"""One predicate, one ceiling -- the two cannot promise different numbers."""
		with patch.object(api.frappe, "get_list", return_value=["a", "b"]) as get_list:
			self.assertEqual(api.LEAVE.pending_count(None, admin=False), 2)

		filters, or_filters = self.predicate(decided=False, admin=False)
		self.assertEqual(get_list.call_args.kwargs["filters"], filters)
		self.assertEqual(get_list.call_args.kwargs["or_filters"], or_filters)
		self.assertEqual(
			get_list.call_args.kwargs["limit_page_length"], api.LEAVE.page_length
		)

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
			self.assertEqual(api.LEAVE.pending_count(active, admin=False), 2)


class TestDecisionVocabulary(TestCase):
	"""What an approver may be offered is derived, never spelled out here."""

	def test_without_a_workflow_the_outcomes_are_the_status_fields_own_options(self):
		meta = SimpleNamespace(get_field=lambda _name: status_field())
		with patch.object(api.frappe, "get_meta", return_value=meta):
			offered = api.LEAVE.decision_vocabulary(None)
		self.assertEqual([row["value"] for row in offered], ["Approved", "Rejected"])

	def test_an_outcome_a_site_adds_by_property_setter_is_offered(self):
		meta = SimpleNamespace(
			get_field=lambda _name: status_field("Open\nApproved\nRejected\nDeferred\nCancelled")
		)
		with patch.object(api.frappe, "get_meta", return_value=meta):
			offered = api.LEAVE.decision_vocabulary(None)
		self.assertEqual(
			[row["value"] for row in offered], ["Approved", "Rejected", "Deferred"]
		)
		# Unknown to this app, so unstyled -- and confirmed, because only the
		# affirmative outcome is applied without asking twice.
		deferred = offered[-1]
		self.assertIsNone(deferred["style"])
		self.assertTrue(deferred["confirm"])

	def test_the_affirmative_outcome_is_the_one_a_page_may_apply_outright(self):
		meta = SimpleNamespace(get_field=lambda _name: status_field())
		with patch.object(api.frappe, "get_meta", return_value=meta):
			offered = {row["value"]: row for row in api.LEAVE.decision_vocabulary(None)}
		self.assertFalse(offered["Approved"]["confirm"])
		self.assertTrue(offered["Rejected"]["confirm"])

	def test_with_a_workflow_the_outcomes_are_its_actions_styled_by_the_site(self):
		active = workflow(
			[
				{"action": "Approve", "next_state": "Approved"},
				{"action": "Approve", "next_state": "Approved"},
				{"action": "Send Back", "next_state": "Draft"},
			]
		)
		with patch.object(
			api.approvals.wf, "state_styles", return_value={"Approved": "Success", "Draft": "Warning"}
		):
			offered = api.LEAVE.decision_vocabulary(active)
		# Parallel rows granting one action to two roles are one button.
		self.assertEqual([row["value"] for row in offered], ["Approve", "Send Back"])
		self.assertEqual(offered[0]["style"], "Success")
		self.assertFalse(offered[0]["confirm"])
		self.assertTrue(offered[1]["confirm"])


class TestStatusDisplay(TestCase):
	"""How a row reads is the server's answer, so the page holds no status names."""

	def row(self, **fields):
		return api.frappe._dict({"status": "Open", "docstatus": 0, **fields})

	def test_an_unsubmitted_application_is_pending_whatever_its_status_says(self):
		label, _style = api.LEAVE.status_display(self.row(status="Approved"), None, {})
		self.assertEqual(label, "Pending")

	def test_a_cancelled_application_reads_as_cancelled_not_as_its_decision(self):
		label, _style = api.LEAVE.status_display(
			self.row(status="Approved", docstatus=2), None, {}
		)
		self.assertEqual(label, "Cancelled")

	def test_a_decided_application_reads_as_its_outcome(self):
		label, style = api.LEAVE.status_display(
			self.row(status="Rejected", docstatus=1), None, {}
		)
		self.assertEqual((label, style), ("Rejected", "Danger"))

	def test_with_a_workflow_the_state_is_the_answer_and_the_site_styles_it(self):
		active = workflow([])
		row = self.row(docstatus=0, workflow_state="Awaiting Approval")
		label, style = api.LEAVE.status_display(row, active, {"Awaiting Approval": "Warning"})
		self.assertEqual((label, style), ("Awaiting Approval", "Warning"))


# What `get_leave_permissions` would have sent for a site running no workflow.
VOCABULARY = [
	{"value": "Approved", "style": "Success", "confirm": False},
	{"value": "Rejected", "style": "Danger", "confirm": True},
]


class TestPermittedDecisions(TestCase):
	"""Which outcomes a *row* accepts, which is narrower than who may decide."""

	def decisions(self, row, *, admin=False, can_submit=True, blocked=False):
		with (
			patch.object(api.frappe, "session", SimpleNamespace(user="me@example.com")),
			patch.object(api.LEAVE, "self_approval_blocked", return_value=blocked),
		):
			return api.LEAVE.permitted_decisions(row, None, VOCABULARY, admin, can_submit)

	def row(self, approver, docstatus=0):
		return api.frappe._dict(
			name="HR-LAP-1", employee="EMP-1", leave_approver=approver, docstatus=docstatus
		)

	def test_the_named_approver_gets_the_whole_vocabulary(self):
		self.assertEqual(
			self.decisions(self.row("me@example.com")), ["Approved", "Rejected"]
		)

	def test_somebody_elses_application_is_not_this_users_to_decide(self):
		self.assertEqual(self.decisions(self.row("someone@example.com")), [])

	def test_an_admin_is_the_backstop_for_somebody_elses(self):
		self.assertTrue(self.decisions(self.row("someone@example.com"), admin=True))

	def test_an_already_decided_application_offers_nothing(self):
		self.assertEqual(self.decisions(self.row("me@example.com", docstatus=1)), [])

	def test_a_reader_without_submit_is_offered_nothing(self):
		self.assertEqual(self.decisions(self.row("me@example.com"), can_submit=False), [])

	def test_self_approval_withholds_the_approval_and_nothing_else(self):
		"""HRMS refuses the approval, not the refusal -- so the page offers one."""
		self.assertEqual(
			self.decisions(self.row("me@example.com"), blocked=True), ["Rejected"]
		)

	def test_with_a_workflow_the_transitions_are_the_answer(self):
		row = api.frappe._dict(
			name="HR-LAP-1", _transitions=[{"action": "Approve", "next_state": "Approved"}]
		)
		self.assertEqual(
			api.LEAVE.permitted_decisions(row, workflow([]), VOCABULARY, False, True),
			["Approve"],
		)


class TestSelfApprovalBlocked(TestCase):
	"""Mirrors `LeaveApplication.validate_for_self_approval`, down to its escape."""

	def blocked(self, *, setting, user_id, active=None):
		db = SimpleNamespace(
			get_single_value=lambda *a, **k: setting,
			get_value=lambda *a, **k: user_id,
		)
		with (
			patch.object(api.frappe, "session", SimpleNamespace(user="me@example.com")),
			patch.object(api.frappe, "db", db),
		):
			return api.LEAVE.self_approval_blocked("EMP-1", active)

	def test_blocked_when_the_setting_is_on_and_it_is_your_own_leave(self):
		self.assertTrue(self.blocked(setting=1, user_id="me@example.com"))

	def test_not_blocked_when_the_site_allows_it(self):
		self.assertFalse(self.blocked(setting=0, user_id="me@example.com"))

	def test_not_blocked_for_somebody_elses_leave(self):
		self.assertFalse(self.blocked(setting=1, user_id="someone@example.com"))

	def test_a_workflow_decides_it_instead(self):
		"""HRMS steps aside for one, so this must not second-guess the workflow."""
		self.assertFalse(
			self.blocked(setting=1, user_id="me@example.com", active=workflow([]))
		)


class TestLeaveAdminRoles(TestCase):
	def test_the_backstop_is_read_off_the_doctype_not_named_here(self):
		with patch.object(api, "roles_with_permission", return_value={"HR Manager"}) as roles:
			self.assertEqual(api.LEAVE.admin_roles(), {"HR Manager"})
		roles.assert_called_once_with(api.LEAVE_APPLICATION, submit=1, create=1)

	def test_a_site_whose_permissions_name_nobody_has_no_backstop(self):
		with patch.object(api, "roles_with_permission", return_value=set()):
			self.assertEqual(api.LEAVE.admin_roles(), set())


class TestDecideGuard(TestCase):
	def test_an_outcome_the_server_does_not_accept_is_refused(self):
		with (
			patch.object(api.LEAVE, "workflow", return_value=None),
			patch.object(api.LEAVE, "decision_vocabulary", return_value=[{"value": "Approved"}]),
			patch.object(api.frappe, "throw", side_effect=ValueError) as throw,
		):
			with self.assertRaises(ValueError):
				api.decide_leave_application("HR-LAP-1", "Maybe")
		self.assertTrue(throw.called)

	def test_the_offered_decisions_are_the_ones_it_accepts(self):
		"""The page's buttons come from `get_leave_permissions`, so they match."""
		meta = SimpleNamespace(get_field=lambda _name: status_field())
		with (
			patch.object(api.LEAVE, "workflow", return_value=None),
			patch.object(api.frappe, "get_meta", return_value=meta),
			patch.object(api.frappe, "has_permission", return_value=False),
			patch.object(api.frappe, "db", SimpleNamespace(get_single_value=lambda *a: 1)),
			# Not what this pins, and it reaches the database of its own accord.
			patch.object(api.approvals, "session_employee_access", return_value="visible"),
			patch.object(api.approvals, "session_employee_filters", return_value={}),
			patch.object(api.LEAVE, "admin_roles", return_value=set()),
			patch.object(api.frappe, "get_roles", return_value=[]),
		):
			permissions = api.get_leave_permissions()
			accepted = [row["value"] for row in api.LEAVE.decision_vocabulary(None)]
		self.assertEqual([row["value"] for row in permissions["decisions"]], accepted)

	def test_the_form_is_told_what_hr_settings_says_about_the_approver(self):
		"""Mandatory is the site's answer, not the request form's assumption."""
		meta = SimpleNamespace(get_field=lambda _name: status_field())
		for setting, expected in ((1, True), (0, False)):
			with (
				patch.object(api.LEAVE, "workflow", return_value=None),
				patch.object(api.frappe, "get_meta", return_value=meta),
				patch.object(api.frappe, "has_permission", return_value=False),
				patch.object(
					api.frappe, "db", SimpleNamespace(get_single_value=lambda *a: setting)
				),
				patch.object(api.approvals, "session_employee_access", return_value="visible"),
				patch.object(api.approvals, "session_employee_filters", return_value={}),
			patch.object(api.approvals, "session_employee_filters", return_value={}),
				patch.object(api.LEAVE, "admin_roles", return_value=set()),
				patch.object(api.frappe, "get_roles", return_value=[]),
			):
				self.assertIs(api.get_leave_permissions()["approver_mandatory"], expected)

	def test_the_page_is_told_why_there_is_no_employee_record(self):
		"""Carried through to the page, which says different things about each.

		`missing` sends the reader to HR and `forbidden` to whoever administers
		permissions. The page said the first to both until this was here, so a
		user whose access had been revoked was asked to have HR create a record
		that already named them -- see `session_employee_access`.
		"""
		meta = SimpleNamespace(get_field=lambda _name: status_field())
		for access in ("visible", "forbidden", "missing"):
			with (
				patch.object(api.LEAVE, "workflow", return_value=None),
				patch.object(api.frappe, "get_meta", return_value=meta),
				patch.object(api.frappe, "has_permission", return_value=False),
				patch.object(api.frappe, "db", SimpleNamespace(get_single_value=lambda *a: 0)),
				patch.object(api.approvals, "session_employee_access", return_value=access),
				patch.object(api.approvals, "session_employee_filters", return_value={}),
				patch.object(api.LEAVE, "admin_roles", return_value=set()),
				patch.object(api.frappe, "get_roles", return_value=[]),
			):
				self.assertEqual(api.get_leave_permissions()["employee_access"], access)


class TestRequestLeave(TestCase):
	"""The field list a request may set is the server's, and so is the employee."""

	def request(self, payload, employee="EMP-1"):
		inserted = {}

		def get_doc(values):
			inserted.update(values)
			return SimpleNamespace(insert=lambda: SimpleNamespace(as_dict=lambda: values))

		with (
			patch.object(api.approvals, "session_employee", return_value=api.frappe._dict(name=employee)),
			patch.object(api.frappe, "parse_json", side_effect=lambda value: value),
			patch.object(api.frappe, "get_doc", side_effect=get_doc),
		):
			api.request_leave(payload)
		return inserted

	def test_the_employee_comes_from_the_session_not_from_the_payload(self):
		values = self.request({"leave_type": "Casual", "from_date": "2026-09-21"})
		self.assertEqual(values["employee"], "EMP-1")

	def test_a_field_outside_the_request_form_is_dropped(self):
		"""`status` sits at permlevel 1 and the series is the doctype's to pick."""
		values = self.request(
			{"leave_type": "Casual", "status": "Approved", "naming_series": "X-", "docstatus": 1}
		)
		self.assertNotIn("status", values)
		self.assertNotIn("naming_series", values)
		self.assertNotIn("docstatus", values)

	def test_leave_cannot_be_requested_for_somebody_else(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				self.request({"employee": "EMP-2", "leave_type": "Casual"})


class TestApprovalsQueueGate(TestCase):
	"""Who is shown an approvals page at all, which a workflow changes."""

	def gate(self, active, *, can_submit=False, roles=()):
		with (
			patch.object(api.frappe, "has_permission", return_value=can_submit),
			patch.object(api.frappe, "get_roles", return_value=list(roles)),
		):
			return api.LEAVE.has_approvals_queue(active, can_read=True)

	def test_without_a_workflow_it_is_the_submit_right(self):
		self.assertTrue(self.gate(None, can_submit=True))
		self.assertFalse(self.gate(None, can_submit=False))

	def test_with_a_workflow_a_transition_of_your_own_is_enough(self):
		"""A state that routes an application back to its author submits nothing."""
		active = workflow([{"allowed": "Line Manager", "action": "Send Back", "next_state": "Draft"}])
		self.assertTrue(self.gate(active, can_submit=False, roles=["Line Manager"]))

	def test_with_a_workflow_holding_none_of_its_roles_is_no_queue(self):
		active = workflow([{"allowed": "Line Manager", "action": "Send Back", "next_state": "Draft"}])
		self.assertFalse(self.gate(active, can_submit=True, roles=["Employee"]))

	def test_a_reader_who_cannot_read_has_no_queue_either(self):
		active = workflow([{"allowed": "Line Manager", "action": "Approve", "next_state": "Done"}])
		with (
			patch.object(api.frappe, "has_permission", return_value=True),
			patch.object(api.frappe, "get_roles", return_value=["Line Manager"]),
		):
			self.assertFalse(api.LEAVE.has_approvals_queue(active, can_read=False))


class TestLeaveUnavailable(TestCase):
	"""A site that does not run HRMS, where `Leave Application` is not a doctype.

	HRMS is not in `required_apps`, so this is a supported site rather than a
	broken one -- and what it has to do is disappear rather than fail. The
	permissions endpoint is the one that carries that: `read: false` is what
	takes the sidebar row, both tabs, the badge and the search bar's "New leave
	request" off the page, and none of the frontend has to know why.

	Everything else refuses, and refuses *first* -- before any of the calls that
	would otherwise reach a table that is not there.
	"""

	def setUp(self):
		self.unavailable = patch.object(api.LEAVE, "available", return_value=False)
		self.unavailable.start()
		self.addCleanup(self.unavailable.stop)

	def test_the_permissions_payload_says_there_is_nothing_here(self):
		payload = api.get_leave_permissions()
		self.assertFalse(payload["read"])
		self.assertFalse(payload["request"])
		self.assertFalse(payload["approve"])
		self.assertEqual(payload["decisions"], [])
		self.assertEqual(payload["pending_approvals"], 0)

	def test_the_permissions_payload_asks_the_database_nothing(self):
		"""The one endpoint every page load makes, on a site with no such doctype.

		Answered without a workflow lookup, a permission check or an employee
		read -- all three of which would be spent to fill in fields that
		`read: false` has already taken off the screen.
		"""
		with (
			patch.object(api.LEAVE, "workflow", side_effect=AssertionError) as workflow,
			patch.object(api.frappe, "has_permission", side_effect=AssertionError),
			patch.object(api.approvals, "session_employee_access", side_effect=AssertionError),
		):
			api.get_leave_permissions()
		self.assertFalse(workflow.called)

	def test_the_queue_refuses(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				api.get_leave_approval_queue()

	def test_raising_one_refuses(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				api.request_leave({"leave_type": "Casual"})

	def test_deciding_one_refuses_before_it_reads_the_vocabulary(self):
		"""Before `decision_vocabulary`, which reads the doctype's own meta."""
		with (
			patch.object(api.LEAVE, "workflow", side_effect=AssertionError),
			patch.object(api.frappe, "throw", side_effect=ValueError),
		):
			with self.assertRaises(ValueError):
				api.decide_leave_application("HR-LAP-1", "Approved")
