"""What the app calls itself, and what answers when nobody has said.

Moved here with the document it reads. It used to sit in `shell.test_shell`,
which was right while `Commons Settings` was the navigation's -- see
`commons.commons_core` on why it is the app's instead.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.commons_core import settings


class TestTitle(TestCase):
	def title(self, stored, installed=True):
		# The whole of `frappe.db`, not two of its methods: site-less there is no
		# connection for the proxy to hand an attribute back from.
		database = SimpleNamespace(
			exists=lambda *args, **kwargs: installed,
			get_single_value=lambda *args, **kwargs: stored,
		)
		with patch.object(settings.frappe, "db", database):
			return settings.title()

	def test_the_site_s_own_name_wins(self):
		self.assertEqual(self.title("  Staff Portal  "), "Staff Portal")

	def test_a_blank_setting_reads_as_unset(self):
		self.assertEqual(self.title("   "), settings.DEFAULT_TITLE)

	def test_a_single_that_has_never_been_saved_reads_as_unset(self):
		self.assertEqual(self.title(None), settings.DEFAULT_TITLE)

	def test_a_site_migrating_into_this_app_has_no_doctype_yet(self):
		self.assertEqual(self.title("Staff Portal", installed=False), settings.DEFAULT_TITLE)
