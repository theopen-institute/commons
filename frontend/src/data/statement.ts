import { computed } from 'vue'
import { useCall } from 'frappe-ui'

/**
 * The reader's own balances, as the Account Balance page draws them.
 *
 * One call and no permission preamble, which is the difference between this
 * section and the three request sections beside it. There is nothing here to
 * raise and nobody to approve it, so there is no "may I" to answer before the
 * page can paint — the server resolves which parties the session user is and
 * answers for those, and a reader who is none returns the same shape with
 * nothing in it. See `commons/statement/api.py`.
 *
 * The two balances stay two numbers all the way out to the screen. Nothing in
 * this module adds `account` to `loans`, and nothing should: money owed on a
 * loan and money owed on an invoice are settled differently and to different
 * schedules, and a single figure combining them is one nobody could act on.
 * That is the whole reason the section has two.
 */

/** One movement on the ledger, as a statement has it. */
export interface StatementLine {
  /** The `GL Entry` id — a list key, and nothing the page shows. */
  name: string
  date: string
  /** The ledger account it was posted to. Shown only where a statement spans
   *  more than one — see `StatementLines`. */
  account: string
  /** What the movement was: `Sales Invoice`, `Payment Entry`, `Fees`. */
  voucher_type: string
  voucher_no: string
  /** The ledger's own note, where it carries one. Plain text; the page renders
   *  it as text. */
  remarks: string | null
  /** Whether this is an opening entry — a balance carried in rather than
   *  something that happened. */
  is_opening: boolean
  /** What put the balance up, and what brought it down. Not debit and credit:
   *  those read backwards for a payable party, and the server has already put
   *  them the right way round — see `ledger._line`. */
  charged: number
  paid: number
  /** The balance after this line. The server's, because it has to start from an
   *  opening figure the page never sees the entries behind. */
  balance: number
}

/** One party's ledger with one company. */
export interface StatementAccount {
  party_type: string
  party: string
  party_name: string
  /** Which way round the balance reads. `Receivable` means a positive balance
   *  is owed *by* the reader; `Payable` means it is owed *to* them. */
  account_type: 'Receivable' | 'Payable'
  company: string
  /** The company's own currency, which is what every figure here is in. */
  currency: string | null
  balance: number
  /** What the balance stood at before the first listed line. */
  opening: number
  /** How many movements there have ever been, which is not how many are listed. */
  entries: number
  lines: StatementLine[]
  /** Whether anything was folded into the opening rather than listed. */
  truncated: boolean
}

/** One loan still owed on. */
export interface LoanBalance {
  loan: string
  party_type: string
  party: string
  company: string
  currency: string | null
  product: string
  status: string
  posting_date: string
  disbursement_date: string | null
  rate_of_interest: number
  sanctioned: number
  disbursed: number
  repaid: number
  written_off: number
  /** Outstanding principal — what is still borrowed. Deliberately not a
   *  settlement figure: interest accrued since the last demand, penalties and
   *  charges are not in it, and the page says so rather than letting a reader
   *  take it for a payoff quote. See `commons/statement/loans.py`. */
  outstanding: number
}

/** The two headline figures, for one currency. */
export interface StatementTotal {
  currency: string | null
  account: number
  loans: number
}

export interface Statement {
  /** Whether this site keeps a ledger at all. */
  ledger: boolean
  /** Whether it lends. */
  lending: boolean
  parties: {
    party_type: string
    party: string
    party_name: string
    account_type: 'Receivable' | 'Payable'
  }[]
  accounts: StatementAccount[]
  loans: LoanBalance[]
  totals: StatementTotal[]
  /** How many movements a statement lists. The page says what "the earlier
   *  ones" means rather than repeating a number the server owns. */
  page_length: number
}

const NONE: Statement = {
  ledger: false,
  lending: false,
  parties: [],
  accounts: [],
  loans: [],
  totals: [],
  page_length: 0,
}

const statementCall = useCall<Statement>({
  url: '/api/v2/method/commons.statement.api.get_statement',
})

export const statement = computed<Statement>(() => statementCall.data ?? NONE)

/**
 * Whether the answer is in — settled or refused, not merely arrived.
 *
 * The same rule the request sections gate on, for the same reason: a call that
 * fails never sets `data`, and a page waiting on that sits in its skeleton for
 * ever. `statementError` is what it should say instead.
 */
export const statementLoaded = computed(() => statementCall.isFinished)
export const statementError = computed(() => statementCall.error ?? null)
export const reloadStatement = () => statementCall.reload()
export const statementLoading = computed(() => statementCall.loading)

/** Whether this login is a party here at all — which is a different question
 *  from whether it has a balance. Somebody with a settled account is still
 *  somebody the page can draw. */
export const isParty = computed(() => statement.value.parties.length > 0)

/** Whether there is anything at all to show. */
export const hasBalances = computed(
  () => statement.value.accounts.length > 0 || statement.value.loans.length > 0,
)

/**
 * How a balance reads to the person whose it is.
 *
 * The sign carries two different sentences depending on which side of the books
 * the party sits, and neither of them is "−1,200". A receivable party in credit
 * has been overpaid or holds a credit note; a payable one showing a negative is
 * the same situation the other way up. Said once here so the headline figure,
 * the per-account heading and the empty state cannot drift apart.
 */
export function balanceSense(
  balance: number,
  accountType: 'Receivable' | 'Payable',
): { label: string; owing: boolean } {
  if (!balance) return { label: 'Settled', owing: false }
  const owedByReader = accountType === 'Receivable' ? balance > 0 : balance < 0
  return {
    label: owedByReader ? 'You owe' : 'Owed to you',
    owing: owedByReader,
  }
}

/** The amount to print beside that sentence — never a negative, because the
 *  sentence has already said which way round it is. */
export function balanceAmount(balance: number): number {
  return Math.abs(balance)
}
