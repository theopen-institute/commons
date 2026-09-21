"""The two questions the navigation asks about the attendance register.

Small, because the module is. What used to be here -- the credit rule, the way
two stored fields become one word, the footings under each block -- moved into
the browser along with the reads that feed it, and is pinned in
`frontend/src/data/attendanceRegister.test.ts`. See `attendance.py` for why the
reads moved.

What is left is worth its own file rather than folding into `test_shell`,
because the two answers fail in opposite directions. `available` wrong in one
direction offers a page whose first read 404s; `can_mark` wrong in the other
puts a whole cohort's attendance in front of every student on the site.
"""

import logging
from unittest import TestCase
from unittest.mock import patch

from commons.education_extensions import attendance

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. See `shell.test_shell`.
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
