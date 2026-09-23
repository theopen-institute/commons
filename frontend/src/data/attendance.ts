import { computed, toValue, ref, type MaybeRefOrGetter, type Ref } from 'vue'
import { useCall } from 'frappe-ui'
import {
  buildRegister,
  EMPTY_REGISTER,
  markFields,
  type CourseRow,
  type GroupRow,
  type Mark,
  type MarkRow,
  type Register,
  type ScheduleRow,
  type StudentRow,
  type TermRow,
} from './attendanceRegister'

/**
 * The attendance register's reads and writes — all of them through APIs Frappe
 * already ships.
 *
 * This app adds no endpoint of its own for any of it, which is the point rather
 * than a boast. Everything below goes through either the REST document API or
 * `frappe.client`, so role permissions, User Permissions and this app's gate in
 * `commons.safer_permissions` all apply to every row read and every row
 * written, without this app restating one of them. That is the same argument
 * the request sections make (see `frontend/README.md`, *Permissions*), and the
 * register had to be brought back into line with it: an earlier version
 * assembled the whole page in one custom endpoint built on `frappe.get_all`,
 * which is `ignore_permissions=True`, and so answered from rows the reader was
 * never entitled to see.
 *
 * Two of Frappe's own shapes are used rather than one, and the split is not
 * arbitrary:
 *
 * * `/api/v2/document/<doctype>` for ordinary doctypes. This is what
 *   `data/requests/section.ts` uses and what the app's README points at.
 * * `frappe.client.get_list` for the two child tables — `Program Course` and
 *   `Student Group Student`. The document API cannot read a child table
 *   usefully: `document_list` never passes a `parent_doctype` to the query
 *   engine, so a child doctype is permission-checked against its own (empty)
 *   permissions and every requested field is stripped, leaving a list of bare
 *   `name`s. `frappe.client.get_list` takes `parent` and is the API the desk
 *   itself uses for the same job.
 *
 * Writes use `frappe.client` throughout: `insert`, `insert_many`, `set_value`
 * and `delete` all run the full document lifecycle — validation, hooks, the
 * site's own Server Scripts and the permission check — and, unlike the REST
 * document routes, each lives at a fixed URL, which is what lets them be plain
 * `useCall`s rather than a URL rebuilt per document.
 */

const DOCUMENT = '/api/v2/document'
const CLIENT = '/api/v2/method/frappe.client'

/**
 * How many rows a list may return.
 *
 * `document_list` defaults to 20 and there is no "all" — `limit: 0` asks for
 * nought, not everything — so every read below says how many it will take. The
 * numbers are an order of magnitude above anything a school produces: a term
 * has tens of sessions, not hundreds, and a group has tens of students.
 */
const PAGE = {
  terms: 200,
  courses: 200,
  programs: 200,
  groups: 200,
  students: 500,
  sessions: 1000,
  marks: 5000,
  sessionTypes: 200,
}

interface ListParams {
  fields: string
  filters?: string
  order_by?: string
  group_by?: string
  limit: number
}

/** A list off the REST document API, permissions applied. */
function documentList<Row>(doctype: string) {
  return useCall<Row[], ListParams>({
    url: `${DOCUMENT}/${encodeURIComponent(doctype)}`,
    immediate: false,
  })
}

interface ChildListParams {
  doctype: string
  parent: string
  fields: string
  filters?: string
  order_by?: string
  limit_page_length: number
}

/** A child table's rows. See the module comment for why this is not the
 *  document API. */
function childList<Row>() {
  return useCall<Row[], ChildListParams>({
    url: `${CLIENT}.get_list`,
    immediate: false,
  })
}

export type { Mark, Register }
export {
  courseChip,
  EMPTY_REGISTER,
  formatHours,
  formatTime,
  fromTimeInput,
  markChanges,
  MARKS,
  sessionTypeLabel,
  toTimeInput,
  UNTYPED_SESSION,
  type Block,
  type CourseRow,
  type GroupRegister,
  type GroupStudent,
  type Session,
  type TermRow,
} from './attendanceRegister'

