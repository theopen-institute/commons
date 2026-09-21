"""Install and migrate hook for the attendance register: the fields it adds to Education.

Four Custom Fields, on three of Education's doctypes. They are what the register
records that Education has nowhere to put:

* `Course Schedule.custom_session_type` -- what kind of session it was. The
  register groups by it and foots each group separately, because a term's
  seminar hours and its field research hours are two different obligations and
  a single total of them answers neither. Free text rather than a Select: the
  vocabulary is the school's (this one runs four, another will run two), the
  register offers whatever is already in use, and a Select would make adding a
  fifth a deploy.
* `Course Schedule.custom_session_details` -- what that session was actually
  about, said in a few words beside the date.
* `Student Attendance.custom_late` -- that the student was there, but not at the
  start. `status` has `Present`, `Absent` and `Leave` and nothing for it, and it
  is not a fourth status: a late arrival *was* present, and every report that
  counts attendance should keep counting them. What it changes is what the hour
  is worth, which is the register's arithmetic and not the doctype's -- see
  `attendance.CREDIT`.
* `Academic Term.custom_inactive` -- that a term was run once and is not run
  again. The term picker drops them; nothing else looks at it.

Guarded rather than shipped as fixtures, for the reason `commons.requests.install`
sets out at length: a Custom Field naming a doctype that is not on the site
raises `LinkValidationError`, `import_fixtures` does not catch that one, and
migrate aborts for the whole site rather than for this app. Education is
optional here in exactly the way ERPNext is there.

The `custom_` prefix is Frappe's mark of a site customisation rather than an
app's own field, and these are an app's. They keep it anyway: they were added by
hand on the site this register was written for, and there are thousands of rows
carrying them. A tidier name would be a rename, a patch, and a fortnight of
somebody's attendance quietly reading as nobody's.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

COURSE_SCHEDULE = "Course Schedule"
STUDENT_ATTENDANCE = "Student Attendance"
ACADEMIC_TERM = "Academic Term"

ATTENDANCE_CUSTOM_FIELDS = {
	COURSE_SCHEDULE: [
		{
			"fieldname": "custom_session_type",
			"label": "Session Type",
			"fieldtype": "Data",
			"insert_after": "color",
			"description": "What kind of session this was. The attendance register groups and totals by it.",
		},
		{
			"fieldname": "custom_session_details",
			"label": "Session Details",
			"fieldtype": "Data",
			"insert_after": "custom_session_type",
		},
	],
	STUDENT_ATTENDANCE: [
		{
			"fieldname": "custom_late",
			"label": "Late",
			"fieldtype": "Check",
			"insert_after": "status",
			"description": "Present, but not from the start. Counts as half the session's hours.",
		},
	],
	ACADEMIC_TERM: [
		{
			"fieldname": "custom_inactive",
			"label": "Inactive",
			"fieldtype": "Check",
			"insert_after": "term_name",
			"description": "A term that was run once and is not offered again. Hidden from the attendance register's term picker.",
		},
	],
}


def sync_attendance_custom_fields() -> None:
	"""Write the four fields, on a site that teaches.

	Silent on a site that does not, which is not a degraded install: without
	Education there are no course schedules to type and no attendance to be late
	for, and the register takes itself off the navigation -- see
	`commons.shell.pages.available`.

	All three doctypes are tested rather than one. They arrive together in
	practice, but `create_custom_fields` is given all four fields in one call and
	a half-answer here would be a half-applied one there.
	"""
	if not all(
		frappe.db.exists("DocType", doctype, cache=True)
		for doctype in (COURSE_SCHEDULE, STUDENT_ATTENDANCE, ACADEMIC_TERM)
	):
		return

	create_custom_fields(ATTENDANCE_CUSTOM_FIELDS)
