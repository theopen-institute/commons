"""Moving a term's students on to the next: their enrolments and their status.

At the end of a term every student enrolled in it goes somewhere -- on to the
next program, round the same one again, into a holding enrolment, or out. What
a person decides then is a `Program Enrollment` for each student going on, and
whatever the site keeps on `Student` to say where a student stands. The page at
`/commons/advancement` lays the old term out with a suggestion per student, and
this module writes what is chosen there: draft enrolments and statuses.

The rest follows from the enrolment, not from this page. Submitting one is
where a site hangs its consequences -- the term's student group, the fee and
its invoice -- so that whichever door an enrolment comes in by, the desk or
here, the same things happen to it.

Nothing about any one school is written here. Which program follows which is
the site's: a Table on `Program` the site adds and names on the Advancement tab
of Commons Settings, whose first row is the suggestion. So is where a
student's standing is kept: a Select on `Student`, with the one of its options
a student moving on is given. Left unnamed, the page offers every program and
suggests none, and leaves standing alone.

Reads go through the browser, by the document API, for the reason
`attendance_register.register` gives at length. Writes come here, because a
term's advancement is one act -- the enrolments and the statuses are either all
made or none are -- and Frappe makes one request one transaction. Every write
below is an ordinary permission-checked insert, so the site's own rules and
Server Scripts run exactly as they would from the desk.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from commons.commons_core import apps
from commons.commons_core.settings import _settings

# What every one of this page's fields in Commons Settings starts with.
PREFIX = "advancement_"

PROGRAM = "Program"
STUDENT = "Student"
ACADEMIC_TERM = "Academic Term"
PROGRAM_ENROLLMENT = "Program Enrollment"
STUDENT_GROUP = "Student Group"
EDUCATION_SETTINGS = "Education Settings"

NEXT_PROGRAMS_FIELD = PREFIX + "next_programs_field"
NEXT_PROGRAM_COLUMN = PREFIX + "next_program_column"
STATUS_FIELD = PREFIX + "status_field"
CONTINUING_STATUS = PREFIX + "continuing_status"
REQUIRE_LEAVING_STATUS = PREFIX + "require_leaving_status"


def available() -> bool:
	"""Whether this site enrols students in programs and groups them at all.

	Groups because the page reads them: who was active in the term being left
	says whether a student simply finished it.
	"""
	return apps.has_doctype(PROGRAM_ENROLLMENT) and apps.has_doctype(STUDENT_GROUP)


def can_advance() -> bool:
	"""Whether this reader enrols students -- the whole of who the page is for.

	Create on `Program Enrollment`. The page's other write, statuses, is
	permission-checked one by one as they are made.
	"""
	return bool(frappe.has_permission(PROGRAM_ENROLLMENT, "create"))


@frappe.whitelist(methods=["GET"])
def advancement_settings() -> dict:
	"""Which of the site's fields say what follows a program and where a student stands.

	`next_programs` is the Table on Program, its child doctype (which
	`frappe.client.get_list` reads a child table by) and the column naming the
	next program. `status` is the Select on Student, its options, and the one
	given to a student moving on. Each is None where the site names nothing
	usable; see `next_programs` and `status`.

	Open to any logged-in reader: it says which columns exist and nothing about
	any row.
	"""
	settings = _settings()
	return {
		"next_programs": next_programs(settings),
		"status": status(settings),
	}


def next_programs(settings) -> dict | None:
	"""Where a program lists the programs a student may go on to.

	Both names or neither. A table with no Link to Program in the named column
	has nothing to offer, and offering every program is then the honest answer.
	"""
	field = valid_field(settings, NEXT_PROGRAMS_FIELD, PROGRAM, frozenset(("Table", "Table MultiSelect")))
	if not field:
		return None
	table = frappe.get_meta(PROGRAM).get_field(field).options
	if not table or not apps.has_doctype(table):
		return None
	column = valid_field(settings, NEXT_PROGRAM_COLUMN, table, frozenset(("Link",)))
	if not column or frappe.get_meta(table).get_field(column).options != PROGRAM:
		return None
	return {"table_field": field, "table_doctype": table, "program_column": column}


def status(settings) -> dict | None:
	"""The Select on Student that says where a student stands, and its options.

	`continuing` is the option a student is given when an enrolment is made for
	them, or None where the setting is blank or names no option of the field --
	the page then suggests no change of status, and still offers every option.

	`require_leaving` is the site's choice that a student enrolled in nothing
	next term must leave it with one of the other options; see `unresolved`.
	It needs a continuing status to mean anything, and is off without one.
	"""
	field = valid_field(settings, STATUS_FIELD, STUDENT, frozenset(("Select",)))
	if not field:
		return None
	options = [
		option for option in (frappe.get_meta(STUDENT).get_field(field).options or "").split("\n") if option
	]
	continuing = (settings.get(CONTINUING_STATUS) or "").strip()
	continuing = continuing if continuing in options else None
	return {
		"field": field,
		"options": options,
		"continuing": continuing,
		"require_leaving": bool(continuing and settings.get(REQUIRE_LEAVING_STATUS)),
	}


def valid_field(settings, setting: str, doctype: str, fieldtypes: frozenset) -> str | None:
	"""The fieldname a setting names, or None if it names nothing usable on this site.

	The same test as the attendance register's (`register.valid_field`), and
	for the same reason: these names go into reads and writes, and a typo in
	the settings must read as the setting being blank rather than break them.
	"""
	fieldname = ((settings or {}).get(setting) or "").strip()
	if not fieldname or not apps.has_doctype(doctype):
		return None
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or field.fieldtype not in fieldtypes:
		return None
	return fieldname


def allowed_programs(chain: dict | None, program: str) -> list[str] | None:
	"""The programs a student in `program` may be enrolled in next, or None for any.

	Read past permissions: the list is configuration on the program, and this
	returns nothing to the reader -- it only refuses an enrolment the page
	would not have offered.
	"""
	if not chain:
		return None
	return frappe.get_all(
		chain["table_doctype"],
		filters={"parenttype": PROGRAM, "parent": program, "parentfield": chain["table_field"]},
		pluck=chain["program_column"],
		order_by="idx asc",
	)


@frappe.whitelist(methods=["POST"])
def apply(source_term: str, target_term: str, decisions, make_current=False) -> dict:
	"""Write a term's advancement: draft enrolments and statuses, all or nothing.

	`decisions` is one row per enrolment in `source_term` that is to change:
	`enrollment`, the next `program` (or none), and the `status` to give the
	student (or none, to leave it). A row may instead name a `student` with
	no enrolment in `source_term` -- one the page found marked as continuing
	with nothing behind it -- and then only its `status` is changed.
	`make_current` also makes `target_term` the current term in Education
	Settings, in the same transaction; see `make_current`.

	Enrolments are made as drafts. Submitting one is what a site's own rules
	hang the term's group, the fee and the invoice on, and that stays a
	person's act, one student at a time, in the desk. A student already
	enrolled in the program that term, draft or submitted, is skipped and
	reported rather than refused, so the page can be applied again after a
	partial edit.
	"""
	if not can_advance():
		frappe.throw(_("You may not enrol students."), frappe.PermissionError)
	decisions = frappe.parse_json(decisions) or []
	if source_term == target_term:
		frappe.throw(_("Students are advanced from one term into another."))

	term = frappe.db.get_value(ACADEMIC_TERM, target_term, ["academic_year", "term_start_date"], as_dict=True)
	if not term:
		frappe.throw(_("Academic Term {0} does not exist.").format(target_term))

	settings = _settings()
	chain = next_programs(settings)
	standing = status(settings)

	names = [row.get("enrollment") for row in decisions if row.get("enrollment")]
	sources = {
		row.name: row
		for row in frappe.get_list(
			PROGRAM_ENROLLMENT,
			filters={"name": ("in", names or [""]), "academic_term": source_term, "docstatus": 1},
			fields=["name", "student", "student_name", "program", "student_category", "student_batch_name"],
		)
	}

	done = {"enrollments": [], "skipped": [], "statuses": []}
	allowed: dict[str, list[str] | None] = {}

	for decision in decisions:
		if not decision.get("enrollment") and decision.get("student"):
			stray_status(decision, standing, done)
			continue
		source = sources.get(decision.get("enrollment"))
		if not source:
			frappe.throw(
				_("{0} is not a submitted enrolment in {1}.").format(decision.get("enrollment"), source_term)
			)

		program = decision.get("program")
		if program:
			if source.program not in allowed:
				allowed[source.program] = allowed_programs(chain, source.program)
			offered = allowed[source.program]
			if offered is not None and program not in offered:
				frappe.throw(
					_("{0} does not follow {1}. Add it to the program's next programs first.").format(
						program, source.program
					)
				)
			if enrolled(source.student, program, target_term):
				done["skipped"].append(
					{"student": source.student, "student_name": source.student_name, "program": program}
				)
			else:
				name = enrol(source, program, target_term, term)
				done["enrollments"].append(
					{
						"name": name,
						"student": source.student,
						"student_name": source.student_name,
						"program": program,
					}
				)

		value = decision.get("status")
		if value and standing:
			before = set_status(source.student, standing, value)
			if before is not None:
				done["statuses"].append(
					{
						"student": source.student,
						"student_name": source.student_name,
						"from": before,
						"to": value,
					}
				)

	if standing and standing["require_leaving"]:
		left = unresolved(source_term, target_term, standing)
		if left:
			frappe.throw(
				_(
					"Nothing was applied. Every student not enrolled in {0} needs a status other than {1}: {2}."
				).format(target_term, standing["continuing"], ", ".join(left))
			)

	if frappe.parse_json(make_current):
		done["current_term"] = set_current_term(target_term)

	return done


def unresolved(source_term: str, target_term: str, standing: dict) -> list[str]:
	"""The students of `source_term` with no enrolment in `target_term` whose status says they continue.

	Asked after everything else is written, so it sees this call's enrolments
	and statuses: a student enrolled in the new term, by this call or before
	it, continues; anyone else must have left, and the status is where that
	is said. Blank counts as not said. Read with the reader's permissions,
	like the rest of `apply`.
	"""
	leaving = [option for option in standing["options"] if option != standing["continuing"]]
	students = {
		row.student: row.student_name
		for row in frappe.get_list(
			PROGRAM_ENROLLMENT,
			filters={"academic_term": source_term, "docstatus": 1},
			fields=["student", "student_name"],
		)
	}
	if not students:
		return []
	entering = set(
		frappe.get_list(
			PROGRAM_ENROLLMENT,
			filters={"academic_term": target_term, "docstatus": ("<", 2), "student": ("in", list(students))},
			pluck="student",
		)
	)
	statuses = {
		row.name: row.get(standing["field"])
		for row in frappe.get_list(
			STUDENT, filters={"name": ("in", list(students))}, fields=["name", standing["field"]]
		)
	}
	return sorted(
		name or student
		for student, name in students.items()
		if student not in entering and statuses.get(student) not in leaving
	)


@frappe.whitelist(methods=["POST"])
def make_current(term: str) -> str:
	"""Make `term` the current term in Education Settings, and its year the current year.

	The page offers it once a term has been advanced into: Education's own
	"current" is what its defaults, its portal and the attendance register
	open on, and moving it is the moment one term hands over to the next.
	"""
	return set_current_term(term)


def set_current_term(term: str) -> str:
	"""Saved through the document, not set in the database: Education Settings'
	`on_update` copies the two into the site's defaults, which is where most of
	Education reads them from.
	"""
	if not apps.has_doctype(EDUCATION_SETTINGS):
		frappe.throw(_("This site has no Education Settings."))
	year = frappe.db.get_value(ACADEMIC_TERM, term, "academic_year")
	if not year:
		frappe.throw(_("Academic Term {0} does not exist or has no academic year.").format(term))
	settings = frappe.get_single(EDUCATION_SETTINGS)
	settings.check_permission("write")
	settings.current_academic_term = term
	settings.current_academic_year = year
	settings.save()
	return term


def stray_status(decision: dict, standing: dict | None, done: dict) -> None:
	"""A status for a student the page found continuing with no enrolment or group to show for it.

	Only a status: with no enrolment in the term being left, there is nothing
	this page could carry forward, and enrolling them is the desk's.
	"""
	if decision.get("program"):
		frappe.throw(_("A student with no enrolment this term can only have their status changed here."))
	value = decision.get("status")
	if not (value and standing):
		return
	student = decision["student"]
	before = set_status(student, standing, value)
	if before is not None:
		done["statuses"].append(
			{
				"student": student,
				"student_name": frappe.db.get_value(STUDENT, student, "student_name"),
				"from": before,
				"to": value,
			}
		)


def enrolled(student: str, program: str, term: str) -> bool:
	"""Whether the student already has an enrolment, draft or submitted, in the program that term."""
	return bool(
		frappe.get_list(
			PROGRAM_ENROLLMENT,
			filters={"student": student, "program": program, "academic_term": term, "docstatus": ("<", 2)},
			pluck="name",
			limit=1,
		)
	)


def enrol(source, program: str, term: str, term_row) -> str:
	"""A draft enrolment in the program, filled as the desk's form fills one.

	The form fetches a program's required courses when a program is picked
	(`program_enrollment.js`); an enrolment made here would otherwise reach
	submission without them. Its fees are not filled here: they are the
	site's, at submission. Dated the day the term starts, or today for a term
	with no dates.
	"""
	enrolment = frappe.new_doc(PROGRAM_ENROLLMENT)
	enrolment.student = source.student
	enrolment.program = program
	enrolment.academic_year = term_row.academic_year
	enrolment.academic_term = term
	enrolment.enrollment_date = getdate(term_row.term_start_date or today())
	enrolment.student_category = source.student_category
	enrolment.student_batch_name = source.student_batch_name
	for course in enrolment.get_courses():
		enrolment.append("courses", {"course": course.course, "course_name": course.course_name})
	enrolment.insert()
	return enrolment.name


def set_status(student: str, standing: dict, value: str) -> str | None:
	"""Give the student `value`, returning what it was -- or None where nothing changed.

	Written with `db_set` and a Version rather than by saving the Student.
	Education's `Student.validate` makes a website User, and sends its welcome
	email, for any student whose email has none; an advancement is no time to
	do that to a whole cohort. The Version is what a save would have recorded,
	so the change reads the same in the student's timeline.
	"""
	if value not in standing["options"]:
		frappe.throw(_("{0} is not a status a student may have.").format(value))
	doc = frappe.get_doc(STUDENT, student)
	doc.check_permission("write")
	field = standing["field"]
	before = doc.get(field) or ""
	if before == value:
		return None
	doc.db_set(field, value)
	version = frappe.new_doc("Version")
	version.ref_doctype = STUDENT
	version.docname = student
	version.data = frappe.as_json(
		{"changed": [[field, before, value]], "added": [], "removed": [], "row_changed": []}
	)
	version.insert(ignore_permissions=True)
	return before