/* -------------------------------------------------------------------------- */
/* Who the register is for                                                     */
/* -------------------------------------------------------------------------- */

interface PermissionAnswer {
  has_permission: boolean
}

function permissionCall(doctype: string, perm: string) {
  return useCall<PermissionAnswer, { doctype: string; docname: string; perm_type: string }>({
    url: `${CLIENT}.has_permission`,
    params: { doctype, docname: '', perm_type: perm },
  })
}

/**
 * Whether marking attendance is this reader's to do.
 *
 * Write on `Student Attendance`, and deliberately not read. `Student` and
 * `Guardian` both hold read — rightly, because a student may see their own
 * record in the desk, where the list is filtered to it. The register is the
 * opposite shape: one term of one course with every student in the group across
 * the top. The people who mark it are the people it was written for.
 *
 * An empty `docname` asks about the doctype rather than about a document, which
 * is what `frappe.has_permission` does with no doc.
 */
const canMarkCall = permissionCall('Student Attendance', 'write')

/** Whether new sessions may be timetabled from here. Separable from marking on
 *  purpose: an assistant who records who turned up need not be somebody who may
 *  add a class to the timetable. */
const canScheduleCall = permissionCall('Course Schedule', 'create')

export const attendanceCan = computed(() => ({
  mark: Boolean(canMarkCall.data?.has_permission),
  schedule: Boolean(canScheduleCall.data?.has_permission),
}))

/** Whether both answers are in — settled or refused, not merely arrived. A call
 *  that fails never sets `data`, and a sidebar waiting on that holds a gap for
 *  ever. */
export const attendancePermissionsLoaded = computed(
  () => canMarkCall.isFinished && canScheduleCall.isFinished,
)

/**
 * What the sidebar row waits on.
 *
 * Only the permission half. Whether the site has a register at all is the
 * server's answer and is already in the shell: `commons.shell.pages.available`
 * drops the row from every workspace on a site with no education module, so a
 * row that is there is a register that exists. See `PAGES` in `data/shell.ts`.
 */
export const attendanceGate = {
  visible: computed(() => attendanceCan.value.mark),
  resolved: attendancePermissionsLoaded,
}

/* -------------------------------------------------------------------------- */
/* The pickers                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The terms, courses and session types the pickers offer.
 *
 * Fetched once and not per filter change: none of it depends on what is
 * selected, and re-sending eight courses every time somebody changes course is
 * how a page ends up reloading what nobody touched.
 */
export function useAttendancePickers() {
  const terms = documentList<TermRow>('Academic Term')
  const courses = documentList<CourseRow>('Course')
  const sessionTypes = documentList<{ custom_session_type: string | null }>('Course Schedule')
  const currentTerm = useCall<string | null, { doctype: string; field: string }>({
    url: `${CLIENT}.get_single_value`,
    params: { doctype: 'Education Settings', field: 'current_academic_term' },
    immediate: false,
  })

  async function load() {
    await Promise.all([
      // `custom_inactive` is the site's way of retiring a term that was run
      // once and is not run again. Retired terms are dropped rather than shown
      // greyed: the picker is for choosing. Nothing stops an old register being
      // read, because the address carries the term.
      terms.submit({
        fields: JSON.stringify(['name', 'term_start_date', 'term_end_date']),
        filters: JSON.stringify([['custom_inactive', '=', 0]]),
        order_by: 'term_start_date desc',
        limit: PAGE.terms,
      }),
      courses.submit({
        fields: JSON.stringify(['name', 'course_name', 'abbreviation', 'default_instructor']),
        order_by: 'name asc',
        limit: PAGE.courses,
      }),
      // The kinds of session this school actually runs, read off what has been
      // scheduled rather than declared anywhere — `custom_session_type` is free
      // text on purpose. `group_by` is how the document API says DISTINCT.
      sessionTypes.submit({
        fields: JSON.stringify(['custom_session_type']),
        group_by: 'custom_session_type',
        order_by: 'custom_session_type asc',
        limit: PAGE.sessionTypes,
      }),
      // Where the page opens when the address names no term. A reader without
      // permission on `Education Settings` gets a refusal here and the first
      // term in the list instead, which is why this is not awaited with the
      // others' success.
      currentTerm.submit({ doctype: 'Education Settings', field: 'current_academic_term' }),
    ])
  }

  return {
    load,
    terms: computed(() => terms.data ?? []),
    courses: computed(() => courses.data ?? []),
    sessionTypes: computed(() =>
      (sessionTypes.data ?? [])
        .map((row) => (row.custom_session_type ?? '').trim())
        .filter(Boolean),
    ),
    currentTerm: computed(() => currentTerm.data ?? null),
    loaded: computed(() => terms.isFinished && courses.isFinished),
    error: computed(() => terms.error ?? courses.error ?? null),
  }
}

