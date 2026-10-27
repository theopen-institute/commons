/**
 * A term's advancement, worked out from the rows the document API returns.
 *
 * Pure: no Vue, no network. `advancement.ts` reads; this joins what came back
 * into one row per enrolment, suggests what becomes of each student, and
 * counts what Apply will write. The rules a
 * school has -- which program follows which, what a continuing student is
 * called -- come in as data, from the site's own fields; see
 * `commons.student_advancement.advancement`.
 */

/** Where the site keeps its rules, as `advancement_settings` reports them. */
export interface AdvancementSettings {
  /** The Table on Program listing what may follow it. Null: any program may. */
  next_programs: {
    table_field: string
    table_doctype: string
    program_column: string
  } | null
  /** The Select on Student holding a student's standing. Null: none is kept. */
  status: {
    field: string
    options: string[]
    /** The option given to a student moving on, or null for none. */
    continuing: string | null
    /** The site requires a student going nowhere to leave with another option. */
    require_leaving: boolean
  } | null
}

export const NO_SETTINGS: AdvancementSettings = {
  next_programs: null,
  status: null,
}

export interface TermRow {
  name: string
  academic_year: string | null
  term_start_date: string | null
}

export interface EnrollmentRow {
  name: string
  student: string
  student_name: string | null
  program: string
  academic_term: string
  docstatus: number
}

export interface StudentRow {
  name: string
  student_name: string | null
  /** The status field's value, under the name `status` whatever the site calls it. */
  status: string | null
}

/** A group of the term being left: who was active in it says who simply finished the term. */
export interface GroupRow {
  name: string
  program: string | null
  academic_term: string | null
}

export interface MemberRow {
  parent: string
  student: string
  active: number
}

/** One row of a program's next programs: the program it belongs to, and one that may follow. */
export interface NextRow {
  parent: string
  program: string
}

/** One enrolment in the term being left, and everything the page shows beside it. */
export interface Candidate {
  enrollment: string
  student: string
  studentName: string
  program: string
  /** The student's standing now, or null where the site keeps none or it is blank. */
  status: string | null
  /** Active in the program's group that term; false if listed and inactive, null if in none. */
  active: boolean | null
  /** Enrolments the student already has in the term being entered. */
  already: { program: string; name: string; draft: boolean }[]
  /** The programs that may follow this one, in the order the site lists them. */
  offered: string[]
  /**
   * Not enrolled in the term being left at all, but marked as continuing and
   * active in none of its groups -- see `findStrays`. Such a row is keyed by
   * `student:<name>` rather than an enrolment, offers no program, and can
   * only have its status changed.
   */
  stray?: boolean
  /** For a stray: the term of the student's latest submitted enrolment. */
  lastTerm?: string | null
}

/** The key a stray's decision is held under: it has no enrolment to key it by. */
export function strayKey(student: string): string {
  return `student:${student}`
}

/**
 * A continuing student who is enrolled in neither term and active in none of
 * the old term's groups -- which should never happen.
 *
 * The status says they continue; nothing else does. Usually a student who
 * left without their status being changed, or one whose enrolment was
 * cancelled. Listed with a warning so that one of the two is put right:
 * enrolled in the desk, or given the status that says they left.
 *
 * Not a stray: a student enrolled in the old term (they are on the list
 * already, and say the same thing with a badge), or one with an enrolment in
 * the new term or any later one, such as a new student starting the first
 * program.
 */
