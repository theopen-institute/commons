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
      scanned: line,
    })),
  }
}

export function lineAmount(line: DraftLine): number {
  return money((line.qty ?? 0) * (line.rate ?? 0))
}

export function money(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * Where a scanned line does not add up by itself: the page says quantity ×
 * rate is one thing and prints another. Usually a misread digit, sometimes a
 * discount on the line. Either way it is the reader's to settle, so this only
 * says so.
 */
export function lineProblem(line: DraftLine): string | null {
  if (!line.scanned) return null
  const { quantity, rate, amount } = line.scanned
  if (Math.abs(money(quantity * rate) - amount) <= TOLERANCE) return null
  return `The scan prints ${amount} for this line, but ${quantity} × ${rate} is ${money(quantity * rate)}.`
}

/** Whether the scan shows any tax, which is what `suggest` starts the tax
 *  option from. */
export function isTaxed(scanned: ScannedInvoice): boolean {
  return scanned.taxes.some((tax) => Math.abs(tax.amount) > TOLERANCE)
}

export interface Totals {
  currency: string
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