/* -------------------------------------------------------------------------- */
/* The register                                                                */
/* -------------------------------------------------------------------------- */

/** The four lists a register is built from, kept as they arrived.
 *
 *  Held rather than discarded because a mark changed on screen is a mark
 *  changed here: the register below is computed from these, so patching one row
 *  re-foots its block and its group without another round of reads. That is
 *  only possible now that the arithmetic is in the browser — the version that
 *  totalled on the server had to re-fetch the whole page after every click. */
export interface RegisterRows {
  groups: GroupRow[]
  students: StudentRow[]
  schedules: ScheduleRow[]
  marks: MarkRow[]
}

const NO_ROWS: RegisterRows = { groups: [], students: [], schedules: [], marks: [] }

/**
 * One term of one course, in four rounds of reads.
 *
 * They are chained because each genuinely depends on the last: a course reaches
 * its groups only through `Program Course`, sessions are read for the groups
 * that came back, and marks for the sessions that came back. Students and
 * sessions do not depend on each other and go together.
 *
 * A custom endpoint would make this one round trip and has to be refused: see
 * the module comment.
 */
export function useAttendanceRegister() {
  const programs = childList<{ parent: string }>()
  const groups = documentList<GroupRow>('Student Group')
  const students = childList<StudentRow>()
  const schedules = documentList<ScheduleRow>('Course Schedule')
  const marks = documentList<MarkRow>('Student Attendance')

  const rows = ref<RegisterRows>(NO_ROWS) as Ref<RegisterRows>
  const register = computed<Register>(() => buildRegister(rows.value))
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<Error | null>(null)

  async function load(term: string, course: string) {
    if (!term || !course) {
      rows.value = NO_ROWS
      loaded.value = false
      return
    }
    loading.value = true
    error.value = null
    try {
      rows.value = await read(term, course)
      loaded.value = true
    } catch (problem) {
      error.value = problem as Error
      rows.value = NO_ROWS
      loaded.value = true
    } finally {
      loading.value = false
    }
  }

  /**
   * Record a mark locally, as the server has just been told it.
   *
   * Called twice per click in the ordinary case — once to show the new mark
   * before the round trip, once with the id the server gave a new row — and a
   * third time, back to the old value, when the write is refused.
   */
  function setMark(session: string, student: string, mark: Mark, name = '') {
    const rest = rows.value.marks.filter(
      (row) => !(row.course_schedule === session && row.student === student),
    )
    if (mark) {
      const previous = rows.value.marks.find(
        (row) => row.course_schedule === session && row.student === student,
      )
      rest.push({
        name: name || previous?.name || '',
        course_schedule: session,
        student,
        ...markFields(mark),
      })
    }
    rows.value = { ...rows.value, marks: rest }
  }

  /** The `Student Attendance` id behind one cell, or empty where there is no
   *  row yet. What a change or a deletion is addressed to. */
  function markDocument(session: string, student: string): string {
    return (
      rows.value.marks.find(
        (row) => row.course_schedule === session && row.student === student,
      )?.name ?? ''
    )
  }

  async function read(term: string, course: string): Promise<RegisterRows> {
    // Which programmes teach this course. The join Education actually models: a
    // `Student Group` names a programme and a term, and a `Program Course` row
    // is what says the course is taught on that programme. A group's own
    // `course` field is only ever set for a course-based group, and the schools
    // this was written for run batch- and activity-based ones.
    const programRows = await fetchRows(programs, {
      doctype: 'Program Course',
      parent: 'Program',
      fields: JSON.stringify(['parent']),
      filters: JSON.stringify([['course', '=', course]]),
      limit_page_length: PAGE.programs,
    })
    const programNames = [...new Set(programRows.map((row) => row.parent))]
    if (!programNames.length) return NO_ROWS

    // Disabled groups are left in deliberately. This page is as much the record
    // of a term that has finished as it is the place to add to one that has
    // not, and a group is usually disabled precisely because its term is over.
    const groupRows = await fetchRows(groups, {
      fields: JSON.stringify(['name', 'student_group_name', 'program', 'disabled']),
      filters: JSON.stringify([
        ['academic_term', '=', term],
        ['program', 'in', programNames],
      ]),
      order_by: 'name asc',
      limit: PAGE.groups,
    })
    const groupNames = groupRows.map((row) => row.name)
    if (!groupNames.length) return NO_ROWS

    const [studentRows, scheduleRows] = await Promise.all([
      // Ordered by name rather than by roll number, because the register is
      // read across: a teacher looks along the top for the student in front of
      // them. Inactive members are dropped — a student who has left the group
      // is not absent from its sessions, and a column of blanks reads as though
      // they were.
      fetchRows(students, {
        doctype: 'Student Group Student',
        parent: 'Student Group',
        fields: JSON.stringify(['parent', 'student', 'student_name']),
        filters: JSON.stringify([
          ['parent', 'in', groupNames],
          ['active', '=', 1],
        ]),
        order_by: 'student_name asc',
        limit_page_length: PAGE.students,
      }),
      fetchRows(schedules, {
        fields: JSON.stringify([
          'name',
          'student_group',
          'schedule_date',
          'from_time',
          'to_time',
          'custom_session_type',
          'custom_session_details',
        ]),
        filters: JSON.stringify([
          ['student_group', 'in', groupNames],
          ['course', '=', course],
        ]),
        order_by: 'schedule_date asc, from_time asc',
        limit: PAGE.sessions,
      }),
    ])

    const sessionNames = scheduleRows.map((row) => row.name)
    // Cancelled marks are dropped: an amended `Student Attendance` leaves the
    // cancelled original behind, carrying the same student and session.
    const markRows = sessionNames.length
      ? await fetchRows(marks, {
          fields: JSON.stringify([
            'name',
            'course_schedule',
            'student',
            'status',
            'custom_late',
          ]),
          filters: JSON.stringify([
            ['course_schedule', 'in', sessionNames],
            ['docstatus', '!=', 2],
          ]),
          limit: PAGE.marks,
        })
      : []

    return {
      groups: groupRows,
      students: studentRows,
      schedules: scheduleRows,
      marks: markRows,
    }
  }

  return { load, register, setMark, markDocument, loading, loaded, error }
}

