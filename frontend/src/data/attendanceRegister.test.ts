import { describe, expect, it } from 'vitest'
import {
  buildRegister,
  credit,
  formatHours,
  formatTime,
  markChanges,
  markFieldList,
  markFields,
  markRow,
  marksOffered,
  NO_FIELDS,
  registerFields,
  scheduleFieldList,
  scheduleRow,
  sessionFields,
  pageThrough,
  resolveGroups,
  sessionHours,
  statedHours,
  toMark,
  type GroupResolution,
  type GroupRow,
  type Mark,
  type MarkRow,
  type RegisterFields,
  type ScheduleRow,
  type StudentRow,
} from './attendanceRegister'

/**
 * What the attendance register has to get right, and what would fail quietly.
 *
 * These were Python once, over a server that assembled the register itself.
 * They came here with the arithmetic when the reads moved to the document API
 * — see the module's own comment for why — and they are worth carrying across
 * rather than rewriting from the code, because each one names a bug that is
 * invisible on screen:
 *
 * * a late arrival credited as a full session, or as none, either of which is a
 *   plausible-looking number in a column of plausible-looking numbers;
 * * an unmarked student and an absent one treated as the same thing — they earn
 *   the same nothing, and they mean entirely different things to whoever is
 *   chasing attendance;
 * * a footing that is the sum of a different set of sessions from the ones
 *   drawn above it, which is what the register this replaced actually did: it
 *   totalled the *first* group's hours under every group on the page;
 * * `Present` plus the late flag read as anything but `Late`, in either
 *   direction, which silently rewrites a term of marks the first time one is
 *   saved;
 * * a field the site has not named being read, written or offered anyway,
 *   which on a site without it fails every read the page makes.
 */

/** The register this page was written for: its four fields, and late worth half. */
const REGISTER: RegisterFields = {
  late_field: 'custom_late',
  late_credit: 0.5,
  session_type_field: 'custom_session_type',
  session_details_field: 'custom_session_details',
  inactive_term_field: 'custom_inactive',
  session_hours_field: null,
  group_resolution: 'Programme',
  leave_counts_as: 'Absent',
}

function student(name: string, group = 'Group A'): StudentRow {
  return { parent: group, student: name, student_name: name.toUpperCase() }
}

function schedule(
  name: string,
  from: string,
  to: string,
  type: string | null = 'Seminar',
  group = 'Group A',
): ScheduleRow {
  return {
    name,
    student_group: group,
    schedule_date: '2025-09-01',
    from_time: from,
    to_time: to,
    session_type: type,
    session_details: null,
  }
}

function mark(session: string, who: string, value: Mark): MarkRow {
  return {
    name: `ATT-${session}-${who}`,
    course_schedule: session,
    student: who,
    status: value === 'Absent' ? 'Absent' : 'Present',
    late: value === 'Late' ? 1 : 0,
  }
}

const GROUP_A: GroupRow = {
  name: 'Group A',
  student_group_name: 'Semester 1',
  program: 'W&R',
  disabled: 0,
}

