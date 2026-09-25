/**
 * The bank reconciliation page's judgement: which loan a deposit probably
 * repays, how much is left on a loan, how a deposit is split, and how
 * candidate vouchers rank.
 *
 * Pure, like `attendanceRegister.ts`: `reconciliation.ts` fetches, and this
 * decides. That split is what lets the suggestions be tested. They are the part
 * of the page most likely to be quietly wrong, and nothing on screen tells a
 * wrong suggestion from a right one.
 *
 * ## How a deposit is matched to a loan
 *
 * The statements this was written for rarely say who paid. A QR payment reads
 * `FPQR-446377887-5650-24:…` and carries no name at all; a transfer sometimes
 * names the sender (`FT/09711000594/Kiran Adhikari/9814347967/…`) and sometimes
 * only an account or phone number. The desk tool offers nothing for any of
 * them, so the bookkeeper remembers who pays from which account.
 *
 * This remembers it instead. Each reconciled repayment is a statement line
 * joined to a loan, so the identifiers on those lines (long numbers, mostly
 * account and phone numbers) are evidence about which loan a new line belongs
 * to. Evidence, in order of weight:
 *
 * 1. the party on the transaction is the borrower (somebody said so);
 * 2. an identifier on this line appeared on two or more earlier repayments of
 *    exactly one loan;
 * 3. the borrower's full name is in the description;
 * 4. an identifier appeared on *one* earlier repayment of one loan. This is
 *    weak, because banks put their own clearing accounts and recurring
 *    transaction numbers in descriptions too;
 * 5. the amount pays the loan off exactly, or is what the borrower usually
 *    pays.
 *
 * The first three are strong: a suggestion resting on one of them may be put
 * into the draft for the bookkeeper to confirm. The fourth is only listed. The
 * fifth is only a tie-breaker, because half the borrowers pay 5,000.
 *
 * How well that works, replayed over register.localhost's 124 reconciled loan
 * repayments with each line judged only on what came before it: 30 strong
 * suggestions, of which 24 named the right loan, 5 the right borrower's other
 * loan, and 1 the wrong borrower (a clearing account seen twice). 5 weak ones,
 * all the right borrower. 89 lines got nothing, almost all QR payments that name
 * nobody, and those are left to the search.
 */

/** A statement line, as the page reads it. */
export interface TransactionRow {
  name: string
  date: string
  deposit: number
  withdrawal: number
  currency: string | null
  description: string | null
  reference_number: string | null
  party_type: string | null
  party: string | null
  allocated_amount: number
  unallocated_amount: number
  status: string
  bank_account: string
  company: string | null
  transaction_type: string | null
}

/** A loan that can still be repaid. */
export interface LoanRow {
  name: string
  applicant_type: string
  applicant: string
  company: string
  loan_product: string | null
  status: string
  loan_amount: number
  disbursed_amount: number
  total_payment: number
  total_principal_paid: number
  total_interest_payable: number
  debit_adjustment_amount: number
  credit_adjustment_amount: number
}

/** One earlier repayment of a loan, and the statement line it was matched to.
 *  A list of these is in the order the repayments were made, oldest first. */
export interface RepaymentHistory {
  loan: string
  amount: number
  /** The description of the statement line it reconciled. Null for a repayment
   *  that was never matched to one. */
  description: string | null
}

/** An uncleared repayment already on the books, which a deposit may be matched to. */
export interface RepaymentRow {
  name: string
  against_loan: string
  applicant_type: string
  applicant: string
  amount_paid: number
  value_date: string
  reference_number: string | null
  reference_date: string | null
}

/** A voucher a statement line could be matched to. ERPNext's
 *  `get_linked_payments` rows have this shape, and loan repayments are given it. */
export interface Candidate {
  rank: number
  doctype: string
  name: string
  paid_amount: number
  reference_no: string | null
  reference_date: string | null
  posting_date: string | null
  party_type: string | null
  party: string | null
  currency: string | null
}

export interface Suggestion {
  loan: string
  score: number
  /** Whether it rests on evidence good enough to fill in the draft: the party,
   *  the name, or an identifier seen more than once. */
  strong: boolean
  /** Why, in the words shown beside the suggestion. */
  reasons: string[]
}

/** Loan statuses that still take a repayment. `Loan Closure Requested` is
 *  one: the borrower has asked to close and the last instalment is usually
 *  what is on its way. */
export const OPEN_LOAN_STATUSES = [
  'Disbursed',
  'Partially Disbursed',
  'Active',
  'Loan Closure Requested',
]

/** Money is compared to the minor unit. Floats that should be equal after an
 *  addition often are not. */
