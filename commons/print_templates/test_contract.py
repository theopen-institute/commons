"""A Web Template's Fields table read as its inputs.

Site-less: no Link rows here, the one check that reads the database. Those are
in `test_print_templates`.
"""

import datetime
from unittest import TestCase

from commons.print_templates import contract

FIELDS = [
	{"label": "Student ID", "fieldname": "student_id", "fieldtype": "Data", "reqd": 1},
	{"label": "Fees Total", "fieldname": "fees_total", "fieldtype": "Currency", "reqd": 1},
	{"label": "As At", "fieldname": "as_at", "fieldtype": "Date"},
	{"label": "Status", "fieldname": "status", "fieldtype": "Select", "options": "Open\nSettled"},
	{"label": "Fees", "fieldname": "fees", "fieldtype": "JSON", "default": '[{"program": "", "lines": []}]'},
	{"fieldtype": "Section Break"},
	{"label": "Loans", "fieldname": "loans", "fieldtype": "Table Break"},
	{"label": "Reference", "fieldname": "reference", "fieldtype": "Data", "reqd": 1},
	{"label": "Balance", "fieldname": "balance", "fieldtype": "Float"},
]

GOOD = {
	"student_id": "S-1",
	"fees_total": 1250,
	"as_at": "2026-09-27",
	"status": "Open",
	"fees": [],
	"loans": [{"reference": "L-1", "balance": 0.0}],
}


class TestContract(TestCase):
	def test_nothing_declared_checks_nothing(self):
		self.assertEqual(contract.check([], {"anything": object()}), [])

	def test_values_that_match_raise_nothing(self):
		self.assertEqual(contract.check(FIELDS, GOOD), [])

	def test_a_date_object_is_a_date(self):
		self.assertEqual(contract.check(FIELDS, {**GOOD, "as_at": datetime.date(2026, 9, 27)}), [])

	def test_a_missing_required_field_is_reported(self):
		values = {k: v for k, v in GOOD.items() if k != "student_id"}
		self.assertEqual(contract.check(FIELDS, values), ["student_id is required but missing."])

	def test_a_missing_optional_field_is_not(self):
		values = {k: v for k, v in GOOD.items() if k != "as_at"}
		self.assertEqual(contract.check(FIELDS, values), [])

	def test_a_wrong_type_is_reported(self):
		self.assertEqual(
			contract.check(FIELDS, {**GOOD, "fees_total": "1250"}),
			["fees_total should be a number, not text."],
		)

	def test_true_is_not_a_number(self):
		self.assertEqual(
			contract.check(FIELDS, {**GOOD, "fees_total": True}),
			["fees_total should be a number, not true/false."],
		)

	def test_a_select_value_outside_its_options_is_reported(self):
		self.assertEqual(
			contract.check(FIELDS, {**GOOD, "status": "Closed"}),
			['status is "Closed", which is not one of its options.'],
		)

	def test_rows_after_a_table_break_are_checked_per_row(self):
		values = {**GOOD, "loans": [{"reference": "L-1"}, {"balance": "x"}]}
		self.assertEqual(
			contract.check(FIELDS, values),
			["loans[1].reference is required but missing.", "loans[1].balance should be a number, not text."],
		)

	def test_an_undeclared_key_is_reported(self):
		self.assertEqual(
			contract.check(FIELDS, {**GOOD, "extra": 1}),
			["extra is passed but not declared in Fields."],
		)

	def test_a_label_stands_in_for_a_missing_fieldname(self):
		fields = [{"label": "Student Name", "fieldtype": "Data", "reqd": 1}]
		self.assertEqual(contract.check(fields, {}), ["student_name is required but missing."])

	def test_rows_may_be_frappe_dicts(self):
		import frappe

		fields = [frappe._dict(f) for f in FIELDS]
		self.assertEqual(contract.check(fields, GOOD), [])
