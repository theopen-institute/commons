/**
 * Types for the shared Bikram Sambat module.
 *
 * The module itself is plain JavaScript under `commons/sambat/js/`,
 * because that tree is what esbuild globs to build the desk bundle and the desk
 * has no TypeScript. Rather than move it, or turn on `allowJs` for a directory
 * outside this project's root, its surface is declared here — which also keeps
 * the contract the SPA relies on written down in one place.
 *
 * `null` is the module's answer for anything outside the calendar it can
 * represent (from 13 April 1913 to the end of its table), never an exception; the optional
 * returns below are that promise in the type system.
 */
declare module '@sambat/bikram_sambat.js' {
  export interface BikramSambatDate {
    year: number
    month: number
    day: number
  }

  export type BikramSambatScript = 'devanagari' | 'latin'

  /** A site's calendar, as `commons.sambat.table` sends it. */
  export interface BikramSambatCalendar {
    first_year: number
    /** The Gregorian date, `YYYY-MM-DD`, of the first year's Baisakh 1. */
    epoch: string
    /** Twelve month lengths per year, from `first_year` on. */
    months: number[][]
  }

  /**
   * Convert with this calendar rather than the shipped one. Malformed leaves the
   * current table in place; `null` goes back to the shipped one. Returns whether
   * the site's calendar is in use.
   */
  export function use_calendar(calendar: BikramSambatCalendar | null | undefined): boolean

  export const MIN_BS_YEAR: number
  export const MAX_BS_YEAR: number

  /** Gregorian to Bikram Sambat. `null` outside the supported span. */
  export function from_gregorian(date: Date): BikramSambatDate | null

  /** Bikram Sambat to Gregorian, at local midnight. `null` if the day does not exist. */
  export function to_gregorian(bs: BikramSambatDate): Date | null

  export function days_in_month(year: number, month: number): number | null

  export function is_valid(bs: BikramSambatDate | null | undefined): boolean

  /** 0 for Sunday, matching `Date.prototype.getDay`. */
  export function weekday(bs: BikramSambatDate): number | null

  export function today(): BikramSambatDate | null

  /** Shift by whole months, clamping the day into the month it lands in. */
  export function add_months(
    bs: BikramSambatDate,
    delta: number,
  ): BikramSambatDate | null

  export function to_devanagari_digits(text: string | number): string

  export function month_name(month: number, script?: BikramSambatScript): string

  export function weekday_name(
    index: number,
    script?: BikramSambatScript,
  ): string

  /** `२०८१-०५-१८`, or `2081-05-18` with `{ script: 'latin' }`. */
  export function format(
    bs: BikramSambatDate | null | undefined,
    options?: { script?: BikramSambatScript },
  ): string
}

/** The shipped table, which tests read to build calendars of the server's shape. */
declare module '@sambat/calendar_data.js' {
  export const FIRST_BS_YEAR: number
  export const EPOCH_UTC_DAY: number
  export const MONTH_LENGTHS: string[]
}

/** Dates the government has published in both calendars, shared with the server's check. */
declare module '@sambat/confirmed_dates.json' {
  const dates: { bs: string; ad: string; what: string; source: string }[]
  export default dates
}
