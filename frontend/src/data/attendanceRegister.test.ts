import { describe, expect, it } from 'vitest'
import {
  buildRegister,
  CREDIT,
  formatHours,
  formatTime,
  markFields,
  nextMark,
  sessionHours,
  toMark,
  type GroupRow,
  type Mark,
  type MarkRow,
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
 * * `Present` plus `custom_late` read as anything but `Late`, in either
 *   direction, which silently rewrites a term of marks the first time one is
 *   saved.
 */

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
    custom_session_type: type,
    custom_session_details: null,
  }
}

function mark(session: string, who: string, value: Mark): MarkRow {
  return {
    name: `ATT-${session}-${who}`,
    course_schedule: session,
    student: who,
    ...markFields(value),
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
    expect(markFields('Late')).toEqual({ status: 'Present', custom_late: 1 })
  })

  // Explicitly off, not merely absent: a student marked late and then corrected
  // to present has a row with the flag already set, and an update that left the
  // field out would leave them late for ever.
  it('writes present back with the flag off', () => {
    expect(markFields('Present')).toEqual({ status: 'Present', custom_late: 0 })
  })

  it('survives the round trip for every mark', () => {
    for (const value of ['Present', 'Late', 'Absent'] as Mark[]) {
      const fields = markFields(value)
      expect(toMark(fields.status, fields.custom_late)).toBe(value)
    }
  })
})

describe('what one more click means', () => {
  it('offers present first, because that is what most of a register is', () => {
    expect(nextMark('')).toBe('Present')
  })

  it('goes round rather than needing an undo', () => {
    expect(nextMark('Present')).toBe('Late')
    expect(nextMark('Late')).toBe('Absent')
    expect(nextMark('Absent')).toBe('')
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
  const register = buildRegister({
    groups: [GROUP_A],
    students: [student('ann'), student('bob'), student('cal'), student('dee')],
    schedules: [schedule('one', '09:00:00', '11:00:00'), schedule('two', '09:00:00', '12:00:00')],
    marks: [
      mark('one', 'ann', 'Present'),
      mark('one', 'bob', 'Late'),
      mark('one', 'cal', 'Absent'),
      mark('two', 'ann', 'Present'),
      mark('two', 'bob', 'Present'),
      mark('two', 'cal', 'Present'),
    ],
  })
  const block = register.groups[0].blocks[0]

  it('foots the block to what was timetabled', () => {
    expect(block.scheduled).toBe(5)
  })

  it('credits the whole session for being there', () => {
    expect(block.credited.ann).toBe(5)
  })

  it('credits half a session for being late', () => {
    expect(block.credited.bob).toBe(4)
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
    expect(CREDIT['']).toBe(CREDIT.Absent)
  })

  it('foots every student in the group, so a column is never missing', () => {
    expect(Object.keys(block.credited).sort()).toEqual(['ann', 'bob', 'cal', 'dee'])
  })

  it('carries the document id behind each mark, which a change is addressed to', () => {
    expect(block.sessions[0].marks.ann.name).toBe('ATT-one-ann')
  })
})

describe('how a group is drawn', () => {
  const register = buildRegister({
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
  })
  const group = register.groups[0]

  it('orders blocks alphabetically with the untyped one last', () => {
    expect(group.blocks.map((block) => block.session_type)).toEqual([
      'Seminar',
      'Workshop',
      null,
    ])
  })

  it('puts only its own sessions in each block', () => {
    expect(group.blocks.map((block) => block.sessions.map((s) => s.name))).toEqual([
      ['s'],
      ['w'],
      ['u'],
    ])
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
    const bare = buildRegister({
      groups: [{ ...GROUP_A, student_group_name: null }],
      students: [],
      schedules: [],
      marks: [],
    })
    expect(bare.groups[0].title).toBe('Group A')
  })
})

describe('two groups on the same course', () => {
  // The bug this shape exists to make impossible. Both groups are on the same
  // programme and the same course, so a register that filtered its sessions
  // anywhere but per group would hand Group B a session it never had — and foot
  // its hours accordingly.
  const register = buildRegister({
    groups: [GROUP_A, { name: 'Group B', student_group_name: null, program: 'W&R', disabled: 0 }],
    students: [student('ann'), student('bob', 'Group B')],
    schedules: [schedule('one', '09:00:00', '11:00:00')],
    marks: [mark('one', 'ann', 'Present')],
  })

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
