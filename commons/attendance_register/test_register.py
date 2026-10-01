"""The two questions the navigation asks about the attendance register, and the fields it is told.

Small, because the module is. What used to be here -- the credit rule, the way
two stored fields become one word, the footings under each block -- moved into
the browser along with the reads that feed it, and is pinned in
`frontend/src/data/attendanceRegister.test.ts`. See `attendance.py` for why the
reads moved.

What is left is worth its own file rather than folding into `test_shell`,
because the two answers fail in opposite directions. `available` wrong in one
direction offers a page whose first read 404s; `can_mark` wrong in the other
puts a whole cohort's attendance in front of every student on the site.

`register_fields` fails a third way: a fieldname sent that the doctype does not
have breaks every read the page makes, so what is pinned is that only a field
the meta has, of a type the page can use, is ever sent.
"""

import logging
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.attendance_register import register as attendance

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. See `better_navigation.test_shell`.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


class TestWhetherTheSiteTeaches(TestCase):
	def present(self, *doctypes: str):
		return patch.object(attendance.apps, "has_doctype", side_effect=lambda doctype: doctype in doctypes)

	def test_both_doctypes_is_a_register(self):
		with self.present(attendance.COURSE_SCHEDULE, attendance.STUDENT_ATTENDANCE):
			self.assertTrue(attendance.available())

	def test_neither_is_not(self):
		with self.present():
			self.assertFalse(attendance.available())

	def test_half_an_education_module_is_not_enough(self):
		"""Either one missing takes the page away.

		They arrive together in practice. The register is made of both -- a
		session and a mark against it -- and offering it on one of them would be
		offering a page whose first read fails.
		"""
		with self.present(attendance.COURSE_SCHEDULE):
			self.assertFalse(attendance.available())
		with self.present(attendance.STUDENT_ATTENDANCE):
			self.assertFalse(attendance.available())


class TestWhoTheRegisterIsFor(TestCase):
	def test_is_write_on_student_attendance(self):
		"""And not read, which is the whole point of the check.

		`Student` and `Guardian` hold read on `Student Attendance`. Asking for
		read here would put the register in front of every student on the site.
		"""
		with patch.object(attendance.frappe, "has_permission", return_value=True) as asked:
			self.assertTrue(attendance.can_mark())
		asked.assert_called_once_with(attendance.STUDENT_ATTENDANCE, "write")

	def test_no_write_is_no_register(self):
		with patch.object(attendance.frappe, "has_permission", return_value=False):
			self.assertFalse(attendance.can_mark())

	def test_the_answer_is_a_boolean(self):
		"""`frappe.has_permission` returns 0/1 as often as True/False, and this
		answer is serialised into a navigation payload."""
		with patch.object(attendance.frappe, "has_permission", return_value=1):
			self.assertIs(attendance.can_mark(), True)


class FakeMeta:
	def __init__(self, fields: dict[str, str]):
		self.fields = fields

	def get_field(self, fieldname):
		fieldtype = self.fields.get(fieldname)
		return frappe._dict(fieldname=fieldname, fieldtype=fieldtype) if fieldtype else None


# The register site's four fields, as Education plus its Custom Fields has them,
# and an hours field it does not have but another school might.
METAS = {
	attendance.STUDENT_ATTENDANCE: FakeMeta({"custom_late": "Check", "status": "Select"}),
	attendance.COURSE_SCHEDULE: FakeMeta(
		{
			"custom_session_type": "Data",
			"custom_session_details": "Data",
			"custom_hours": "Float",
			"custom_periods": "Int",
			"color": "Color",
		}
	),
	attendance.ACADEMIC_TERM: FakeMeta({"custom_inactive": "Check", "term_name": "Data"}),
}

CONFIGURED = {
	"late_field": "custom_late",
	"late_credit": 0.5,
	"session_type_field": "custom_session_type",
	"session_details_field": "custom_session_details",
	"inactive_term_field": "custom_inactive",
	"session_hours_field": "custom_hours",
	"group_resolution": "Both",
	"leave_counts_as": "Excused",
}


