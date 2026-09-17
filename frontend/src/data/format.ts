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

/**
 * "412 KB" — a file's size, at the precision a person reading a list of
 * receipts cares about: whether this is the photo or the thumbnail.
 *
 * Powers of 1024 with the short units, which is what every file manager the
 * reader has ever used shows them.
 */
export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB'
  const units = ['B', 'KB', 'MB', 'GB']
  const power = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const size = bytes / 1024 ** power
  // Whole numbers above a kilobyte: a receipt is not more legible for being
  // 412.3 KB rather than 412 KB.
  return `${power === 0 || size >= 10 ? Math.round(size) : size.toFixed(1)} ${units[power]}`
}

/**
 * Prefix a bare host with `https`, so a link pasted from the address bar is
 * accepted as typed.
 *
 * `reference_url` is a Frappe `Data(URL)` field and that check wants a scheme,
 * which browsers increasingly hide — so what a requester copies often has none.
 * Supplying it here is kinder than bouncing the row back over something we can
 * fix ourselves, and it belongs with the form that collects the link rather
 * than with the document that stores it.
 */
export function withScheme(url?: string | null): string {
  const link = (url ?? '').trim()
  // Whitespace inside is the mark of something that was never a link. Left
  // alone it fails the server's check, which is the answer wanted here —
  // adding a scheme would only turn a plain sentence into a passing "URL".
  if (!link || link.startsWith('/') || link.includes(' ')) return link
  return /^[a-z][a-z0-9+.-]*:/i.test(link) ? link : `https://${link}`
}
