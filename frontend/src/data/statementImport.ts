import { isoDate, type ScannedDate } from './captureRules'
import { identifiers, money } from './reconciliationRules'

/**
 * A read statement, judged: which rows are new, which are already on the
 * account, and which rows' running balances say something was misread.
 *
 * Pure, like `reconciliationRules.ts`, and tested the same way. The server
 * (`commons.banking.statement_import`) reads the file; this decides what to
 * propose, and the import dialog shows it.
 *
 * ## Already imported
 *
 * A statement row is the same transaction as an existing line when the date,
 * the direction and the amount agree. Several rows can agree with several
 * lines (a borrower paying 5,000 twice on one day is two real deposits), so
 * lines are paired off one each, preferring the line whose description or
 * reference is the same, and a row left over is new. A line a day or three
 * away is accepted only when the descriptions agree as well, because banks
 * post some transactions on the value date and some on the day after, and an
 * earlier import may have used either.
 *
 * ## Balances that stop adding up
 *
 * Where the statement prints a running balance, each row's balance should be
 * the one before it plus the deposit less the withdrawal. When Claude has
 * copied a PDF, a row where that fails is the row to look at: a digit misread,
 * a row skipped, or a debit taken for a credit. Statements printed newest
 * first are recognised and walked the other way.
 */

/** A row as `read_statement` answers it. */
export interface StatementRow {
  date: ScannedDate
  description: string
  reference: string | null
  withdrawal: number
  deposit: number
  balance: number | null
}

export interface StatementReading {
  source: 'spreadsheet' | 'document'
  is_statement: boolean
  account_number: string | null
  currency: string | null
  opening_balance: number | null
  closing_balance: number | null
  notes: string[]
  rows: StatementRow[]
  model: string
}

/** A line already on the account, as the dialog reads it. */
export interface ExistingLine {
  name: string
  date: string
  deposit: number
  withdrawal: number
  description: string | null
  reference_number: string | null
}

export type RowStatus =
  /** Not on the account yet: proposed for import. */
  | 'new'
  /** The same transaction is already a line on the account. */
  | 'duplicate'
  /** The date could not be read as a real day. Cannot be imported as it is. */
  | 'bad-date'

export interface ProposedRow extends StatementRow {
  key: number
  /** `YYYY-MM-DD` Gregorian, or null where the date is not a real day. */
  iso: string | null
  status: RowStatus
  /** The line it duplicates, for a duplicate. */
  existing: string | null
  /** The running balance does not follow from the row before. */
  balanceBreak: boolean
}

export interface BalanceSummary {
  /** Rows whose printed balance could be checked against the one before. */
  checked: number
  broken: number
  /** Whether the statement lists its rows newest first. */
  newestFirst: boolean
  /** Opening plus every row, against the printed closing balance. Null where
   *  either is not printed. */
  closingDifference: number | null
}

function net(row: Pick<StatementRow, 'deposit' | 'withdrawal'>): number {
  return money((row.deposit || 0) - (row.withdrawal || 0))
}

function words(text: string | null | undefined): string {
  return ` ${(text ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()} `
}

/** Whether a row and a line describe the same transaction, beyond date and
 *  amount: the same text, one containing the other, a shared identifier, or
 *  the same reference. */
export function sameDescription(row: Pick<StatementRow, 'description' | 'reference'>, line: ExistingLine): boolean {
  const a = words(row.description)
  const b = words(line.description)
  if (a.trim() && b.trim() && (a === b || a.includes(b) || b.includes(a))) return true
  const ids = new Set([...identifiers(row.description), ...identifiers(row.reference)])
  if ([...identifiers(line.description), ...identifiers(line.reference_number)].some((id) => ids.has(id))) {
    return true
  }
  const reference = (row.reference ?? '').trim()
  return Boolean(reference && reference === (line.reference_number ?? '').trim())
}

function daysApart(a: string, b: string): number {
  return Math.abs(Date.UTC(+a.slice(0, 4), +a.slice(5, 7) - 1, +a.slice(8, 10)) -
    Date.UTC(+b.slice(0, 4), +b.slice(5, 7) - 1, +b.slice(8, 10))) / 86_400_000
}

/** How far apart a row and a line may be dated and still be the same
 *  transaction, when their descriptions agree. */
export const DATE_SLACK = 3

/**
 * Every row, with what the dialog proposes for it.
 *
 * Pairing runs in three passes, strictest first, so a line is claimed by the
 * row it matches best before a looser rule can give it to another: same day
 * and same description, then same day, then within `DATE_SLACK` days and same
 * description.
 */
