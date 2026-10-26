"""What the advancement page is told about the site's fields, and what `apply` refuses.

The settings fail quietly in the same way the attendance register's do: a name
sent that the doctype does not have breaks every read the page makes. So only
a Table on Program whose column links to Program, and only a Select on Student,
is ever sent, and a continuing status that is not one of the Select's options
reads as none. What `apply` writes is checked against a site, not here.
"""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.student_advancement import advancement

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


def field(fieldtype, options=None):
	return SimpleNamespace(fieldtype=fieldtype, options=options)


class Meta:
	def __init__(self, fields):
		self.fields = fields

	def get_field(self, name):
		return self.fields.get(name)


METAS = {
	"Program": Meta({"next": field("Table", "Next Program"), "title": field("Data"), "label": field("Data")}),
	"Academic Term": Meta({"academic_year": field("Link", "Academic Year"), "term_name": field("Data")}),
	"Next Program": Meta({"program": field("Link", "Program"), "course": field("Link", "Course")}),
	"Student": Meta({"standing": field("Select", "Enrolled\nGraduated\nWithdrawn"), "note": field("Data")}),
}


class SiteTestCase(TestCase):
	def setUp(self):
		self.enterContext(patch.object(advancement.apps, "has_doctype", side_effect=lambda doctype: True))
		self.enterContext(patch.object(frappe, "get_meta", side_effect=lambda doctype: METAS[doctype]))


class TestNextPrograms(SiteTestCase):
	def test_a_table_and_its_program_column(self):
		settings = {advancement.NEXT_PROGRAMS_FIELD: "next", advancement.NEXT_PROGRAM_COLUMN: "program"}
		self.assertEqual(
			advancement.next_programs(settings),
			{"table_field": "next", "table_doctype": "Next Program", "program_column": "program"},
		)

	def test_a_column_linking_elsewhere_is_none(self):
		settings = {advancement.NEXT_PROGRAMS_FIELD: "next", advancement.NEXT_PROGRAM_COLUMN: "course"}
		self.assertIsNone(advancement.next_programs(settings))

	def test_a_field_that_is_no_table_is_none(self):
		settings = {advancement.NEXT_PROGRAMS_FIELD: "title", advancement.NEXT_PROGRAM_COLUMN: "program"}
		self.assertIsNone(advancement.next_programs(settings))

	def test_unset_is_none(self):
		self.assertIsNone(advancement.next_programs({}))
		self.assertIsNone(advancement.allowed_programs(None, "Anything"))


class TestStatus(SiteTestCase):
	def test_a_select_and_its_options(self):
		settings = {advancement.STATUS_FIELD: "standing", advancement.CONTINUING_STATUS: "Enrolled"}
		self.assertEqual(
			advancement.status(settings),
			{
				"field": "standing",
				"options": ["Enrolled", "Graduated", "Withdrawn"],
				"continuing": "Enrolled",
				"require_leaving": False,
			},
		)

	def test_the_leaving_rule_needs_a_continuing_status(self):
		on = {advancement.STATUS_FIELD: "standing", advancement.REQUIRE_LEAVING_STATUS: 1}
		self.assertFalse(advancement.status(on)["require_leaving"])
		on[advancement.CONTINUING_STATUS] = "Enrolled"
		self.assertTrue(advancement.status(on)["require_leaving"])

	def test_a_continuing_status_that_is_no_option_is_none(self):
		settings = {advancement.STATUS_FIELD: "standing", advancement.CONTINUING_STATUS: "Active"}
		self.assertIsNone(advancement.status(settings)["continuing"])

	def test_a_field_that_is_no_select_is_none(self):
		self.assertIsNone(advancement.status({advancement.STATUS_FIELD: "note"}))


class TestGroupName(SiteTestCase):
	def test_term_and_program_fields(self):
		settings = {advancement.GROUP_NAME_FORMAT: "W&R - {academic_year} {term_name} - {program.label}"}
		self.assertEqual(
			advancement.group_name(settings),
			{
				"format": "W&R - {academic_year} {term_name} - {program.label}",
				"term_fields": ["academic_year", "term_name"],
				"program_fields": ["label"],
			},
		)

	def test_names_are_allowed(self):
		settings = {advancement.GROUP_NAME_FORMAT: "{program.name} - {name}"}
		self.assertEqual(advancement.group_name(settings)["program_fields"], ["name"])

	def test_a_field_the_doctype_lacks_is_none(self):
		self.assertIsNone(advancement.group_name({advancement.GROUP_NAME_FORMAT: "{program.term_name}"}))

	def test_no_placeholder_or_unset_is_none(self):
		self.assertIsNone(advancement.group_name({advancement.GROUP_NAME_FORMAT: "Fixed"}))
		self.assertIsNone(advancement.group_name({}))


class TestApplyRefuses(TestCase):
	def test_a_reader_who_may_not_enrol(self):
		def throw(message, exc=frappe.ValidationError, *args, **kwargs):
			raise exc(message)

		with (
			patch.object(advancement, "can_advance", return_value=False),
			patch.object(frappe, "throw", throw),
		):
			with self.assertRaises(frappe.PermissionError):
				advancement.apply("A", "B", "[]")

	def test_the_same_term_twice(self):
		with patch.object(advancement, "can_advance", return_value=True):
			with patch.object(frappe, "throw", side_effect=frappe.ValidationError) as throw:
				with self.assertRaises(frappe.ValidationError):
					advancement.apply("A", "A", "[]")
				throw.assert_called_once()

	def test_a_status_that_is_no_option(self):
		standing = {"field": "standing", "options": ["Enrolled"], "continuing": "Enrolled"}
		with patch.object(frappe, "throw", side_effect=frappe.ValidationError):
			with self.assertRaises(frappe.ValidationError):
				advancement.set_status("someone", standing, "Expelled")

	def test_a_program_for_a_student_with_no_enrolment(self):
		with patch.object(frappe, "throw", side_effect=frappe.ValidationError):
			with self.assertRaises(frappe.ValidationError):
				advancement.stray_status({"student": "someone", "program": "Two"}, None, {})

	def test_a_current_term_that_does_not_exist(self):
		with (
			patch.object(advancement.apps, "has_doctype", return_value=True),
			patch.object(frappe, "db", SimpleNamespace(get_value=lambda *args, **kwargs: None)),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
		):
			with self.assertRaises(frappe.ValidationError):
				advancement.set_current_term("No such term")
