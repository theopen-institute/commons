import { computed, toValue, ref, type MaybeRefOrGetter, type Ref } from 'vue'
import { useCall } from 'frappe-ui'
import {
  buildRegister,
  EMPTY_REGISTER,
  markFieldList,
  markFields,
  markRow,
  pageThrough,
  registerFields,
  resolveGroups,
  scheduleFieldList,
  scheduleRow,
  type ApiRow,
  type CourseRow,
  type GroupRow,
  type Mark,
  type MarkRow,
  type Paged,
  type Register,
  type RegisterFields,
  type ScheduleRow,
  type StudentRow,
  type TermRow,
} from './attendanceRegister'
import { permissionCall } from './permissions'

/**
 * The attendance register's reads and writes — all of them through APIs Frappe
 * already ships.
 *
 * This app adds no endpoint of its own for any of it, which is the point rather
 * than a boast. (It asks one question of its own, which of the site's fields
 * to read — see `attendanceFields` — and that answer is fieldnames, not rows.)
 * Everything below goes through either the REST document API or
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
 * How many rows a list returns: all of them.
 *
 * `document_list` defaults to 20 and there is no "all" — `limit: 0` asks for
 * nought, not everything. Every read used to name a cap instead (500 students,
 * 1,000 sessions, 5,000 marks), and a list past its cap was cut short with
 * nothing on the page to say so. Now every read is paged through to the end by
 * `fetchRows` (see `pageThrough`), a page at a time, and a list that reaches
 * the safety ceiling is reported in `incomplete` for the page to warn about.
 * The page parameters are filled in there, so the reads below name none.
 */
interface ListParams {
  fields: string
  filters?: string
  order_by?: string
  group_by?: string
  start?: number
  limit?: number
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
  limit_start?: number
  limit_page_length?: number
}

/** A child table's rows. See the module comment for why this is not the
 *  document API. */
function childList<Row>() {
  return useCall<Row[], ChildListParams>({
    url: `${CLIENT}.get_list`,
    immediate: false,
  })
}