export function money(value: number | null | undefined): number {
  return Math.round((value ?? 0) * 100) / 100
}

/** The amount on a line, whichever side of the account it is on. */
export function amountOf(row: Pick<TransactionRow, 'deposit' | 'withdrawal'>): number {
  return money((row.deposit || 0) - (row.withdrawal || 0))
}

/**
 * Principal still owed on a loan.
 *
 * Lending's `get_pending_principal_amount`, restated because it is not
 * whitelisted. A fully disbursed loan counts its whole repayable total less
 * its interest; a loan still being disbursed counts only what has gone out.
 * Principal only. On a loan that charges interest the repayment's own
 * `calculate_amounts` is the authority, and the page says so beside the figure.
 */
export function outstandingPrincipal(loan: LoanRow): number {
  const adjustments = (loan.debit_adjustment_amount || 0) - (loan.credit_adjustment_amount || 0)
  const base = ['Disbursed', 'Closed', 'Active', 'Written Off', 'Settled'].includes(loan.status)
    ? (loan.total_payment || 0) - (loan.total_interest_payable || 0)
    : loan.disbursed_amount || 0
  return money(Math.max(0, base + adjustments - (loan.total_principal_paid || 0)))
}

/** Lower case and letters and digits only, so that `Heema Rai GFL/Open` and
 *  `heema rai` meet. */
function normalise(text: string | null | undefined): string {
  return ` ${(text ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()} `
}

/**
 * The identifiers on a statement line: runs of six or more digits.
 *
 * Account numbers, phone numbers and wallet ids are what repeat from one of a
 * borrower's payments to the next. So do some numbers that identify nothing,
 * such as the bank's own branch codes. Those turn up on the lines of many
 * loans, and `suggestLoans` discards them for that reason.
 */
export function identifiers(description: string | null | undefined): string[] {
  return [...new Set((description ?? '').match(/\d{6,}/g) ?? [])]
}

/** Whether a borrower's name is in a description. Every part of it, not just
 *  the surname: `Rai` is on half the statements in the country. */
export function nameAppears(name: string | null | undefined, description: string | null | undefined) {
  const parts = normalise(name).trim().split(' ').filter((part) => part.length >= 2)
  if (!parts.length) return false
  if (parts.length === 1 && parts[0].length < 5) return false
  const text = normalise(description)
  return parts.every((part) => text.includes(` ${part} `))
}

/**
 * The loans a deposit probably repays, best first, with the reasons.
 *
 * Only loans with something left to repay, and only loans some evidence points
 * at. A loan that nothing points at is still offered, through the search
 * beside the suggestions, but it is not guessed at.
 */
export function suggestLoans(
  transaction: TransactionRow,
  loans: LoanRow[],
  borrowerNames: Record<string, string>,
  history: RepaymentHistory[],
): Suggestion[] {
  const amount = money(transaction.unallocated_amount)
  if (amount <= 0 || transaction.deposit <= 0) return []

  // Which loans each identifier has been seen with. An identifier seen with
  // two loans identifies neither of them.
  const seenWith = new Map<string, Map<string, number>>()
  const usualAmounts = new Map<string, Set<number>>()
  const lastPaid = new Map<string, number>()
  history.forEach((row, index) => lastPaid.set(row.loan, index))
  for (const row of history) {
    if (!usualAmounts.has(row.loan)) usualAmounts.set(row.loan, new Set())
    usualAmounts.get(row.loan)!.add(money(row.amount))
    for (const id of identifiers(row.description)) {
      if (!seenWith.has(id)) seenWith.set(id, new Map())
      const loansForId = seenWith.get(id)!
      loansForId.set(row.loan, (loansForId.get(row.loan) ?? 0) + 1)
    }
  }
  const lineIds = identifiers(transaction.description)

  const suggestions: Suggestion[] = []
  for (const loan of loans) {
    const outstanding = outstandingPrincipal(loan)
    if (outstanding <= 0) continue
    let score = 0
    let strong = false
    const reasons: string[] = []

    if (
      transaction.party &&
      transaction.party_type === loan.applicant_type &&
      transaction.party === loan.applicant
    ) {
      score += 8
      strong = true
      reasons.push('Borrower is the party on this line')
    }

    const matchedIds = lineIds.filter((id) => {
      const loansForId = seenWith.get(id)
      return loansForId?.size === 1 && loansForId.has(loan.name)
    })
    if (matchedIds.length) {
      const times = Math.max(...matchedIds.map((id) => seenWith.get(id)!.get(loan.name)!))
      score += times > 1 ? 6 : 2
      strong ||= times > 1
      reasons.push(
        `${matchedIds[0]} was on ${times === 1 ? 'an earlier repayment' : `${times} earlier repayments`}`,
      )
    }

    if (nameAppears(borrowerNames[loan.applicant], transaction.description)) {
      score += 5
      strong = true
      reasons.push('Borrower named in the description')
    }

    // Tie-breakers only. They are not enough to put a loan in the list without
    // some other evidence.
    let tieBreak = 0
    if (money(outstanding) === amount) {
      tieBreak += 2
      reasons.push('Pays the loan off exactly')
    } else if (usualAmounts.get(loan.name)?.has(amount)) {
      tieBreak += 1
      reasons.push('Same amount as earlier repayments')
    }

    if (score > 0) suggestions.push({ loan: loan.name, score: score + tieBreak, strong, reasons })
  }

  // A borrower with two open loans is found twice by the same evidence, and
  // the loan they are paying is nearly always the one they paid last. On
  // register.localhost's history a third of the strong suggestions found the
  // right borrower and then ranked their other loan first.
  const applicantOf = new Map(loans.map((loan) => [loan.name, loan.applicant]))
  const byBorrower = new Map<string, Suggestion[]>()
  for (const suggestion of suggestions) {
    const applicant = applicantOf.get(suggestion.loan)!
    if (!byBorrower.has(applicant)) byBorrower.set(applicant, [])
    byBorrower.get(applicant)!.push(suggestion)
  }
  for (const group of byBorrower.values()) {
    if (group.length < 2) continue
    const current = group.reduce((best, row) =>
      (lastPaid.get(row.loan) ?? -1) > (lastPaid.get(best.loan) ?? -1) ? row : best,
    )
    if (!lastPaid.has(current.loan)) continue
    current.score += 1
    current.reasons.push('The loan this borrower paid last')
  }
  return suggestions.sort((a, b) => b.score - a.score || a.loan.localeCompare(b.loan))
}

