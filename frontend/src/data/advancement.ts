import { computed, ref } from 'vue'
import { useCall } from 'frappe-ui'
import {
  buildCandidates,
  defaultTerms,
  groupNameFor,
  NO_SETTINGS,
  renderGroupName,
  type AdvancementSettings,
  type Candidate,
  type Decision,
  type EnrollmentRow,
  type FieldValues,
  type GroupRow,
  type MemberRow,
  type NextRow,
  type StudentRow,
  type TermRow,
} from './advancementPlan'
import { pageThrough, type Paged } from './attendanceRegister'
import { permissionCall } from './permissions'

/**
 * The advancement page's reads, and its one write.
 *
 * Reads go through the REST document API, and child tables through
 * `frappe.client.get_list`, as the attendance register's do and for the same
 * reasons (see `data/attendance.ts`): every row is filtered by the reader's own
 * permissions, and the document API strips a child table's fields. The write
 * is this app's `apply`, because a term's groups, enrolments and statuses are
 * one act that should land whole or not at all. See
 * `commons.student_advancement.advancement`.
 */

const DOCUMENT = '/api/v2/document'
const CLIENT = '/api/v2/method/frappe.client'
const ADVANCEMENT = '/api/v2/method/commons.student_advancement.advancement'

export type {
  AdvancementSettings,
  Candidate,
  Decision,
  GroupRow,
  TermRow,
} from './advancementPlan'

/** Whether enrolling students is this reader's to do -- who the page is for. */
const canAdvanceCall = permissionCall('Program Enrollment', 'create')

export const canAdvance = computed(() => Boolean(canAdvanceCall.data?.has_permission))
export const advancePermissionLoaded = computed(() => canAdvanceCall.isFinished)

/** Whether this reader may change which term is current: write on Education Settings. */
const canSetCurrentCall = permissionCall('Education Settings', 'write')

export const canSetCurrent = computed(() => Boolean(canSetCurrentCall.data?.has_permission))

interface ListCall<Row> {
  submit: (params: Record<string, unknown>) => Promise<Row[] | null>
  error: Error | null
}

function documentList<Row>(doctype: string): ListCall<Row> {
  return useCall<Row[], Record<string, unknown>>({
    url: `${DOCUMENT}/${encodeURIComponent(doctype)}`,
    immediate: false,
  })
}

function childList<Row>(): ListCall<Row> {
  return useCall<Row[], Record<string, unknown>>({
    url: `${CLIENT}.get_list`,
    immediate: false,
  })
}

/** Every row of a list, a page at a time. See `pageThrough`. */
function readAll<Row>(
  call: ListCall<Row>,
  style: 'document' | 'client',
  params: Record<string, unknown>,
): Promise<Paged<Row>> {
  return pageThrough(async (start, length) => {
    const rows = await call.submit({
      ...params,
      ...(style === 'document'
        ? { start, limit: length }
        : { limit_start: start, limit_page_length: length }),
    })
    if (rows === null) throw call.error ?? new Error('That could not be loaded.')
    return rows
  })
}

/**
 * The page's data for one pair of terms, and what it needs before any pair.
 *
 * `load()` reads what does not depend on the terms -- the settings, the terms,
 * the programs, every student group and which terms have enrolments -- and
 * `loadTerms(from, to)` the rest. The groups are read whole because a new
 * group is named after the program's latest one, whatever term it was in.
 */