export type { Mark, Register, RegisterFields }
export {
  courseChip,
  EMPTY_REGISTER,
  formatHours,
  formatTime,
  fromTimeInput,
  markChanges,
  marksOffered,
  MAX_ROWS,
  sessionFields,
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
/* Which of the site's fields                                                  */
/* -------------------------------------------------------------------------- */

const fieldsCall = useCall<Partial<RegisterFields>>({
  url: '/api/v2/method/commons.attendance_register.register.register_fields',
  immediate: false,
})

/**
 * The site's fields for what Education does not record, as the Attendance
 * tab of Commons Settings names them. Until they are in, the register reads as a site that named none
 * — but nothing reads or writes before they are: every read below waits on
 * `loadAttendanceFields`, since a register read without the late field would
 * show every late arrival as on time, and a mark saved from it would clear the
 * flag.
 */
export const attendanceFields = computed(() => registerFields(fieldsCall.data))

let fieldsLoaded: Promise<RegisterFields> | null = null

/** Ask once per page load; a refusal is asked again next time rather than kept. */
export function loadAttendanceFields(): Promise<RegisterFields> {
  fieldsLoaded ??= fieldsCall.submit().then((data) => {
    if (data === null || fieldsCall.error) {
      fieldsLoaded = null
      throw (
        fieldsCall.error ??
        new Error("The register's settings could not be loaded.")
      )
    }
    return attendanceFields.value
  })
  return fieldsLoaded
}

/* -------------------------------------------------------------------------- */
/* Who the register is for                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Whether marking attendance is this reader's to do.
 *
 * Write on `Student Attendance`, and deliberately not read. `Student` and
 * `Guardian` both hold read — rightly, because a student may see their own
 * record in the desk, where the list is filtered to it. The register is the
 * opposite shape: one term of one course with every student in the group across
 * the top. The people who mark it are the people it was written for.
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
 *  that fails never sets `data`, and a page waiting on that shows its skeleton
 *  for ever. */
export const attendancePermissionsLoaded = computed(
  () => canMarkCall.isFinished && canScheduleCall.isFinished,
)

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
  const sessionTypes = documentList<ApiRow>('Course Schedule')
  const currentTerm = useCall<
    string | null,
    { doctype: string; field: string }
  >({
    url: `${CLIENT}.get_single_value`,
    params: { doctype: 'Education Settings', field: 'current_academic_term' },
    immediate: false,
  })

  const fieldsError = ref<Error | null>(null)
  const readError = ref<Error | null>(null)
  const termRows = ref<TermRow[]>([])
  const courseRows = ref<CourseRow[]>([])
  const typeRows = ref<ApiRow[]>([])
  const listsLoaded = ref(false)
  /** The pickers' lists that reached the safety ceiling. */
  const incomplete = ref<string[]>([])

  /** One picker's list, read through to the end, into its ref. A refusal is
   *  kept to show, and leaves the list empty rather than stopping the others. */
  async function readInto<Row>(
    target: Ref<Row[]>,
    label: string,
    reading: Promise<Paged<Row>>,
  ) {
    try {
      const { rows, complete } = await reading
      target.value = rows
      if (!complete) incomplete.value = [...incomplete.value, label]
    } catch (problem) {
      if (problem instanceof Cancelled) return
      target.value = []
      readError.value ??= problem as Error
    }
  }

  async function load() {
    let fields: RegisterFields
    try {
      fields = await loadAttendanceFields()
      fieldsError.value = null
    } catch (problem) {
      fieldsError.value = problem as Error
      return
    }
    readError.value = null
    incomplete.value = []
    const typeField = fields.session_type_field
    await Promise.all([
      // The inactive-term field, where the site has one, is how it retires a
      // term that was run once and is not run again. Retired terms are dropped
      // rather than shown greyed: the picker is for choosing. Nothing stops an
      // old register being read, because the address carries the term.
      readInto(
        termRows,
        'terms',
        fetchRows(terms, 'document', {
          fields: JSON.stringify(['name', 'term_start_date', 'term_end_date']),
          ...(fields.inactive_term_field
            ? {
                filters: JSON.stringify([[fields.inactive_term_field, '=', 0]]),
              }
            : {}),
          order_by: 'term_start_date desc, name asc',
        }),
      ),
      readInto(
        courseRows,
        'courses',
        fetchRows(courses, 'document', {
          fields: JSON.stringify([
            'name',
            'course_name',
            'abbreviation',
            'default_instructor',
          ]),
          order_by: 'name asc',
        }),
      ),
      // The kinds of session this school actually runs, read off what has been
      // scheduled rather than declared anywhere — the type is free text on
      // purpose. `group_by` is how the document API says DISTINCT. Not asked
      // at all on a site that keeps no type.
      typeField
        ? readInto(
            typeRows,
            'session types',
            fetchRows(sessionTypes, 'document', {
              fields: JSON.stringify([typeField]),
              group_by: typeField,
              order_by: `${typeField} asc`,
            }),
          )
        : null,
      // Where the page opens when the address names no term. A reader without
      // permission on `Education Settings` gets a refusal here and the first
      // term in the list instead, which is why this is not awaited with the
      // others' success.
      currentTerm.submit({
        doctype: 'Education Settings',
        field: 'current_academic_term',
      }),
    ])
    listsLoaded.value = true
  }

  return {
    load,
    terms: computed(() => termRows.value),
    courses: computed(() => courseRows.value),
    sessionTypes: computed(() => {
      const typeField = attendanceFields.value.session_type_field
      if (!typeField) return []
      return typeRows.value
        .map((row) => String(row[typeField] ?? '').trim())
        .filter(Boolean)
    }),
    currentTerm: computed(() => currentTerm.data ?? null),
    loaded: computed(() => listsLoaded.value),
    incomplete: computed(() => incomplete.value),
    error: computed(() => fieldsError.value ?? readError.value ?? null),
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

const NO_ROWS: RegisterRows = {
  groups: [],
  students: [],
  schedules: [],
  marks: [],
}

/**
 * One term of one course, in four rounds of reads.
 *
 * They are chained because each genuinely depends on the last: a course reaches
 * its groups (through `Program Course`, its own `course` field or both — see
 * `GroupResolution`), sessions are read for the groups that came back, and
 * marks for the sessions that came back. Students and sessions do not depend on
 * each other and go together. Each round may be several requests: every list is
 * read to its end (see `fetchRows`).
 *
 * A custom endpoint would make this one round trip and has to be refused: see
 * the module comment.
 */
export function useAttendanceRegister() {
  const programs = childList<{ parent: string }>()
  const groups = documentList<GroupRow>('Student Group')
  const students = childList<StudentRow>()
  const schedules = documentList<ApiRow>('Course Schedule')
  const marks = documentList<ApiRow>('Student Attendance')

  const rows = ref<RegisterRows>(NO_ROWS) as Ref<RegisterRows>
  const register = computed<Register>(() =>
    buildRegister(rows.value, attendanceFields.value),
  )
  /** The lists this register's read stopped short of, at the safety ceiling.
   *  Empty for any register a school produces; the page warns when it is not. */
  const incomplete = ref<string[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<Error | null>(null)

  /**
   * Which `load` is the current one.
   *
   * The five calls above are shared by every load, so changing course while a
   * register is still coming in starts a second read on the same calls — which
   * aborts the first one's request in flight. Left alone, that aborted read
   * resolved afterwards and reported a failure (or an empty register) over the
   * second read that had just succeeded. Each load takes a number, and only
   * the newest may write `rows`, `error` or `loading`.
   */
  let sequence = 0

  async function load(term: string, course: string) {
    const ticket = ++sequence
    if (!term || !course) {
      rows.value = NO_ROWS
      incomplete.value = []
      loaded.value = false
      loading.value = false
      return
    }
    loading.value = true
    error.value = null
    const current = () => ticket === sequence
    try {
      const short: string[] = []
      const next = await read(term, course, current, short)
      if (!current()) return
      rows.value = next
      incomplete.value = short
      loaded.value = true
    } catch (problem) {
      // Superseded or cancelled: not this read's failure to report, and the
      // read that replaced it will say what it found.
      if (!current() || problem instanceof Cancelled) return
      error.value = problem as Error
      rows.value = NO_ROWS
      incomplete.value = []
      loaded.value = true
    } finally {
      if (current()) loading.value = false
    }
  }

  /**
   * `current` is asked after every round. A read that has been superseded
   * stops there rather than sending its next round, which would go out on the
   * same shared call as the newer read's and abort that one in turn.
   *
   * `short` collects the lists that reached the safety ceiling.
   */
  async function read(
    term: string,
    course: string,
    current: () => boolean,
    short: string[],
  ): Promise<RegisterRows> {
    const stillCurrent = () => {
      if (!current()) throw new Cancelled()
    }
    const all = async <Row>(label: string, reading: Promise<Paged<Row>>) => {
      const { rows, complete } = await reading
      if (!complete) short.push(label)
      return rows
    }

    const fields = await loadAttendanceFields()
    stillCurrent()

    // How this course reaches its groups is the site's setting (Attendance
    // Register Settings, *Find Student Groups By*): through the programmes a
    // `Program Course` row puts it on, through course-based groups' own
    // `course`, or both. See `GroupResolution`.
    //
    // Disabled groups are left in deliberately. This page is as much the record
    // of a term that has finished as it is the place to add to one that has
    // not, and a group is usually disabled precisely because its term is over.
    const groupRows = await resolveGroups(
      fields.group_resolution,
      term,
      course,
      {
        programmes: async (taught) => {
          const found = await all(
            'programmes',
            fetchRows(programs, 'client', {
              doctype: 'Program Course',
              parent: 'Program',
              fields: JSON.stringify(['parent']),
              filters: JSON.stringify([['course', '=', taught]]),
              order_by: 'parent asc',
            }),
          )
          stillCurrent()
          return found.map((row) => row.parent)
        },
        groups: async (filters) => {
          const found = await all(
            'student groups',
            fetchRows(groups, 'document', {
              fields: JSON.stringify([
                'name',
                'student_group_name',
                'program',
                'disabled',
              ]),
              filters: JSON.stringify(filters),
              order_by: 'name asc',
            }),
          )
          stillCurrent()
          return found
        },
      },
    )
    stillCurrent()
    const groupNames = groupRows.map((row) => row.name)
    if (!groupNames.length) return NO_ROWS

    const [studentRows, scheduleRows] = await Promise.all([
      // Ordered by name rather than by roll number, because the register is
      // read across: a teacher looks along the top for the student in front of
      // them. Inactive members are dropped — a student who has left the group
      // is not absent from its sessions, and a column of blanks reads as though
      // they were.
      all('students', fetchRows(students, 'client', {
        doctype: 'Student Group Student',
        parent: 'Student Group',
        fields: JSON.stringify(['parent', 'student', 'student_name']),
        filters: JSON.stringify([
          ['parent', 'in', groupNames],
          ['active', '=', 1],
        ]),
        order_by: 'student_name asc, name asc',
      })),
      all('sessions', fetchRows(schedules, 'document', {
        fields: JSON.stringify(scheduleFieldList(fields)),
        filters: JSON.stringify([
          ['student_group', 'in', groupNames],
          ['course', '=', course],
        ]),
        order_by: 'schedule_date asc, from_time asc, name asc',
      })),
    ])
    stillCurrent()

    const sessionNames = scheduleRows.map((row) => row.name)
    // Cancelled marks are dropped: an amended `Student Attendance` leaves the
    // cancelled original behind, carrying the same student and session.
    const markRows = sessionNames.length
      ? await all('marks', fetchRows(marks, 'document', {
          fields: JSON.stringify(markFieldList(fields)),
          filters: JSON.stringify([
            ['course_schedule', 'in', sessionNames],
            ['docstatus', '!=', 2],
          ]),
          order_by: 'name asc',
        }))
      : []
    stillCurrent()

    return {
      groups: groupRows,
      students: studentRows,
      schedules: scheduleRows.map((row) => scheduleRow(row, fields)),
      marks: markRows.map((row) => markRow(row, fields)),
    }
  }

  return {
    load,
    register,
    loading,
    loaded,
    error,
    incomplete: computed(() => incomplete.value),
  }
}

/**
 * Run one of the reads above to its last row, and throw rather than return
 * nothing.
 *
 * Paged with `pageThrough`: the document API takes `start` and `limit`,
 * `frappe.client.get_list` takes `limit_start` and `limit_page_length`, and
 * `style` says which. Every read that pages has an `order_by` ending in a
 * unique column, so a row cannot shift between two pages.
 *
 * `useCall.submit` resolves null on failure and leaves the reason on the call.
 * A chain of reads has to stop at the first refusal rather than carry on with
 * an empty list and draw a register that is missing half a term.
 */
async function fetchRows<Row, Params extends object>(
  call: {
    submit: (params: Params) => Promise<Row[] | null>
    error: Error | null
    aborted: boolean
  },
  style: 'document' | 'client',
  params: Params,
): Promise<Paged<Row>> {
  return pageThrough(async (start, length) => {
    const rows = await call.submit({
      ...params,
      ...(style === 'document'
        ? { start, limit: length }
        : { limit_start: start, limit_page_length: length }),
    })
    // An aborted request is one somebody called off — a newer read, or the page
    // going away — and not a refusal to put in front of the reader.
    if (call.aborted || call.error?.name === 'AbortError') throw new Cancelled()
    if (rows === null) throw call.error ?? new Error('That could not be loaded.')
    return rows
  })
}

/** A read that was called off rather than refused. Never shown. */
class Cancelled extends Error {}

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
  call: {
    submit: (params: Params) => Promise<Result | null>
    error: Error | null
  },
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
  Excused: 'lucide-minus',
  '': '',
}

export const MARK_COLOURS: Record<Mark, string> = {
  Present: 'bg-surface-green-2 text-ink-green-3',
  Late: 'bg-surface-amber-2 text-ink-amber-3',
  Absent: 'bg-surface-red-2 text-ink-red-3',
  Excused: 'bg-surface-gray-2 text-ink-gray-6',
  '': 'bg-surface-white',
}

export const MARK_LABELS: Record<Mark, string> = {
  Present: 'Present',
  Late: 'Late',
  Absent: 'Absent',
  Excused: 'On leave (excused)',
  '': 'Not marked',
}

export const STUDENT_ATTENDANCE = 'Student Attendance'
export const COURSE_SCHEDULE = 'Course Schedule'

/** The document a new mark is, ready for `insert`. */
export function newMark(session: string, student: string, mark: Mark) {
  return {
    doctype: STUDENT_ATTENDANCE,
    course_schedule: session,
    student,
    ...markFields(mark, attendanceFields.value),
  }
}

/** The fields a changed mark sets. */
export function markValues(mark: Mark) {
  return markFields(mark, attendanceFields.value)
}

/** Whether the term picker's selection contains a date — what bounds the
 *  session dialog's date field. */
export function termBounds(
  terms: MaybeRefOrGetter<TermRow[]>,
  term: MaybeRefOrGetter<string>,
) {
  const found = computed(() =>
    toValue(terms).find((row) => row.name === toValue(term)),
  )
  return {
    start: computed(() => found.value?.term_start_date ?? null),
    end: computed(() => found.value?.term_end_date ?? null),
  }
}