/** Whether a statement reference says anything. Banks fill the column with `-`
 *  when they have nothing to put there, and ERPNext ranks on it all the same. */
export function meaningfulReference(reference: string | null | undefined): string {
  const value = (reference ?? '').trim()
  return /^[-–—.\s0]*$/.test(value) ? '' : value
}

/** The reference a repayment made from a line is given: the statement's own, or
 *  failing that the description, which is what ERPNext's dialog falls back to
 *  as well. Trimmed to `Loan Repayment.reference_number`'s 140 characters. */
export function proposedReference(transaction: TransactionRow): string {
  return (meaningfulReference(transaction.reference_number) || (transaction.description ?? '').trim()).slice(
    0,
    140,
  )
}

/**
 * Uncleared repayments as matching candidates, ranked the way ERPNext ranks
 * its own: one point to start, and one each for the same reference, the same
 * party and the exact amount.
 *
 * This is lending's `get_lr_matching_query` done here, because the original
 * cannot be used. It names neither its rank nor its amount column, so
 * ERPNext's sort fails with `KeyError` as soon as it finds anything.
 */
export function repaymentCandidates(
  transaction: TransactionRow,
  repayments: RepaymentRow[],
  exactOnly: boolean,
): Candidate[] {
  const reference = meaningfulReference(transaction.reference_number)
  const amount = money(transaction.unallocated_amount)
  return repayments
    .filter((row) => !exactOnly || money(row.amount_paid) === amount)
    .map((row) => ({
      rank:
        1 +
        (reference && row.reference_number === reference ? 1 : 0) +
        (transaction.party &&
        row.applicant_type === transaction.party_type &&
        row.applicant === transaction.party
          ? 1
          : 0) +
        (money(row.amount_paid) === amount ? 1 : 0),
      doctype: 'Loan Repayment',
      name: row.name,
      paid_amount: row.amount_paid,
      reference_no: row.reference_number,
      reference_date: row.reference_date,
      posting_date: row.value_date?.slice(0, 10) ?? null,
      party_type: row.applicant_type,
      party: row.applicant,
      currency: transaction.currency,
    }))
}

/** ERPNext's candidates and the repayments, in one list, best first. The sort
 *  is stable, so equal ranks keep the order each source gave them. */
export function mergeCandidates(...lists: Candidate[][]): Candidate[] {
  return lists
    .flat()
    .map((row, index) => ({ row, index }))
    .sort((a, b) => b.row.rank - a.row.rank || a.index - b.index)
    .map(({ row }) => row)
}

/** One line of a split deposit, as the loan panel drafts it. */
export interface RepaymentLine {
  loan: string
  amount: number
}

export interface SplitCheck {
  total: number
  /** What is left of the deposit after these lines. */
  remaining: number
  /** Reasons Save is refused. */
  errors: string[]
  /** Reasons to look twice, which do not stop anything. */
  warnings: string[]
}

