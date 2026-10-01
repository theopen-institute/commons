import { describe, expect, it } from 'vitest'
import { adDayTitle, calendarMode, counterpartLabel, todayLabel } from './calendar'

/**
 * What `BikramDatePicker` shows of Bikram Sambat. On a site that uses it, the
 * picker is what it always was; on one that does not, nothing of that calendar
 * should leak through -- not the grid, not a tooltip, not the footer -- even for
 * a browser that remembers choosing it.
 */

// 2082 Baisakh 1, the first day of the year.
const NEW_YEAR = new Date(2025, 3, 14)
const NEW_YEAR_ISO = '2025-04-14'

describe('calendarMode', () => {
  it('draws the calendar this browser chose, where the site offers both', () => {
    expect(calendarMode('BS', true)).toBe('BS')
    expect(calendarMode('AD', true)).toBe('AD')
  })

  it('is always Gregorian on a site without Bikram Sambat', () => {
    expect(calendarMode('BS', false)).toBe('AD')
    expect(calendarMode('AD', false)).toBe('AD')
  })
})

describe('adDayTitle', () => {
  it('names the Bikram Sambat date beside the Gregorian where it is used', () => {
    const title = adDayTitle(NEW_YEAR, NEW_YEAR_ISO, true)
    expect(title.startsWith(`${NEW_YEAR_ISO} — `)).toBe(true)
    expect(title.length).toBeGreaterThan(NEW_YEAR_ISO.length + 3)
  })

  it('is only the Gregorian date elsewhere', () => {
    expect(adDayTitle(NEW_YEAR, NEW_YEAR_ISO, false)).toBe(NEW_YEAR_ISO)
  })

  it('is only the Gregorian date outside the Bikram Sambat tables', () => {
    expect(adDayTitle(new Date(1900, 0, 1), '1900-01-01', true)).toBe('1900-01-01')
  })
})

describe('counterpartLabel', () => {
  it('shows the other calendar where there are two', () => {
    expect(counterpartLabel(NEW_YEAR, NEW_YEAR_ISO, 'BS', true)).toBe(NEW_YEAR_ISO)
    const bs = counterpartLabel(NEW_YEAR, NEW_YEAR_ISO, 'AD', true)
    expect(bs).not.toBe('')
    expect(bs).not.toBe(NEW_YEAR_ISO)
  })

  it('shows nothing where there is one', () => {
    expect(counterpartLabel(NEW_YEAR, NEW_YEAR_ISO, 'AD', false)).toBe('')
    expect(counterpartLabel(NEW_YEAR, NEW_YEAR_ISO, 'BS', false)).toBe('')
  })

  it('shows nothing with no date', () => {
    expect(counterpartLabel(null, '', 'AD', true)).toBe('')
  })
})

describe('todayLabel', () => {
  it('speaks the language of the calendar on screen', () => {
    expect(todayLabel('AD')).toBe('Today')
    expect(todayLabel('BS')).toBe('आज')
  })
})
