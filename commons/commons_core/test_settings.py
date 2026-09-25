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


class TestOverrideEnabled(TestCase):
	def enabled(self, stored, installed=True):
		database = SimpleNamespace(exists=lambda *args, **kwargs: installed)
		doc = settings.frappe._dict({settings.ENABLE_PERMISSION_GATE: stored})
		with (
			patch.object(settings.frappe, "db", database),
			patch.object(settings.frappe, "get_cached_doc", return_value=doc),
		):
			return settings.feature_enabled(settings.ENABLE_PERMISSION_GATE)

	def test_ticking_the_switch_turns_the_override_on(self):
		self.assertTrue(self.enabled(1))

	def test_unticked_leaves_it_off(self):
		self.assertFalse(self.enabled(0))

	def test_a_field_nobody_has_saved_leaves_it_off(self):
		"""Opt-in: a site that never asked gets core's behaviour."""
		self.assertFalse(self.enabled(None))

	def test_a_site_migrating_into_this_app_leaves_it_off(self):
		self.assertFalse(self.enabled(1, installed=False))

	def test_the_desk_is_told_each_browser_feature(self):
		bootinfo = settings.frappe._dict()
		with patch.object(settings, "feature_enabled", side_effect=lambda field: field == settings.ENABLE_SIDEBAR_MEMORY):
			settings.extend_bootinfo(bootinfo)
		self.assertEqual(
			bootinfo.commons_features,
			{
				"bikram_sambat": False,
				"unencoded_at_in_routes": False,
				"user_permission_gate": False,
				"sidebar_memory": True,
				"derived_docfields": False,
				"visual_email_editor": False,
			},
		)