/**
 * Run one of the reads above, and throw rather than return nothing.
 *
 * `useCall.submit` resolves null on failure and leaves the reason on the call.
 * A chain of reads has to stop at the first refusal rather than carry on with
 * an empty list and draw a register that is missing half a term.
 */
async function fetchRows<Row, Params extends object>(
  call: { submit: (params: Params) => Promise<Row[] | null>; error: Error | null },
  params: Params,
): Promise<Row[]> {
  const rows = await call.submit(params)
  if (rows === null) throw call.error ?? new Error('That could not be loaded.')
  return rows
}

/* -------------------------------------------------------------------------- */
/* Writing                                                                     */
/* -------------------------------------------------------------------------- */

/** `frappe.client.insert` — one new document, through the full lifecycle. */
export function useInsertDocument<Result = { name: string }>() {
  return useCall<Result, { doc: string }>({
    url: `${CLIENT}.insert`,
    method: 'POST',
    immediate: false,
  })
}

/**
 * `frappe.client.insert_many` — a roster of new documents in one request.
 *
 * One request is one transaction in Frappe, which is the whole reason this is
 * here rather than a loop of `insert`: marking twenty students present is
 * either recorded or not, instead of leaving a class half marked with no way to
 * tell from the page which half.
 */
export function useInsertDocuments() {
  return useCall<string[], { docs: string }>({
    url: `${CLIENT}.insert_many`,
    method: 'POST',
    immediate: false,
  })
}

