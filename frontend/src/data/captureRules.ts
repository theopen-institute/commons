import { to_gregorian } from '@bikram/bikram_sambat.js'

/**
 * Turning what Claude read off a scan into a draft Purchase Invoice, and the
 * checks that tell a bookkeeper where to look again.
 *
 * Pure, like `reconciliationRules.ts`, and tested the same way (`yarn test`).
 * Nothing here is fetched or written.
 *
 * Two things are decided here and nowhere else:
 *
 * * **Dates.** The scan's dates come back as printed, with the calendar they
 *   are in, because Nepali invoices are often dated in Bikram Sambat and a
 *   model asked to convert one would do the arithmetic badly. They are
 *   converted here, with the same tables `BikramDatePicker` draws from.
 * * **What counts as not adding up.** The page never corrects a figure. It
 *   compares what the scan says with what the draft will book and says so
 *   where they differ.
 */

export interface ScannedDate {
  printed: string
  year: number
  month: number
  day: number
  calendar: 'AD' | 'BS'
}

export interface ScannedParty {
  name: string | null
  tax_id: string | null
}

export interface ScannedLine {
  description: string
  quantity: number
  rate: number
  amount: number
}

export interface ScannedTax {
  label: string
  rate: number | null
  amount: number
}

/** What `commons.document_capture.purchase_invoice.SCHEMA` asks for. */
export interface ScannedInvoice {
  is_invoice: boolean
  supplier: ScannedParty
  buyer: ScannedParty
  invoice_number: string | null
  invoice_date: ScannedDate | null
  due_date: ScannedDate | null
  currency: string | null
  lines: ScannedLine[]
  discount: number | null
  /** The lines' total before tax, as printed. Null where the page prints
   *  none, which many do. */
  subtotal: number | null
  taxes: ScannedTax[]
  total: number | null
  notes: string[]
}

export interface SupplierCandidate {
  name: string
  supplier_name: string | null
  tax_id: string | null
  reason: string
  /** Close enough to choose without asking. */
  strong: boolean
}

export interface CompanyRow {
  name: string
  company_name: string | null
  tax_id: string | null
  default_currency: string | null
}

/** What `read_invoice` answers. */
export interface Reading {
  extracted: ScannedInvoice
  companies: CompanyRow[]
  company: { name: string | null; reason: string | null }
  suppliers: SupplierCandidate[]
  model: string
}

export interface DraftLine {
  /** Local only, for `v-for`. */
  key: number
  description: string
  qty: number | null
  rate: number | null
  /**
   * The row total, as printed. Not sent to the server: ERPNext books quantity
   * × rate, and recomputes the amount from them. It is here to check those two
   * against, because a row whose figures do not multiply out is usually a
   * misread digit or a discount printed on the line.
   */
  amount: number | null
  expense_account: string
  /** Why this account, from `suggest`. Cleared when the reader picks one. */
  reason: string
  review: boolean
  /** The line as the scan printed it, or null for a line the reader added. */
  scanned: ScannedLine | null
}

export interface Draft {
  company: string
  supplier: string
  /** Set when the reader chose to make the supplier rather than pick one. */
  newSupplier: { supplier_name: string; tax_id: string } | null
  bill_no: string
  bill_date: string
  posting_date: string
  due_date: string
  discount_amount: number | null
  /** A tax option's key from `suggest`: `none`, `template:…` or `invoice:…`. */
  taxes: string
  lines: DraftLine[]
}

/** Amounts closer than this are the same amount. The scan's figures are to
 *  the paisa or cent, and so are ERPNext's. */
export const TOLERANCE = 0.005

function pad(value: number) {
  return String(value).padStart(2, '0')
}

/**
 * A scanned date as `YYYY-MM-DD` Gregorian, or null if it does not exist.
 *
 * A Gregorian date is checked by building it and reading it back, because
 * `Date.UTC(2026, 1, 30)` is quietly the 2nd of March and a misread "30/02"
 * should come back as nothing, not as a different day.
 */
export function isoDate(date: ScannedDate | null | undefined): string | null {
  if (!date) return null
  const { year, month, day } = date
  if (![year, month, day].every(Number.isInteger)) return null

  if (date.calendar === 'BS') {
    const gregorian = to_gregorian({ year, month, day })
    if (!gregorian) return null
    return `${gregorian.getFullYear()}-${pad(gregorian.getMonth() + 1)}-${pad(gregorian.getDate())}`
  }

  const built = new Date(Date.UTC(year, month - 1, day))
  if (built.getUTCFullYear() !== year || built.getUTCMonth() !== month - 1 || built.getUTCDate() !== day) {
    return null
  }
  return `${year}-${pad(month)}-${pad(day)}`
}

/** "2081-05-12 B.S." as the reader would recognise it, for the note beside
 *  a converted date. */
export function printedDate(date: ScannedDate | null | undefined): string {
  if (!date) return ''
  return date.calendar === 'BS' ? `${date.printed} (Bikram Sambat)` : date.printed
}

let nextKey = 0

