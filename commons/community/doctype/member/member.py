import frappe
from frappe import _
from frappe.model.document import Document

from commons.community.naming import full_name

MEMBER_TYPES = ("Faculty", "Associate Faculty", "Fellow", "Student")


class Member(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		alternate_email_address: DF.Data | None
		biography: DF.TextEditor | None
		cv: DF.Attach | None
		first_name: DF.Data
		full_name: DF.Data | None
		hide_from_website: DF.Check
		last_name: DF.Data | None
		member_email_address: DF.Data | None
		member_record: DF.DynamicLink
		member_type: DF.Link
		middle_name: DF.Data | None
		phone_number: DF.Data | None
	# end: auto-generated types

	def validate(self):
		self.full_name = full_name(self)
		self.validate_member_type()
		self.validate_member_record()

	def validate_member_type(self):
		"""The link filter only shapes the dropdown; membership is defined by this list."""
		if self.member_type not in MEMBER_TYPES:
			frappe.throw(
				_("A member must be one of: {0}.").format(", ".join(MEMBER_TYPES))
			)

	def validate_member_record(self):
		"""One person, one membership record: the link is the member's identity here."""
		duplicate = frappe.db.exists(
			"Member",
			{
				"member_type": self.member_type,
				"member_record": self.member_record,
				"name": ["!=", self.name],
			},
		)
		if duplicate:
			frappe.throw(
				_("{0} {1} is already a member under {2}.").format(
					self.member_type, self.member_record, frappe.bold(duplicate)
				)
			)