export function findStrays(input: {
  /** Students whose status is the continuing one. */
  continuing: StudentRow[]
  candidates: Candidate[]
  entering: EnrollmentRow[]
  groups: GroupRow[]
  members: MemberRow[]
  sourceTerm: string
  /** The students' enrolments, draft or submitted, in any term. */
  latest: { student: string; program: string; academic_term: string }[]
  /** For ordering terms by when they start. */
  terms: TermRow[]
}): Candidate[] {
  const starts = new Map(input.terms.map((row) => [row.name, row.term_start_date ?? '']))
  const start = (term: string) => starts.get(term) ?? ''
  const lastOf = new Map<string, { program: string; academic_term: string }>()
  for (const row of input.latest) {
    const known = lastOf.get(row.student)
    if (!known || start(row.academic_term) > start(known.academic_term)) lastOf.set(row.student, row)
  }
  const sourceStart = start(input.sourceTerm)
  const listed = new Set(input.candidates.map((row) => row.student))
  const entering = new Set(input.entering.map((row) => row.student))
  const oldGroups = new Set(
    input.groups.filter((row) => row.academic_term === input.sourceTerm).map((row) => row.name),
  )
  const active = new Set(
    input.members.filter((row) => row.active && oldGroups.has(row.parent)).map((row) => row.student),
  )
  return input.continuing
    .filter((row) => !listed.has(row.name) && !entering.has(row.name) && !active.has(row.name))
    .filter((row) => {
      const last = lastOf.get(row.name)
      return !last || start(last.academic_term) <= sourceStart
    })
    .map((row): Candidate => {
      const last = lastOf.get(row.name)
      return {
        enrollment: strayKey(row.name),
        student: row.name,
        studentName: row.student_name || row.name,
        program: last?.program ?? '',
        status: row.status,
        active: null,
        already: [],
        offered: [],
        stray: true,
        lastTerm: last?.academic_term ?? null,
      }
    })
    .sort((a, b) => a.studentName.localeCompare(b.studentName))
}

/** Whether a listed student is marked as continuing but is not active in the term's group. */
export function continuingWithoutGroup(candidate: Candidate, settings: AdvancementSettings): boolean {
  const continuing = settings.status?.continuing
  return Boolean(continuing && candidate.status === continuing && candidate.active !== true)
}

/** What becomes of one student. Null `program`: no new enrolment. Null `status`: left as it is. */
export interface Decision {
  program: string | null
  status: string | null
}

/**
 * One candidate per enrolment in the term being left, in program then name order.
 *
 * `offered` is the site's list for the program where it keeps one, and every
 * program otherwise -- the page then suggests none, and the choice is the
 * reader's.
 */
export function buildCandidates(input: {
  enrollments: EnrollmentRow[]
  entering: EnrollmentRow[]
  students: StudentRow[]
  groups: GroupRow[]
  members: MemberRow[]
  nextRows: NextRow[] | null
  programs: string[]
  sourceTerm: string
}): Candidate[] {
  const students = new Map(input.students.map((row) => [row.name, row]))
  const groupProgram = new Map(
    input.groups
      .filter((row) => row.academic_term === input.sourceTerm)
      .map((row) => [row.name, row.program]),
  )

  // Active in a group of the program, that term. A student listed in two of
  // its groups counts as active if either says so.
  const membership = new Map<string, boolean>()
  for (const row of input.members) {
    const program = groupProgram.get(row.parent)
    if (!program) continue
    const key = `${row.student}\u0000${program}`
    membership.set(key, Boolean(membership.get(key)) || Boolean(row.active))
  }

  const offered = new Map<string, string[]>()
  for (const row of input.nextRows ?? []) {
    const list = offered.get(row.parent) ?? []
    if (row.program && !list.includes(row.program)) list.push(row.program)
    offered.set(row.parent, list)
  }

  const candidates = input.enrollments.map((row): Candidate => {
    const student = students.get(row.student)
    return {
      enrollment: row.name,
      student: row.student,
      studentName: student?.student_name || row.student_name || row.student,
      program: row.program,
      status: student?.status || null,
      active: membership.get(`${row.student}\u0000${row.program}`) ?? null,
      already: input.entering
        .filter((other) => other.student === row.student)
        .map((other) => ({ program: other.program, name: other.name, draft: other.docstatus === 0 })),
      offered: input.nextRows ? (offered.get(row.program) ?? []) : input.programs,
    }
  })

  return candidates.sort(
    (a, b) => a.program.localeCompare(b.program) || a.studentName.localeCompare(b.studentName),
  )
}

/** Why a candidate is suggested no change, or null where the suggestion is to move on. */
export function holdReason(candidate: Candidate, settings: AdvancementSettings): string | null {
  if (candidate.stray) return 'Enrolled, but in no group and no enrolment'
  if (candidate.already.length) return 'Already enrolled in the new term'
  const continuing = settings.status?.continuing
  if (continuing && candidate.status && candidate.status !== continuing) {
    return `${candidate.status}`
  }
  if (candidate.active === false) return 'Inactive in the group'
  if (!settings.next_programs) return 'No next programs are set up'
  if (!candidate.offered.length) return 'Nothing follows this program'
  return null
}