export function blankLine(): DraftLine {
  return {
    key: nextKey++,
    description: '',
    qty: 1,
    rate: null,
    amount: null,
    expense_account: '',
    reason: '',
    review: false,
    scanned: null,
  }
}

/**
 * The draft a reading starts from.
 *
 * The supplier is filled in only for a strong candidate: a similar name is a
 * suggestion to accept, not an answer. The posting date is the invoice's own,
 * which is how this site books them; `today` stands in where the scan has no
 * date that exists.
 */
export function draftFrom(reading: Reading, today: string): Draft {
  const scanned = reading.extracted
  const best = reading.suppliers[0]
  const billDate = isoDate(scanned.invoice_date)
  return {
    company: reading.company.name ?? '',
    supplier: best?.strong ? best.name : '',
    newSupplier: null,
    bill_no: scanned.invoice_number ?? '',
    bill_date: billDate ?? '',
    posting_date: billDate ?? today,
    due_date: isoDate(scanned.due_date) ?? '',
    discount_amount: scanned.discount || null,
    taxes: 'none',
    lines: scanned.lines.map((line) => ({
      ...blankLine(),
      description: line.description,
      qty: line.quantity || 1,
      rate: line.rate,
      amount: line.amount,
      scanned: line,
    })),
  }
}

/** What ERPNext will book for a line: quantity × rate. */
export function lineAmount(line: DraftLine): number {
  return money((line.qty ?? 0) * (line.rate ?? 0))
}

/** The line's row total where it has one, and what it books where it does
 *  not: a line the reader added and gave no total. */
export function rowTotal(line: DraftLine): number {
  return line.amount ?? lineAmount(line)
}

function same(a: number, b: number): boolean {
  return Math.abs(a - b) <= TOLERANCE
}