export function proposeRows(reading: Pick<StatementReading, 'rows' | 'opening_balance'>, existing: ExistingLine[]): ProposedRow[] {
  const rows: ProposedRow[] = reading.rows.map((row, key) => {
    const iso = isoDate(row.date)
    return { ...row, key, iso, status: iso ? 'new' : 'bad-date', existing: null, balanceBreak: false }
  })

  const unclaimed = new Set(existing.map((line) => line.name))
  const passes: ((row: ProposedRow, line: ExistingLine) => boolean)[] = [
    (row, line) => line.date === row.iso && sameDescription(row, line),
    (row, line) => line.date === row.iso,
    (row, line) => daysApart(line.date, row.iso!) <= DATE_SLACK && sameDescription(row, line),
  ]
  for (const pass of passes) {
    for (const row of rows) {
      if (row.status !== 'new') continue
      const line = existing.find(
        (candidate) =>
          unclaimed.has(candidate.name) &&
          money(candidate.deposit - candidate.withdrawal) === net(row) &&
          pass(row, candidate),
      )
      if (!line) continue
      unclaimed.delete(line.name)
      row.status = 'duplicate'
      row.existing = line.name
    }
  }

  const breaks = balanceBreaks(reading.rows, reading.opening_balance)
  for (const row of rows) row.balanceBreak = breaks.broken.has(row.key)
  return rows
}

/**
 * Which rows' running balances do not follow from the row before.
 *
 * Tried in the printed order, then newest first, and the order with fewer
 * breaks is taken: a statement printed newest first fails every row in the
 * other direction. The first row is checked against the opening balance where
 * one is printed and the rows run oldest first.
 */
export function balanceBreaks(
  rows: Pick<StatementRow, 'deposit' | 'withdrawal' | 'balance'>[],
  opening: number | null,
): { broken: Set<number>; checked: number; newestFirst: boolean } {
  const walk = (order: number[], start: number | null) => {
    const broken = new Set<number>()
    let checked = 0
    let previous = start
    for (const index of order) {
      const row = rows[index]
      if (row.balance === null || row.balance === undefined) {
        previous = previous === null ? null : money(previous + net(row))
        continue
      }
      if (previous !== null) {
        checked++
        if (money(previous + net(row)) !== money(row.balance)) broken.add(index)
      }
      previous = row.balance
    }
    return { broken, checked }
  }
  const forward = rows.map((_, index) => index)
  const oldestFirst = walk(forward, opening)
  const newestFirst = walk([...forward].reverse(), null)
  return newestFirst.broken.size < oldestFirst.broken.size && newestFirst.checked > 0
    ? { ...newestFirst, newestFirst: true }
    : { ...oldestFirst, newestFirst: false }
}

export function balanceSummary(reading: StatementReading, rows: ProposedRow[]): BalanceSummary {
  const breaks = balanceBreaks(reading.rows, reading.opening_balance)
  const { opening_balance: opening, closing_balance: closing } = reading
  return {
    checked: breaks.checked,
    broken: breaks.broken.size,
    newestFirst: breaks.newestFirst,
    closingDifference:
      opening === null || closing === null
        ? null
        : money(closing - opening - rows.reduce((sum, row) => sum + net(row), 0)),
  }
}

/** Whether the statement's account number is this Bank Account's, comparing
 *  digits only and allowing for a statement that masks all but the last few
 *  ("XXXX2333"). Null where either is missing. */
export function accountMatches(printed: string | null, own: (string | null)[]): boolean | null {
  const digits = (value: string | null) => (value ?? '').replace(/\D/g, '')
  const statement = digits(printed)
  const ours = own.map(digits).filter(Boolean)
  if (!statement || !ours.length) return null
  return ours.some((account) => account === statement || (statement.length >= 4 && account.endsWith(statement)))
}

/** The Bank Transaction a row becomes, ready for `insert_many`. Submitted on
 *  insert, as ERPNext's own statement import does. */
export function transactionFor(row: ProposedRow, bankAccount: string, currency: string | null) {
  return {
    doctype: 'Bank Transaction',
    docstatus: 1,
    date: row.iso,
    bank_account: bankAccount,
    deposit: money(row.deposit),
    withdrawal: money(row.withdrawal),
    description: row.description,
    reference_number: row.reference || undefined,
    ...(currency ? { currency } : {}),
  }
}