describe('what a mark means', () => {
  it('reads present as present', () => {
    expect(toMark('Present', 0)).toBe('Present')
  })

  it('reads present with the late flag as late', () => {
    expect(toMark('Present', 1)).toBe('Late')
  })

  it('reads absent as absent', () => {
    expect(toMark('Absent', 0)).toBe('Absent')
  })

  // Education's third status, which this register does not offer. It reads as
  // absent rather than as a fourth thing the grid would have to draw and the
  // footings would have to price. A mark made in the desk stays legible; it
  // just cannot be made from here.
  it('reads leave as absent', () => {
    expect(toMark('Leave', 0)).toBe('Absent')
  })

  it('writes late back as present with the flag', () => {
    expect(markFields('Late', REGISTER)).toEqual({
      status: 'Present',
      custom_late: 1,
    })
  })

  // Explicitly off, not merely absent: a student marked late and then corrected
  // to present has a row with the flag already set, and an update that left the
  // field out would leave them late for ever.
  it('writes present back with the flag off', () => {
    expect(markFields('Present', REGISTER)).toEqual({
      status: 'Present',
      custom_late: 0,
    })
  })

  it('survives the round trip for every mark', () => {
    for (const value of ['Present', 'Late', 'Absent'] as Mark[]) {
      const fields = markFields(value, REGISTER)
      expect(toMark(String(fields.status), Number(fields.custom_late))).toBe(
        value,
      )
    }
  })

  it('writes the flag under whatever the site calls it', () => {
    expect(
      markFields('Late', { ...REGISTER, late_field: 'arrived_late' }),
    ).toEqual({
      status: 'Present',
      arrived_late: 1,
    })
  })

  // A site with no late field: naming one would refuse every save.
  it('writes only the status where there is no late field', () => {
    expect(markFields('Present', NO_FIELDS)).toEqual({ status: 'Present' })
    expect(markFields('Absent', NO_FIELDS)).toEqual({ status: 'Absent' })
  })

  it('offers late only where there is a field to keep it in', () => {
    expect(marksOffered(REGISTER)).toEqual(['Present', 'Late', 'Absent', ''])
    expect(marksOffered(NO_FIELDS)).toEqual(['Present', 'Absent', ''])
  })
})

describe("which of the site's fields are used", () => {
  it('reads nothing the site has not named', () => {
    expect(scheduleFieldList(NO_FIELDS)).toEqual([
      'name',
      'student_group',
      'schedule_date',
      'from_time',
      'to_time',
    ])
    expect(markFieldList(NO_FIELDS)).toEqual([
      'name',
      'course_schedule',
      'student',
      'status',
    ])
  })

  it('reads what it has named', () => {
    expect(scheduleFieldList(REGISTER)).toContain('custom_session_type')
    expect(scheduleFieldList(REGISTER)).toContain('custom_session_details')
    expect(markFieldList(REGISTER)).toContain('custom_late')
  })

  it("brings a row under the register's own names", () => {
    const row = {
      name: 'CS-1',
      student_group: 'Group A',
      schedule_date: '2025-09-01',
      from_time: '9:00:00',
      to_time: '11:00:00',
      custom_session_type: 'Seminar',
      custom_session_details: 'Week one',
    }
    expect(scheduleRow(row, REGISTER)).toMatchObject({
      session_type: 'Seminar',
      session_details: 'Week one',
    })
    // The same row on a site that names neither: the values are not read even
    // if they happen to be there.
    expect(scheduleRow(row, NO_FIELDS)).toMatchObject({
      session_type: null,
      session_details: null,
    })
  })

  it('reads nobody as late without a late field', () => {
    const row = {
      name: 'SA-1',
      course_schedule: 'CS-1',
      student: 'ann',
      status: 'Present',
      custom_late: 1,
    }
    expect(markRow(row, REGISTER).late).toBe(1)
    expect(markRow(row, NO_FIELDS).late).toBe(0)
  })

  it("writes a session's type and details only into fields the site has", () => {
    const values = { session_type: 'Seminar', session_details: '' }
    expect(sessionFields(REGISTER, values)).toEqual({
      custom_session_type: 'Seminar',
      custom_session_details: null,
    })
    expect(sessionFields(NO_FIELDS, values)).toEqual({})
  })

  it('treats a missing answer as a site that named nothing', () => {
    expect(registerFields(null)).toEqual(NO_FIELDS)
    expect(registerFields({})).toEqual(NO_FIELDS)
  })

  it('holds the late credit between none and all of a session', () => {
    expect(registerFields({ late_credit: 0.5 }).late_credit).toBe(0.5)
    expect(registerFields({ late_credit: 0 }).late_credit).toBe(0)
    expect(registerFields({ late_credit: 2 }).late_credit).toBe(1)
    expect(registerFields({ late_credit: -1 }).late_credit).toBe(0)
    expect(registerFields({ late_credit: Number.NaN }).late_credit).toBe(1)
  })

  // The names go into filters and field lists. The server has checked them
  // against the meta; this is only so that nothing else ever gets that far.
  it('drops anything that is not a fieldname', () => {
    expect(
      registerFields({
        ...REGISTER,
        late_field: 'custom_late; drop',
        session_type_field: '',
      }).late_field,
    ).toBeNull()
    expect(
      registerFields({ ...REGISTER, inactive_term_field: ' custom_inactive ' })
        .inactive_term_field,
    ).toBe('custom_inactive')
  })
})

