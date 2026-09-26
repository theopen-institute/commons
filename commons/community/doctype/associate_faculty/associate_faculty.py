from frappe.model.document import Document


class AssociateFaculty(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		end_date: DF.Date | None
		member_id: DF.Link | None
		start_date: DF.Date | None
	# end: auto-generated types

	def validate(self):
		# self.full_name = full_name(self)
		pass
