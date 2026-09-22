import frappe
from frappe import _
from frappe.model.document import Document

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
		first_name: DF.Data | None
		full_name: DF.Data | None
		full_name_manual: DF.Data | None
		hide_from_website: DF.Check
		image: DF.AttachImage | None
		last_name: DF.Data | None
		member_id: DF.Data
		member_type: DF.Link
		middle_name: DF.Data | None
		phone_number: DF.Data | None
	# end: auto-generated types

	def validate(self):
		self.full_name = (self.full_name_manual or "").strip() or " ".join(part.strip() for part in [self.first_name, self.middle_name, self.last_name] if part and part.strip())
