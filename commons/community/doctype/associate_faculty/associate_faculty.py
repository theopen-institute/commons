from frappe.model.document import Document

from commons.community.naming import full_name


class AssociateFaculty(Document):
	def validate(self):
		self.full_name = full_name(self)
