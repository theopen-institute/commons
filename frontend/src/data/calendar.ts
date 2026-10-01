import { format, from_gregorian } from '@bikram/bikram_sambat.js'

/**
 * What a date picker shows of Bikram Sambat, given whether the site uses it.
 *
 * Pure, so the rules can be pinned without a browser: `BikramDatePicker` asks
 * these with the site's answer (`bikramSambatEnabled` in `data/features.ts`)
 * and draws whatever comes back. With the calendar off a picker is a plain
 * Gregorian one -- no toggle, no Bikram Sambat in a tooltip or a footer -- even
 * for a browser that remembers choosing it on a site where it was on.
 */

export type CalendarMode = 'AD' | 'BS'

/** The calendar to draw: the one this browser chose, if the site offers it. */
export function calendarMode(preferred: CalendarMode, bikramSambat: boolean): CalendarMode {
  return bikramSambat ? preferred : 'AD'
}

/** A Gregorian day cell's tooltip: its date, and the Bikram Sambat one where used. */
export function adDayTitle(date: Date, iso: string, bikramSambat: boolean): string {
  if (!bikramSambat) return iso
  const bs = from_gregorian(date)
  return bs ? `${iso} — ${format(bs)}` : iso
}

/**
 * The selected date in whichever calendar is not on screen, or nothing on a
 * site with only one calendar.
 */
export function counterpartLabel(
  date: Date | null,
  iso: string,
  mode: CalendarMode,
  bikramSambat: boolean,
): string {
  if (!date || !bikramSambat) return ''
  if (mode === 'BS') return iso
  const bs = from_gregorian(date)
  return bs ? format(bs) : ''
}

/** The footer's shortcut to today, in the language of the calendar on screen. */
export function todayLabel(mode: CalendarMode): string {
  return mode === 'BS' ? 'आज' : 'Today'
}
