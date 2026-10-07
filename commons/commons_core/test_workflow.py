"""Which queue candidates are this user's, found before a page is cut.

Site-less: `permitted_transitions` is the site's answer and is stubbed here. What
is pinned is the search around it -- that twenty candidates somebody else must
act on no longer hide the ones waiting on this user -- and the self-approval rule
`apply_workflow` adds to `get_transitions`, which a button must not outrun.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from commons.commons_core import workflow as wf

MOVE = [{"action": "Approve"}]


def transitions(mine):
	"""A stub `permitted_transitions` that offers a move on exactly the names in `mine`."""
	calls = []

	def permitted(doctype, names, workflow=None):
		calls.append(list(names))
		return {name: (MOVE if name in mine else []) for name in names}

	return permitted, calls


class FirstActionable(TestCase):
	def test_rows_beyond_the_first_page_are_found(self):
		"""The failure: twenty rows for somebody else at the top, and an empty queue."""
		names = [f"theirs-{i}" for i in range(20)] + ["mine-1", "mine-2"]
		permitted, _calls = transitions({"mine-1", "mine-2"})
		with patch.object(wf, "permitted_transitions", side_effect=permitted):
			found = wf.first_actionable("ToDo", names, object(), limit=20)
		self.assertEqual(list(found), ["mine-1", "mine-2"])
		self.assertEqual(found["mine-1"], MOVE)

	def test_the_candidates_order_is_kept(self):
		names = ["c", "a", "b"]
		permitted, _calls = transitions({"a", "b", "c"})
		with patch.object(wf, "permitted_transitions", side_effect=permitted):
			self.assertEqual(list(wf.first_actionable("ToDo", names, object(), limit=20)), ["c", "a", "b"])

	def test_it_stops_at_a_page(self):
		names = [f"mine-{i}" for i in range(50)]
		permitted, calls = transitions(set(names))
		with patch.object(wf, "permitted_transitions", side_effect=permitted):
			found = wf.first_actionable("ToDo", names, object(), limit=20)
		self.assertEqual(len(found), 20)
		# A first page that is all actionable costs one batch, as it did before.
		self.assertEqual(len(calls), 1)

	def test_the_search_is_bounded(self):
		names = [f"theirs-{i}" for i in range(100)] + ["mine"]
		permitted, calls = transitions({"mine"})
		with patch.object(wf, "permitted_transitions", side_effect=permitted):
			found = wf.first_actionable("ToDo", names, object(), limit=20, scan_limit=60)
		self.assertEqual(found, {})
		self.assertEqual(sum(len(batch) for batch in calls), 60)

	def test_nothing_to_look_through_is_nothing(self):
		with patch.object(wf, "permitted_transitions") as permitted:
			self.assertEqual(wf.first_actionable("ToDo", [], object(), limit=20), {})
		permitted.assert_not_called()


def row(action, next_state="Next", allow_self_approval=0):
	"""One transition as `get_transitions` returns it."""
	return frappe._dict(action=action, next_state=next_state, allow_self_approval=allow_self_approval)


def as_user(user):
	return patch.object(wf.frappe, "session", SimpleNamespace(user=user), create=True)


class ApprovableActions(TestCase):
	"""The bug: `get_transitions` offered an owner a self-approval the write refused."""

	def test_an_owner_is_not_offered_what_self_approval_forbids(self):
		doc = frappe._dict(owner="me@example.com")
		with as_user("me@example.com"):
			found = wf.approvable_actions(doc, [row("Approve"), row("Withdraw", allow_self_approval=1)])
		self.assertEqual([action["action"] for action in found], ["Withdraw"])

	def test_somebody_else_is_offered_it(self):
		doc = frappe._dict(owner="them@example.com")
		with as_user("me@example.com"):
			found = wf.approvable_actions(doc, [row("Approve")])
		self.assertEqual(found, [{"action": "Approve", "next_state": "Next"}])

	def test_administrator_is_never_refused(self):
		doc = frappe._dict(owner="Administrator")
		with as_user("Administrator"):
			self.assertEqual(len(wf.approvable_actions(doc, [row("Approve")])), 1)

	def test_parallel_rows_are_judged_by_the_one_apply_workflow_picks(self):
		"""`apply_workflow` takes the last row naming an action, so that one decides."""
		doc = frappe._dict(owner="me@example.com")
		with as_user("me@example.com"):
			allowed_last = wf.approvable_actions(
				doc, [row("Approve", "A"), row("Approve", "B", allow_self_approval=1)]
			)
			refused_last = wf.approvable_actions(
				doc, [row("Approve", "A", allow_self_approval=1), row("Approve", "B")]
			)
		self.assertEqual(allowed_last, [{"action": "Approve", "next_state": "B"}])
		self.assertEqual(refused_last, [])

	def test_permitted_transitions_applies_it(self):
		"""Every queue, badge and button reads `permitted_transitions`, so the rule lives there."""
		doc = MagicMock(owner="me@example.com")
		doc.get.side_effect = lambda field: {"owner": "me@example.com"}.get(field)
		doc.has_permission.return_value = True
		with (
			as_user("me@example.com"),
			patch.object(wf.frappe, "get_doc", return_value=doc),
			patch("frappe.model.workflow.get_transitions", return_value=[row("Approve")]),
		):
			self.assertEqual(wf.permitted_transitions("ToDo", ["T-1"], object()), {"T-1": []})