describe("what saving a session's marks writes", () => {
  const stored = {
    asmita: { name: 'SA-1', mark: 'Present' as Mark },
    bikash: { name: 'SA-2', mark: 'Absent' as Mark },
  }

  it('writes nothing for a draft that matches what is stored', () => {
    expect(
      markChanges(stored, { asmita: 'Present', bikash: 'Absent', chandra: '' }),
    ).toEqual({
      insert: [],
      update: [],
      remove: [],
    })
  })

  it('creates, changes and clears only what moved', () => {
    expect(
      markChanges(stored, { asmita: 'Late', bikash: '', chandra: 'Present' }),
    ).toEqual({
      insert: [{ student: 'chandra', mark: 'Present' }],
      update: [{ name: 'SA-1', mark: 'Late' }],
      remove: ['SA-2'],
    })
  })

  it('leaves alone a student the draft does not mention', () => {
    expect(markChanges(stored, {})).toEqual({
      insert: [],
      update: [],
      remove: [],
    })
  })
})

describe('how long a session is', () => {
  it('is its length in hours', () => {
    expect(sessionHours('09:00:00', '11:30:00')).toBe(2.5)
  })

  // Frappe sends a Time as `str(timedelta)`, which does not pad the hour: a
  // nine o'clock class arrives as `9:00:00`. Slicing fixed offsets instead of
  // splitting on the colon is how that becomes a register full of nonsense
  // every morning and nowhere else.
  it('reads an unpadded hour, which is what the API actually sends', () => {
    expect(sessionHours('8:00:00', '11:00:00')).toBe(3)
    expect(formatTime('8:05:00')).toBe('08:05')
    expect(formatTime('15:00:00')).toBe('15:00')
  })

  it('is worth nothing when a time is missing', () => {
    expect(sessionHours(null, '11:00:00')).toBe(0)
  })

  // Rather than a negative number. `Course Schedule` refuses to save one, so
  // this only defends the footings against a row that predates the check — but
  // a negative session would subtract itself from a term total, which is a
  // figure somebody would act on.
  it('is worth nothing when it runs backwards', () => {
    expect(sessionHours('11:00:00', '09:00:00')).toBe(0)
  })

  it('prints without trailing zeroes', () => {
    expect(formatHours(2.5)).toBe('2.5')
    expect(formatHours(3)).toBe('3')
    expect(formatHours(0)).toBe('0')
  })
})

