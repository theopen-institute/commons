/**
 * The attendance register, assembled from the rows the document API returns.
 *
 * Pure: no Vue, no network, nothing that reaches for a session. `attendance.ts`
 * fetches; this turns what came back into the shape the page draws, and it is
 * the whole of the arithmetic.
 *
 * ## Why this is in the browser
 *
 * It began on the server, which let one endpoint answer with a register already
 * joined and footed. That was pleasant and it was wrong, for a reason that has
 * nothing to do with arithmetic: to assemble a register the server had to read
 * six tables with `frappe.get_all`, which is `ignore_permissions=True`. It
 * therefore walked straight past User Permissions and past this app's own gate
 * in `commons.safer_permissions` — the module whose entire purpose is that a
 * role grants nothing until a User Permission narrows it. A single `can_mark`
 * check at the door is not a substitute for that: it answers "may this person
 * mark attendance at all", not "which groups are theirs".
 *
 * So the rows are fetched through the standard document API, which applies
 * every one of those rules without this app restating any of them, and the
 * joining and totalling happen here. The cost is that four of these reads are
 * chained rather than one call being made, and that this file is arithmetic in
 * a language with no server-side tests. `attendanceRegister.test.ts` is the
 * answer to the second; the first is what correctness costs here.
 */

/**
 * What a cell can say.
 *
 * Four words rather than `Student Attendance`'s two fields. `Late` is stored as
 * present with a flag, because a late arrival *was* there and every report that
 * counts attendance should keep counting them; the empty string is no record at
 * all, which is what an untouched cell means and what clears one.
 */
export type Mark = 'Present' | 'Late' | 'Absent' | ''

export const PRESENT = 'Present'
export const LATE = 'Late'
export const ABSENT = 'Absent'
export const UNMARKED = ''

/** The marks a session's details offer, in the order they are drawn, on a site
 *  that records lateness. See `marksOffered` for one that does not. */
export const MARKS: Mark[] = [PRESENT, LATE, ABSENT, UNMARKED]

/* -------------------------------------------------------------------------- */
/* The site's own fields                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Which of the site's fields the register stores what Education cannot, and
 * what a late arrival is worth.
 *
 * Education has nowhere to say what kind of session a class was, what it
 * covered, that a student came late, or that a term is not run any more. A
 * school that wants any of those adds a field and names it in Commons
 * Settings; `commons.attendance_register.register.register_fields` sends the
 * names, having checked each against the doctype. A null is a site that does
 * without, and the page does too: no Late mark, no blocks by type, no details
 * line, every term in the picker.
 *
 * The register this page was written for keeps them as `custom_late`,
 * `custom_session_type`, `custom_session_details` and `custom_inactive`, and
 * those names used to be written into this file. They were one school's.
 */
export interface RegisterFields {
  /** A Check on `Student Attendance`: present, but late. */
  late_field: string | null
  /** The share of a session's hours a late arrival earns, 0 to 1. */
  late_credit: number
  /** Text on `Course Schedule` naming the kind of session. */
  session_type_field: string | null
  /** Text on `Course Schedule` saying what a session covered. */
  session_details_field: string | null
  /** A Check on `Academic Term` retiring a term from the picker. */
  inactive_term_field: string | null
}

/** A site that has named nothing. A late arrival is worth a full session there,
 *  the setting's own default — though without a late field there are none. */
export const NO_FIELDS: RegisterFields = {
  late_field: null,
  late_credit: 1,
  session_type_field: null,
  session_details_field: null,
  inactive_term_field: null,
}

/** What a fieldname can look like. The server has already checked each against
 *  the doctype's meta; this is only so that nothing else is ever put into a
 *  filter or a field list, whatever arrives. */
const FIELDNAME = /^[a-z_][a-z0-9_]*$/i

function fieldname(value: unknown): string | null {
  return typeof value === 'string' && FIELDNAME.test(value.trim())
    ? value.trim()
    : null
}

