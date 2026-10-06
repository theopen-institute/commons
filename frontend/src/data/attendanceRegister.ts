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
 * Words rather than `Student Attendance`'s two fields. `Late` is stored as
 * present with a flag, because a late arrival *was* there and every report that
 * counts attendance should keep counting them; the empty string is no record at
 * all, which is what an untouched cell means and what clears one. `Excused` is
 * Education's `Leave` on a site that counts leave as excused (see
 * `LeaveCountsAs`); it is read, never offered.
 */
export type Mark = 'Present' | 'Late' | 'Absent' | 'Excused' | ''

export const PRESENT = 'Present'
export const LATE = 'Late'
export const ABSENT = 'Absent'
export const EXCUSED = 'Excused'
export const UNMARKED = ''

/** Education's third status, which this register reads but does not offer. */
export const LEAVE = 'Leave'

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
 *
 * Two rules come with them, each a choice the settings offer and each
 * defaulting to what the register did before it was a choice:
 * `group_resolution` and `leave_counts_as`.
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
  /** A Float or Int on `Course Schedule`: the hours a session is worth, where
   *  set, instead of the time between its start and end. */
  session_hours_field: string | null
  /** How a course reaches its student groups. See `GroupResolution`. */
  group_resolution: GroupResolution
  /** What Education's `Leave` is worth. See `LeaveCountsAs`. */
  leave_counts_as: LeaveCountsAs
  /** Where a course lists its kinds of session and the hours planned for each.
   *  See `CoursePlanFields`. */
  course_plan: CoursePlanFields | null
}

/**
 * A table on `Course` listing the kinds of session the course is taught in and
 * the hours planned for each, and which of its columns say which.
 *
 * All four or none, as the server sends them: the Table field, the child
 * doctype it holds (which is what `frappe.client.get_list` reads a child table
 * by), the column naming the kind of session in the same words as
 * `session_type_field`, and the column of planned hours.
 */
export interface CoursePlanFields {
  table_field: string
  table_doctype: string
  type_column: string
  hours_column: string
}

/**
 * How a course finds its student groups for a term.
 *
 * Education models two ways for a group to take a course. `Programme`: a
 * `Student Group` names a programme and a term, and a `Program Course` row says
 * the course is taught on that programme — which is how batch- and
 * activity-based groups take a course, and what this register always did.
 * `Course`: a course-based group names the course itself, in its own `course`
 * field. `Both` takes the groups either way finds. Which one is right is how a
 * school runs its groups, so it is the site's setting.
 */
export type GroupResolution = 'Programme' | 'Course' | 'Both'
export const GROUP_RESOLUTIONS: GroupResolution[] = [
  'Programme',
  'Course',
  'Both',
]

/**
 * What a `Leave` mark counts as.
 *
 * `Absent`: a session the student missed like any other, so it earns nothing
 * and still counts among the hours they could have had. `Excused`: the session
 * is left out of that student's total altogether — neither earned nor possible —
 * so a fortnight's sick leave does not read as a fortnight's truancy.
 */
export type LeaveCountsAs = 'Absent' | 'Excused'
export const LEAVE_RULES: LeaveCountsAs[] = ['Absent', 'Excused']

/** What `buildRegister` needs of the settings: the two rules that price a mark. */
export type RegisterRules = Pick<RegisterFields, 'late_credit' | 'leave_counts_as'>

/** A site that has named nothing. A late arrival is worth a full session there,
 *  the setting's own default — though without a late field there are none. */
export const NO_FIELDS: RegisterFields = {
  late_field: null,
  late_credit: 1,
  session_type_field: null,
  session_details_field: null,
  inactive_term_field: null,
  session_hours_field: null,
  group_resolution: 'Programme',
  leave_counts_as: 'Absent',
  course_plan: null,
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

/** A doctype's name: words, digits, spaces and the odd hyphen, which is what
 *  Frappe allows one to be called. Checked for the same reason as `fieldname`. */
const DOCTYPE = /^[a-z0-9][a-z0-9 _-]*$/i

/** The course plan as sent, or null unless every part of it is a name. */
function coursePlanFields(value: unknown): CoursePlanFields | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, unknown>
  const table_field = fieldname(raw.table_field)
  const type_column = fieldname(raw.type_column)
  const hours_column = fieldname(raw.hours_column)
  const table_doctype =
    typeof raw.table_doctype === 'string' && DOCTYPE.test(raw.table_doctype.trim())
      ? raw.table_doctype.trim()
      : null
  return table_field && table_doctype && type_column && hours_column
    ? { table_field, table_doctype, type_column, hours_column }
    : null
}

