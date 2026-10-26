/**
 * A term's advancement, worked out from the rows the document API returns.
 *
 * Pure: no Vue, no network. `advancement.ts` reads; this joins what came back
 * into one row per enrolment, suggests what becomes of each student, names
 * the groups a new term needs, and counts what Apply will write. The rules a
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
  } | null
  /** The format a new group is named by, and the fields of the term and the
   *  program it reads. Null: named after the program's last group. */
  group_name: {
    format: string
    term_fields: string[]
    program_fields: string[]
  } | null
}

export const NO_SETTINGS: AdvancementSettings = {
  next_programs: null,
  status: null,
  group_name: null,
}

/** A row's fields by name, as read for the group name format. */
export type FieldValues = Record<string, string | number | null | undefined>

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

export interface GroupRow {
  name: string
  student_group_name: string | null
  program: string | null
  academic_term: string | null
  creation: string
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

/** The ways a term's name is written into a group's: as it stands, and without brackets. */
export function termForms(term: string): string[] {
  const bare = term.replace(/[()[\]]/g, '').replace(/\s+/g, ' ').trim()
  return bare === term ? [term] : [term, bare]
}

/**
 * A group name from the site's format: `{field}` from the term, and
 * `{program.field}` from the program. Null if a placeholder has no value, so a
 * program whose label is not filled in yet falls back rather than being named
 * "W&R - 2026-27 Fall - ".
 */
export function renderGroupName(
  format: string,
  term: FieldValues,
  program: FieldValues,
): string | null {
  let missing = false
  const name = format.replace(
    /\{\s*(program\.)?([a-z0-9_]+)\s*\}/g,
    (_, onProgram: string | undefined, field: string) => {
      const value = (onProgram ? program : term)[field]
      if (value === null || value === undefined || String(value).trim() === '') missing = true
      return String(value ?? '').trim()
    },
  )
  return missing ? null : name.replace(/\s+/g, ' ').trim()
}

/**
 * The name to give a new group for `program` in `term`, where the site has no
 * format for it (see `renderGroupName`).
 *
 * Copied from the program's latest group, with that group's term swapped for
 * the new one -- a school names its groups after a pattern, and the last one
 * made is the best statement of it. The term is matched as written or without
 * its brackets ("2025-26 Spring" for "2025-26 (Spring)"). Where the program
 * has never been grouped, or its last group's name does not contain its term,
 * the program and the term.
 */
export function groupNameFor(program: string, term: string, groups: GroupRow[]): string {
  const fallback = `${program} - ${term}`
  const latest = groups
    .filter((row) => row.program === program && row.academic_term && row.academic_term !== term)
    .sort((a, b) => b.creation.localeCompare(a.creation))[0]
  const name = latest?.student_group_name || latest?.name
  if (!latest?.academic_term || !name) return fallback
  const from = termForms(latest.academic_term)
  const to = termForms(term)
  for (let i = from.length - 1; i >= 0; i--) {
    if (name.includes(from[i])) return name.replace(from[i], to[Math.min(i, to.length - 1)])
  }
  return fallback
}

/** The term's existing group for a program, if it has one. */
export function existingGroup(program: string, term: string, groups: GroupRow[]): GroupRow | null {
  return groups.find((row) => row.program === program && row.academic_term === term) ?? null
}

/** What Apply will write, worked out from the decisions. */
export interface Plan {
  /** Rows with something to write, in candidate order. */
  rows: { candidate: Candidate; decision: Decision }[]
  /** Enrolments to draft, counted by program. */
  enrolments: { program: string; count: number; group: string | null }[]
  /** Programs the new term has no group for, which Apply will make. */
  newGroups: string[]
  /** Students whose status changes. */
  statusChanges: number
}

/**
 * The plan for a set of decisions. A decision repeating an enrolment the
 * student already has is left out: the server would skip it.
 */
export function buildPlan(
  candidates: Candidate[],
  decisions: Record<string, Decision>,
  groups: GroupRow[],
  targetTerm: string,
): Plan {
  const rows: Plan['rows'] = []
  const counts = new Map<string, number>()
  let statusChanges = 0
  for (const candidate of candidates) {
    const decision = decisions[candidate.enrollment]
    if (!decision) continue
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
  const enrolments = [...counts].map(([program, count]) => ({
    program,
    count,
    group: existingGroup(program, targetTerm, groups)?.name ?? null,
  }))
  return {
    rows,
    enrolments,
    newGroups: enrolments.filter((row) => !row.group).map((row) => row.program),
    statusChanges,
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
