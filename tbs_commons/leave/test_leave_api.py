"""The leave queue's predicate, and who the app thinks may decide.

Both used to be stated twice -- once here and once in a list query the frontend
built for itself -- and the two drifted: the badge counted `status = "Open"` and
the page did not, the badge was uncapped and the page stopped at twenty. What
these pin is that there is now one predicate, that the count and the list are
the same question asked twice, and that the roles are read off the doctype
rather than named in Python.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from tbs_commons.leave import api


class TestQueueFilters(TestCase):
	def setUp(self):
		self.session = patch.object(
			api.frappe, "session", SimpleNamespace(user="approver@example.com")
		)
		self.session.start()
		self.addCleanup(self.session.stop)

	def test_pending_is_undecided_and_open_not_merely_undecided(self):
		"""A status set from the desk without a submit is not waiting on anyone."""
		self.assertEqual(
			api._queue_filters(decided=False, admin=False),
			{"docstatus": 0, "status": "Open", "leave_approver": "approver@example.com"},
		)

	def test_decided_is_submitted_whatever_the_decision_was(self):
		self.assertEqual(
			api._queue_filters(decided=True, admin=False),
			{"docstatus": 1, "leave_approver": "approver@example.com"},
		)

	def test_an_admin_sees_the_queue_they_are_the_backstop_for(self):
		self.assertEqual(
			api._queue_filters(decided=False, admin=True),
			{"docstatus": 0, "status": "Open"},
		)

	def test_the_badge_counts_exactly_what_the_page_would_list(self):
		"""One predicate, one ceiling -- the two cannot promise different numbers."""
		with patch.object(api.frappe, "get_list", return_value=["a", "b"]) as get_list:
			self.assertEqual(api._pending_count(admin=False), 2)

		self.assertEqual(
			get_list.call_args.kwargs["filters"],
			api._queue_filters(decided=False, admin=False),
		)
		self.assertEqual(get_list.call_args.kwargs["limit_page_length"], api.PAGE_LENGTH)


class TestCanDecide(TestCase):
	"""`can_decide` on a row is the server's answer, not the row's docstatus."""

	def queue(self, rows, *, admin, can_submit=True):
		with (
			patch.object(api.frappe, "session", SimpleNamespace(user="me@example.com")),
			patch.object(api.frappe.utils, "cint", return_value=0),
			patch.object(api.frappe, "get_list", return_value=rows),
			patch.object(api.frappe, "has_permission", return_value=can_submit),
			patch.object(api, "leave_admin_roles", return_value={"Owner"} if admin else set()),
			patch.object(api.frappe, "get_roles", return_value=["Owner"] if admin else []),
		):
			return api.get_leave_approval_queue(0)

	def row(self, approver, docstatus=0):
		return api.frappe._dict(
			name="HR-LAP-1", leave_approver=approver, docstatus=docstatus
		)

	def test_the_named_approver_may_decide_their_own_queue(self):
		rows = self.queue([self.row("me@example.com")], admin=False)
		self.assertTrue(rows[0].can_decide)

	def test_somebody_elses_application_is_not_this_users_to_decide(self):
		rows = self.queue([self.row("someone@example.com")], admin=False)
		self.assertFalse(rows[0].can_decide)

	def test_an_admin_is_the_backstop_for_somebody_elses(self):
		rows = self.queue([self.row("someone@example.com")], admin=True)
		self.assertTrue(rows[0].can_decide)

	def test_an_already_decided_application_offers_nothing(self):
		rows = self.queue([self.row("me@example.com", docstatus=1)], admin=False)
		self.assertFalse(rows[0].can_decide)

	def test_a_reader_without_submit_is_offered_nothing(self):
		rows = self.queue([self.row("me@example.com")], admin=False, can_submit=False)
		self.assertFalse(rows[0].can_decide)


class TestLeaveAdminRoles(TestCase):
	def test_the_backstop_is_read_off_the_doctype_not_named_here(self):
		with patch.object(api, "roles_with_permission", return_value={"HR Manager"}) as roles:
			self.assertEqual(api.leave_admin_roles(), {"HR Manager"})
		roles.assert_called_once_with(api.LEAVE_APPLICATION, submit=1, create=1)

	def test_a_site_whose_permissions_name_nobody_has_no_backstop(self):
		with patch.object(api, "roles_with_permission", return_value=set()):
			self.assertEqual(api.leave_admin_roles(), set())


class TestDecideGuard(TestCase):
	def test_an_outcome_the_server_does_not_accept_is_refused(self):
		with patch.object(api.frappe, "throw", side_effect=ValueError) as throw:
			with self.assertRaises(ValueError):
				api.decide_leave_application("HR-LAP-1", "Maybe")
		self.assertTrue(throw.called)

	def test_the_offered_decisions_are_the_ones_it_accepts(self):
		"""The page's buttons come from `get_leave_permissions`, so they match."""
		with (
			patch.object(api.frappe, "has_permission", return_value=False),
			patch.object(api, "leave_admin_roles", return_value=set()),
			patch.object(api.frappe, "get_roles", return_value=[]),
		):
			offered = api.get_leave_permissions()["decisions"]
		self.assertEqual(tuple(offered), api.DECISIONS)