export function useAdvancement() {
  const settingsCall = useCall<AdvancementSettings>({
    url: `${ADVANCEMENT}.advancement_settings`,
    immediate: false,
  })
  const termsCall = documentList<TermRow>('Academic Term')
  const programsCall = documentList<FieldValues & { name: string }>('Program')
  const groupsCall = documentList<GroupRow>('Student Group')
  const enrolledTermsCall = documentList<{ academic_term: string }>('Program Enrollment')
  const currentTermCall = useCall<string | null, { doctype: string; field: string }>({
    url: `${CLIENT}.get_single_value`,
    immediate: false,
  })
  const leavingCall = documentList<EnrollmentRow>('Program Enrollment')
  const enteringCall = documentList<EnrollmentRow>('Program Enrollment')
  const studentsCall = documentList<Record<string, string | null>>('Student')
  const membersCall = childList<MemberRow>()
  const nextCall = childList<Record<string, string>>()

  const settings = ref<AdvancementSettings>(NO_SETTINGS)
  const terms = ref<TermRow[]>([])
  const programs = ref<string[]>([])
  const programRowsByName = ref<Record<string, FieldValues>>({})
  const groups = ref<GroupRow[]>([])
  const defaults = ref({ from: '', to: '' })
  const loaded = ref(false)
  /** Education Settings' current term, or null where it is unset or unreadable. */
  const currentTerm = ref<string | null>(null)
  const error = ref<Error | null>(null)

  const candidates = ref<Candidate[]>([])
  const termsLoaded = ref(false)
  const termsLoading = ref(false)
  const termsError = ref<Error | null>(null)
  /** Lists that stopped at the safety ceiling, said rather than hidden. */
  const incomplete = ref<string[]>([])

  async function load() {
    error.value = null
    try {
      // The settings first: the group name format says which fields of the
      // terms and the programs to read.
      const found = await settingsCall.submit()
      if (found === null) throw settingsCall.error ?? new Error('The settings could not be loaded.')
      settings.value = { ...NO_SETTINGS, ...found }
      const naming = settings.value.group_name
      const [termRows, programRows, groupRows, enrolled] = await Promise.all([
        readAll(termsCall, 'document', {
          fields: JSON.stringify([
            ...new Set(['name', 'academic_year', 'term_start_date', ...(naming?.term_fields ?? [])]),
          ]),
          order_by: 'term_start_date desc, name asc',
        }),
        readAll(programsCall, 'document', {
          fields: JSON.stringify([...new Set(['name', ...(naming?.program_fields ?? [])])]),
          order_by: 'name asc',
        }),
        readAll(groupsCall, 'document', {
          fields: JSON.stringify([
            'name',
            'student_group_name',
            'program',
            'academic_term',
            'creation',
          ]),
          order_by: 'creation desc',
        }),
        readAll(enrolledTermsCall, 'document', {
          fields: JSON.stringify(['academic_term']),
          filters: JSON.stringify([['docstatus', '=', 1]]),
          group_by: 'academic_term',
          order_by: 'academic_term asc',
        }),
      ])
      terms.value = termRows.rows
      programs.value = programRows.rows.map((row) => row.name)
      programRowsByName.value = Object.fromEntries(programRows.rows.map((row) => [row.name, row]))
      groups.value = groupRows.rows
      await loadCurrentTerm()
      defaults.value = defaultTerms(
        termRows.rows,
        enrolled.rows.map((row) => row.academic_term),
      )
      incomplete.value = [
        ...(termRows.complete ? [] : ['terms']),
        ...(groupRows.complete ? [] : ['student groups']),
      ]
      loaded.value = true
    } catch (problem) {
      error.value = problem as Error
    }
  }

  /** A refusal reads as no current term rather than failing the page. */
  async function loadCurrentTerm() {
    const value = await currentTermCall.submit({
      doctype: 'Education Settings',
      field: 'current_academic_term',
    })
    currentTerm.value = currentTermCall.error ? null : value || null
  }

  /** Called-off reads are told apart by ticket: only the latest pair is kept. */
  let ticket = 0

  async function loadTerms(from: string, to: string) {
    const mine = ++ticket
    termsError.value = null
    termsLoaded.value = false
    candidates.value = []
    if (!from || !to) return
    termsLoading.value = true
    try {
      const statusField = settings.value.status?.field ?? null
      const chain = settings.value.next_programs
      const [leaving, entering] = await Promise.all([
        readAll(leavingCall, 'document', {
          fields: JSON.stringify(['name', 'student', 'student_name', 'program', 'academic_term', 'docstatus']),
          filters: JSON.stringify([
            ['academic_term', '=', from],
            ['docstatus', '=', 1],
          ]),
          order_by: 'program asc, student_name asc',
        }),
        readAll(enteringCall, 'document', {
          fields: JSON.stringify(['name', 'student', 'student_name', 'program', 'academic_term', 'docstatus']),
          filters: JSON.stringify([
            ['academic_term', '=', to],
            ['docstatus', '<', 2],
          ]),
          order_by: 'program asc',
        }),
      ])
      const students = [...new Set(leaving.rows.map((row) => row.student))]
      const leavingGroups = groups.value
        .filter((row) => row.academic_term === from)
        .map((row) => row.name)
      const programsLeft = [...new Set(leaving.rows.map((row) => row.program))]

      const [studentRows, memberRows, nextRows] = await Promise.all([
        students.length
          ? readAll(studentsCall, 'document', {
              fields: JSON.stringify(['name', 'student_name', ...(statusField ? [statusField] : [])]),
              filters: JSON.stringify([['name', 'in', students]]),
            })
          : { rows: [], complete: true },
        leavingGroups.length
          ? readAll(membersCall, 'client', {
              doctype: 'Student Group Student',
              parent: 'Student Group',
              fields: JSON.stringify(['parent', 'student', 'active']),
              filters: JSON.stringify([['parent', 'in', leavingGroups]]),
            })
          : { rows: [], complete: true },
        chain && programsLeft.length
          ? readAll(nextCall, 'client', {
              doctype: chain.table_doctype,
              parent: 'Program',
              fields: JSON.stringify(['parent', chain.program_column]),
              filters: JSON.stringify([
                ['parent', 'in', programsLeft],
                ['parentfield', '=', chain.table_field],
              ]),
              order_by: 'parent asc, idx asc',
            })
          : { rows: [], complete: true },
      ])
      if (mine !== ticket) return

      candidates.value = buildCandidates({
        enrollments: leaving.rows,
        entering: entering.rows,
        students: studentRows.rows.map(
          (row): StudentRow => ({
            name: row.name as string,
            student_name: row.student_name ?? null,
            status: statusField ? (row[statusField] ?? null) : null,
          }),
        ),
        groups: groups.value,
        members: memberRows.rows,
        nextRows: chain
          ? nextRows.rows.map(
              (row): NextRow => ({ parent: row.parent, program: row[chain.program_column] }),
            )
          : null,
        programs: programs.value,
        sourceTerm: from,
      })
      incomplete.value = [
        ...incomplete.value.filter((label) => label === 'terms' || label === 'student groups'),
        ...(leaving.complete && entering.complete ? [] : ['enrolments']),
      ]
      termsLoaded.value = true
    } catch (problem) {
      if (mine === ticket) termsError.value = problem as Error
    } finally {
      if (mine === ticket) termsLoading.value = false
    }
  }

  /**
   * The name a new group for `program` in `term` is offered under: the site's
   * format where it has one and every placeholder has a value, else the
   * program's last group's name with the term swapped.
   */
  function groupName(program: string, term: string): string {
    const naming = settings.value.group_name
    const termRow = terms.value.find((row) => row.name === term)
    if (naming && termRow) {
      const named = renderGroupName(
        naming.format,
        termRow as unknown as FieldValues,
        programRowsByName.value[program] ?? { name: program },
      )
      if (named) return named
    }
    return groupNameFor(program, term, groups.value)
  }

  return {
    currentTerm,
    loadCurrentTerm,
    groupName,
    settings,
    terms,
    programs,
    groups,
    defaults,
    loaded,
    error,
    candidates,
    termsLoaded,
    termsLoading,
    termsError,
    incomplete,
    load,
    loadTerms,
  }
}

/** What `apply` reports back. */
export interface Applied {
  /** The term made current, where Apply was asked to. */
  current_term?: string
  groups: string[]
  enrollments: { name: string; student: string; student_name: string; program: string }[]
  skipped: { student: string; student_name: string; program: string }[]
  statuses: { student: string; student_name: string; from: string; to: string }[]
}

export function useApply() {
  return useCall<
    Applied,
    {
      source_term: string
      target_term: string
      decisions: { enrollment: string; program: string | null; status: string | null }[]
      group_names: Record<string, string>
      make_current: boolean
    }
  >({
    url: `${ADVANCEMENT}.apply`,
    method: 'POST',
    immediate: false,
  })
}

/** `make_current`: make a term the current one in Education Settings. */
export function useMakeCurrent() {
  return useCall<string, { term: string }>({
    url: `${ADVANCEMENT}.make_current`,
    method: 'POST',
    immediate: false,
  })
}