describe('what a student earns', () => {
  const rows = {
    groups: [GROUP_A],
    students: [student('ann'), student('bob'), student('cal'), student('dee')],
    schedules: [
      schedule('one', '09:00:00', '11:00:00'),
      schedule('two', '09:00:00', '12:00:00'),
    ],
    marks: [
      mark('one', 'ann', 'Present'),
      mark('one', 'bob', 'Late'),
      mark('one', 'cal', 'Absent'),
      mark('two', 'ann', 'Present'),
      mark('two', 'bob', 'Present'),
      mark('two', 'cal', 'Present'),
    ],
  }
  const register = buildRegister(rows, REGISTER)
  const block = register.groups[0].blocks[0]

  it('foots the block to what was timetabled', () => {
    expect(block.scheduled).toBe(5)
  })

  it('credits the whole session for being there', () => {
    expect(block.credited.ann).toBe(5)
  })

  it("credits a late arrival with the site's share of the session", () => {
    // Half of the 2h session, on the register's own rule.
    expect(block.credited.bob).toBe(4)
  })

  it('takes that share from the setting, not from this file', () => {
    expect(buildRegister(rows, { ...REGISTER, late_credit: 1 }).groups[0].blocks[0].credited.bob).toBe(5)
    expect(buildRegister(rows, { ...REGISTER, late_credit: 0 }).groups[0].blocks[0].credited.bob).toBe(3)
    expect(buildRegister(rows, { ...REGISTER, late_credit: 0.25 }).groups[0].blocks[0].credited.bob).toBe(3.5)
  })

  it('credits none of it for being absent', () => {
    expect(block.credited.cal).toBe(3)
  })

  // Dee has no mark against either session, which is what an untouched cell
  // means and is the state the grid draws as blank. Both earn nothing; nothing
  // anywhere turns one into the other.
  it('keeps unmarked and absent apart', () => {
    expect(block.credited.dee).toBe(0)
    expect(block.sessions[0].marks.dee).toBeUndefined()
    expect(block.sessions[0].marks.cal.mark).toBe('Absent')
    expect(credit('', 0.5)).toBe(credit('Absent', 0.5))
  })

  it('foots every student in the group, so a column is never missing', () => {
    expect(Object.keys(block.credited).sort()).toEqual([
      'ann',
      'bob',
      'cal',
      'dee',
    ])
  })

  it('carries the document id behind each mark, which a change is addressed to', () => {
    expect(block.sessions[0].marks.ann.name).toBe('ATT-one-ann')
  })
})

describe('how a group is drawn', () => {
  const register = buildRegister(
    {
      groups: [GROUP_A],
      students: [student('ann'), student('bob')],
      schedules: [
        schedule('w', '09:00:00', '11:00:00', 'Workshop'),
        schedule('s', '09:00:00', '12:00:00', 'Seminar'),
        schedule('u', '09:00:00', '10:00:00', null),
      ],
      marks: [
        mark('w', 'ann', 'Present'),
        mark('w', 'bob', 'Absent'),
        mark('s', 'ann', 'Late'),
        mark('s', 'bob', 'Present'),
        mark('u', 'ann', 'Present'),
      ],
    },
    REGISTER,
  )
  const group = register.groups[0]

  it('orders blocks alphabetically with the untyped one last', () => {
    expect(group.blocks.map((block) => block.session_type)).toEqual([
      'Seminar',
      'Workshop',
      null,
    ])
  })

  it('puts only its own sessions in each block', () => {
    expect(
      group.blocks.map((block) => block.sessions.map((s) => s.name)),
    ).toEqual([['s'], ['w'], ['u']])
  })

  it('foots the group to the sum of its blocks', () => {
    expect(group.scheduled).toBe(6)
    expect(group.scheduled).toBe(
      group.blocks.reduce((total, block) => total + block.scheduled, 0),
    )
  })

  it('foots a student to the sum of their blocks', () => {
    // Ann: present at the 2h workshop, late for the 3h seminar, present at the
    // 1h untyped session.
    expect(group.credited.ann).toBe(4.5)
    expect(group.credited.bob).toBe(3)
  })

  it('titles a group by its own name, falling back to its id', () => {
    expect(group.title).toBe('Semester 1')
    const bare = buildRegister(
      {
        groups: [{ ...GROUP_A, student_group_name: null }],
        students: [],
        schedules: [],
        marks: [],
      },
      REGISTER,
    )
    expect(bare.groups[0].title).toBe('Group A')
  })
})