/**
 * What the endpoint sent, as the page uses it.
 *
 * The credit is held to 0 through 1 here as well as on the server. Above 1 a
 * late arrival would out-earn being on time, and below 0 it would take hours
 * off a student, and either one is a figure in a column that somebody acts on.
 */
export function registerFields(
  raw: Partial<RegisterFields> | null | undefined,
): RegisterFields {
  const credit = Number(raw?.late_credit ?? NO_FIELDS.late_credit)
  return {
    late_field: fieldname(raw?.late_field),
    late_credit: Number.isFinite(credit)
      ? Math.min(Math.max(credit, 0), 1)
      : NO_FIELDS.late_credit,
    session_type_field: fieldname(raw?.session_type_field),
    session_details_field: fieldname(raw?.session_details_field),
    inactive_term_field: fieldname(raw?.inactive_term_field),
  }
}

/** The marks a session's details offer on this site. Late only where there is a
 *  field to keep it in: offered anyway, it would be saved as plain present. */
export function marksOffered(fields: RegisterFields): Mark[] {
  return fields.late_field ? MARKS : MARKS.filter((mark) => mark !== LATE)
}

/** What a session's marks dialog has to write to turn what is stored into what
 *  was chosen. */
export interface MarkChanges {
  /** Students with no `Student Attendance` row yet, and the mark to create. */
  insert: { student: string; mark: Mark }[]
  /** Existing rows whose mark changed. */
  update: { name: string; mark: Mark }[]
  /** Existing rows cleared back to unmarked. */
  remove: string[]
}

/**
 * The writes between a session's stored marks and a draft of them.
 *
 * A student the draft leaves out is left alone rather than cleared: the draft
 * says only what was chosen, so nothing is written for anybody it does not
 * mention. A draft that matches what is stored is no writes at all, which is
 * what lets the dialog say "no changes" and keep Save shut.
 */
export function markChanges(
  stored: Record<string, SessionMark>,
  draft: Record<string, Mark>,
): MarkChanges {
  const changes: MarkChanges = { insert: [], update: [], remove: [] }
  for (const [student, mark] of Object.entries(draft)) {
    const row = stored[student]
    if ((row?.mark ?? UNMARKED) === mark) continue
    if (!row?.name) {
      if (mark) changes.insert.push({ student, mark })
    } else if (mark) {
      changes.update.push({ name: row.name, mark })
    } else {
      changes.remove.push(row.name)
    }
  }
  return changes
}

/**
 * What a mark earns of a session's hours.
 *
 * What a late arrival earns is the school's rule rather than Frappe's —
 * `Student Attendance` has no such concept — so it is the site's setting, and
 * every figure on the page comes through here. Absent and unmarked both earn
 * nothing and stay distinguishable everywhere else: a student nobody has marked
 * is not a student who was away.
 */
export function credit(mark: Mark, lateCredit: number): number {
  if (mark === PRESENT) return 1
  if (mark === LATE) return lateCredit
  return 0
}

/**
 * Two stored fields as the one word the page uses.
 *
 * `Leave` is Education's third status and this register does not offer it, so
 * it reads as absent rather than as a fourth thing the grid would have to draw
 * and the footings would have to price. A mark made in the desk stays legible
 * here; it just cannot be made from here.
 */
export function toMark(status: string | null, late: number | null): Mark {
  if (status !== PRESENT) return ABSENT
  return late ? LATE : PRESENT
}

/** The one word back into the stored fields, which is the only place it happens.
 *
 *  The late flag is written explicitly rather than left out when it is off: a
 *  student marked late and then corrected to present has a row with the flag
 *  already set, and an update that omitted the field would leave them late for
 *  ever. A site with no late field has only the status to write. */
export function markFields(
  mark: Mark,
  fields: RegisterFields,
): Record<string, string | 0 | 1> {
  const status = mark === ABSENT ? ABSENT : PRESENT
  return fields.late_field
    ? { status, [fields.late_field]: mark === LATE ? 1 : 0 }
    : { status }
}

