"""The Awesome Bar's pages, and how often it works them out.

Site-less. Core asks the bar's hooks on every keystroke after a short debounce;
what is pinned here is that one burst of typing walks the workspaces once, per
user, rather than once a keystroke.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.better_navigation import search


class FakeCache:
	"""`frappe.cache`'s per-user get and set, over a dict."""

	def __init__(self):
		self.store = {}

	def get_value(self, key, user=None):
		return self.store.get((key, user))

	def set_value(self, key, value, user=None, expires_in_sec=None):
		self.expires = expires_in_sec
		self.store[(key, user)] = value


class TheBarWalksThePagesOncePerBurst(TestCase):
	def run_as(self, user, cache, rows):
		with (
			patch.object(search.frappe, "cache", cache),
			patch.object(search.frappe, "session", SimpleNamespace(user=user)),
			patch.object(search.settings, "title", return_value="Commons"),
			patch.object(search, "_rows", side_effect=rows),
		):
			return search.awesomebar_results("lea")

	def test_keystrokes_after_the_first_reuse_the_pages(self):
		walks = []
		cache = FakeCache()
		rows = lambda: walks.append(1) or [{"label": "Leave", "path": "/commons/requests/leave"}]  # noqa: E731
		for _keystroke in range(3):
			found = self.run_as("a@example.com", cache, rows)
		self.assertEqual(len(walks), 1)
		self.assertEqual(found[0]["route"], "/commons/requests/leave")
		self.assertEqual(cache.expires, search.ROWS_TTL)

	def test_each_user_gets_their_own_pages(self):
		walks = []
		cache = FakeCache()
		rows = lambda: walks.append(1) or []  # noqa: E731
		self.run_as("a@example.com", cache, rows)
		self.run_as("b@example.com", cache, rows)
		self.assertEqual(len(walks), 2)

	def test_nothing_typed_asks_nothing(self):
		with patch.object(search, "_cached_rows", side_effect=AssertionError("walked the pages")):
			self.assertEqual(search.awesomebar_results("  "), [])
