import { to_gregorian } from '@bikram/bikram_sambat.js'

/**
 * Turning what Claude read off a scan into a draft Purchase Invoice, and the
 * checks that tell a bookkeeper where to look again.
 *
 * Pure, like `reconciliationRules.ts`, and tested the same way (`yarn test`).
 * Nothing here is fetched or written.
 *
 * Nothing here fills in a figure. Each one on the scan is read on its own,
 * and where they do not agree, or one is missing, the page says so and the
 * reader settles it against the paper. The point of the checks is to catch
 * what the model misread, and a figure worked out from the others would agree
 * with them by construction and hide exactly that.
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

/** Each figure as printed, or null where the line does not print it. Never
 *  worked out from the others: see `SCHEMA` on the server. */
export interface ScannedLine {
  description: string
  quantity: number | null
  rate: number | null
  amount: number | null
}

export interface ScannedTax {
  label: string
  rate: number | null
  amount: number | null
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
   * × rate. It is here to check those two against, because a row whose figures
   * do not multiply out is usually a misread digit.
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

/** A line the reader adds by hand: a quantity of 1, the invoices' own rule
 *  for a line that prints none, and the rest empty until typed from the paper. */
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
 * Every figure is the scan's, gaps included, with two rules for what a line
 * that leaves one out means:
 *
 * * no quantity printed is a quantity of 1;
 * * no rate printed, but a row total, is that total as the rate: the usual
 *   service line, "Audit fee ... 50,000". Copied, not worked out, so where a
 *   quantity above 1 is printed too, the line does not multiply out and is
 *   flagged like any other.
 *
 * A row total that is not printed stays missing. The supplier is filled in only for a strong candidate: a
 * similar name is a suggestion to accept, not an answer. The posting date is
 * the invoice's own, which is how this site books them; `today` stands in
 * where the scan has no date that exists.
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
    discount_amount: scanned.discount ?? null,
    taxes: 'none',
    lines: scanned.lines.map((line) => ({
      ...blankLine(),
      description: line.description,
      qty: line.quantity ?? 1,
      rate: line.rate ?? line.amount,
      amount: line.amount,
      scanned: line,
    })),
  }
}

/** What ERPNext will book for a line: quantity × rate. This, not the row
 *  total, is what the invoice is made of and what its totals are checked with. */
export function lineAmount(line: DraftLine): number {
  return money((line.qty ?? 0) * (line.rate ?? 0))
}

export function money(value: number): number {
  return Math.round(value * 100) / 100
}

function same(a: number, b: number): boolean {
  return Math.abs(a - b) <= TOLERANCE
}

function known(value: number | null | undefined): value is number {
  return typeof value === 'number' && !Number.isNaN(value)
}

function sum(values: (number | null | undefined)[]): number | null {
  return values.every(known) ? money(values.reduce((total, value) => total + value, 0)) : null
}

function listed(words: string[]): string {
  return words.length < 2 ? words.join('') : `${words.slice(0, -1).join(', ')} or ${words[words.length - 1]}`
}

export interface LineFlags {
  qty: boolean
  rate: boolean
  amount: boolean
  /** What is wrong with the line, or null if its figures agree. */
  message: string | null
}

const FIELD_NAMES = { qty: 'quantity', rate: 'rate' } as const

/**
 * Which of a line's figures to highlight, and why.
 *
 * Quantity × rate is what the invoice books, so a missing quantity or rate is
 * flagged: there is nothing to book. The row total is only there to check
 * them against, so a line that prints none is not a fault, only a line with
 * nothing to check. When all three are there and quantity × rate is not the
 * row total, all three are flagged, because nothing on the page says which
 * one was misread.
 *
 * Read off the draft rather than the scan, so a flag clears when the reader
 * corrects the figure from the paper and returns if a later edit breaks it.
 */
export function lineFlags(line: DraftLine): LineFlags {
  const missing = (['qty', 'rate'] as const).filter((field) => !known(line[field]))
  if (missing.length) {
    const names = missing.map((field) => FIELD_NAMES[field])
    return {
      qty: missing.includes('qty'),
      rate: missing.includes('rate'),
      amount: false,
      message: line.scanned
        ? `No ${listed(names)} was read for this line. Enter ${missing.length > 1 ? 'them' : 'it'} from the paper.`
        : `Enter the ${listed(names).replace(' or ', ' and ')} from the paper.`,
    }
  }
  if (!known(line.amount)) return { qty: false, rate: false, amount: false, message: null }
  const booked = lineAmount(line)
  if (same(booked, line.amount)) return { qty: false, rate: false, amount: false, message: null }
  const asRead =
    line.scanned !== null &&
    line.qty === (line.scanned.quantity ?? 1) &&
    line.rate === (line.scanned.rate ?? line.scanned.amount) &&
    line.amount === line.scanned.amount
  return {
    qty: true,
    rate: true,
    amount: true,
    message:
      `${asRead ? 'As read, ' : ''}${line.qty} × ${line.rate} is ${booked}, not the row total of ${line.amount}. ` +
      'One of the three is probably misread: check them against the paper. The invoice books quantity × rate.',
  }
}

/** Whether the line's rate is its printed row total because the scan printed
 *  no rate, and the reader has not changed it. Said beside the line, so that
 *  figure is not taken for one the page printed as a rate. */
export function rateFromTotal(line: DraftLine): boolean {
  return (
    line.scanned !== null &&
    line.scanned.rate === null &&
    known(line.scanned.amount) &&
    line.rate === line.scanned.amount
  )
}

/** The line's message alone, for callers that only want to know whether it
 *  has one. */
export function lineProblem(line: DraftLine): string | null {
  return lineFlags(line).message
}

