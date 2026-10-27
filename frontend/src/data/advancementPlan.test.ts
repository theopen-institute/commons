import { describe, expect, it } from 'vitest'
import {
  buildCandidates,
  buildPlan,
  continuingWithoutGroup,
  findStrays,
  defaultTerms,
  holdReason,
  needsLeavingStatus,
  NO_SETTINGS,
  suggest,
  type AdvancementSettings,
  type Candidate,
  type EnrollmentRow,
  type GroupRow,
} from './advancementPlan'

/**
 * What the advancement page has to get right. Each of these fails quietly: a
 * wrong suggestion is one more student a busy person has to notice.
 */

const SETTINGS: AdvancementSettings = {
  next_programs: { table_field: 'next', table_doctype: 'Next Program', program_column: 'program' },
  status: {
    field: 'standing',
    options: ['Enrolled', 'Graduated', 'Withdrawn'],
    continuing: 'Enrolled',
    require_leaving: true,
  },
}

function enrolment(student: string, program: string, term = 'T1', docstatus = 1): EnrollmentRow {
  return { name: `PE-${student}-${term}`, student, student_name: student, program, academic_term: term, docstatus }
}

function group(name: string, program: string, term: string): GroupRow {
  return { name, program, academic_term: term }
}

function candidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    enrollment: 'PE-a',
    student: 'a',
    studentName: 'A',
    program: 'One',
    status: 'Enrolled',
    active: true,
    already: [],
    offered: ['Two', 'Hold'],
    ...overrides,
  }
}

describe('candidates', () => {
  const base = {
    enrollments: [enrolment('b', 'One'), enrolment('a', 'One'), enrolment('c', 'Two')],
    entering: [enrolment('c', 'Three', 'T2', 0)],
    students: [
      { name: 'a', student_name: 'Ann', status: 'Enrolled' },
      { name: 'b', student_name: 'Bo', status: null },
    ],
    groups: [group('G1', 'One', 'T1'), group('G2', 'Two', 'T1'), group('GX', 'One', 'T0')],
    members: [
      { parent: 'G1', student: 'a', active: 1 },
      { parent: 'G1', student: 'b', active: 0 },
      { parent: 'GX', student: 'c', active: 1 },
    ],
    nextRows: [
      { parent: 'One', program: 'Two' },
      { parent: 'One', program: 'Hold' },
    ],
    programs: ['One', 'Two', 'Three', 'Hold'],
    sourceTerm: 'T1',
  }

  it('joins status, membership and the new term, in program and name order', () => {
    const rows = buildCandidates(base)
    expect(rows.map((row) => row.studentName)).toEqual(['Ann', 'Bo', 'c'])
    expect(rows[0]).toMatchObject({ status: 'Enrolled', active: true, offered: ['Two', 'Hold'] })
    expect(rows[1]).toMatchObject({ status: null, active: false })
  })

  it('counts membership only in a group of the same program that term', () => {
    const c = buildCandidates(base).find((row) => row.student === 'c')!
    expect(c.active).toBeNull()
    expect(c.already).toEqual([{ program: 'Three', name: 'PE-c-T2', draft: true }])
  })

  it('offers nothing after a program with no rows, and everything where no table is kept', () => {
    expect(buildCandidates(base).find((row) => row.student === 'c')!.offered).toEqual([])
    expect(buildCandidates({ ...base, nextRows: null })[0].offered).toEqual(base.programs)
  })
})

describe('suggestions', () => {
  it('moves a continuing student on to the first program listed', () => {
    expect(suggest(candidate(), SETTINGS)).toEqual({ program: 'Two', status: null })
  })

  it('gives the continuing status to a student without one', () => {
    expect(suggest(candidate({ status: null }), SETTINGS)).toEqual({ program: 'Two', status: 'Enrolled' })
  })

  it('holds a student who left, who is inactive, or who is already enrolled', () => {
    for (const held of [
      candidate({ status: 'Withdrawn' }),
      candidate({ active: false }),
      candidate({ already: [{ program: 'Two', name: 'x', draft: true }] }),
    ]) {
      expect(suggest(held, SETTINGS)).toEqual({ program: null, status: null })
      expect(holdReason(held, SETTINGS)).toBeTruthy()
    }
  })

  it('suggests nothing where the site keeps no next programs', () => {
    expect(suggest(candidate(), NO_SETTINGS)).toEqual({ program: null, status: null })
  })

  it('suggests no status where the site names no continuing one', () => {
    const settings = { ...SETTINGS, status: { ...SETTINGS.status!, continuing: null } }
    expect(suggest(candidate({ status: null }), settings)).toEqual({ program: 'Two', status: null })
  })
})