/**
 * Whether a split of a deposit across loans can be booked.
 *
 * The server refuses the same things (`reconciliation._validated_lines`). They
 * are checked here too so that the button can say so before anything is sent.
 * Paying more than a loan's outstanding principal is allowed, because lending
 * books the excess as a refund owed to the borrower, but it is worth a warning:
 * usually it is a typo.
 */
export function checkSplit(
  lines: RepaymentLine[],
  unallocated: number,
  outstanding: Record<string, number>,
): SplitCheck {
  const errors: string[] = []
  const warnings: string[] = []
  const total = money(lines.reduce((sum, line) => sum + (line.amount || 0), 0))
  const remaining = money(unallocated - total)

  if (!lines.length) errors.push('Choose a loan')
  const seen = new Set<string>()
  for (const line of lines) {
    if (seen.has(line.loan)) errors.push(`${line.loan} is on two lines`)
    seen.add(line.loan)
    if (!(line.amount > 0)) errors.push(`${line.loan} has no amount`)
    const owed = outstanding[line.loan]
    if (owed !== undefined && money(line.amount) > owed) {
      warnings.push(`${line.loan} is paid ${money(line.amount - owed).toFixed(2)} more than its outstanding principal`)
    }
  }
  if (remaining < 0) errors.push('The lines come to more than the deposit')
  return { total, remaining, errors, warnings }
}

/**
 * Spread a deposit over newly chosen loans: each takes what is left of the
 * deposit, up to what it owes. For a deposit that covers one loan exactly this
 * is the whole of the arithmetic; for a sibling paying two it gets close enough
 * that the bookkeeper only corrects one figure.
 */
export function proposeAmount(unallocatedRemaining: number, outstanding: number): number {
  const left = money(unallocatedRemaining)
  if (left <= 0) return 0
  return outstanding > 0 ? Math.min(left, money(outstanding)) : left
}

/* -------------------------------------------------------------------------- */
/* Statement lines and book entries                                               */
/* -------------------------------------------------------------------------- */

/** Whole days from one `YYYY-MM-DD` to another. */
export function daysBetween(from: string, to: string): number {
  const utc = (value: string) => {
    const [y, m, d] = value.slice(0, 10).split('-').map(Number)
    return Date.UTC(y, m - 1, d)
  }
  return Math.round((utc(to) - utc(from)) / 86_400_000)
}

/**
 * An entry posted to the bank's GL account that no statement line accounts
 * for yet: a cheque not yet presented, a transfer not yet imported, or a
 * voucher that did go through and was never matched. One row of ERPNext's
 * Bank Reconciliation Statement report.
 */
export interface BookEntry {
  doctype: string
  name: string
  date: string
  /** Into the bank, as the books have it. */
  debit: number
  /** Out of the bank. */
  credit: number
  against: string | null
  reference: string | null
  /** A voucher not yet submitted, which will post to the bank's account when
   *  it is. Not in the ledger, so never counted in the balance check. */
  draft?: boolean
}

/**
 * Which open line and which entry are probably the same money: the same
 * amount going the same way, and the nearest in date where there are several.
 * One partner each, so a list of ten 5,000 deposits is not told that every one
 * of them matches every 5,000 receipt. A posted entry is preferred to a draft
 * of the same amount: the draft may be the abandoned first attempt at it.
 *
 * Only a hint for the two lists. Matching is still the bookkeeper's, by
 * dragging one onto the other.
 */
export function likelyPairs(
  lines: { name: string; date: string; deposit: number; withdrawal: number; unallocated_amount: number }[],
  entries: BookEntry[],
): Map<string, string> {
  const pairs = new Map<string, string>()
  const taken = new Set<string>()
  const key = (entry: BookEntry) => `${entry.doctype}:${entry.name}`
  const candidates = lines
    .filter((line) => line.unallocated_amount > 0.005)
    .flatMap((line) =>
      entries
        .filter((entry) =>
          line.deposit > 0
            ? money(entry.debit) === money(line.unallocated_amount) && entry.debit > 0
            : money(entry.credit) === money(line.unallocated_amount) && entry.credit > 0,
        )
        .map((entry) => ({
          line: line.name,
          entry: key(entry),
          draft: entry.draft ? 1 : 0,
          gap: Math.abs(daysBetween(line.date, entry.date)),
        })),
    )
    .sort((a, b) => a.draft - b.draft || a.gap - b.gap)
  for (const candidate of candidates) {
    if (pairs.has(candidate.line) || taken.has(candidate.entry)) continue
    pairs.set(candidate.line, candidate.entry)
    taken.add(candidate.entry)
  }
  return pairs
}
