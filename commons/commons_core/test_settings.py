"""What the app calls itself, and what answers when nobody has said.

Moved here with the document it reads. It used to sit in `better_navigation.test_shell`,
which was right while `Commons Settings` was the navigation's -- see
`commons.commons_core` on why it is the app's instead.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.commons_core import settings


def cached(doc, installed=True):
	"""`frappe.get_cached_doc` for the settings, as a site with or without the doctype answers.

	Without it Frappe raises `ImportError`, and the settings reader then asks
	whether the doctype exists -- which is the only database question left, so
	`frappe.db` is stood in with just that.
	"""

	def get_cached_doc(*args, **kwargs):
		if not installed:
			raise ImportError("No module named commons_settings")
		return doc

	return (
		patch.object(settings.frappe, "get_cached_doc", side_effect=get_cached_doc),
		patch.object(settings.frappe, "db", SimpleNamespace(exists=lambda *args, **kwargs: installed)),
	)


class TestTitle(TestCase):
	def title(self, stored, installed=True):
		get_cached_doc, database = cached(settings.frappe._dict({"title": stored}), installed)
		with get_cached_doc, database:
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
		get_cached_doc, database = cached(
			settings.frappe._dict({settings.ENABLE_PERMISSION_GATE: stored}), installed
		)
		with get_cached_doc, database:
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

	def test_a_settings_controller_that_fails_to_import_is_not_hidden(self):
		"""The doctype is there, so an `ImportError` is a fault, not a site mid-migrate."""
		database = SimpleNamespace(exists=lambda *args, **kwargs: True)
		with (
			patch.object(settings.frappe, "db", database),
			patch.object(settings.frappe, "get_cached_doc", side_effect=ImportError("broken")),
			self.assertRaises(ImportError),
		):
			settings.feature_enabled(settings.ENABLE_PERMISSION_GATE)

	def test_an_installed_site_asks_no_existence_question(self):
		"""The per-request query this used to make."""
		database = SimpleNamespace(exists=lambda *args, **kwargs: self.fail("asked whether the doctype exists"))
		doc = settings.frappe._dict({settings.ENABLE_PERMISSION_GATE: 1})
		with (
			patch.object(settings.frappe, "db", database),
			patch.object(settings.frappe, "get_cached_doc", return_value=doc),
		):
			self.assertTrue(settings.feature_enabled(settings.ENABLE_PERMISSION_GATE))

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
				"user_menu": False,
				"navigation_rail": False,
				"derived_docfields": False,
				"visual_email_editor": False,
			},
		)
