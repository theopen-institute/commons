import { describe, expect, it } from 'vitest'
import { format, from_gregorian, to_gregorian } from '@sambat/bikram_sambat.js'
import confirmed from '@sambat/confirmed_dates.json'

/**
 * The shipped calendar table against dates the government has published, rather
 * than against another converter: the days public holidays fell on, from the
 * Ministry of Home Affairs' lists. The server checks every calendar it fetches
 * against the same file (`commons.sambat.table.validate`), so a
 * date added there guards both.
 */

const day = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

describe('Bikram Sambat table', () => {
  it.each(confirmed.map((date) => [date.bs, date.ad, date.what]))(
    'puts %s on %s (%s)',
    (bs, iso) => {
      const [year, month, dayOfMonth] = bs.split('-').map(Number)
      expect(format(from_gregorian(day(iso)), { script: 'latin' })).toBe(bs)
      expect(to_gregorian({ year, month, day: dayOfMonth })?.getTime()).toBe(day(iso).getTime())
    },
  )

  it('answers nothing past the end of the table, rather than a thirteenth month', () => {
    expect(format(from_gregorian(day('2039-04-13')), { script: 'latin' })).toBe('2095-12-30')
    expect(from_gregorian(day('2039-04-14'))).toBeNull()
    expect(from_gregorian(day('1913-04-12'))).toBeNull()
  })
})