describe('the plan', () => {
  it('counts enrolments and status changes, and leaves out what would change nothing', () => {
    const a = candidate()
    const b = candidate({ enrollment: 'PE-b', student: 'b', status: null })
    const c = candidate({ enrollment: 'PE-c', student: 'c', already: [{ program: 'Two', name: 'x', draft: false }] })
    const plan = buildPlan(
      [a, b, c],
      {
        'PE-a': { program: 'Hold', status: 'Enrolled' },
        'PE-b': { program: 'Two', status: 'Enrolled' },
        'PE-c': { program: 'Two', status: null },
      },
    )
    expect(plan.rows.map((row) => row.candidate.student)).toEqual(['a', 'b'])
    expect(plan.rows[0].decision).toEqual({ program: 'Hold', status: null })
    expect(plan.enrolments).toEqual([
      { program: 'Hold', count: 1 },
      { program: 'Two', count: 1 },
    ])
    expect(plan.statusChanges).toBe(1)
  })
})

describe('students going nowhere', () => {
  const nowhere = { program: null, status: null }

  it('must leave with a status other than the continuing one', () => {
    expect(needsLeavingStatus(candidate(), nowhere, SETTINGS)).toBe(true)
    expect(needsLeavingStatus(candidate({ status: null }), nowhere, SETTINGS)).toBe(true)
    expect(needsLeavingStatus(candidate(), { program: null, status: 'Graduated' }, SETTINGS)).toBe(false)
    expect(needsLeavingStatus(candidate({ status: 'Withdrawn' }), nowhere, SETTINGS)).toBe(false)
  })

  it('does not apply to a student moving on or already enrolled, or without a continuing status', () => {
    expect(needsLeavingStatus(candidate(), { program: 'Two', status: null }, SETTINGS)).toBe(false)
    expect(
      needsLeavingStatus(candidate({ already: [{ program: 'Two', name: 'x', draft: true }] }), nowhere, SETTINGS),
    ).toBe(false)
    expect(needsLeavingStatus(candidate(), nowhere, NO_SETTINGS)).toBe(false)
  })

  it('holds the plan back until each has one', () => {
    const plan = buildPlan(
      [candidate(), candidate({ enrollment: 'PE-b', student: 'b' })],
      { 'PE-a': nowhere, 'PE-b': { program: null, status: 'Withdrawn' } },
      SETTINGS,
    )
    expect(plan.unresolved.map((row) => row.student)).toEqual(['a'])
    expect(plan.rows.map((row) => row.candidate.student)).toEqual(['b'])
  })
})

describe('continuing students with nothing behind them', () => {
  const terms = [
    { name: 'T0', academic_year: null, term_start_date: '2025-02-01' },
    { name: 'T1', academic_year: null, term_start_date: '2025-08-01' },
    { name: 'T2', academic_year: null, term_start_date: '2026-02-01' },
  ]
  const base = {
    continuing: [
      { name: 'listed', student_name: 'Listed', status: 'Enrolled' },
      { name: 'active', student_name: 'Active', status: 'Enrolled' },
      { name: 'entering', student_name: 'Entering', status: 'Enrolled' },
      { name: 'later', student_name: 'Later', status: 'Enrolled' },
      { name: 'stray', student_name: 'Stray', status: 'Enrolled' },
    ],
    candidates: [candidate({ student: 'listed' })],
    entering: [enrolment('entering', 'One', 'T2', 0)],
    groups: [group('G1', 'One', 'T1')],
    members: [{ parent: 'G1', student: 'active', active: 1 }],
    sourceTerm: 'T1',
    terms,
    latest: [
      { student: 'later', program: 'One', academic_term: 'T2' },
      { student: 'stray', program: 'Two', academic_term: 'T0' },
    ],
  }

  it('lists only those enrolled in neither term, in no group, and in no later term', () => {
    const strays = findStrays(base)
    expect(strays.map((row) => row.student)).toEqual(['stray'])
    expect(strays[0]).toMatchObject({
      enrollment: 'student:stray',
      stray: true,
      program: 'Two',
      lastTerm: 'T0',
      offered: [],
    })
  })

  it('is suggested no change and never blocks Apply', () => {
    const [stray] = findStrays(base)
    expect(suggest(stray, SETTINGS)).toEqual({ program: null, status: null })
    expect(needsLeavingStatus(stray, { program: null, status: null }, SETTINGS)).toBe(false)
  })

  it('flags a listed student who is continuing but not active in the group', () => {
    expect(continuingWithoutGroup(candidate({ active: false }), SETTINGS)).toBe(true)
    expect(continuingWithoutGroup(candidate({ active: null }), SETTINGS)).toBe(true)
    expect(continuingWithoutGroup(candidate(), SETTINGS)).toBe(false)
    expect(continuingWithoutGroup(candidate({ status: 'Withdrawn', active: null }), SETTINGS)).toBe(false)
  })
})

describe('default terms', () => {
  const terms = [
    { name: 'Fall 26', academic_year: null, term_start_date: '2026-08-01' },
    { name: 'Spring 26', academic_year: null, term_start_date: '2026-02-01' },
    { name: 'Spring 27', academic_year: null, term_start_date: '2027-02-01' },
  ]

  it('advances the latest term with enrolments into the one after it', () => {
    expect(defaultTerms(terms, ['Spring 26'])).toEqual({ from: 'Spring 26', to: 'Fall 26' })
    expect(defaultTerms(terms, ['Spring 27'])).toEqual({ from: 'Spring 27', to: '' })
    expect(defaultTerms(terms, [])).toEqual({ from: '', to: '' })
  })
})
