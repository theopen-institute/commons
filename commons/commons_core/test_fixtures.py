"""That a fixture for an app the site lacks is skipped, not fatal: bench --site SITE execute commons.commons_core.test_fixtures.run

`commons/fixtures/custom_field_education.json` and `custom_field_erpnext.json`
name doctypes that only exist where Education and ERPNext are installed. They
are safe as fixtures because of one behaviour of Frappe's fixture import, set
out in `commons/fixtures/README.md`: a Custom Field whose doctype is missing
raises `DoesNotExistError`, which `import_fixtures` catches and skips the file
for. Were that ever some other exception, it would abort migrate for the whole
site -- so it is pinned here, through Frappe's own `import_fixtures`, and this
is the suite to run before taking a Frappe upgrade to production.

The file-level rule it depends on -- one app per file, since a failing record
stops its file but keeps what came before it -- is checked without a site.

Rollback-only. `import_doc` commits after every file, so `frappe.db.commit` is
held off for the duration; the probe that does import is a virtual field, and
`in_create_custom_fields` spares it the `updatedb` that would commit too.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons import testing

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")

# Each optional app's file, and the app whose doctypes it names.
OPTIONAL = {
	"custom_field_education.json": "education",
	"custom_field_erpnext.json": "erpnext",
}

ABSENT = "Commons Fixture Probe Absent"
PROBE = "commons_fixture_probe"


def records(fname: str) -> list[dict]:
	with open(os.path.join(FIXTURES, fname), encoding="utf-8") as handle:
		return json.load(handle)


class TestFixtureFiles(TestCase):
	"""Site-less: the shape the skip relies on."""

	def test_every_optional_app_file_is_there(self):
		for fname in OPTIONAL:
			self.assertTrue(records(fname), fname)

	def test_optional_app_files_hold_only_custom_fields(self):
		for fname in OPTIONAL:
			self.assertEqual({row["doctype"] for row in records(fname)}, {"Custom Field"}, fname)

	def test_no_other_file_names_an_optional_apps_doctypes(self):
		"""Otherwise a site without the app would fail that file partway, keeping half of it."""
		optional = {row["dt"] for fname in OPTIONAL for row in records(fname)}
		for fname in sorted(os.listdir(FIXTURES)):
			if not fname.endswith(".json") or fname in OPTIONAL:
				continue
			named = {row.get("dt") or row.get("doc_type") for row in records(fname)}
			self.assertFalse(named & optional, fname)

	def test_optional_app_files_do_not_share_doctypes(self):
		seen = {}
		for fname in OPTIONAL:
			for dt in {row["dt"] for row in records(fname)}:
				self.assertNotIn(dt, seen, f"{dt} is in both {seen.get(dt)} and {fname}")
				seen[dt] = fname


@testing.site_suite()
class TestFixturesForAbsentApps(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("fixtures_test")
		self.folder = tempfile.mkdtemp()

	def tearDown(self):
		frappe.db.rollback(save_point="fixtures_test")
		shutil.rmtree(self.folder, ignore_errors=True)
		frappe.clear_cache(doctype="ToDo")

	def write(self, fname: str, rows: list[dict]) -> None:
		with open(os.path.join(self.folder, fname), "w", encoding="utf-8") as handle:
			json.dump(rows, handle)

	def import_fixtures(self) -> str:
		"""Frappe's own `import_fixtures`, reading this test's folder. Returns what it printed."""
		from frappe.utils import fixtures

		get_app_path = frappe.get_app_path

		def app_path(app, *parts):
			if app == "commons" and parts and parts[0] == "fixtures":
				return os.path.join(self.folder, *parts[1:])
			return get_app_path(app, *parts)

		printed = io.StringIO()
		frappe.flags.in_create_custom_fields = True
		try:
			with (
				patch.object(frappe, "get_app_path", side_effect=app_path),
				patch.object(frappe.db, "commit"),
				contextlib.redirect_stdout(printed),
			):
				fixtures.import_fixtures("commons")
		finally:
			frappe.flags.in_create_custom_fields = False
		return printed.getvalue()

	def custom_field(self, dt: str, fieldname: str) -> dict:
		return {
			"doctype": "Custom Field",
			"name": f"{dt}-{fieldname}",
			"dt": dt,
			"fieldname": fieldname,
			"label": "Fixture Probe",
			"fieldtype": "Data",
			"insert_after": "description",
			"is_virtual": 1,
		}

	def test_a_missing_doctype_skips_its_file_and_migrate_goes_on(self):
		self.assertFalse(frappe.db.exists("DocType", ABSENT))
		self.write("a_absent.json", [self.custom_field(ABSENT, PROBE)])
		self.write("b_present.json", [self.custom_field("ToDo", PROBE)])

		printed = self.import_fixtures()

		self.assertIn("Skipping fixture syncing from the file a_absent.json", printed)
		self.assertFalse(frappe.db.exists("Custom Field", f"{ABSENT}-{PROBE}"))
		self.assertTrue(
			frappe.db.exists("Custom Field", f"ToDo-{PROBE}"), "the file after it was not imported"
		)

	def test_each_optional_file_names_only_its_own_apps_doctypes(self):
		installed = set(frappe.get_installed_apps())
		for fname, app in OPTIONAL.items():
			for dt in sorted({row["dt"] for row in records(fname)}):
				if app not in installed:
					# The case the skip is for: none of them may be here either.
					self.assertFalse(frappe.db.exists("DocType", dt), f"{dt} ({fname})")
					continue
				module = frappe.db.get_value("DocType", dt, "module")
				self.assertEqual(frappe.local.module_app.get(frappe.scrub(module)), app, f"{dt} ({fname})")


def run():
	"""Run this suite against a site by hand, verbosely."""
	result = unittest.TextTestRunner(verbosity=2).run(
		unittest.TestSuite(
			unittest.defaultTestLoader.loadTestsFromTestCase(case)
			for case in (TestFixtureFiles, TestFixturesForAbsentApps)
		)
	)
	if not result.wasSuccessful():
		raise RuntimeError("Fixture tests failed")
	return dict(tests=result.testsRun, success=True)