export function money(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * Where a line does not add up by itself: quantity × rate is one figure and the
 * row total another. On a scan that is usually a misread digit, sometimes a
 * discount printed on the line. It is the reader's to settle, so this says so
 * and `lineFixes` offers the ways to settle it.
 *
 * Read off the draft rather than the scan, so it clears when the reader fixes
 * the line and comes back if a later edit breaks it again.
 */
export function lineProblem(line: DraftLine): string | null {
  if (line.amount === null || line.qty === null || line.rate === null) return null
  const booked = lineAmount(line)
  if (same(booked, line.amount)) return null
  const printed =
    line.scanned !== null &&
    line.qty === line.scanned.quantity &&
    line.rate === line.scanned.rate &&
    line.amount === line.scanned.amount
  return (
    `${printed ? 'As printed, ' : ''}${line.qty} × ${line.rate} is ${booked}, but the row total is ` +
    `${line.amount}. The invoice books ${booked}.`
  )
}

export interface LineFix {
  label: string
  values: Partial<Pick<DraftLine, 'qty' | 'rate' | 'amount'>>
}

/**
 * The ways to make a line that does not add up agree with itself, trusting
 * one figure or the other.
 *
 * Trusting the row total keeps the quantity when the total divides by it to
 * the cent, and otherwise books the row as one of the total: 100 for three
 * items is not a rate ERPNext can hold, and 3 × 33.33 would book 99.99.
 */
export function lineFixes(line: DraftLine): LineFix[] {
  if (!lineProblem(line) || line.amount === null || !line.qty || line.rate === null) return []
  const fixes: LineFix[] = []
  const rate = money(line.amount / line.qty)
  if (same(money(line.qty * rate), line.amount)) {
    fixes.push({ label: `Make the rate ${rate}`, values: { rate } })
  } else {
    fixes.push({ label: `Book it as 1 × ${line.amount}`, values: { qty: 1, rate: line.amount } })
  }
  const booked = lineAmount(line)
  fixes.push({ label: `Make the row total ${booked}`, values: { amount: booked } })
  return fixes
}

/**
 * Whether the rows add up to the subtotal printed under them. If they do not,
 * a line is missing, extra or misread, and the reader should hear so before
 * they reach the bill's total.
 *
 * A printed subtotal can be before the invoice's discount or after it, so
 * either counts. Null where the scan prints no subtotal.
 */
export function rowsMatchSubtotal(draft: Draft, scanned: ScannedInvoice): boolean | null {
  if (scanned.subtotal === null || scanned.subtotal === undefined) return null
  const rows = money(draft.lines.reduce((sum, line) => sum + rowTotal(line), 0))
  const discount = draft.discount_amount ?? 0
  return same(rows, scanned.subtotal) || same(money(rows - discount), scanned.subtotal)
}

/** Whether the scan shows any tax, which is what `suggest` starts the tax
 *  option from. */
export function isTaxed(scanned: ScannedInvoice): boolean {
  return scanned.taxes.some((tax) => Math.abs(tax.amount) > TOLERANCE)
}

export interface Totals {
  currency: string
  /** Quantity × rate over the lines, before the invoice's discount. */
  total: number
  /** After the invoice's discount. */
  net_total: number
  discount_amount: number
  taxes: { description: string; amount: number }[]
  total_taxes_and_charges: number
  grand_total: number
  rounded_total: number | null
}

/**
 * Whether what ERPNext will book is what the scan says is payable.
 *
 * Either total counts: an invoice printed to the rupee matches ERPNext's
 * rounded total, and one printed to the paisa its grand total. `null` when the
 * scan printed no total, which is its own warning: nothing to check against.
 */
export function totalMatches(scannedTotal: number | null, totals: Totals): boolean | null {
  if (scannedTotal === null || scannedTotal === undefined) return null
  const candidates = [totals.grand_total, totals.rounded_total].filter(
    (value): value is number => typeof value === 'number',
  )
  return candidates.some((value) => Math.abs(value - scannedTotal) <= TOLERANCE)
}

export interface Check {
  key: 'lines' | 'tax' | 'total'
  label: string
  /** Where the scan's figure comes from, when that needs saying. */
  source: string
  scan: number | null
  draft: number
  /** Null where the scan has no figure to compare with. */
  matches: boolean | null
}

/**
 * The bill against the scan, one stage at a time: the lines before tax, the
 * tax, then what is payable. A difference in the total is traced to the first
 * stage that differs, which is where to look.
 *
 * The lines are compared with the printed subtotal where there is one, and
 * otherwise with the row totals, which start as printed and are the reader's
 * to correct. Either the draft's total before the discount or after it may
 * match, since a printed subtotal can be either.
 */
export function checks(draft: Draft, scanned: ScannedInvoice, totals: Totals): Check[] {
  const rows = money(draft.lines.reduce((sum, line) => sum + rowTotal(line), 0))
  const printedSubtotal = scanned.subtotal !== null && scanned.subtotal !== undefined
  const linesScan = printedSubtotal ? (scanned.subtotal as number) : rows
  const linesDraft = same(totals.net_total, linesScan) ? totals.net_total : totals.total

  const found: Check[] = [
    {
      key: 'lines',
      label: 'Lines, before tax',
      source: printedSubtotal ? 'printed subtotal' : 'sum of the row totals',
      scan: linesScan,
      draft: linesDraft,
      matches: same(linesDraft, linesScan),
    },
  ]

  const scannedTax = money(scanned.taxes.reduce((sum, tax) => sum + tax.amount, 0))
  if (scanned.taxes.length || Math.abs(totals.total_taxes_and_charges) > TOLERANCE) {
    found.push({
      key: 'tax',
      label: 'Tax',
      source: scanned.taxes.length ? '' : 'none printed',
      scan: scannedTax,
      draft: totals.total_taxes_and_charges,
      matches: same(scannedTax, totals.total_taxes_and_charges),
    })
  }

  const payable = totalMatches(scanned.total, totals)
  found.push({
    key: 'total',
    label: 'Total payable',
    source: scanned.total === null ? 'none printed' : '',
    scan: scanned.total,
    draft:
      payable && totals.rounded_total !== null && same(totals.rounded_total, scanned.total ?? NaN)
        ? totals.rounded_total
        : totals.grand_total,
    matches: payable,
  })
  return found
}

/** What `preview` and `create` take. Only the fields the server reads. */
export type InvoicePayload = ReturnType<typeof invoicePayload>

export function invoicePayload(draft: Draft) {
  return {
    company: draft.company,
    supplier: draft.newSupplier ? null : draft.supplier,
    bill_no: draft.bill_no,
    bill_date: draft.bill_date || null,
    posting_date: draft.posting_date || null,
    due_date: draft.due_date || null,
    discount_amount: draft.discount_amount || 0,
    taxes: draft.taxes,
    items: draft.lines.map((line) => ({
      description: line.description,
      qty: line.qty,
      rate: line.rate,
      expense_account: line.expense_account,
    })),
  }
}

/**
 * What stops the draft being saved, keyed by the field the message belongs
 * under. The server checks all of this again; these are here so the reader is
 * told beside the field rather than in a banner after pressing Save.
 */
export function draftProblems(draft: Draft): Record<string, string> {
  const found: Record<string, string> = {}
  if (!draft.company) found.company = 'Choose the company'
  if (draft.newSupplier) {
    if (!draft.newSupplier.supplier_name.trim()) found.supplier = 'Name the new supplier'
  } else if (!draft.supplier) found.supplier = 'Choose the supplier'
  if (!draft.posting_date) found.posting_date = 'Give a posting date'
  if (draft.due_date && draft.posting_date && draft.due_date < draft.posting_date) {
    found.due_date = 'Due before it is posted'
  }
  if (!draft.lines.length) found.lines = 'Add at least one line'
  draft.lines.forEach((line, index) => {
    if (!line.description.trim()) found[`description-${index}`] = 'Describe it'
    if (!line.qty || line.qty <= 0) found[`qty-${index}`] = 'Above zero'
    if (line.rate === null || Number.isNaN(line.rate)) found[`rate-${index}`] = 'Enter a rate'
    if (!line.expense_account) found[`account-${index}`] = 'Choose an account'
  })
  return found
}