describe('two groups on the same course', () => {
  // The bug this shape exists to make impossible. Both groups are on the same
  // programme and the same course, so a register that filtered its sessions
  // anywhere but per group would hand Group B a session it never had — and foot
  // its hours accordingly.
  const register = buildRegister(
    {
      groups: [
        GROUP_A,
        {
          name: 'Group B',
          student_group_name: null,
          program: 'W&R',
          disabled: 0,
        },
      ],
      students: [student('ann'), student('bob', 'Group B')],
      schedules: [schedule('one', '09:00:00', '11:00:00')],
      marks: [mark('one', 'ann', 'Present')],
    },
    REGISTER,
  )

  it('gives each group only its own students', () => {
    expect(register.groups[0].students.map((s) => s.student)).toEqual(['ann'])
    expect(register.groups[1].students.map((s) => s.student)).toEqual(['bob'])
  })

  it('gives each group only its own sessions and its own total', () => {
    expect(register.groups[0].scheduled).toBe(2)
    expect(register.groups[1].blocks).toEqual([])
    expect(register.groups[1].scheduled).toBe(0)
    expect(register.groups[1].credited.bob).toBe(0)
  })
})

describe('a site that keeps no session type', () => {
  // Every session reads as untyped, so they are one block and one footing: the
  // page draws that block without a heading.
  const register = buildRegister(
    {
      groups: [GROUP_A],
      students: [student('ann')],
      schedules: [
        scheduleRow(
          {
            name: 'a',
            student_group: 'Group A',
            from_time: '9:00:00',
            to_time: '10:00:00',
            custom_session_type: 'Seminar',
          },
          NO_FIELDS,
        ),
        scheduleRow(
          {
            name: 'b',
            student_group: 'Group A',
            from_time: '9:00:00',
            to_time: '11:00:00',
            custom_session_type: 'Workshop',
          },
          NO_FIELDS,
        ),
      ],
      marks: [],
    },
    NO_FIELDS,
  )

  it('puts every session in one block', () => {
    expect(
      register.groups[0].blocks.map((block) => block.session_type),
    ).toEqual([null])
    expect(register.groups[0].blocks[0].sessions.map((s) => s.name)).toEqual([
      'a',
      'b',
    ])
    expect(register.groups[0].scheduled).toBe(3)
  })
})

describe('the rules a site chooses', () => {
  it("defaults to the register's behaviour before they were settings", () => {
    expect(registerFields({})).toMatchObject({
      group_resolution: 'Programme',
      leave_counts_as: 'Absent',
      session_hours_field: null,
    })
  })

  it('keeps an option it offers and drops one it does not', () => {
    expect(registerFields({ group_resolution: 'Both' }).group_resolution).toBe(
      'Both',
    )
    expect(
      registerFields({ group_resolution: 'Everything' as GroupResolution })
        .group_resolution,
    ).toBe('Programme')
    expect(registerFields({ leave_counts_as: 'Excused' }).leave_counts_as).toBe(
      'Excused',
    )
  })
})

describe('what leave counts as', () => {
  const leave: MarkRow = {
    name: 'ATT-two-ann',
    course_schedule: 'two',
    student: 'ann',
    status: 'Leave',
    late: 0,
  }
  const rows = {
    groups: [GROUP_A],
    students: [student('ann'), student('bob')],
    schedules: [
      schedule('one', '09:00:00', '11:00:00'),
      schedule('two', '09:00:00', '12:00:00'),
    ],
    marks: [
      mark('one', 'ann', 'Present'),
      leave,
      mark('one', 'bob', 'Present'),
      mark('two', 'bob', 'Absent'),
    ],
  }

  it('reads leave as absent by default, as the register always did', () => {
    expect(toMark('Leave', 0, 'Absent')).toBe('Absent')
    const block = buildRegister(rows, REGISTER).groups[0].blocks[0]
    expect(block.sessions[1].marks.ann.mark).toBe('Absent')
    expect(block.credited.ann).toBe(2)
    expect(block.possible.ann).toBe(5)
  })

  it('reads leave as excused where the site says so', () => {
    expect(toMark('Leave', 0, 'Excused')).toBe('Excused')
    // Only leave: an absence is still an absence.
    expect(toMark('Absent', 0, 'Excused')).toBe('Absent')
  })

  // Ann was excused the 3h session: it is out of her total both ways, so she
  // has 2 of a possible 2. Bob, absent from it, still has 2 of 5.
  it('leaves an excused session out of earned and possible hours alike', () => {
    const group = buildRegister(rows, { ...REGISTER, leave_counts_as: 'Excused' })
      .groups[0]
    const block = group.blocks[0]
    expect(block.sessions[1].marks.ann.mark).toBe('Excused')
    expect(block.scheduled).toBe(5)
    expect(block.credited.ann).toBe(2)
    expect(block.possible.ann).toBe(2)
    expect(block.credited.bob).toBe(2)
    expect(block.possible.bob).toBe(5)
    expect(group.possible).toEqual({ ann: 2, bob: 5 })
    expect(group.credited).toEqual({ ann: 2, bob: 2 })
  })

  it('counts an unmarked session as possible', () => {
    const block = buildRegister(
      { ...rows, students: [...rows.students, student('cal')] },
      { ...REGISTER, leave_counts_as: 'Excused' },
    ).groups[0].blocks[0]
    expect(block.possible.cal).toBe(5)
  })

  it('writes excused back as leave, should it ever be written', () => {
    expect(markFields('Excused', REGISTER)).toEqual({
      status: 'Leave',
      custom_late: 0,
    })
  })

  it('is not offered as a mark to make', () => {
    expect(marksOffered({ ...REGISTER, leave_counts_as: 'Excused' })).not.toContain(
      'Excused',
    )
  })
})