/**
 * A stored Time as a count of hours.
 *
 * Frappe sends a Time as `str(timedelta)`, which does **not** pad the hour: a
 * nine o'clock class arrives as `9:00:00` and a three o'clock one as `15:00:00`.
 * Splitting on the colon rather than slicing fixed offsets is what makes those
 * the same shape.
 */
function hoursInto(value: string | null): number | null {
  if (!value) return null
  const [hours, minutes, seconds] = value.split(':').map(Number)
  if ([hours, minutes].some((part) => !Number.isFinite(part))) return null
  return hours + minutes / 60 + (Number.isFinite(seconds) ? seconds : 0) / 3600
}

/** A stored Time as the clock reads it — `9:00:00` and `09:00:00` both give
 *  `09:00`. Seconds are never anything but zero on a timetable and cost three
 *  characters in a column that has none to spare. */
export function formatTime(value: string | null): string {
  const [hours, minutes] = (value ?? '').split(':')
  if (!hours || minutes === undefined) return ''
  return `${hours.padStart(2, '0')}:${minutes.padStart(2, '0')}`
}

/** `HH:MM` for a time input, which will not accept an unpadded hour. */
export function toTimeInput(value: string | null): string {
  return formatTime(value)
}

/** `HH:MM` back to what a Time field stores. */
export function fromTimeInput(value: string): string {
  return `${value}:00`
}

/** Two decimal places, as a number — every figure on the page is a sum of
 *  these, so they are rounded once here rather than only when printed. */