/**
 * What the page proposes for a student, before anybody changes it.
 *
 * Nothing, for a student already enrolled in the new term, whose standing is
 * not the continuing one, or who is inactive in the term's group -- each of
 * which says the student did not simply finish the term. Otherwise the first
 * program the site lists, and the continuing status where it differs.
 */
export function suggest(candidate: Candidate, settings: AdvancementSettings): Decision {
  if (holdReason(candidate, settings)) return { program: null, status: null }
  const continuing = settings.status?.continuing ?? null
  return {
    program: candidate.offered[0],
    status: continuing && continuing !== candidate.status ? continuing : null,
  }
}

/** What Apply will write, worked out from the decisions. */
export interface Plan {
  /** Rows with something to write, in candidate order. */
  rows: { candidate: Candidate; decision: Decision }[]
  /** Enrolments to draft, counted by program. */
  enrolments: { program: string; count: number }[]
  /** Students whose status changes. */
  statusChanges: number
  /** Students going nowhere whose status still says they continue. Apply
   *  waits until there are none. See `needsLeavingStatus`. */
  unresolved: Candidate[]
}

/** The statuses a student who is not continuing may have: every option but the continuing one. */
export function leavingStatuses(settings: AdvancementSettings): string[] {
  const status = settings.status
  if (!status?.continuing || !status.require_leaving) return []
  return status.options.filter((option) => option !== status.continuing)
}

/**
 * Whether a student is left with no enrolment in the new term and a status
 * that does not say they left.
 *
 * A student going nowhere has finished one way or another, and the status is
 * where that is recorded: they must end the advancement with one of the
 * statuses other than the continuing one (Withdrawn or Graduated, say), not
 * with the continuing one or none. Only where the site names a continuing
 * status; without one there is no rule to keep. A student already enrolled in
 * the new term is continuing, whatever this page decides. Only where the site
 * has switched the rule on (Require a Leaving Status), and `apply` keeps it
 * too.
 */
export function needsLeavingStatus(
  candidate: Candidate,
  decision: Decision,
  settings: AdvancementSettings,
): boolean {
  const leaving = leavingStatuses(settings)
  if (!leaving.length || candidate.stray || decision.program || candidate.already.length) return false
  return !leaving.includes(decision.status ?? candidate.status ?? '')
}

/**
 * The plan for a set of decisions. A decision repeating an enrolment the
 * student already has is left out: the server would skip it.
 */
export function buildPlan(
  candidates: Candidate[],
  decisions: Record<string, Decision>,
  settings: AdvancementSettings = NO_SETTINGS,
): Plan {
  const rows: Plan['rows'] = []
  const unresolved: Candidate[] = []
  const counts = new Map<string, number>()
  let statusChanges = 0
  for (const candidate of candidates) {
    const decision = decisions[candidate.enrollment]
    if (!decision) continue
    if (needsLeavingStatus(candidate, decision, settings)) unresolved.push(candidate)
    const program =
      decision.program && !candidate.already.some((row) => row.program === decision.program)
        ? decision.program
        : null
    const status = decision.status && decision.status !== candidate.status ? decision.status : null
    if (!program && !status) continue
    rows.push({ candidate, decision: { program, status } })
    if (program) counts.set(program, (counts.get(program) ?? 0) + 1)
    if (status) statusChanges++
  }
  return {
    rows,
    enrolments: [...counts].map(([program, count]) => ({ program, count })),
    statusChanges,
    unresolved,
  }
}

/** Whether a decision differs from the page's own suggestion. */
export function isEdited(decision: Decision, suggestion: Decision): boolean {
  return decision.program !== suggestion.program || decision.status !== suggestion.status
}

/**
 * The term to advance from and the term to advance into, where the address
 * names neither: the latest term anybody is enrolled in, and the one after it.
 */
export function defaultTerms(
  terms: TermRow[],
  enrolledTerms: string[],
): { from: string; to: string } {
  const ordered = [...terms].sort((a, b) =>
    (a.term_start_date ?? '').localeCompare(b.term_start_date ?? ''),
  )
  const enrolled = new Set(enrolledTerms)
  let index = -1
  ordered.forEach((row, i) => {
    if (enrolled.has(row.name)) index = i
  })
  if (index < 0) return { from: '', to: '' }
  return { from: ordered[index].name, to: ordered[index + 1]?.name ?? '' }
}
