import { afterEach, describe, expect, it } from 'vitest'
import * as bs from '@sambat/bikram_sambat.js'
import { MONTH_LENGTHS } from '@sambat/calendar_data.js'

/**
 * Converting with the calendar a site sends at boot (`use_calendar`), which the
 * server keeps current from opensource-nepal's. Its own file, because loading a
 * calendar changes the module's table for every test after it.
 */

const day = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}
const latin = (date: Date) => bs.format(bs.from_gregorian(date), { script: 'latin' })

// The shipped rows from BS 2000, shaped the way the server sends them, and three
// more years past where the shipped table ends.
const fromTwoThousand = MONTH_LENGTHS.slice(2000 - 1970).map((row: string) =>
  Array.from(row, (character) => Number(character) + 28),
)
const later = ['343432221123', '333433122122', '334333212122'].map((row) =>
  Array.from(row, (character) => Number(character) + 28),
)
const site = { first_year: 2000, epoch: '1943-04-14', months: [...fromTwoThousand, ...later] }

afterEach(() => bs.use_calendar(null))

describe('use_calendar', () => {
  it('converts with the site calendar, past where the shipped table ends', () => {
    expect(bs.from_gregorian(day('2040-01-01'))).toBeNull()
    expect(bs.use_calendar(site)).toBe(true)
    expect(bs.MAX_BS_YEAR).toBe(2098)
    expect(latin(day('2040-01-01'))).toMatch(/^2096-/)
    expect(latin(day('2026-01-15'))).toBe('2082-10-01')
  })

  it('keeps the shipped years before it where the two meet on the same day', () => {
    bs.use_calendar(site)
    expect(bs.MIN_BS_YEAR).toBe(1970)
    expect(latin(day('1913-04-13'))).toBe('1970-01-01')
  })

  it('drops them where the two do not meet, rather than shift every one', () => {
    bs.use_calendar({ ...site, epoch: '1943-04-15' })
    expect(bs.MIN_BS_YEAR).toBe(2000)
    expect(bs.from_gregorian(day('1930-01-01'))).toBeNull()
  })

  it('takes the changes a site has fetched', () => {
    const changed = site.months.map((row) => row.slice())
    // Move a day from Kartik to Mangsir in BS 2083.
    changed[83][6] -= 1
    changed[83][7] += 1
    bs.use_calendar({ ...site, months: changed })
    expect(latin(day('2026-11-16'))).toBe('2083-08-01')
  })

  it('leaves the table alone when what it is handed is not a calendar', () => {
    bs.use_calendar(site)
    const broken = site.months.map((row) => row.slice())
    broken[10][0] = 33
    expect(bs.use_calendar({ ...site, months: broken })).toBe(false)
    expect(bs.use_calendar({ ...site, months: [] })).toBe(false)
    expect(bs.use_calendar({ first_year: 2000, epoch: 'soon', months: site.months })).toBe(false)
    expect(bs.MAX_BS_YEAR).toBe(2098)
  })

  it('goes back to the shipped table with no calendar', () => {
    bs.use_calendar(site)
    expect(bs.use_calendar(null)).toBe(false)
    expect(bs.MAX_BS_YEAR).toBe(2095)
  })
})