/**
 * Quantity × rate over the lines, which is what the invoice is: the figure the
 * printed tax is checked with where no subtotal is printed. Null while any line
 * lacks a quantity or a rate, since a sum with a gap in it checks nothing. Row
 * totals never enter it; they only check their own line.
 */
export function linesTotal(draft: Draft): number | null {
  if (!draft.lines.length || !draft.lines.every((line) => known(line.qty) && known(line.rate))) return null
  return money(draft.lines.reduce((total, line) => total + lineAmount(line), 0))
}

/**
 * Where the scan's printed figures do not agree with one another, each said
 * once, before ERPNext comes into it.
 *
 * Only printed figures are checked, and a check that needs a figure the page
 * does not print is left out rather than given a worked-out one:
 *
 * * each tax's printed amount against its printed rate, charged on the printed
 *   subtotal, or on the lines' quantity × rate where there is no subtotal;
 * * the printed total against the printed subtotal, discount and tax, only
 *   where all of those are printed.
 *
 * Whether the lines come to the printed subtotal, and the draft to the printed
 * total, is the stage table's to say (`checks`), on ERPNext's own figures.
 * Where a subtotal could be before the discount or after it, either counts.
 */
export function scanProblems(draft: Draft, scanned: ScannedInvoice): string[] {
  const found: string[] = []
  const discount = draft.discount_amount ?? 0
  const subtotal = known(scanned.subtotal) ? scanned.subtotal : null

  const base = subtotal ?? linesTotal(draft)
  for (const tax of scanned.taxes) {
    if (!known(tax.amount)) {
      found.push(`No amount was read for ${tax.label}.`)
      continue
    }
    if (base === null || !known(tax.rate)) continue
    const candidates = [base, money(base - discount)].map((on) => money((on * tax.rate!) / 100))
    if (!candidates.some((expected) => same(expected, tax.amount!))) {
      found.push(`${tax.label} at ${tax.rate}% of ${base} is ${candidates[0]}, not the printed ${tax.amount}.`)
    }
  }

  const taxTotal = sum(scanned.taxes.map((tax) => tax.amount))
  if (known(scanned.total) && subtotal !== null && taxTotal !== null) {
    const candidates = [money(subtotal + taxTotal), money(subtotal - discount + taxTotal)]
    if (!candidates.some((expected) => same(expected, scanned.total!))) {
      const nearest = candidates.reduce((a, b) => (Math.abs(a - scanned.total!) <= Math.abs(b - scanned.total!) ? a : b))
      const gap = money(Math.abs(nearest - scanned.total))
      found.push(
        `The printed subtotal${discount ? ', discount' : ''} and tax come to ${nearest}, but the printed total is ` +
          `${scanned.total}` +
          (gap < 1 ? `, a difference of ${gap} that may be rounding.` : '.'),
      )
    }
  }
  return found
}

/** Whether the scan shows any tax, which is what `suggest` starts the tax
 *  option from. A tax line whose amount could not be read counts. */
export function isTaxed(scanned: ScannedInvoice): boolean {
  return scanned.taxes.some((tax) => !known(tax.amount) || Math.abs(tax.amount) > TOLERANCE)
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
  if (!known(scannedTotal)) return null
  const candidates = [totals.grand_total, totals.rounded_total].filter(known)
  return candidates.some((value) => same(value, scannedTotal))
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
 * What the draft will book against what the scan prints, one stage at a
 * time: the lines before tax, the tax, then what is payable. The scan side is
 * only ever a printed figure, or a sum of printed figures; where one is
 * missing the stage has nothing to compare and says so.
 *
 * The draft side is always ERPNext's, which is quantity × rate. The lines are
 * compared with the printed subtotal, and have nothing to compare with where
 * none is printed: the row totals are not summed to stand in for one. Either
 * the draft's total before the discount or after it may match, since a printed
 * subtotal can be either.
 */
export function checks(scanned: ScannedInvoice, totals: Totals): Check[] {
  const linesScan = known(scanned.subtotal) ? scanned.subtotal : null
  const linesDraft = linesScan !== null && same(totals.net_total, linesScan) ? totals.net_total : totals.total

  const found: Check[] = [
    {
      key: 'lines',
      label: 'Lines, before tax',
      source: linesScan !== null ? 'printed subtotal' : 'none printed',
      scan: linesScan,
      draft: linesDraft,
      matches: linesScan === null ? null : same(linesDraft, linesScan),
    },
  ]

  const scannedTax = sum(scanned.taxes.map((tax) => tax.amount))
  if (scanned.taxes.length || Math.abs(totals.total_taxes_and_charges) > TOLERANCE) {
    found.push({
      key: 'tax',
      label: 'Tax',
      source: !scanned.taxes.length ? 'none printed' : scannedTax === null ? 'an amount is missing' : '',
      scan: scanned.taxes.length ? scannedTax : 0,
      draft: totals.total_taxes_and_charges,
      matches: scanned.taxes.length && scannedTax === null ? null : same(scannedTax ?? 0, totals.total_taxes_and_charges),
    })
  }

  const payable = totalMatches(scanned.total, totals)
  found.push({
    key: 'total',
    label: 'Total payable',
    source: known(scanned.total) ? '' : 'none printed',
    scan: known(scanned.total) ? scanned.total : null,
    draft:
      payable && known(totals.rounded_total) && same(totals.rounded_total, scanned.total as number)
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
    // A cleared number field holds '' rather than null, so the test is for a
    // number, not for null: a blank rate must not reach the server as 0.
    if (!known(line.qty) || line.qty <= 0) found[`qty-${index}`] = 'Above zero'
    if (!known(line.rate)) found[`rate-${index}`] = 'Enter a rate'
    if (!line.expense_account) found[`account-${index}`] = 'Choose an account'
  })
  return found
}
