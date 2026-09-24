import frappe
from frappe import _
from frappe.model.document import Document

MEMBER_TYPES = ("Faculty", "Associate Faculty", "Fellow", "Student")

# The three whose `member_id` is a Link back to Member and whose autoname is
# `format:{member_id}`, so that one can be found -- or made -- from a Member and
# nothing else. `Student` is the education app's: named by series, with no
# member_id of any kind, so a Member of that type keeps whatever `member_details`
# someone sets by hand.
LINKED_MEMBER_TYPES = ("Faculty", "Associate Faculty", "Fellow")


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
		member_details: DF.DynamicLink | None
		member_id: DF.Data
		member_type: DF.Literal["", "Faculty", "Associate Faculty", "Fellow", "Student"]
		middle_name: DF.Data | None
		phone_number: DF.Data | None
	# end: auto-generated types

	def validate(self):
		self.full_name = (self.full_name_manual or "").strip() or " ".join(part.strip() for part in [self.first_name, self.middle_name, self.last_name] if part and part.strip())

		# A Member being inserted has no row for the detail record's `member_id`
		# to point at yet, so its link would not validate. `after_insert` takes
		# that case, once there is something to link to.
		if not self.is_new():
			self.set_member_details()

	def after_insert(self):
		if self.set_member_details():
			self.db_set("member_details", self.member_details, update_modified=False)

	def set_member_details(self) -> bool:
		"""Point `member_details` at this member's detail record, creating one if
		there is none. Return whether the field was changed."""
		if self.member_type not in LINKED_MEMBER_TYPES:
			return False

		# A changed `member_type` leaves the old pointer in place, naming a record
		# of a doctype the dynamic link no longer resolves against. That is as
		# empty as empty, so re-resolve it rather than trust it.
		if self.member_details and frappe.db.exists(self.member_type, self.member_details):
			return False

		# `member_id` on the detail record is a Link to Member, so it holds a
		# Member *name*. The two are the same string for a Member that has never
		# had its member_id edited without a rename, but the name is what the
		# link is checked against.
		name = frappe.db.get_value(self.member_type, {"member_id": self.name})

		# The detail record is named `format:{member_id}`, the same string as this
		# Member, so one made before its link was set (or left behind by a deleted
		# Member) sits at our name with an empty or dangling `member_id`. Inserting
		# would collide with it; it is this member's record, so claim it instead.
		if not name and frappe.db.exists(self.member_type, self.name):
			details = frappe.get_doc(self.member_type, self.name)
			if details.member_id and details.member_id != self.name and frappe.db.exists("Member", details.member_id):
				frappe.throw(
					_("{0} {1} already exists and belongs to Member {2}").format(
						_(self.member_type), frappe.bold(self.name), frappe.bold(details.member_id)
					),
					frappe.DuplicateEntryError,
				)
			details.member_id = self.name
			details.save(ignore_permissions=True)
			name = details.name

		if not name:
			details = frappe.new_doc(self.member_type)
			details.member_id = self.name
			# The category is the Member's own field, and whoever may write this
			# Member has just set it. The detail record is what that setting
			# means, not a second thing to be separately permitted.
			details.insert(ignore_permissions=True)
			name = details.name

		self.member_details = name
		return True
