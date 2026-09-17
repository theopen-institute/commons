"""Why an employee record is absent, which is not the same question as whether it is.

`session_employee` answers `None` two ways -- nobody has created the record, and
the record exists but this user may not read it -- and for a caller that only
wants the record those are the same answer. For a page that has to explain an
empty state they are not: one sends the reader to HR and the other to whoever
administers permissions, and leave told everybody the first.

These pin the discriminator, including the case the whole thing exists for: no
read permission at all, over a record that is sitting there with the caller's own
login on it.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from tbs_commons import api


class TestSessionEmployeeAccess(TestCase):
	def setUp(self):
		self.session = patch.object(
			api.frappe, "session", SimpleNamespace(user="employee@example.com")
		)
		self.session.start()
		self.addCleanup(self.session.stop)

	def access(self, can_read, readable, exists):
		"""`session_employee_access` over a site that answers these three ways."""
		with (
			patch.object(api.frappe, "has_permission", return_value=can_read),
			patch.object(api.frappe, "get_list", return_value=readable),
			# `frappe.db` is a Local proxy with no site behind it here, so the
			# attribute is replaced rather than patched into.
			patch.object(api.frappe, "db", SimpleNamespace(exists=Mock(return_value=exists))),
		):
			return api.session_employee_access()

	def test_a_record_the_permission_checked_read_returns_is_visible(self):
		self.assertEqual(self.access(True, ["HR-EMP-00001"], True), "visible")

	def test_no_record_and_nothing_behind_it_is_missing(self):
		"""Nobody has linked this login. The fix is HR's."""
		self.assertEqual(self.access(True, [], False), "missing")

	def test_a_record_withheld_by_user_permissions_is_forbidden(self):
		"""Read on the doctype, but the row does not survive the query's filters."""
		self.assertEqual(self.access(True, [], True), "forbidden")

	def test_a_record_behind_a_revoked_doctype_permission_is_forbidden(self):
		"""The case this exists for.

		No read on `Employee` at all, so `session_employee` never runs a query and
		returns `None` -- indistinguishable, before this, from having no record.
		The raw existence check is what separates them, and it is why that check
		cannot itself be permission-checked: being refused is one of the two
		answers it has to tell apart.
		"""
		self.assertEqual(self.access(False, [], True), "forbidden")

	def test_the_discriminator_looks_for_the_same_row_the_read_did(self):
		"""Both halves filter identically, or `forbidden` would mean nothing.

		A discriminator that searched wider than the read -- every employee row
		naming this login, rather than the active one -- would report a leaver's
		record as withheld, when nothing is withholding it. It has stopped being
		theirs, which is `missing`.
		"""
		exists = Mock(return_value=False)
		with (
			patch.object(api.frappe, "has_permission", return_value=True),
			patch.object(api.frappe, "get_list", return_value=[]) as get_list,
			patch.object(api.frappe, "db", SimpleNamespace(exists=exists)),
		):
			api.session_employee_access()

		self.assertEqual(get_list.call_args.kwargs["filters"], exists.call_args.args[1])
