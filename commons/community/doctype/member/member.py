import frappe
from frappe import _
from frappe.model.document import Document

from commons.community.naming import full_name

MEMBER_TYPES = ("Faculty", "Associate Faculty", "Fellow", "Student")


class Member(Document):
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
