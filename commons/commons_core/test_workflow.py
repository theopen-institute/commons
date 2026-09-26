"""Which queue candidates are this user's, found before a page is cut.

Site-less: `permitted_transitions` is the site's answer and is stubbed here. What
is pinned is the search around it -- that twenty candidates somebody else must
act on no longer hide the ones waiting on this user.
"""

from unittest import TestCase
from unittest.mock import patch

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