class TestWhichFieldsTheRegisterUses(TestCase):
	def fields(self, settings, doctypes=tuple(METAS)):
		with (
			patch.object(attendance, "_settings", return_value=settings),
			patch.object(attendance.apps, "has_doctype", side_effect=lambda doctype: doctype in doctypes),
			patch.object(attendance.frappe, "get_meta", side_effect=lambda doctype: METAS[doctype]),
		):
			return attendance.register_fields()

	def test_a_configured_site_gets_its_fields(self):
		self.assertEqual(
			self.fields(frappe._dict(CONFIGURED)),
			{
				"late_field": "custom_late",
				"late_credit": 0.5,
				"session_type_field": "custom_session_type",
				"session_details_field": "custom_session_details",
				"inactive_term_field": "custom_inactive",
				"session_hours_field": "custom_hours",
				"group_resolution": "Both",
				"leave_counts_as": "Excused",
			},
		)

	def test_a_site_that_set_nothing_gets_nothing(self):
		"""And today's rules: a late arrival worth a full session, which is the
		field's default rather than 0, groups found through their programme, and
		leave read as absence."""
		self.assertEqual(
			self.fields(frappe._dict()),
			{
				"late_field": None,
				"late_credit": 1.0,
				"session_type_field": None,
				"session_details_field": None,
				"inactive_term_field": None,
				"session_hours_field": None,
				"group_resolution": "Programme",
				"leave_counts_as": "Absent",
			},
		)

	def test_before_migrate_there_are_no_settings_to_read(self):
		self.assertIsNone(self.fields(None)["late_field"])
		self.assertEqual(self.fields(None)["late_credit"], 1.0)
		self.assertEqual(self.fields(None)["group_resolution"], "Programme")
		self.assertEqual(self.fields(None)["leave_counts_as"], "Absent")

	def test_a_field_the_doctype_lacks_is_blank(self):
		"""A typo would otherwise be in the filter of every read the page makes."""
		settings = frappe._dict(CONFIGURED, inactive_term_field="custom_retired")
		self.assertIsNone(self.fields(settings)["inactive_term_field"])

	def test_a_field_of_the_wrong_type_is_blank(self):
		"""The late flag is written 0 and 1; a Select would refuse them, a Data would keep them."""
		settings = frappe._dict(CONFIGURED, late_field="status", session_type_field="color")
		fields = self.fields(settings)
		self.assertIsNone(fields["late_field"])
		self.assertIsNone(fields["session_type_field"])

	def test_a_field_on_another_doctype_is_blank(self):
		settings = frappe._dict(CONFIGURED, inactive_term_field="custom_late")
		self.assertIsNone(self.fields(settings)["inactive_term_field"])

	def test_without_education_everything_is_blank(self):
		fields = self.fields(frappe._dict(CONFIGURED), doctypes=())
		self.assertEqual(
			{key for key, value in fields.items() if value},
			{"late_credit", "group_resolution", "leave_counts_as"},
		)

	def test_whitespace_around_a_name_is_not_a_different_name(self):
		settings = frappe._dict(CONFIGURED, late_field=" custom_late ")
		self.assertEqual(self.fields(settings)["late_field"], "custom_late")

	def test_the_late_credit_is_held_between_none_and_all(self):
		for stored, expected in ((-1, 0.0), (0, 0.0), (0.25, 0.25), (1, 1.0), (3, 1.0)):
			with self.subTest(stored=stored):
				settings = frappe._dict(CONFIGURED, late_credit=stored)
				self.assertEqual(self.fields(settings)["late_credit"], expected)

	def test_the_hours_field_is_a_number(self):
		"""Float or Int; a Data field of numbers-as-text would be summed as strings."""
		for fieldname, expected in (("custom_hours", "custom_hours"), ("custom_periods", "custom_periods")):
			with self.subTest(fieldname=fieldname):
				settings = frappe._dict(CONFIGURED, session_hours_field=fieldname)
				self.assertEqual(self.fields(settings)["session_hours_field"], expected)
		for fieldname in ("custom_session_type", "custom_late", "custom_missing"):
			with self.subTest(fieldname=fieldname):
				settings = frappe._dict(CONFIGURED, session_hours_field=fieldname)
				self.assertIsNone(self.fields(settings)["session_hours_field"])

	def test_each_rule_is_one_of_its_options(self):
		for setting, options in (
			("group_resolution", ("Programme", "Course", "Both")),
			("leave_counts_as", ("Absent", "Excused")),
		):
			for option in options:
				with self.subTest(setting=setting, option=option):
					settings = frappe._dict(CONFIGURED, **{setting: option})
					self.assertEqual(self.fields(settings)[setting], option)

	def test_an_unknown_rule_is_todays(self):
		"""Saved before the field existed, or edited to something it does not offer."""
		for stored in (None, "", "programme", "Everything"):
			with self.subTest(stored=stored):
				settings = frappe._dict(CONFIGURED, group_resolution=stored, leave_counts_as=stored)
				fields = self.fields(settings)
				self.assertEqual(fields["group_resolution"], "Programme")
				self.assertEqual(fields["leave_counts_as"], "Absent")