function round(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * How long a session runs, in hours.
 *
 * A session running backwards is worth nothing rather than a negative number.
 * `Course Schedule` refuses to save one, so this only defends the footings
 * against a row that predates the check — but a negative session would subtract
 * itself from a term total, which is a figure somebody would act on.
 */
export function sessionHours(from: string | null, to: string | null): number {
  const start = hoursInto(from)
  const end = hoursInto(to)
  if (start === null || end === null) return 0
  return round(Math.max(end - start, 0))
}

/** An hours figure with the trailing zeroes off: `2.5`, `3`, `0`. Totals are
 *  read down a column, and a column of `3.00`s is harder to scan than one of
 *  `3`s. */
export function formatHours(value: number): string {
  return String(round(value))
}

/* -------------------------------------------------------------------------- */
/* The rows, as the document API sends them                                    */
/* -------------------------------------------------------------------------- */

export interface TermRow {
  name: string
  term_start_date: string | null
  term_end_date: string | null
}

export interface CourseRow {
  name: string
  course_name: string | null
  /** The short form the chips are labelled with, where the school has set one. */
  abbreviation: string | null
  default_instructor: string | null
}

export interface GroupRow {
  name: string
  student_group_name: string | null
  program: string | null
  disabled: 0 | 1
}

export interface StudentRow {
  /** The `Student Group` this row belongs to. */
  parent: string
  student: string
  student_name: string | null
}

/** A `Course Schedule`, with the site's own fields under the register's names.
 *  See `scheduleRow`. */
export interface ScheduleRow {
  name: string
  student_group: string
  schedule_date: string | null
  from_time: string | null
  to_time: string | null
  session_type: string | null
  session_details: string | null
}

/** A `Student Attendance`, the same way. See `markRow`. */
export interface MarkRow {
  /** The `Student Attendance` id — what a change or a deletion needs. */
  name: string
  course_schedule: string
  student: string
  status: string | null
  late: 0 | 1 | null
}

/** A row as the document API sent it, keyed by whatever the site's fields are
 *  called. */
export type ApiRow = Record<string, unknown>

function text(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

/** The fields a session is read with: Education's own, and those of the site's
 *  it has named. */
export function scheduleFieldList(fields: RegisterFields): string[] {
  return [
    'name',
    'student_group',
    'schedule_date',
    'from_time',
    'to_time',
    ...[fields.session_type_field, fields.session_details_field].filter(
      (name): name is string => Boolean(name),
    ),
  ]
}

/** The fields a mark is read with. */
export function markFieldList(fields: RegisterFields): string[] {
  return [
    'name',
    'course_schedule',
    'student',
    'status',
    ...(fields.late_field ? [fields.late_field] : []),
  ]
}

/** A session as it came back, under the names the register uses. A field the
 *  site has not named reads as nothing, which is one block and no details. */
export function scheduleRow(row: ApiRow, fields: RegisterFields): ScheduleRow {
  return {
    name: String(row.name),
    student_group: String(row.student_group),
    schedule_date: text(row.schedule_date),
    from_time: text(row.from_time),
    to_time: text(row.to_time),
    session_type: fields.session_type_field
      ? text(row[fields.session_type_field])
      : null,
    session_details: fields.session_details_field
      ? text(row[fields.session_details_field])
      : null,
  }
}

/** A mark as it came back. With no late field, nobody is late. */
export function markRow(row: ApiRow, fields: RegisterFields): MarkRow {
  return {
    name: String(row.name),
    course_schedule: String(row.course_schedule),
    student: String(row.student),
    status: text(row.status),
    late: fields.late_field && row[fields.late_field] ? 1 : 0,
  }
}

/** What a session's dialog writes for its type and details: only the fields the
 *  site has, since naming one it lacks would refuse the whole save. */
export function sessionFields(
  fields: RegisterFields,
  values: { session_type: string; session_details: string },
): Record<string, string | null> {
  const written: Record<string, string | null> = {}
  if (fields.session_type_field)
    written[fields.session_type_field] = values.session_type || null
  if (fields.session_details_field) {
    written[fields.session_details_field] = values.session_details || null
  }
  return written
}

/* -------------------------------------------------------------------------- */
/* The register, as the page draws it                                          */
/* -------------------------------------------------------------------------- */

/** One student's mark on one session, with the document behind it. The grid
 *  reads the word; a write needs the id. */
export interface SessionMark {
  name: string
  mark: Mark
}

export interface Session {
  name: string
  group: string
  schedule_date: string | null
  from_time: string | null
  to_time: string | null
  hours: number
  session_type: string | null
  session_details: string | null
  /** Keyed by student. A student absent from this map is unmarked, which is not
   *  the same as absent. */
  marks: Record<string, SessionMark>
}

export interface Block {
  /** Null for sessions nobody typed. Drawn last. */
  session_type: string | null
  sessions: Session[]
  /** Hours timetabled. */
  scheduled: number
  /** Hours earned, per student. Less than `scheduled` for anybody who missed a
   *  session or arrived late at one. */
  credited: Record<string, number>
}

export interface GroupStudent {
  student: string
  student_name: string
}

export interface GroupRegister {
  name: string
  title: string
  program: string | null
  students: GroupStudent[]
  blocks: Block[]
  scheduled: number
  credited: Record<string, number>
}

export interface Register {
  groups: GroupRegister[]
}

export const EMPTY_REGISTER: Register = { groups: [] }

/** What a block of untyped sessions is called. The field is empty rather than
 *  naming the absence of a type; this is the English for it. On a site with no
 *  session type field every session is untyped, and the page draws no block
 *  headings at all rather than one saying this. */
export const UNTYPED_SESSION = 'Unspecified'

export function sessionTypeLabel(sessionType: string | null): string {
  return sessionType || UNTYPED_SESSION
}

/** The chip a course is offered as: the abbreviation where the school has set
 *  one, the full name where it has not. The register this replaced built `CEM`
 *  out of `Critical Epistemology and Methodology` with a regular expression
 *  over its capital letters, which is right until a course is called `Field
 *  Methods II`. A long right name beats a short wrong one. */
export function courseChip(course: CourseRow): string {
  return course.abbreviation || course.course_name || course.name
}

/**
 * Everything the page draws, from the rows that were fetched.
 *
 * The one place the six lists become one register. Each group gets its own
 * students and its own sessions — which is the bug this shape exists to make
 * impossible, because the register this replaced totalled the *first* group's
 * hours under every group on the page.
 */
export function buildRegister(
  rows: {
    groups: GroupRow[]
    students: StudentRow[]
    schedules: ScheduleRow[]
    marks: MarkRow[]
  },
  lateCredit: number,
): Register {
  const byGroup = new Map<string, GroupStudent[]>()
  for (const row of rows.students) {
    const list = byGroup.get(row.parent) ?? []
    list.push({
      student: row.student,
      student_name: row.student_name || row.student,
    })
    byGroup.set(row.parent, list)
  }

  const bySession = new Map<string, Record<string, SessionMark>>()
  for (const row of rows.marks) {
    const marks = bySession.get(row.course_schedule) ?? {}
    marks[row.student] = { name: row.name, mark: toMark(row.status, row.late) }
    bySession.set(row.course_schedule, marks)
  }

  const sessions = rows.schedules.map<Session>((row) => ({
    name: row.name,
    group: row.student_group,
    schedule_date: row.schedule_date,
    from_time: row.from_time,
    to_time: row.to_time,
    hours: sessionHours(row.from_time, row.to_time),
    session_type: row.session_type || null,
    session_details: row.session_details || null,
    marks: bySession.get(row.name) ?? {},
  }))

  return {
    groups: rows.groups.map((group) =>
      buildGroup(
        group,
        byGroup.get(group.name) ?? [],
        sessions.filter((session) => session.group === group.name),
        lateCredit,
      ),
    ),
  }
}

function buildGroup(
  row: GroupRow,
  students: GroupStudent[],
  sessions: Session[],
  lateCredit: number,
): GroupRegister {
  const blocks = sessionTypes(sessions).map((sessionType) =>
    buildBlock(
      sessionType,
      sessions.filter((session) => session.session_type === sessionType),
      students,
      lateCredit,
    ),
  )
  return {
    name: row.name,
    title: row.student_group_name || row.name,
    program: row.program,
    students,
    blocks,
    scheduled: round(
      blocks.reduce((total, block) => total + block.scheduled, 0),
    ),
    credited: Object.fromEntries(
      students.map((student) => [
        student.student,
        round(
          blocks.reduce(
            (total, block) => total + (block.credited[student.student] ?? 0),
            0,
          ),
        ),
      ]),
    ),
  }
}

/**
 * The kinds of session a group had, in the order they are drawn.
 *
 * Alphabetical, with the untyped block last. The register this replaced sorted
 * the school's own vocabulary by prefixing anything beginning "Faculty" with an
 * exclamation mark before comparing, which put seminars at the top of the page
 * — correct for one school's four session types and meaningless for a fifth or
 * for anybody else's. The field is free text, so there is no order to read off
 * it; alphabetical is the one a reader can predict, and a school that wants a
 * particular order has the naming of them.
 */
function sessionTypes(sessions: Session[]): (string | null)[] {
  const found = new Set(sessions.map((session) => session.session_type))
  const typed = [...found]
    .filter((name): name is string => Boolean(name))
    .sort()
  return found.has(null) ? [...typed, null] : typed
}

/**
 * The sessions of one kind, and what they came to.
 *
 * `scheduled` is what was timetabled and `credited` is what each student earned
 * of it — the same figure only for somebody who was at all of it on time, which
 * is the comparison the block exists to make.
 */
function buildBlock(
  sessionType: string | null,
  sessions: Session[],
  students: GroupStudent[],
  lateCredit: number,
): Block {
  return {
    session_type: sessionType,
    sessions,
    scheduled: round(
      sessions.reduce((total, session) => total + session.hours, 0),
    ),
    credited: Object.fromEntries(
      students.map((student) => [
        student.student,
        round(
          sessions.reduce(
            (total, session) =>
              total +
              session.hours *
                credit(
                  session.marks[student.student]?.mark ?? UNMARKED,
                  lateCredit,
                ),
            0,
          ),
        ),
      ]),
    ),
  }
}