describe("a session's own hours", () => {
  const HOURS: RegisterFields = { ...REGISTER, session_hours_field: 'custom_hours' }

  it('reads the hours field only where the site names one', () => {
    expect(scheduleFieldList(HOURS)).toContain('custom_hours')
    expect(scheduleFieldList(REGISTER)).not.toContain('custom_hours')
  })

  it('overrides the times where the field has a value', () => {
    const row = {
      name: 'a',
      student_group: 'Group A',
      from_time: '9:00:00',
      to_time: '10:00:00',
      custom_hours: 1.5,
    }
    const register = buildRegister(
      {
        groups: [GROUP_A],
        students: [student('ann')],
        schedules: [
          scheduleRow(row, HOURS),
          scheduleRow({ ...row, name: 'b', custom_hours: 0 }, HOURS),
          scheduleRow({ ...row, name: 'c' }, REGISTER),
        ],
        marks: [mark('a', 'ann', 'Present')],
      },
      HOURS,
    )
    const sessions = register.groups[0].blocks[0].sessions
    // 1.5 stated; 0 is a number field nobody filled in, so the times decide;
    // and on a site with no hours field the value is never read.
    expect(sessions.map((session) => session.hours)).toEqual([1.5, 1, 1])
    expect(register.groups[0].scheduled).toBe(3.5)
    expect(register.groups[0].credited.ann).toBe(1.5)
  })

  it('takes only a positive number as set', () => {
    expect(statedHours(2)).toBe(2)
    expect(statedHours('2.5')).toBe(2.5)
    expect(statedHours(0)).toBeNull()
    expect(statedHours(-1)).toBeNull()
    expect(statedHours(null)).toBeNull()
    expect(statedHours('')).toBeNull()
    expect(statedHours('two')).toBeNull()
    expect(sessionHours('09:00:00', '10:00:00', 4)).toBe(4)
  })
})

