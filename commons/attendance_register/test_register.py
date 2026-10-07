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
the meta has, of a type the page can use, is ever sent. The course plan is three
such names, and is sent whole or not at all.
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
	"""A doctype's fields, each a fieldtype or a `(fieldtype, options)` pair."""

	def __init__(self, fields: dict[str, str | tuple[str, str]]):
		self.fields = fields

	def get_field(self, fieldname):
		spec = self.fields.get(fieldname)
		if not spec:
			return None
		fieldtype, options = spec if isinstance(spec, tuple) else (spec, None)
		return frappe._dict(fieldname=fieldname, fieldtype=fieldtype, options=options)


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
	# The register site's course plan, and a Table naming a doctype no site has.
	attendance.COURSE: FakeMeta(
		{
			"custom_contact_hours": ("Table", "Course Contact Hours"),
			"custom_orphan_table": ("Table", "Course Orphan Rows"),
			"course_name": "Data",
		}
	),
	"Course Contact Hours": FakeMeta(
		{"contact_hour_type": "Link", "hours": "Int", "description": "Text", "note": "Small Text"}
	),
}

PLAN = {
	"course_plan_field": "custom_contact_hours",
	"course_plan_type_column": "contact_hour_type",
	"course_plan_hours_column": "hours",
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
	**PLAN,
}


def configured(values: dict, **overrides) -> frappe._dict:
	"""Commons Settings holding `values`, each under its `attendance_` name."""
	return frappe._dict({attendance.PREFIX + key: value for key, value in {**values, **overrides}.items()})


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
			self.fields(configured(CONFIGURED)),
			{
				"late_field": "custom_late",
				"late_credit": 0.5,
				"session_type_field": "custom_session_type",
				"session_details_field": "custom_session_details",
				"inactive_term_field": "custom_inactive",
				"session_hours_field": "custom_hours",
				"group_resolution": "Both",
				"leave_counts_as": "Excused",
				"course_plan": {
					"table_field": "custom_contact_hours",
					"table_doctype": "Course Contact Hours",
					"type_column": "contact_hour_type",
					"hours_column": "hours",
				},
			},
		)

	def test_a_site_that_set_nothing_gets_nothing(self):
		"""And today's rules: a late arrival worth a full session, which is the
		field's default rather than 0, groups found through their programme, and
		leave read as absence."""
		self.assertEqual(
			self.fields(configured({})),
			{
				"late_field": None,
				"late_credit": 1.0,
				"session_type_field": None,
				"session_details_field": None,
				"inactive_term_field": None,
				"session_hours_field": None,
				"group_resolution": "Programme",
				"leave_counts_as": "Absent",
				"course_plan": None,
			},
		)

	def test_a_field_the_doctype_lacks_is_blank(self):
		"""A typo would otherwise be in the filter of every read the page makes."""
		settings = configured(CONFIGURED, inactive_term_field="custom_retired")
		self.assertIsNone(self.fields(settings)["inactive_term_field"])

	def test_a_field_of_the_wrong_type_is_blank(self):
		"""The late flag is written 0 and 1; a Select would refuse them, a Data would keep them."""
		settings = configured(CONFIGURED, late_field="status", session_type_field="color")
		fields = self.fields(settings)
		self.assertIsNone(fields["late_field"])
		self.assertIsNone(fields["session_type_field"])

	def test_a_field_on_another_doctype_is_blank(self):
		settings = configured(CONFIGURED, inactive_term_field="custom_late")
		self.assertIsNone(self.fields(settings)["inactive_term_field"])

	def test_without_education_everything_is_blank(self):
		fields = self.fields(configured(CONFIGURED), doctypes=())
		self.assertEqual(
			{key for key, value in fields.items() if value},
			{"late_credit", "group_resolution", "leave_counts_as"},
		)

	def test_whitespace_around_a_name_is_not_a_different_name(self):
		settings = configured(CONFIGURED, late_field=" custom_late ")
		self.assertEqual(self.fields(settings)["late_field"], "custom_late")

	def test_the_late_credit_is_held_between_none_and_all(self):
		for stored, expected in ((-1, 0.0), (0, 0.0), (0.25, 0.25), (1, 1.0), (3, 1.0)):
			with self.subTest(stored=stored):
				settings = configured(CONFIGURED, late_credit=stored)
				self.assertEqual(self.fields(settings)["late_credit"], expected)

	def test_the_hours_field_is_a_number(self):
		"""Float or Int; a Data field of numbers-as-text would be summed as strings."""
		for fieldname, expected in (("custom_hours", "custom_hours"), ("custom_periods", "custom_periods")):
			with self.subTest(fieldname=fieldname):
				settings = configured(CONFIGURED, session_hours_field=fieldname)
				self.assertEqual(self.fields(settings)["session_hours_field"], expected)
		for fieldname in ("custom_session_type", "custom_late", "custom_missing"):
			with self.subTest(fieldname=fieldname):
				settings = configured(CONFIGURED, session_hours_field=fieldname)
				self.assertIsNone(self.fields(settings)["session_hours_field"])

	def test_each_rule_is_one_of_its_options(self):
		for setting, options in (
			("group_resolution", ("Programme", "Course", "Both")),
			("leave_counts_as", ("Absent", "Excused")),
		):
			for option in options:
				with self.subTest(setting=setting, option=option):
					settings = configured(CONFIGURED, **{setting: option})
					self.assertEqual(self.fields(settings)[setting], option)

	def test_an_unknown_rule_is_todays(self):
		"""Saved before the field existed, or edited to something it does not offer."""
		for stored in (None, "", "programme", "Everything"):
			with self.subTest(stored=stored):
				settings = configured(CONFIGURED, group_resolution=stored, leave_counts_as=stored)
				fields = self.fields(settings)
				self.assertEqual(fields["group_resolution"], "Programme")
				self.assertEqual(fields["leave_counts_as"], "Absent")

	def test_a_course_plan_is_all_three_names_or_none(self):
		"""A table with no usable type column has no row the page could match to
		a session, and one with no hours column has nothing planned."""
		for setting, value in (
			("course_plan_field", ""),
			("course_plan_field", "custom_missing"),
			("course_plan_field", "course_name"),
			("course_plan_type_column", ""),
			("course_plan_type_column", "custom_missing"),
			("course_plan_type_column", "description"),
			("course_plan_hours_column", ""),
			("course_plan_hours_column", "contact_hour_type"),
			("course_plan_hours_column", "note"),
		):
			with self.subTest(setting=setting, value=value):
				settings = configured(CONFIGURED, **{setting: value})
				self.assertIsNone(self.fields(settings)["course_plan"])

	def test_a_table_whose_rows_the_site_lacks_is_no_plan(self):
		settings = configured(CONFIGURED, course_plan_field="custom_orphan_table")
		self.assertIsNone(self.fields(settings)["course_plan"])

	def test_a_course_plan_column_may_be_a_link_or_text(self):
		"""The register site's column links to a `Contact Hour Type`; another
		school's may be free text, as the session type field is."""
		for fieldtype in ("Link", "Data", "Select", "Autocomplete"):
			with self.subTest(fieldtype=fieldtype):
				meta = FakeMeta({"contact_hour_type": fieldtype, "hours": "Float"})
				with patch.dict(METAS, {"Course Contact Hours": meta}):
					plan = self.fields(configured(CONFIGURED))["course_plan"]
				self.assertEqual(plan["type_column"], "contact_hour_type")