/** `frappe.client.set_value` — a dict of fields onto one document, saved. */
export function useSetValue() {
  return useCall<
    { name: string },
    { doctype: string; name: string; fieldname: string }
  >({ url: `${CLIENT}.set_value`, method: 'POST', immediate: false })
}

/** `frappe.client.delete`. */
export function useDeleteDocument() {
  return useCall<string, { doctype: string; name: string }>({
    url: `${CLIENT}.delete`,
    method: 'POST',
    immediate: false,
  })
}

/**
 * Run a write, and say whether it landed.
 *
 * Not "did `submit` resolve something". `submit` resolves the response's `data`,
 * and `frappe.client.delete` answers with nothing at all — so a deletion that
 * worked and one that was refused both come back null, and reading the return
 * value as a success flag silently undoes every clearing of a mark on screen
 * while the row really is gone from the database.
 *
 * The call's own `error` is what tells them apart. `useFetch` clears it at the
 * start of every request, so after the await it is this request's answer and
 * not the last one's.
 */
export async function write<Result, Params extends object>(
  call: { submit: (params: Params) => Promise<Result | null>; error: Error | null },
  params: Params,
): Promise<{ ok: boolean; data: Result | null }> {
  const data = await call.submit(params)
  return { ok: !call.error, data }
}

/* -------------------------------------------------------------------------- */
/* How a mark reads                                                            */
/* -------------------------------------------------------------------------- */

/**
 * A tick, a clock and a cross rather than three coloured blocks: colour alone
 * is not a distinction everybody can make, and the grid is read at a glance by
 * whoever is covering the class. The colours are there too, because for
 * everybody else they are what makes a row of absences visible from across the
 * page. Shared by the grid and the session's details so the two never disagree
 * about what a mark looks like.
 */
export const MARK_GLYPHS: Record<Mark, string> = {
  Present: 'lucide-check',
  Late: 'lucide-clock',
  Absent: 'lucide-x',
  '': '',
}

export const MARK_COLOURS: Record<Mark, string> = {
  Present: 'bg-surface-green-2 text-ink-green-3',
  Late: 'bg-surface-amber-2 text-ink-amber-3',
  Absent: 'bg-surface-red-2 text-ink-red-3',
  '': 'bg-surface-white',
}

export const MARK_LABELS: Record<Mark, string> = {
  Present: 'Present',
  Late: 'Late',
  Absent: 'Absent',
  '': 'Not marked',
}

export const STUDENT_ATTENDANCE = 'Student Attendance'
export const COURSE_SCHEDULE = 'Course Schedule'

/** The document a new mark is, ready for `insert`. */
export function newMark(session: string, student: string, mark: Mark) {
  return { doctype: STUDENT_ATTENDANCE, course_schedule: session, student, ...markFields(mark) }
}

/** The fields a changed mark sets. */
export function markValues(mark: Mark) {
  return markFields(mark)
}

/** Whether the term picker's selection contains a date — what bounds the
 *  session dialog's date field. */
export function termBounds(
  terms: MaybeRefOrGetter<TermRow[]>,
  term: MaybeRefOrGetter<string>,
) {
  const found = computed(() => toValue(terms).find((row) => row.name === toValue(term)))
  return {
    start: computed(() => found.value?.term_start_date ?? null),
    end: computed(() => found.value?.term_end_date ?? null),
  }
}
