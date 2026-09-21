"""What the navigation needs to know about the attendance register.

Two questions and no data. Whether this site keeps a register at all, and
whether this reader is one of the people it is for — the sidebar asks both
before drawing a row, and `commons.search` asks them again before the desk's
Awesome Bar offers the same page.

There was a good deal more here. An earlier version of the register assembled
the whole page on the server: it resolved a term and a course into student
groups, indexed the students into them, grouped the sessions, translated marks
and totalled the hours, and handed the browser one payload. It read nicely and
it was wrong, for a reason that has nothing to do with any of that:

Assembling a register means reading six tables, and it read them with
`frappe.get_all` — which is `ignore_permissions=True`. So it walked past User
Permissions and past this app's own gate in `commons.safer_permissions`, the
module whose entire purpose is that a role grants nothing until a User
Permission narrows it. One `can_mark` check at the door is not a substitute:
that answers "may this person mark attendance", not "which groups are theirs".

The register now reads and writes through the APIs Frappe already ships —
`/api/v2/document/...` and `frappe.client` — so every row is filtered by the
same rules as everything else in this app, and the joining and the arithmetic
happen in `frontend/src/data/attendanceRegister.ts`. There is no endpoint here
for it to call, which is the point. The custom fields it stores its answers in
are still this app's; see `install.py`.
"""

import frappe

from commons.commons_core import apps

COURSE_SCHEDULE = "Course Schedule"
STUDENT_ATTENDANCE = "Student Attendance"


def available() -> bool:
	"""Whether this site teaches anything at all.

	The two doctypes the register is made of rather than "is Education
	installed", for the reason `commons_core.apps` gives: a session and a mark
	against it are what the page is, so they are the question it is actually
	asking. Both, because a site with one and not the other would be offered a
	page whose first read fails.
	"""
	return apps.has_doctype(COURSE_SCHEDULE) and apps.has_doctype(STUDENT_ATTENDANCE)


def can_mark() -> bool:
	"""Whether this reader marks attendance -- the whole of who the page is for.

	Write permission on `Student Attendance`, and deliberately not read.
	`Student` and `Guardian` both hold read, rightly: a student may see their
	own record in the desk, where the list is filtered to it. The register is
	the opposite shape -- one term of one course, every student in the group
	across the top -- so offering it on read would put a row in front of every
	student on the site for a page written for the people who mark it.

	This decides the *navigation* and nothing else. It is not what keeps one
	reader out of another's rows: the page reads through the document API, so
	that is settled per row, by Frappe and by `commons.safer_permissions`. The
	browser asks the same question for itself through
	`frappe.client.has_permission` -- see `frontend/src/data/attendance.ts` --
	rather than through an endpoint here, because there is no reason for this
	app to own a second way of asking it.
	"""
	return bool(frappe.has_permission(STUDENT_ATTENDANCE, "write"))
