"""Which of a site's own fields the attendance register reads, and the rules it counts by.

The register's settings, apart from Commons Settings because the register is
not part of what Commons is: it is a page for a site that teaches, kept in this
app only because its screen is drawn by this app's frontend. Read by
`commons.attendance_register.register`.
"""

from frappe.model.document import Document


class AttendanceRegisterSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		group_resolution: DF.Literal["Programme", "Course", "Both"]
		inactive_term_field: DF.Data | None
		late_credit: DF.Float
		late_field: DF.Data | None
		leave_counts_as: DF.Literal["Absent", "Excused"]
		session_details_field: DF.Data | None
		session_hours_field: DF.Data | None
		session_type_field: DF.Data | None
	# end: auto-generated types

	pass
