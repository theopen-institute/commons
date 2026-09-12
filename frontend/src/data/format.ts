const dateFormatter = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

/**
 * Parse a Frappe date (`YYYY-MM-DD`) as a local date.
 *
 * Deliberately not `new Date(string)`: a bare YYYY-MM-DD is parsed as UTC
 * midnight, which renders as the day before for anyone west of it.
 */
function parseDate(value?: string | null): Date | null {
  if (!value) return null
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day)
}

/** Renders a Frappe date in the viewer's locale. */
export function formatDate(value?: string | null): string {
  const date = parseDate(value)
  if (!date) return value || '—'
  return dateFormatter.format(date)
}

/**
 * A leave period as one phrase, e.g. "Sep 21 – 23, 2026".
 *
 * `formatRange` rather than two formatted dates joined by a dash: it collapses
 * the shared month and year, and does so in the order the viewer's locale
 * actually uses — hand-rolling that produced "21–Sep 23, 2026" under a
 * month-first locale.
 */
export function formatDateRange(
  from?: string | null,
  to?: string | null,
): string {
  const start = parseDate(from)
  const end = parseDate(to)
  if (!start || !end) return formatDate(from || to)
  if (from === to) return dateFormatter.format(start)
  return dateFormatter.formatRange(start, end)
}

type BadgeTheme = 'gray' | 'blue' | 'green' | 'amber' | 'red'

export function statusTheme(status?: string | null): BadgeTheme {
  switch (status) {
    case 'Active':
      return 'green'
    case 'Suspended':
      return 'amber'
    case 'Left':
      return 'red'
    default:
      return 'gray'
  }
}

const currencyFormatters = new Map<string, Intl.NumberFormat>()

/**
 * An amount in the document's own currency.
 *
 * The currency comes off the record rather than the browser: a request raised
 * against a GBP company reads in GBP wherever it is opened. Falls back to a
 * plain number when the record has no currency yet — an unsaved draft — rather
 * than guessing one.
 */
export function formatCurrency(
  value?: number | null,
  currency?: string | null,
): string {
  const amount = value ?? 0
  if (!currency) return amount.toLocaleString(undefined, { maximumFractionDigits: 2 })

  let formatter = currencyFormatters.get(currency)
  if (!formatter) {
    formatter = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      // Whole units read better in a list of estimates; the pennies on an
      // estimate are noise.
      maximumFractionDigits: 0,
    })
    currencyFormatters.set(currency, formatter)
  }
  return formatter.format(amount)
}

/** "3 items" / "1 item" — the count, said properly. */
export function pluralise(count: number, singular: string, plural?: string) {
  return `${count} ${count === 1 ? singular : (plural ?? `${singular}s`)}`
}
