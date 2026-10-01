"""What the navigation and the page need to know about the attendance register.

Two questions and one lookup, and no data. Whether this site keeps a register
at all, and whether this reader is one of the people it is for -- the sidebar
asks both before drawing a row, and `commons.better_navigation.search` asks
them again before the desk's Awesome Bar offers the same page. And which of the
site's own fields the register stores what Education has no field for:
`register_fields`, which is the page's to call.

Its settings are the Attendance tab of `Commons Settings`, each field named
with an `attendance_` prefix so it reads as the register's beside the rest. They
were a Single of their own for a while, `Attendance Register Settings`; one
settings form for the app's pages turned out easier to find than two. The code
used to sit in a package called `education_extensions`, named after a module
one site keeps its Custom DocTypes in, which is that site's own custom module
now.

There was a good deal more here. An earlier version of the register assembled
the whole page on the server: it resolved a term and a course into student
groups, indexed the students into them, grouped the sessions, translated marks
and totalled the hours, and handed the browser one payload. It read nicely and
it was wrong, for a reason that has nothing to do with any of that:

Assembling a register means reading six tables, and it read them with
`frappe.get_all` -- which is `ignore_permissions=True`. So it walked past User
Permissions and past this app's own gate in `commons.safer_permissions`, the
module whose entire purpose is that a role grants nothing until a User
Permission narrows it. One `can_mark` check at the door is not a substitute:
that answers "may this person mark attendance", not "which groups are theirs".

The register now reads and writes through the APIs Frappe already ships --
`/api/v2/document/...` and `frappe.client` -- so every row is filtered by the
same rules as everything else in this app, and the joining and the arithmetic
happen in `frontend/src/data/attendanceRegister.ts`. `register_fields` returns
fieldnames and a number and nothing read from any row, which is why it can be
an endpoint of this app's without reopening that.
"""

import frappe
from frappe.utils import flt

from commons.commons_core import apps
from commons.commons_core.settings import _settings

# What every one of the register's fields in Commons Settings starts with.
PREFIX = "attendance_"

COURSE_SCHEDULE = "Course Schedule"
STUDENT_ATTENDANCE = "Student Attendance"
ACADEMIC_TERM = "Academic Term"

# What a field holding a session's type or details may be: a value the page can
# show as a line of text and write back as one. Not Text Editor or HTML, whose
# value is markup and would be shown as its tags.
TEXT_FIELDTYPES = frozenset(("Data", "Select", "Link", "Autocomplete", "Small Text", "Text", "Long Text"))

# Each register field: the doctype it must be on and the fieldtypes it may
# have. The keys are what the page is sent; the setting that names each is the
# key with `PREFIX` in front.
REGISTER_FIELDS = {
	"late_field": (STUDENT_ATTENDANCE, frozenset(("Check",))),
	"session_type_field": (COURSE_SCHEDULE, TEXT_FIELDTYPES),
	"session_details_field": (COURSE_SCHEDULE, TEXT_FIELDTYPES),
	"inactive_term_field": (ACADEMIC_TERM, frozenset(("Check",))),
	"session_hours_field": (COURSE_SCHEDULE, frozenset(("Float", "Int"))),
}

LATE_CREDIT = PREFIX + "late_credit"

# What a late arrival earns where the setting has never been saved: the field's
# own default, which counts it as fully present. Nothing about lateness is this
# app's rule to invent.
DEFAULT_LATE_CREDIT = 1.0

# The register's two choices of rule, each with the options the settings offer
# and the answer a site gets that never chose: the register's behaviour before
# either was a setting.
#
# `group_resolution` is how a course finds its student groups. Education models
# two ways for a group to take a course: through its programme (a group names a
# programme and a term, and `Program Course` says the course is on it), or
# directly (a course-based group's own `course`). Which a school uses is how it
# runs its groups, so it is the site's to say.
#
# `leave_counts_as` is what Education's `Leave` status is worth. Absent counts
# the session against the student like any other absence; Excused leaves it out
# of that student's total altogether, earned hours and possible hours alike.
CHOICES = {
	"group_resolution": (("Programme", "Course", "Both"), "Programme"),
	"leave_counts_as": (("Absent", "Excused"), "Absent"),
}


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


@frappe.whitelist(methods=["GET"])
def register_fields() -> dict:
	"""Which of the site's fields the register reads and writes, and what late is worth.

	Education has nowhere to say that a session was a seminar, what it covered,
	that a student came late, or that a term is not run any more. A school that
	wants any of them adds a Custom Field and names it on the Attendance tab of
	Commons Settings; this is how the page learns which. Every key is a fieldname or None, and None is
	the page doing without: no Late mark, no grouping by type, no details line,
	every term in the picker, and hours read off each session's times.

	Two rules ride along with the fields, `group_resolution` and
	`leave_counts_as`, each one of its options; see `CHOICES`.

	A name is only sent if the doctype's meta has a field of that name and of a
	type the page can use. The page puts these names into the filters and the
	field lists of document API calls and into the values it writes; a typo in
	the settings would otherwise fail every read the register makes, and a Data
	field named as the late flag would be written 0s and 1s.

	Open to any logged-in reader, not only to those who `can_mark`: it says
	which columns exist, which the desk's own form for any of these doctypes
	says to anybody who can open it, and nothing about any row.
	"""
	settings = _settings()
	fields = {key: valid_field(settings, PREFIX + key, *spec) for key, spec in REGISTER_FIELDS.items()}
	fields["late_credit"] = late_credit(settings)
	for key, (options, default) in CHOICES.items():
		fields[key] = choice(settings, PREFIX + key, options, default)
	return fields


def choice(settings, setting: str, options: tuple, default: str) -> str:
	"""A Select setting's value, or its default if unsaved or not one of its options.

	Unsaved is the common case rather than an edge: a Select added to a Single
	that was saved before it existed reads as nothing until somebody saves the
	form again, and nothing must mean what the register did before there was a
	choice.
	"""
	stored = ((settings.get(setting) if settings else None) or "").strip()
	return stored if stored in options else default


def valid_field(settings, setting: str, doctype: str, fieldtypes: frozenset) -> str | None:
	"""The fieldname a setting names, or None if it names nothing usable on this site.

	`settings` is None between this app landing and its migrate. A doctype the
	site lacks -- no Education -- is None too, not an error: the register is not
	offered there, and this must still answer.
	"""
	fieldname = ((settings.get(setting) if settings else None) or "").strip()
	if not fieldname or not apps.has_doctype(doctype):
		return None
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or field.fieldtype not in fieldtypes:
		return None
	return fieldname


def late_credit(settings) -> float:
	"""The share of a session's hours a late arrival earns, held to 0 through 1.

	Unsaved reads as the field's default rather than as 0: `flt(None)` is 0,
	which would quietly price every late arrival as an absence on a site that
	never opened the form. A stored 0 is a school's real answer and is kept.
	"""
	stored = settings.get(LATE_CREDIT) if settings else None
	if stored is None or stored == "":
		return DEFAULT_LATE_CREDIT
	return min(max(flt(stored), 0.0), 1.0)