/** One of a rule's options, or its default for anything else. */
function option<Option extends string>(
  value: unknown,
  options: Option[],
  fallback: Option,
): Option {
  return options.includes(value as Option) ? (value as Option) : fallback
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
    session_hours_field: fieldname(raw?.session_hours_field),
    group_resolution: option(
      raw?.group_resolution,
      GROUP_RESOLUTIONS,
      NO_FIELDS.group_resolution,
    ),
    leave_counts_as: option(
      raw?.leave_counts_as,
      LEAVE_RULES,
      NO_FIELDS.leave_counts_as,
    ),
    course_plan: coursePlanFields(raw?.course_plan),
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
 * is not a student who was away. Excused earns nothing either, and is taken out
 * of the hours possible too — see `counts`.
 */
export function credit(mark: Mark, lateCredit: number): number {
  if (mark === PRESENT) return 1
  if (mark === LATE) return lateCredit
  return 0
}

/** Whether a mark's session counts among the hours a student could have had.
 *  Every mark but Excused, unmarked included: a session nobody has marked yet
 *  is still one the student was timetabled for. */
export function counts(mark: Mark): boolean {
  return mark !== EXCUSED
}

/**
 * Two stored fields as the one word the page uses.
 *
 * `Leave` is Education's third status and this register does not offer it. By
 * default it reads as absent, which is what the register always did; on a site
 * that counts leave as excused it reads as `Excused`, which the grid draws and
 * the footings leave out. Either way a mark made in the desk stays legible
 * here; it just cannot be made from here.
 */
export function toMark(
  status: string | null,
  late: number | null,
  leave: LeaveCountsAs = NO_FIELDS.leave_counts_as,
): Mark {
  if (status === LEAVE && leave === EXCUSED) return EXCUSED
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
  const status = mark === ABSENT ? ABSENT : mark === EXCUSED ? LEAVE : PRESENT
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
export function sessionHours(
  from: string | null,
  to: string | null,
  stated: number | null = null,
): number {
  if (stated !== null) return round(stated)
  const start = hoursInto(from)
  const end = hoursInto(to)
  if (start === null || end === null) return 0
  return round(Math.max(end - start, 0))
}

/**
 * A session's own hours, from the site's hours field, or null to work them out
 * from its times.
 *
 * Only a positive number counts as set. A Float or Int field reads as 0 on every
 * session nobody filled in — Frappe stores no "blank" for a number — so taking
 * 0 at its word would make every such session worth nothing the day the setting
 * is named. A session really worth no hours is one whose times say so.
 */
export function statedHours(value: unknown): number | null {
  const hours = typeof value === 'string' && value.trim() ? Number(value) : value
  return typeof hours === 'number' && Number.isFinite(hours) && hours > 0
    ? hours
    : null
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
  /** The hours the site's hours field gives the session, or null where it has
   *  none (or no such field) and the times decide. See `statedHours`. */
  stated_hours?: number | null
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
    ...[
      fields.session_type_field,
      fields.session_details_field,
      fields.session_hours_field,
    ].filter((name): name is string => Boolean(name)),
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
    stated_hours: fields.session_hours_field
      ? statedHours(row[fields.session_hours_field])
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
/* A course's plan                                                             */
/* -------------------------------------------------------------------------- */

/** One kind of session a course is taught in, and the hours planned for it. */
export interface PlanRow {
  session_type: string
  hours: number
}

/**
 * The plan's rows, as the register uses them, in the table's own order.
 *
 * A kind listed twice is one kind with both rows' hours: a table has no rule
 * against it, and two lines of fifteen hours mean thirty. A row naming no kind
 * is dropped, because no session could be matched to it. Hours that are not a
 * positive number count as none, so a row somebody has yet to fill in still
 * offers its kind without planning anything for it.
 */
export function planRows(rows: ApiRow[], plan: CoursePlanFields): PlanRow[] {
  const byType = new Map<string, number>()
  for (const row of rows) {
    const sessionType = String(row[plan.type_column] ?? '').trim()
    if (!sessionType) continue
    const hours = statedHours(row[plan.hours_column]) ?? 0
    byType.set(sessionType, (byType.get(sessionType) ?? 0) + hours)
  }
  return [...byType].map(([session_type, hours]) => ({
    session_type,
    hours: round(hours),
  }))
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
  /** Hours the course's plan sets for this kind of session, or null where it
   *  sets none: no plan, or a kind the plan does not list. */
  planned: number | null
  /** Hours earned, per student. Less than `scheduled` for anybody who missed a
   *  session or arrived late at one. */
  credited: Record<string, number>
  /** Hours each student could have earned: `scheduled`, less any session they
   *  were excused. The same as `scheduled` for everybody on a site that reads
   *  leave as absent. */
  possible: Record<string, number>
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
  /** The hours the course's plan sets in all, or null where it has no plan.
   *  Every group taking the course is meant to be taught all of it. */
  planned: number | null
  credited: Record<string, number>
  possible: Record<string, number>
}

export interface Register {
  groups: GroupRegister[]
  /** The course's plan, empty where it has none. */
  plan: PlanRow[]
}

export const EMPTY_REGISTER: Register = { groups: [], plan: [] }

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
 *
 * `rules` are the two settings that price a mark: what a late arrival earns and
 * what leave counts as.
 *
 * `plan` is the course's plan (see `planRows`), and puts planned hours beside
 * scheduled ones. Every kind it lists gets a block in every group, sessions or
 * none, because a kind of session a group has not had yet is exactly what a
 * plan is there to show.
 */
export function buildRegister(
  rows: {
    groups: GroupRow[]
    students: StudentRow[]
    schedules: ScheduleRow[]
    marks: MarkRow[]
    plan?: PlanRow[]
  },
  rules: RegisterRules,
): Register {
  const plan = rows.plan ?? []
  const lateCredit = rules.late_credit
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
    marks[row.student] = {
      name: row.name,
      mark: toMark(row.status, row.late, rules.leave_counts_as),
    }
    bySession.set(row.course_schedule, marks)
  }

  const sessions = rows.schedules.map<Session>((row) => ({
    name: row.name,
    group: row.student_group,
    schedule_date: row.schedule_date,
    from_time: row.from_time,
    to_time: row.to_time,
    hours: sessionHours(row.from_time, row.to_time, row.stated_hours ?? null),
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
        plan,
      ),
    ),
    plan,
  }
}

function buildGroup(
  row: GroupRow,
  students: GroupStudent[],
  sessions: Session[],
  lateCredit: number,
  plan: PlanRow[],
): GroupRegister {
  const planned = new Map(plan.map((line) => [line.session_type, line.hours]))
  const blocks = sessionTypes(sessions, plan).map((sessionType) =>
    buildBlock(
      sessionType,
      sessions.filter((session) => session.session_type === sessionType),
      students,
      lateCredit,
      sessionType === null ? null : (planned.get(sessionType) ?? null),
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
    planned: plan.length
      ? round(plan.reduce((total, line) => total + line.hours, 0))
      : null,
    credited: sumBlocks(blocks, students, 'credited'),
    possible: sumBlocks(blocks, students, 'possible'),
  }
}

/** Each student's figure, added up across the blocks. */
function sumBlocks(
  blocks: Block[],
  students: GroupStudent[],
  key: 'credited' | 'possible',
): Record<string, number> {
  return Object.fromEntries(
    students.map((student) => [
      student.student,
      round(
        blocks.reduce(
          (total, block) => total + (block[key][student.student] ?? 0),
          0,
        ),
      ),
    ]),
  )
}

/**
 * The kinds of session a group had or is planned to have, in the order they
 * are drawn.
 *
 * The course's plan first, in the plan's own order, whether the group has had
 * any of each or not. Then any other kind it had, alphabetically, and the
 * untyped block last. The register this replaced sorted the school's own
 * vocabulary by prefixing anything beginning "Faculty" with an exclamation mark
 * before comparing, which put seminars at the top of the page — correct for one
 * school's four session types and meaningless for a fifth or for anybody
 * else's. A plan is the school saying what order its kinds come in; without
 * one, the field is free text with no order to read off it, and alphabetical is
 * the one a reader can predict.
 */
function sessionTypes(sessions: Session[], plan: PlanRow[]): (string | null)[] {
  const planned = plan.map((line) => line.session_type)
  const found = new Set(sessions.map((session) => session.session_type))
  const others = [...found]
    .filter((name): name is string => Boolean(name) && !planned.includes(name!))
    .sort()
  return [...planned, ...others, ...(found.has(null) ? [null] : [])]
}

/**
 * The sessions of one kind, and what they came to.
 *
 * `scheduled` is what was timetabled and `credited` is what each student earned
 * of it — the same figure only for somebody who was at all of it on time, which
 * is the comparison the block exists to make. `possible` is what each student
 * could have earned: `scheduled` less what they were excused. `planned` is what
 * the course's plan sets for the kind, where it sets anything.
 */
function buildBlock(
  sessionType: string | null,
  sessions: Session[],
  students: GroupStudent[],
  lateCredit: number,
  planned: number | null,
): Block {
  return {
    session_type: sessionType,
    sessions,
    scheduled: round(
      sessions.reduce((total, session) => total + session.hours, 0),
    ),
    planned,
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
    possible: Object.fromEntries(
      students.map((student) => [
        student.student,
        round(
          sessions.reduce(
            (total, session) =>
              counts(session.marks[student.student]?.mark ?? UNMARKED)
                ? total + session.hours
                : total,
            0,
          ),
        ),
      ]),
    ),
  }
}

/* -------------------------------------------------------------------------- */
/* Reading every row                                                           */
/* -------------------------------------------------------------------------- */

/** Rows asked for per request. Big enough that a term's register is a handful
 *  of requests, small enough that no one response is a burden. */
export const PAGE_SIZE = 500

/** The most rows one list is read to. Not a limit any school's register should
 *  meet — it is there so that a runaway list stops rather than paging for ever,
 *  and a list that reaches it says so on the page (`complete: false`). */
export const MAX_ROWS = 20000

/** A list read through, and whether it is all of it. */
export interface Paged<Row> {
  rows: Row[]
  complete: boolean
}

/**
 * Every row of a list, one page at a time.
 *
 * `document_list` and `frappe.client.get_list` both default to twenty rows and
 * have no "all", and a single fixed limit silently drops whatever is past it —
 * a register with the last week of term missing looks exactly like one where
 * nothing was timetabled. So a list is read until a page comes back short.
 *
 * At `maxRows` it stops and asks for one row more: none, and the list really
 * was that long; one, and it was cut short, which is `complete: false` for the
 * page to warn about rather than to hide.
 */
export async function pageThrough<Row>(
  fetchPage: (start: number, length: number) => Promise<Row[]>,
  pageSize = PAGE_SIZE,
  maxRows = MAX_ROWS,
): Promise<Paged<Row>> {
  const rows: Row[] = []
  for (;;) {
    const length = Math.min(pageSize, maxRows - rows.length)
    const page = await fetchPage(rows.length, length)
    rows.push(...page)
    if (page.length < length) return { rows, complete: true }
    if (rows.length >= maxRows) {
      const beyond = await fetchPage(rows.length, 1)
      return { rows, complete: beyond.length === 0 }
    }
  }
}

/* -------------------------------------------------------------------------- */
/* A teacher's own courses                                                     */
/* -------------------------------------------------------------------------- */

/**
 * The terms the course shortcuts cover: the current term, the one before it,
 * and every term after it that has been created, oldest first.
 *
 * "Current" is Education Settings' current term where it names one the picker
 * has. Otherwise it is the term today falls in, or failing that the last one
 * to have started: a school between terms is still teaching the one it just
 * finished, as far as its registers go. Terms starting the same day as the
 * current one count as current too.
 */
export function shortcutTerms(
  terms: TermRow[],
  current: string | null,
  today: string,
): string[] {
  const dated = terms
    .filter((row): row is TermRow & { term_start_date: string } =>
      Boolean(row.term_start_date),
    )
    .sort((a, b) =>
      a.term_start_date < b.term_start_date
        ? -1
        : a.term_start_date > b.term_start_date
          ? 1
          : a.name < b.name
            ? -1
            : 1,
    )
  if (!dated.length) return []
  const started = dated.filter((row) => row.term_start_date <= today)
  const now =
    dated.find((row) => row.name === current) ??
    started.find(
      (row) => !row.term_end_date || row.term_end_date >= today,
    ) ??
    started.at(-1) ??
    null
  if (!now) return dated.map((row) => row.name)
  const from = now.term_start_date
  const before = dated.filter((row) => row.term_start_date < from).at(-1)
  return [
    ...(before ? [before.name] : []),
    ...dated.filter((row) => row.term_start_date >= from).map((row) => row.name),
  ]
}

/** One term's row of course shortcuts. */
export interface ShortcutRow {
  term: string
  courses: CourseRow[]
}

/** A `Student Group` as the shortcuts read it: which term, and how it reaches
 *  its courses. */
export interface ShortcutGroupRow {
  name: string
  academic_term: string
  program: string | null
  course: string | null
}

/**
 * A teacher's own courses in each of the shortcut terms.
 *
 * A course is theirs in a term if either:
 *
 * - they taught a session of it in that term: `Course Schedule.instructor` is
 *   one of `mine`, which is the record of who actually stood in the room; or
 * - it is taught in that term at all, and its `default_instructor` is one of
 *   `mine`. This is what puts a term on the list before anything in it is
 *   timetabled, which is the only way a term that has just been created can
 *   have any shortcuts. "Taught in that term" follows the site's
 *   `GroupResolution`, as the register itself does.
 *
 * Terms with none of the teacher's courses are left out. Courses are in name
 * order, as the picker has them.
 */
export function instructorShortcuts(input: {
  terms: string[]
  mine: string[]
  courses: CourseRow[]
  groups: ShortcutGroupRow[]
  /** The teacher's own sessions in those terms, one row per course and group. */
  taught: { course: string; student_group: string }[]
  /** `Program Course` rows for the groups' programmes. */
  programCourses: { parent: string; course: string }[]
  resolution: GroupResolution
}): ShortcutRow[] {
  const termOf = new Map(input.groups.map((row) => [row.name, row.academic_term]))
  const byName = new Map(input.courses.map((row) => [row.name, row]))
  const defaults = new Set(
    input.courses
      .filter(
        (row) => row.default_instructor && input.mine.includes(row.default_instructor),
      )
      .map((row) => row.name),
  )
  const viaProgramme = input.resolution !== 'Course'
  const viaCourse = input.resolution !== 'Programme'

  return input.terms
    .map((term) => {
      const found = new Set<string>()
      for (const row of input.taught) {
        if (termOf.get(row.student_group) === term) found.add(row.course)
      }
      for (const group of input.groups) {
        if (group.academic_term !== term) continue
        if (viaCourse && group.course && defaults.has(group.course)) found.add(group.course)
        if (viaProgramme && group.program) {
          for (const row of input.programCourses) {
            if (row.parent === group.program && defaults.has(row.course)) found.add(row.course)
          }
        }
      }
      const courses = [...found]
        .sort()
        .map(
          (name) =>
            byName.get(name) ?? {
              name,
              course_name: null,
              abbreviation: null,
              default_instructor: null,
            },
        )
      return { term, courses }
    })
    .filter((row) => row.courses.length)
}

/* -------------------------------------------------------------------------- */
/* Which groups take a course                                                  */
/* -------------------------------------------------------------------------- */

/** The two reads that find a course's groups, supplied by `attendance.ts`. */
export interface GroupReads {
  /** The programmes a `Program Course` row puts the course on. */
  programmes: (course: string) => Promise<string[]>
  /** The term's groups matching extra filters. */
  groups: (filters: unknown[][]) => Promise<GroupRow[]>
}

/**
 * The student groups that take a course in a term, found the way the site says.
 *
 * See `GroupResolution`. With `Both`, a group either way finds is listed once.
 * Sorted by name, as the single read always was.
 */
export async function resolveGroups(
  resolution: GroupResolution,
  term: string,
  course: string,
  reads: GroupReads,
): Promise<GroupRow[]> {
  const termFilter = ['academic_term', '=', term]
  const found: GroupRow[][] = []
  if (resolution === 'Programme' || resolution === 'Both') {
    const programmes = [...new Set(await reads.programmes(course))]
    if (programmes.length)
      found.push(await reads.groups([termFilter, ['program', 'in', programmes]]))
  }
  if (resolution === 'Course' || resolution === 'Both') {
    found.push(await reads.groups([termFilter, ['course', '=', course]]))
  }
  const byName = new Map<string, GroupRow>()
  for (const row of found.flat()) if (!byName.has(row.name)) byName.set(row.name, row)
  return [...byName.values()].sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  )
}