class TestWhoIsTeaching(TestCase):
	"""`my_instructors` reads past permissions, so what is pinned is that it
	answers about the reader and nobody else."""

	def answer(self, employees, instructors, doctypes=("Instructor", "Employee")):
		asked = []

		def get_all(doctype, filters=None, **_):
			asked.append((doctype, filters))
			return employees if doctype == "Employee" else instructors

		with (
			patch.object(attendance.apps, "has_doctype", side_effect=lambda doctype: doctype in doctypes),
			patch.object(attendance.frappe, "get_all", side_effect=get_all),
			patch.object(attendance.frappe, "session", frappe._dict(user="teacher@example.com")),
		):
			return attendance.my_instructors(), asked

	def test_is_the_instructors_of_the_readers_own_employee_records(self):
		found, asked = self.answer(["HR-EMP-1"], ["Peter Graif"])
		self.assertEqual(found, ["Peter Graif"])
		self.assertEqual(
			asked,
			[
				("Employee", {"user_id": "teacher@example.com"}),
				("Instructor", {"employee": ("in", ["HR-EMP-1"])}),
			],
		)

	def test_no_employee_is_no_instructor(self):
		"""And never an unfiltered read of every Instructor."""
		found, asked = self.answer([], ["Somebody Else"])
		self.assertEqual(found, [])
		self.assertEqual([doctype for doctype, _ in asked], ["Employee"])

	def test_without_education_or_hr_there_is_nobody(self):
		for doctypes in (("Instructor",), ("Employee",), ()):
			with self.subTest(doctypes=doctypes):
				found, asked = self.answer(["HR-EMP-1"], ["Peter Graif"], doctypes)
				self.assertEqual(found, [])
				self.assertEqual(asked, [])