describe('reading a list to its end', () => {
  /** A list of `total` rows, served a page at a time, with each request kept. */
  function server(total: number) {
    const asked: [number, number][] = []
    const rows = Array.from({ length: total }, (_, index) => index)
    return {
      asked,
      fetchPage: async (start: number, length: number) => {
        asked.push([start, length])
        return rows.slice(start, start + length)
      },
    }
  }

  it('pages through until a page comes back short', async () => {
    const list = server(1234)
    const result = await pageThrough(list.fetchPage, 500)
    expect(result.rows).toHaveLength(1234)
    expect(result.rows.at(-1)).toBe(1233)
    expect(result.complete).toBe(true)
    expect(list.asked).toEqual([
      [0, 500],
      [500, 500],
      [1000, 500],
    ])
  })

  it('asks once more when the last page is exactly full', async () => {
    const list = server(1000)
    const result = await pageThrough(list.fetchPage, 500)
    expect(result).toMatchObject({ complete: true })
    expect(result.rows).toHaveLength(1000)
    expect(list.asked).toHaveLength(3)
  })

  it('reads an empty list in one request', async () => {
    const list = server(0)
    expect(await pageThrough(list.fetchPage, 500)).toEqual({
      rows: [],
      complete: true,
    })
    expect(list.asked).toHaveLength(1)
  })

  it('says so when it stops at the ceiling', async () => {
    const list = server(30)
    const result = await pageThrough(list.fetchPage, 10, 25)
    expect(result.rows).toHaveLength(25)
    expect(result.complete).toBe(false)
    expect(list.asked).toEqual([
      [0, 10],
      [10, 10],
      [20, 5],
      [25, 1],
    ])
  })

  it('is complete when the list is exactly the ceiling', async () => {
    const result = await pageThrough(server(25).fetchPage, 10, 25)
    expect(result).toMatchObject({ complete: true })
    expect(result.rows).toHaveLength(25)
  })

  it('passes a refusal straight through', async () => {
    await expect(
      pageThrough(async () => {
        throw new Error('Not permitted')
      }),
    ).rejects.toThrow('Not permitted')
  })
})

describe('which groups take a course', () => {
  // W&R teaches the course; Group C is course-based and names it itself; Group
  // A is both on the programme and course-based.
  const BY_PROGRAMME: GroupRow[] = [
    { ...GROUP_A },
    { name: 'Group B', student_group_name: null, program: 'W&R', disabled: 0 },
  ]
  const BY_COURSE: GroupRow[] = [
    { name: 'Group C', student_group_name: null, program: null, disabled: 0 },
    { ...GROUP_A },
  ]

  function reads(programmes: string[] = ['W&R', 'W&R']) {
    const asked: unknown[][][] = []
    const programmesAsked: string[] = []
    return {
      asked,
      programmesAsked,
      reads: {
        programmes: async (course: string) => {
          programmesAsked.push(course)
          return programmes
        },
        groups: async (filters: unknown[][]) => {
          asked.push(filters)
          const course = filters.find((filter) => filter[0] === 'course')
          return course ? BY_COURSE : BY_PROGRAMME
        },
      },
    }
  }

  const names = (rows: GroupRow[]) => rows.map((row) => row.name)

  it("by programme, as the register always did", async () => {
    const read = reads()
    const groups = await resolveGroups('Programme', 'T1', 'CEM', read.reads)
    expect(names(groups)).toEqual(['Group A', 'Group B'])
    expect(read.programmesAsked).toEqual(['CEM'])
    expect(read.asked).toEqual([
      [
        ['academic_term', '=', 'T1'],
        ['program', 'in', ['W&R']],
      ],
    ])
  })

  it('by programme finds nothing where no programme teaches it', async () => {
    const read = reads([])
    expect(await resolveGroups('Programme', 'T1', 'CEM', read.reads)).toEqual([])
    expect(read.asked).toEqual([])
  })

  it("by course, through course-based groups' own field", async () => {
    const read = reads()
    const groups = await resolveGroups('Course', 'T1', 'CEM', read.reads)
    expect(names(groups)).toEqual(['Group A', 'Group C'])
    expect(read.programmesAsked).toEqual([])
    expect(read.asked).toEqual([
      [
        ['academic_term', '=', 'T1'],
        ['course', '=', 'CEM'],
      ],
    ])
  })

  it('both ways, each group once and in order', async () => {
    const read = reads()
    const groups = await resolveGroups('Both', 'T1', 'CEM', read.reads)
    expect(names(groups)).toEqual(['Group A', 'Group B', 'Group C'])
    expect(read.asked).toHaveLength(2)
  })

  it('both ways still finds course-based groups with no programme', async () => {
    const groups = await resolveGroups('Both', 'T1', 'CEM', reads([]).reads)
    expect(names(groups)).toEqual(['Group A', 'Group C'])
  })
})
