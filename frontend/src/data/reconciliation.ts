import { computed, ref, type Ref } from 'vue'
import { upload, useCall } from 'frappe-ui'
import {
  OPEN_LOAN_STATUSES,
  money,
  type Candidate,
  type BookEntry,
  type LoanRow,
  type RepaymentHistory,
  type RepaymentRow,
  type TransactionRow,
} from './reconciliationRules'
import type { OutstandingDocument } from './paymentAllocation'
import type { ExistingLine, StatementReading } from './statementImport'

/**
 * The bank reconciliation page's reads and writes.
 *
 * Almost all of it is ERPNext's. The desk's Bank Reconciliation Tool is a form
 * with a data table glued into it, but the functions behind it are sound, and
 * every write here is one of them:
 *
 * * `reconcile_vouchers`, `create_payment_entry_bts`, `create_journal_entry_bts`,
 *   `update_bank_transaction` and `auto_reconcile_vouchers`, from
 *   `bank_reconciliation_tool.py`;
 * * `remove_payment_entries` on the `Bank Transaction` itself, which is what the
 *   desk form's Unreconcile button runs;
 * * `set_closing_balance_as_per_statement` on `Bank Account`.
 *
 * The one write of this app's own is `commons.banking.reconciliation.create_loan_repayments`.
 * It makes the Loan Repayment a person makes in the desk and matches it to the
 * deposit in one request. See that module for why it is one request.
 *
 * Reads go through the document API wherever that can answer, so User
 * Permissions and `commons.safer_permissions` apply. Two ERPNext reads cannot
 * be replaced with one: the balance "as per ERP", which is a cleared-balance
 * computation over four voucher types, and the candidate search. The candidate
 * search reads vouchers without a permission check, which is why the page is
 * offered only to somebody who may write a Bank Transaction (see
 * `commons.banking.reconciliation.can_reconcile`).
 *
 * Loan repayments are left out of that search deliberately. Lending's
 * `get_lr_matching_query` returns rows ERPNext cannot sort (no `rank`
 * column), so asking it for them fails the whole search the moment one exists.
 * They are read here instead and ranked in `reconciliationRules.ts`.
 */

const DOCUMENT = '/api/v2/document'
const METHOD = '/api/v2/method'
const CLIENT = `${METHOD}/frappe.client`
const TOOL = `${METHOD}/erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool`
const BANK_ACCOUNT_API = `${METHOD}/erpnext.accounts.doctype.bank_account.bank_account`
const COMMONS = `${METHOD}/commons.banking.reconciliation`

export const BANK_TRANSACTION = 'Bank Transaction'
export const LOAN_REPAYMENT = 'Loan Repayment'

/** How many rows each list may return. `document_list` defaults to 20 and has
 *  no "all", so every read says. A bank account sees a few hundred lines a
 *  year, and a lender this size has a hundred or so loans. */
const PAGE = {
  accounts: 100,
  transactions: 2000,
  loans: 2000,
  history: 5000,
  repayments: 1000,
}

/** The voucher types ERPNext's candidate search is asked about. Loan
 *  Repayment is not one of them; see the module comment. */
export const VOUCHER_TYPES = [
  { key: 'payment_entry', label: 'Payment Entry' },
  { key: 'journal_entry', label: 'Journal Entry' },
  { key: 'sales_invoice', label: 'Sales Invoice' },
  { key: 'purchase_invoice', label: 'Purchase Invoice' },
  { key: 'bank_transaction', label: 'Bank Transaction' },
] as const

export type VoucherKey = (typeof VOUCHER_TYPES)[number]['key'] | 'loan_repayment'

interface ListParams {
  fields: string
  filters?: string
  order_by?: string
  limit: number
}

function documentList<Row>(doctype: string) {
  return useCall<Row[], ListParams>({
    url: `${DOCUMENT}/${encodeURIComponent(doctype)}`,
    immediate: false,
  })
}

/** Run a read and throw rather than carry on with nothing. The same contract
 *  as `attendance.ts`'s `fetchRows`. */
async function fetchRows<Row, Params extends object>(
  call: { submit: (params: Params) => Promise<Row | null>; error: Error | null },
  params: Params,
): Promise<Row> {
  const rows = await call.submit(params)
  if (rows === null) throw call.error ?? new Error('That could not be loaded.')
  return rows
}

/** Run a write and say whether it landed. `submit` resolves null both for a
 *  refusal and for a call that answers with nothing, so the call's `error` is
 *  what tells them apart. */
export async function write<Result, Params extends object>(
  call: { submit: (params: Params) => Promise<Result | null>; error: Error | null },
  params: Params,
): Promise<{ ok: boolean; data: Result | null; error: Error | null }> {
  const data = await call.submit(params)
  return { ok: !call.error, data, error: call.error }
}

/* -------------------------------------------------------------------------- */
/* Who the page is for                                                         */
/* -------------------------------------------------------------------------- */

function permissionCall(doctype: string, perm: string) {
  return useCall<{ has_permission: boolean }, { doctype: string; docname: string; perm_type: string }>({
    url: `${CLIENT}.has_permission`,
    params: { doctype, docname: '', perm_type: perm },
  })
}

/** Write on `Bank Transaction`, the server's own test. See `can_reconcile`. */
const canReconcileCall = permissionCall(BANK_TRANSACTION, 'write')

/** Whether the loan tab is offered. A site without lending has no such
 *  doctype, the call is refused, and the answer is no, which is right. */
const canRepayCall = permissionCall(LOAN_REPAYMENT, 'submit')

export const reconciliationCan = computed(() => ({
  reconcile: Boolean(canReconcileCall.data?.has_permission),
  repayLoans: Boolean(canRepayCall.data?.has_permission),
}))

export const reconciliationPermissionsLoaded = computed(
  () => canReconcileCall.isFinished && canRepayCall.isFinished,
)

/** What the sidebar row waits on. Whether the site has bank statements at all
 *  is the shell's answer already (`commons.shell.pages.available`). */
export const reconciliationGate = {
  visible: computed(() => reconciliationCan.value.reconcile),
  resolved: computed(() => canReconcileCall.isFinished),
}

/* -------------------------------------------------------------------------- */
/* Bank accounts and their balances                                            */
/* -------------------------------------------------------------------------- */

export interface BankAccountRow {
  name: string
  account_name: string | null
  bank: string | null
  account: string | null
  company: string | null
  is_default: 0 | 1
}

/** The company's own bank accounts, the ones statements are kept for. A
 *  borrower's or supplier's bank account is a Bank Account too, and has no
 *  statement here. */
export function useBankAccounts() {
  const call = documentList<BankAccountRow>('Bank Account')
  async function load() {
    await call.submit({
      fields: JSON.stringify(['name', 'account_name', 'bank', 'account', 'company', 'is_default']),
      filters: JSON.stringify([
        ['is_company_account', '=', 1],
        ['disabled', '=', 0],
      ]),
      order_by: 'is_default desc, name asc',
      limit: PAGE.accounts,
    })
  }
  return {
    load,
    accounts: computed(() => call.data ?? []),
    loaded: computed(() => call.isFinished),
    error: computed(() => call.error ?? null),
  }
}

/** Record the bank's closing figure for a date. A `Bank Account Balance` row,
 *  which is where ERPNext's newer banking screens keep it too, so the figure
 *  is there the next time anybody opens either. */
export function useSetStatementBalance() {
  return useCall<unknown, { bank_account: string; date: string; balance: number }>({
    url: `${BANK_ACCOUNT_API}.set_closing_balance_as_per_statement`,
    method: 'POST',
    immediate: false,
  })
}

export interface Balances {
  /** What the books say the bank held the day before the period opens. */
  opening: number | null
  /** What the books say it held at the period's end, counting only what has
   *  cleared. The figure a statement's closing balance should equal. */
  cleared: number | null
  /** The bank's own closing figure, as last recorded for this account on or
   *  before the period's end. Null where none has been recorded. */
  statement: number | null
  statementDate: string | null
}

/** The period's four figures. The books' two are ERPNext's cleared balance,
 *  the "balance as per ERP" its own tool heads the page with; the statement's
 *  is the latest `Bank Account Balance` recorded on or before the period's end. */
export function usePeriodBalances() {
  const opening = useCall<number, { bank_account: string; till_date: string; company: string }>({
    url: `${TOOL}.get_account_balance`,
    immediate: false,
  })
  const closing = useCall<number, { bank_account: string; till_date: string; company: string }>({
    url: `${TOOL}.get_account_balance`,
    immediate: false,
  })
  const statement = useCall<{ balance: number; date: string | null }, { bank_account: string; date: string }>({
    url: `${BANK_ACCOUNT_API}.get_closing_balance_as_per_statement`,
    immediate: false,
  })
  const empty: Balances = { opening: null, cleared: null, statement: null, statementDate: null }
  const balances = ref<Balances>(empty)

  async function load(account: BankAccountRow | null, from: string, to: string) {
    if (!account?.company || !from || !to) return
    balances.value = empty
    const [openingValue, closingValue, recorded] = await Promise.all([
      opening.submit({ bank_account: account.name, till_date: dayBefore(from), company: account.company }),
      closing.submit({ bank_account: account.name, till_date: to, company: account.company }),
      statement.submit({ bank_account: account.name, date: to }),
    ])
    // A zero with no date is ERPNext's way of saying none was recorded.
    const date = recorded?.date ? String(recorded.date).slice(0, 10) : null
    balances.value = {
      opening: openingValue,
      cleared: closingValue,
      statement: date ? recorded!.balance : null,
      statementDate: date,
    }
  }

  return { load, balances }
}

function dayBefore(date: string): string {
  const [year, month, day] = date.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day - 1)).toISOString().slice(0, 10)
}

interface ReportRow {
  posting_date?: string
  payment_document?: string
  payment_entry?: string
  debit?: number
  credit?: number
  against_account?: string | null
  reference_no?: string | null
}

export interface StatementReport {
  /** The entries no statement line accounts for as of the day. */
  entries: BookEntry[]
}

/**
 * ERPNext's Bank Reconciliation Statement report, for one bank account on
 * one day.
 *
 * The report is where ERPNext itself lists the entries that have not cleared,
 * across every voucher type that can touch a bank account (lending adds loan
 * repayments and disbursements through a hook). It is also the computation
 * behind the "balance as per ERP" the page quotes, so the board's right-hand
 * column is exactly what that balance leaves out. A report run is permission-checked by the
 * report's roles: Accounts User, Accounts Manager and Auditor.
 */
function useStatementReport() {
  const call = useCall<{ result: (ReportRow | unknown[])[] }, { report_name: string; filters: string }>({
    url: `${METHOD}/frappe.desk.query_report.run`,
    immediate: false,
  })

  async function run(account: BankAccountRow, date: string): Promise<StatementReport> {
    const answer = await fetchRows(call, {
      report_name: 'Bank Reconciliation Statement',
      filters: JSON.stringify({
        account: account.account,
        report_date: date,
        company: account.company,
        include_pos_transactions: 1,
      }),
    })
    const rows = answer.result.filter((row): row is ReportRow => !!row && !Array.isArray(row))
    const entries = rows
      .filter((row) => row.payment_document && row.payment_entry)
      .map((row) => ({
        doctype: row.payment_document!,
        name: row.payment_entry!,
        date: String(row.posting_date ?? '').slice(0, 10),
        debit: row.debit ?? 0,
        credit: row.credit ?? 0,
        against: row.against_account ?? null,
        reference: row.reference_no ?? null,
      }))
    return { entries }
  }

  return { run }
}

/** The entries the bank has not seen yet, as of today: the right-hand column
 *  of the "to reconcile" view. */
export function useUnmatchedEntries() {
  const report = useStatementReport()
  const entries = ref<BookEntry[]>([])
  const loaded = ref(false)
  const error = ref<Error | null>(null)

  async function load(account: BankAccountRow | null) {
    if (!account?.account || !account.company) {
      entries.value = []
      return
    }
    error.value = null
    try {
      entries.value = (await report.run(account, isoToday())).entries
      loaded.value = true
    } catch (problem) {
      error.value = problem as Error
      entries.value = []
    }
  }

  return { load, entries, loaded, error }
}

/**
 * Drafts that will post to the bank's GL account when submitted.
 *
 * One read per voucher type, because each names the bank account in a field of
 * its own: `paid_from` or `paid_to` on a Payment Entry, an accounts row on a
 * Journal Entry, `cash_bank_account` on a paid Purchase Invoice, a payment row
 * on a POS Sales Invoice, and `payment_account` or `disbursement_account` on
 * lending's two. All through Frappe's permission-checked reads, so a draft
 * somebody may not see is not shown to them. The two child tables go through
 * `frappe.client.get_list` with their parent, like every child read here.
 *
 * Read regardless of the period on screen. A draft's date is whatever it was
 * when somebody started it, and it may well change before it is submitted, so
 * it says little about which statement the money belongs to.
 */
export function useDraftEntries() {
  const paymentsIn = documentList<{ name: string; posting_date: string; received_amount: number; party_name: string | null; reference_no: string | null }>('Payment Entry')
  const paymentsOut = documentList<{ name: string; posting_date: string; paid_amount: number; party_name: string | null; reference_no: string | null }>('Payment Entry')
  const journalRows = useCall<
    { parent: string; debit_in_account_currency: number; credit_in_account_currency: number }[],
    { doctype: string; parent: string; fields: string; filters: string; limit_page_length: number }
  >({ url: `${CLIENT}.get_list`, immediate: false })
  const journals = documentList<{ name: string; posting_date: string; title: string | null; cheque_no: string | null }>('Journal Entry')
  const purchases = documentList<{ name: string; posting_date: string; paid_amount: number; supplier_name: string | null; bill_no: string | null }>('Purchase Invoice')
  const posRows = useCall<
    { parent: string; amount: number }[],
    { doctype: string; parent: string; fields: string; filters: string; limit_page_length: number }
  >({ url: `${CLIENT}.get_list`, immediate: false })
  const sales = documentList<{ name: string; posting_date: string; customer_name: string | null }>('Sales Invoice')
  const repayments = documentList<{ name: string; posting_date: string; amount_paid: number; applicant: string; reference_number: string | null }>(LOAN_REPAYMENT)
  const disbursements = documentList<{ name: string; disbursement_date: string; disbursed_amount: number; applicant: string; reference_number: string | null }>('Loan Disbursement')

  const drafts = ref<BookEntry[]>([])
  const error = ref<Error | null>(null)

  async function load(account: BankAccountRow | null, lending: boolean) {
    const gl = account?.account
    if (!gl) {
      drafts.value = []
      return
    }
    error.value = null
    const draft = (field: string) => JSON.stringify([['docstatus', '=', 0], [field, '=', gl]])
    const list = (fields: string[], filters: string) => ({ fields: JSON.stringify(fields), filters, limit: PAGE.repayments })
    const child = (doctype: string, parent: string, fields: string[]) => ({
      doctype,
      parent,
      fields: JSON.stringify(fields),
      filters: JSON.stringify([['docstatus', '=', 0], ['account', '=', gl]]),
      limit_page_length: PAGE.repayments,
    })
    try {
      const [inRows, outRows, jeRows, piRows, siRows, lrRows, ldRows] = await Promise.all([
        fetchRows(paymentsIn, list(['name', 'posting_date', 'received_amount', 'party_name', 'reference_no'], draft('paid_to'))),
        fetchRows(paymentsOut, list(['name', 'posting_date', 'paid_amount', 'party_name', 'reference_no'], draft('paid_from'))),
        fetchRows(journalRows, child('Journal Entry Account', 'Journal Entry', ['parent', 'debit_in_account_currency', 'credit_in_account_currency'])),
        fetchRows(
          purchases,
          list(
            ['name', 'posting_date', 'paid_amount', 'supplier_name', 'bill_no'],
            JSON.stringify([['docstatus', '=', 0], ['is_paid', '=', 1], ['cash_bank_account', '=', gl]]),
          ),
        ),
        fetchRows(posRows, child('Sales Invoice Payment', 'Sales Invoice', ['parent', 'amount'])),
        lending
          ? fetchRows(repayments, list(['name', 'posting_date', 'amount_paid', 'applicant', 'reference_number'], draft('payment_account')))
          : [],
        lending
          ? fetchRows(disbursements, list(['name', 'disbursement_date', 'disbursed_amount', 'applicant', 'reference_number'], draft('disbursement_account')))
          : [],
      ])

      // A journal or a POS invoice can touch the account on more than one
      // row; each is one entry, net.
      const net = <Row extends { parent: string }>(rows: Row[], amount: (row: Row) => number) => {
        const totals = new Map<string, number>()
        for (const row of rows) totals.set(row.parent, (totals.get(row.parent) ?? 0) + amount(row))
        return totals
      }
      const jeNet = net(jeRows, (row) => row.debit_in_account_currency - row.credit_in_account_currency)
      const siNet = net(siRows, (row) => row.amount)
      const [jeDocs, siDocs] = await Promise.all([
        jeNet.size
          ? fetchRows(journals, list(['name', 'posting_date', 'title', 'cheque_no'], JSON.stringify([['name', 'in', [...jeNet.keys()]]])))
          : [],
        siNet.size
          ? fetchRows(sales, list(['name', 'posting_date', 'customer_name'], JSON.stringify([['name', 'in', [...siNet.keys()]]])))
          : [],
      ])

      const entry = (doctype: string, name: string, date: string, amount: number, against: string | null, reference: string | null): BookEntry => ({
        doctype,
        name,
        date: String(date ?? '').slice(0, 10),
        debit: amount > 0 ? amount : 0,
        credit: amount < 0 ? -amount : 0,
        against,
        reference,
        draft: true,
      })
      drafts.value = [
        ...inRows.map((row) => entry('Payment Entry', row.name, row.posting_date, row.received_amount, row.party_name, row.reference_no)),
        ...outRows.map((row) => entry('Payment Entry', row.name, row.posting_date, -row.paid_amount, row.party_name, row.reference_no)),
        ...jeDocs.map((row) => entry('Journal Entry', row.name, row.posting_date, jeNet.get(row.name) ?? 0, row.title, row.cheque_no)),
        ...piRows.map((row) => entry('Purchase Invoice', row.name, row.posting_date, -row.paid_amount, row.supplier_name, row.bill_no)),
        ...siDocs.map((row) => entry('Sales Invoice', row.name, row.posting_date, siNet.get(row.name) ?? 0, row.customer_name, null)),
        ...lrRows.map((row) => entry(LOAN_REPAYMENT, row.name, row.posting_date, row.amount_paid, row.applicant, row.reference_number)),
        ...ldRows.map((row) => entry('Loan Disbursement', row.name, row.disbursement_date, -row.disbursed_amount, row.applicant, row.reference_number)),
      ]
        .filter((row) => row.debit || row.credit)
        .sort((a, b) => a.date.localeCompare(b.date))
    } catch (problem) {
      error.value = problem as Error
      drafts.value = []
    }
  }

  return { load, drafts, error }
}

/** Submit a draft and match it to a statement line, in one transaction. See
 *  `commons.banking.reconciliation.submit_and_reconcile`. */
export function useSubmitAndReconcile() {
  return useCall<
    { transaction: string; status: string; unallocated_amount: number; voucher: string },
    { bank_transaction: string; voucher_type: string; voucher: string }
  >({ url: `${COMMONS}.submit_and_reconcile`, method: 'POST', immediate: false })
}

function isoToday(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

export interface Progress {
  /** The latest statement line imported: how far the bank's side is known. */
  lastLineDate: string | null
  /** The statement's currency, off that line: a Bank Account names none. */
  currency: string | null
  /** The dates of every line still open, for saying how many fall outside the
   *  period on screen. */
  openDates: string[]
}

/** How far the statement runs, and where its open lines are. Independent of
 *  the period on screen. */
export function useProgress() {
  const lastLine = documentList<{ date: string; currency: string | null }>(BANK_TRANSACTION)
  const openLines = documentList<{ date: string }>(BANK_TRANSACTION)

  const progress = ref<Progress | null>(null)
  const error = ref<Error | null>(null)

  async function load(account: BankAccountRow | null) {
    if (!account) {
      progress.value = null
      return
    }
    error.value = null
    const base = [
      ['bank_account', '=', account.name],
      ['docstatus', '=', 1],
    ]
    try {
      const [last, open] = await Promise.all([
        fetchRows(lastLine, {
          fields: JSON.stringify(['date', 'currency']),
          filters: JSON.stringify(base),
          order_by: 'date desc',
          limit: 1,
        }),
        fetchRows(openLines, {
          fields: JSON.stringify(['date']),
          filters: JSON.stringify([...base, ['unallocated_amount', '>', 0]]),
          limit: PAGE.transactions,
        }),
      ])
      progress.value = {
        lastLineDate: last[0]?.date ?? null,
        currency: last[0]?.currency ?? null,
        openDates: open.map((line) => line.date),
      }
    } catch (problem) {
      error.value = problem as Error
      progress.value = null
    }
  }

  return { load, progress, error }
}

/* -------------------------------------------------------------------------- */
/* Statement lines                                                             */
/* -------------------------------------------------------------------------- */

export type TransactionView = 'unreconciled' | 'reconciled' | 'all'

const TRANSACTION_FIELDS = [
  'name',
  'date',
  'deposit',
  'withdrawal',
  'currency',
  'description',
  'reference_number',
  'party_type',
  'party',
  'allocated_amount',
  'unallocated_amount',
  'status',
  'bank_account',
  'company',
  'transaction_type',
]

export function useTransactions() {
  const list = documentList<TransactionRow>(BANK_TRANSACTION)
  const beforeList = documentList<TransactionRow>(BANK_TRANSACTION)
  const afterList = documentList<TransactionRow>(BANK_TRANSACTION)
  const rows = ref<TransactionRow[]>([]) as Ref<TransactionRow[]>
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<Error | null>(null)

  /**
   * The period's lines, and with `outside` also every line still open on
   * either side of it. Those are the ones the desk tool lost: a deposit nobody
   * dealt with last month simply dropped out of this month's dates.
   */
  async function load(bankAccount: string, from: string, to: string, outside = false) {
    if (!bankAccount) return
    loading.value = true
    error.value = null
    const base = [
      ['bank_account', '=', bankAccount],
      ['docstatus', '=', 1],
    ]
    const read = (call: typeof list, filters: unknown[]) =>
      fetchRows(call, {
        fields: JSON.stringify(TRANSACTION_FIELDS),
        filters: JSON.stringify([...base, ...filters]),
        order_by: 'date asc, creation asc',
        limit: PAGE.transactions,
      })
    try {
      const [inside, before, after] = await Promise.all([
        read(list, [['date', 'between', [from, to]]]),
        outside ? read(beforeList, [['date', '<', from], ['unallocated_amount', '>', 0]]) : [],
        outside ? read(afterList, [['date', '>', to], ['unallocated_amount', '>', 0]]) : [],
      ])
      rows.value = [...before, ...inside, ...after]
      loaded.value = true
    } catch (problem) {
      error.value = problem as Error
      rows.value = []
    } finally {
      loading.value = false
    }
  }

  /** Put a line the server has just changed back into the list, so the page
   *  moves on without re-reading everything. */
  function patch(name: string, values: Partial<TransactionRow>) {
    rows.value = rows.value.map((row) => (row.name === name ? { ...row, ...values } : row))
  }

  return { load, patch, rows, loading, loaded, error }
}

/** Whether a line is in the chosen view. `Reconciled` is ERPNext's own status;
 *  "unreconciled" is anything with money left to account for, which includes
 *  a line matched in part. */
export function inView(row: TransactionRow, view: TransactionView): boolean {
  if (view === 'all') return true
  const open = (row.unallocated_amount || 0) > 0.005
  return view === 'unreconciled' ? open : !open
}

/* -------------------------------------------------------------------------- */
/* Loans                                                                       */
/* -------------------------------------------------------------------------- */

/** The field each applicant doctype keeps a person's name in. */
const APPLICANT_TITLE: Record<string, string> = {
  Student: 'student_name',
  Employee: 'employee_name',
  Customer: 'customer_name',
  Member: 'member_name',
}

export interface LoanBook {
  loans: LoanRow[]
  /** Applicant id to the name a person would recognise. */
  names: Record<string, string>
  /** Every earlier repayment of these loans, with the statement line it was
   *  matched to where there is one. What suggestions learn from. */
  history: RepaymentHistory[]
  /** Repayments already on the books that no statement line accounts for
   *  yet, posted to this bank. */
  uncleared: RepaymentRow[]
}

const EMPTY_BOOK: LoanBook = { loans: [], names: {}, history: [], uncleared: [] }

/**
 * Everything the loan tab needs for one bank account, in three rounds.
 *
 * Fetched once per account rather than per line: forty statement lines are
 * judged against the same hundred loans.
 */
export function useLoanBook() {
  const loans = documentList<LoanRow>('Loan')
  const repayments = documentList<{ name: string; against_loan: string; amount_paid: number }>(
    LOAN_REPAYMENT,
  )
  const uncleared = documentList<RepaymentRow>(LOAN_REPAYMENT)
  const links = useCall<
    { parent: string; payment_entry: string }[],
    { doctype: string; parent: string; fields: string; filters: string; limit_page_length: number }
  >({ url: `${CLIENT}.get_list`, immediate: false })
  const lines = documentList<{ name: string; description: string | null }>(BANK_TRANSACTION)
  const nameLists = new Map<string, ReturnType<typeof documentList<Record<string, string>>>>()

  const book = ref<LoanBook>(EMPTY_BOOK) as Ref<LoanBook>
  const loading = ref(false)
  const error = ref<Error | null>(null)

  async function load(account: BankAccountRow | null) {
    if (!account?.company || !account.account) {
      book.value = EMPTY_BOOK
      return
    }
    loading.value = true
    error.value = null
    try {
      const [loanRows, open] = await Promise.all([
        fetchRows(loans, {
          fields: JSON.stringify([
            'name',
            'applicant_type',
            'applicant',
            'company',
            'loan_product',
            'status',
            'loan_amount',
            'disbursed_amount',
            'total_payment',
            'total_principal_paid',
            'total_interest_payable',
            'debit_adjustment_amount',
            'credit_adjustment_amount',
            'posting_date',
          ]),
          filters: JSON.stringify([
            ['docstatus', '=', 1],
            ['company', '=', account.company],
            ['status', 'in', OPEN_LOAN_STATUSES],
          ]),
          order_by: 'name asc',
          limit: PAGE.loans,
        }),
        fetchRows(uncleared, {
          fields: JSON.stringify([
            'name',
            'against_loan',
            'applicant_type',
            'applicant',
            'amount_paid',
            'value_date',
            'reference_number',
            'reference_date',
          ]),
          filters: JSON.stringify([
            ['docstatus', '=', 1],
            ['clearance_date', 'is', 'not set'],
            ['payment_account', '=', account.account],
          ]),
          order_by: 'value_date asc',
          limit: PAGE.repayments,
        }),
      ])

      const loanNames = loanRows.map((row) => row.name)
      const [paid, linked, described, names] = await Promise.all([
        loanNames.length
          ? fetchRows(repayments, {
              fields: JSON.stringify(['name', 'against_loan', 'amount_paid']),
              filters: JSON.stringify([
                ['docstatus', '=', 1],
                ['against_loan', 'in', loanNames],
              ]),
              // Oldest first: `suggestLoans` reads the order as "paid last".
              order_by: 'value_date asc, creation asc',
              limit: PAGE.history,
            })
          : [],
        // Which statement line each repayment was matched to. A child table,
        // so `frappe.client.get_list` with its parent. The document API
        // cannot read one (see `attendance.ts`).
        fetchRows(links, {
          doctype: 'Bank Transaction Payments',
          parent: BANK_TRANSACTION,
          fields: JSON.stringify(['parent', 'payment_entry']),
          filters: JSON.stringify([['payment_document', '=', LOAN_REPAYMENT]]),
          limit_page_length: PAGE.history,
        }),
        // The descriptions of this account's matched lines, read by account
        // rather than by name so the filter stays short however long the
        // history is.
        fetchRows(lines, {
          fields: JSON.stringify(['name', 'description']),
          filters: JSON.stringify([
            ['bank_account', '=', account.name],
            ['docstatus', '=', 1],
            ['deposit', '>', 0],
            ['allocated_amount', '>', 0],
          ]),
          limit: PAGE.history,
        }),
        borrowerNames(loanRows),
      ])

      const lineOf = new Map(linked.map((row) => [row.payment_entry, row.parent]))
      const descriptionOf = new Map(described.map((row) => [row.name, row.description]))
      book.value = {
        loans: loanRows,
        names,
        history: paid.map((row) => ({
          loan: row.against_loan,
          amount: row.amount_paid,
          description: descriptionOf.get(lineOf.get(row.name) ?? '') ?? null,
        })),
        uncleared: open,
      }
    } catch (problem) {
      error.value = problem as Error
      book.value = EMPTY_BOOK
    } finally {
      loading.value = false
    }
  }

  /** The names behind the applicant ids, one read per applicant doctype. A
   *  doctype this reader may not read leaves its borrowers named by id, which
   *  costs the name-in-description suggestion and nothing else. */
  async function borrowerNames(rows: LoanRow[]): Promise<Record<string, string>> {
    const byType = new Map<string, string[]>()
    for (const row of rows) {
      if (!byType.has(row.applicant_type)) byType.set(row.applicant_type, [])
      byType.get(row.applicant_type)!.push(row.applicant)
    }
    const names: Record<string, string> = {}
    await Promise.all(
      [...byType].map(async ([doctype, ids]) => {
        const field = APPLICANT_TITLE[doctype]
        if (!field) return
        if (!nameLists.has(doctype)) nameLists.set(doctype, documentList<Record<string, string>>(doctype))
        const call = nameLists.get(doctype)!
        const found = await call.submit({
          fields: JSON.stringify(['name', field]),
          filters: JSON.stringify([['name', 'in', [...new Set(ids)]]]),
          limit: PAGE.loans,
        })
        for (const row of found ?? []) if (row[field]) names[row.name] = row[field]
      }),
    )
    return names
  }

  return { load, book, loading, error }
}

/* -------------------------------------------------------------------------- */
/* Candidates                                                                  */
/* -------------------------------------------------------------------------- */

export interface CandidateQuery {
  transaction: string
  types: VoucherKey[]
  exactMatch: boolean
  from: string
  to: string
}

/** ERPNext's candidate search, without loan repayments. Dates are always sent:
 *  with none, its queries compare against `BETWEEN NULL AND NULL` and quietly
 *  find nothing. */
export function useCandidates() {
  const call = useCall<
    Candidate[],
    { bank_transaction_name: string; document_types: string; from_date: string; to_date: string }
  >({ url: `${TOOL}.get_linked_payments`, immediate: false })

  async function search(query: CandidateQuery): Promise<Candidate[]> {
    const types: string[] = query.types.filter((type) => type !== 'loan_repayment')
    if (!types.length) return []
    if (query.exactMatch) types.push('exact_match')
    return fetchRows(call, {
      bank_transaction_name: query.transaction,
      document_types: JSON.stringify(types),
      from_date: query.from,
      to_date: query.to,
    })
  }

  return { search, loading: computed(() => call.loading) }
}

/* -------------------------------------------------------------------------- */
/* Writes                                                                      */
/* -------------------------------------------------------------------------- */

/** The transaction as ERPNext hands it back after a write. */
export interface ReconciledTransaction {
  name: string
  status: string
  allocated_amount: number
  unallocated_amount: number
  payment_entries?: LinkedVoucher[]
}

export interface LinkedVoucher {
  name: string
  payment_document: string
  payment_entry: string
  allocated_amount: number
  reconciliation_type: string | null
}

/** Match vouchers that already exist. `vouchers` has to be a JSON string,
 *  because the function parses it itself and a JSON array fails its type check. */
export function useReconcileVouchers() {
  return useCall<ReconciledTransaction, { bank_transaction_name: string; vouchers: string }>({
    url: `${TOOL}.reconcile_vouchers`,
    method: 'POST',
    immediate: false,
  })
}

export function useCreateLoanRepayments() {
  return useCall<
    { transaction: string; status: string; unallocated_amount: number; repayments: string[]; draft?: boolean },
    {
      bank_transaction: string
      repayments: { loan: string; amount: number }[]
      reference_number: string
      /** Insert the repayments as drafts: not submitted, not matched. */
      draft?: boolean
    }
  >({ url: `${COMMONS}.create_loan_repayments`, method: 'POST', immediate: false })
}

/* Accounting dimensions ---------------------------------------------------- */

/** One of the company's accounting dimensions, as
 *  `commons.banking.reconciliation.accounting_dimensions` answers it. */
export interface AccountingDimension {
  fieldname: string
  label: string
  document_type: string
  /** The company's default value, if it names one. */
  default: string | null
  mandatory_for_pl: boolean
  mandatory_for_bs: boolean
}

/** Values for the dimensions an entry carries, keyed by fieldname. */
export type DimensionValues = Record<string, string | null>

/**
 * The company's dimensions, and which must be set.
 *
 * ERPNext refuses to submit a voucher whose GL entries leave out a dimension
 * marked mandatory for that kind of account, and a bank line's own entry is
 * against a Balance Sheet account. So the entry forms ask for every mandatory
 * dimension up front. Read through this app's endpoint because an Accounts
 * User may not read `Accounting Dimension` itself.
 */
export function useAccountingDimensions() {
  const call = useCall<AccountingDimension[], { company: string }>({
    url: `${COMMONS}.accounting_dimensions`,
    immediate: false,
  })
  const cache = new Map<string, AccountingDimension[]>()
  return {
    async load(company: string): Promise<AccountingDimension[]> {
      if (!cache.has(company)) cache.set(company, await fetchRows(call, { company }))
      return cache.get(company)!
    },
  }
}

/** The dimensions an entry has to carry: any the company makes mandatory for
 *  either kind of account. The bank's own line is a Balance Sheet account and
 *  the other side is usually Profit and Loss, so an entry from a statement
 *  line touches both. */
export function requiredDimensions(dimensions: AccountingDimension[]): AccountingDimension[] {
  return dimensions.filter((dimension) => dimension.mandatory_for_pl || dimension.mandatory_for_bs)
}

/* Payment and journal entries ------------------------------------------------ */

export interface PaymentEntryParams {
  bank_transaction_name: string
  party_type: string
  party: string
  posting_date: string
  reference_number: string
  reference_date: string
  mode_of_payment?: string
  cost_center?: string
  project?: string
}

/**
 * Create a Payment Entry from a line, with its dimensions, and reconcile it.
 *
 * Two ERPNext calls. `create_payment_entry_bts` with `allow_edit` builds the
 * entry (accounts, amounts, exchange rate, all worked out from the line and
 * the party) and returns it unsaved. The dimensions are set on it, because a
 * Payment Entry's GL entries take them from its header, and
 * `create_payment_entry_and_reconcile` then inserts, submits and matches it.
 * The single-call `create_payment_entry_bts` has no way to pass them.
 */
export function useCreatePaymentEntry() {
  const prepare = useCall<Record<string, unknown>, PaymentEntryParams & { allow_edit: number }>({
    url: `${TOOL}.create_payment_entry_bts`,
    method: 'POST',
    immediate: false,
  })
  const create = useCall<
    { transaction: ReconciledTransaction; payment_entry: { name: string } },
    { bank_transaction_name: string; payment_entry_doc: Record<string, unknown> }
  >({ url: `${TOOL}.create_payment_entry_and_reconcile`, method: 'POST', immediate: false })

  const insert = useInsertDraft()

  return {
    /**
     * `references` are the invoices the payment is booked against, as
     * `referenceRows` in `paymentAllocation.ts` builds them. They go on the
     * entry's references table, as the desk's "Get Outstanding Invoices" puts
     * them; ERPNext works out the unallocated rest itself when it validates.
     *
     * With `draft`, the entry is inserted as a draft instead: not submitted,
     * not matched. The line keeps what it had left.
     */
    async run(
      params: PaymentEntryParams,
      dimensions: DimensionValues,
      draft = false,
      references: Record<string, unknown>[] = [],
    ): Promise<EntryResult> {
      const built = await write(prepare, { ...params, allow_edit: 1 })
      if (!built.ok || !built.data) return { ok: false, error: built.error, unallocated: null, name: null }
      const { name: _unsaved, ...doc } = built.data
      const entry = { ...doc, ...present(dimensions), references }
      if (draft) return insert.run({ ...entry, doctype: 'Payment Entry', docstatus: 0 })
      const done = await write(create, {
        bank_transaction_name: params.bank_transaction_name,
        payment_entry_doc: entry,
      })
      return {
        ok: done.ok,
        error: done.error,
        unallocated: done.data?.transaction.unallocated_amount ?? null,
        name: done.data?.payment_entry?.name ?? null,
      }
    },
  }
}

/**
 * A party's outstanding invoices and other documents a payment can be booked
 * against, through ERPNext's own calls: `get_party_account` for the party's
 * receivable or payable account, then `get_outstanding_reference_documents`,
 * which is what the desk's "Get Outstanding Invoices" calls. It checks read
 * permission on the party, and it splits an invoice with payment terms into
 * one row per term, as the desk does.
 *
 * Only documents with something outstanding: credit notes and returns, which
 * come back negative, are left to the desk.
 */
export function useOutstandingDocuments() {
  const account = useCall<string | null, { party_type: string; party: string; company: string }>({
    url: `${METHOD}/erpnext.accounts.party.get_party_account`,
    immediate: false,
  })
  const documents = useCall<OutstandingDocument[] | null, { args: string }>({
    url: `${METHOD}/erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents`,
    method: 'POST',
    immediate: false,
  })
  return {
    async load(query: {
      company: string
      party_type: string
      party: string
      posting_date: string
      payment_type: 'Receive' | 'Pay'
    }): Promise<OutstandingDocument[]> {
      const partyAccount = await fetchRows(account, {
        party_type: query.party_type,
        party: query.party,
        company: query.company,
      })
      if (!partyAccount) return []
      const rows = await fetchRows(documents, {
        args: JSON.stringify({ ...query, party_account: partyAccount, get_outstanding_invoices: true }),
      }).catch((error) => {
        // Answers with nothing, rather than an empty list, when there is nothing
        // outstanding; that is not a failure.
        if (documents.error) throw error
        return []
      })
      return (rows ?? []).filter((row) => row.outstanding_amount > 0)
    },
  }
}

/** What creating an entry from a line comes back with: whether it worked, what
 *  is left on the line, and the new document's name. */
export interface EntryResult {
  ok: boolean
  error: Error | null
  unallocated: number | null
  name: string | null
}

/** Insert one draft document through `frappe.client.insert`, which runs its
 *  validation and checks `create`, and submits nothing. */
function useInsertDraft() {
  const call = useCall<{ name: string }, { doc: string }>({
    url: `${CLIENT}.insert`,
    method: 'POST',
    immediate: false,
  })
  return {
    async run(doc: Record<string, unknown>, unallocated: number | null = null): Promise<EntryResult> {
      const done = await write(call, { doc: JSON.stringify(doc) })
      return { ok: done.ok, error: done.error, unallocated, name: done.data?.name ?? null }
    },
  }
}

export interface JournalEntryParams {
  transaction: TransactionRow
  /** The other side of the entry. */
  account: string
  entry_type: string
  posting_date: string
  reference_number: string
  reference_date: string
  party_type?: string | null
  party?: string | null
}

/**
 * Create a Journal Entry from a line, with its dimensions, and reconcile it.
 *
 * ERPNext's `create_bank_entry_and_reconcile`, which takes the entry's rows
 * as given and copies every field of each onto its journal line. So each row
 * carries the dimensions itself: `create_journal_entry_bts` builds the rows
 * for you and has nowhere to put them, and the function's own `dimensions`
 * argument is accepted and never read. Both rows are sent, because it adds
 * none of its own: the bank's GL account, and the other side.
 *
 * For what is left on the line rather than its whole amount, so a line that is
 * already part matched is not over-allocated.
 */
export function useCreateJournalEntry() {
  const bank = documentList<{ account: string | null }>('Bank Account')
  const create = useCall<
    { transaction: ReconciledTransaction; journal_entry: { name: string } },
    {
      bank_transaction_name: string
      cheque_date: string
      posting_date: string
      cheque_no: string
      voucher_type: string
      entries: Record<string, unknown>[]
    }
  >({ url: `${TOOL}.create_bank_entry_and_reconcile`, method: 'POST', immediate: false })

  const accountType = documentList<{ report_type: string | null }>('Account')
  const company = documentList<{ cost_center: string | null }>('Company')
  const insert = useInsertDraft()

  /**
   * The company's default cost center, for the other side when it is an
   * income or expense account. What `create_bank_entry_and_reconcile` adds
   * itself, so a draft gets it too and can be submitted as it stands. Left
   * out, rather than failing, if either cannot be read: the draft is still
   * made, and the desk asks for it at submit.
   */
  async function costCenterFor(account: string, companyName: string | null): Promise<string | null> {
    if (!companyName) return null
    try {
      const [[typed], [owner]] = await Promise.all([
        fetchRows(accountType, { fields: JSON.stringify(['report_type']), filters: JSON.stringify([['name', '=', account]]), limit: 1 }),
        fetchRows(company, { fields: JSON.stringify(['cost_center']), filters: JSON.stringify([['name', '=', companyName]]), limit: 1 }),
      ])
      return typed?.report_type === 'Profit and Loss' ? (owner?.cost_center ?? null) : null
    } catch {
      return null
    }
  }

  return {
    /** With `draft`, the same two rows are inserted as a draft Journal Entry
     *  instead: not submitted, not matched. The line keeps what it had left. */
    async run(params: JournalEntryParams, dimensions: DimensionValues, draft = false): Promise<EntryResult> {
      const [row] = await fetchRows(bank, {
        fields: JSON.stringify(['account']),
        filters: JSON.stringify([['name', '=', params.transaction.bank_account]]),
        limit: 1,
      })
      if (!row?.account) {
        return { ok: false, error: new Error('This bank account has no GL account.'), unallocated: null, name: null }
      }
      const amount = money(params.transaction.unallocated_amount)
      const deposit = params.transaction.deposit > 0
      const tags = present(dimensions)
      if (draft) {
        const costCenter = await costCenterFor(params.account, params.transaction.company)
        return insert.run(
          {
            doctype: 'Journal Entry',
            docstatus: 0,
            voucher_type: params.entry_type,
            company: params.transaction.company,
            posting_date: params.posting_date,
            cheque_no: params.reference_number,
            cheque_date: params.reference_date,
            accounts: [
              {
                account: row.account,
                bank_account: params.transaction.bank_account,
                debit_in_account_currency: deposit ? amount : 0,
                credit_in_account_currency: deposit ? 0 : amount,
                ...tags,
              },
              {
                account: params.account,
                debit_in_account_currency: deposit ? 0 : amount,
                credit_in_account_currency: deposit ? amount : 0,
                ...(params.party ? { party_type: params.party_type, party: params.party } : {}),
                ...(costCenter ? { cost_center: costCenter } : {}),
                ...tags,
              },
            ],
          },
          params.transaction.unallocated_amount,
        )
      }
      const done = await write(create, {
        bank_transaction_name: params.transaction.name,
        cheque_date: params.reference_date,
        posting_date: params.posting_date,
        cheque_no: params.reference_number,
        voucher_type: params.entry_type,
        entries: [
          {
            account: row.account,
            bank_account: params.transaction.bank_account,
            debit: deposit ? amount : 0,
            credit: deposit ? 0 : amount,
            ...tags,
          },
          {
            account: params.account,
            debit: deposit ? 0 : amount,
            credit: deposit ? amount : 0,
            ...(params.party ? { party_type: params.party_type, party: params.party } : {}),
            ...tags,
          },
        ],
      })
      return {
        ok: done.ok,
        error: done.error,
        unallocated: done.data?.transaction.unallocated_amount ?? null,
        name: done.data?.journal_entry?.name ?? null,
      }
    },
  }
}

/** Dimension values that are set, as fields to spread onto a document. */
function present(values: DimensionValues): Record<string, string> {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value)) as Record<string, string>
}

/** Reference and party on a line. Both party fields are always sent: the
 *  function clears whichever one it is not given. */
export function useUpdateTransaction() {
  return useCall<
    TransactionRow,
    { bank_transaction_name: string; reference_number: string; party_type: string | null; party: string | null }
  >({ url: `${TOOL}.update_bank_transaction`, method: 'POST', immediate: false })
}

/** Unlink everything matched to a line. Cancels nothing: the vouchers stay
 *  submitted and become matchable again. The desk form's Unreconcile button. */
export function useUnlinkTransaction() {
  // The document route, because the method belongs to the document. The URL
  // names the line, so it is a ref that is pointed at a line before each call.
  const url = ref('')
  const call = useCall<unknown, Record<string, never>>({ url, method: 'POST', immediate: false })
  return {
    call,
    async unlink(name: string) {
      url.value = `${DOCUMENT}/${encodeURIComponent(BANK_TRANSACTION)}/${encodeURIComponent(name)}/method/remove_payment_entries/`
      return write(call, {})
    },
  }
}

/** The vouchers matched to one line, for the reconciled view. */
export function useLinkedVouchers() {
  return useCall<
    LinkedVoucher[],
    { doctype: string; parent: string; fields: string; filters: string; limit_page_length: number }
  >({ url: `${CLIENT}.get_list`, immediate: false })
}

export function linkedVoucherParams(transaction: string) {
  return {
    doctype: 'Bank Transaction Payments',
    parent: BANK_TRANSACTION,
    fields: JSON.stringify([
      'name',
      'payment_document',
      'payment_entry',
      'allocated_amount',
      'reconciliation_type',
    ]),
    filters: JSON.stringify([['parent', '=', transaction]]),
    limit_page_length: 100,
  }
}

/** ERPNext's own automatic matcher. It works through every unreconciled line
 *  on the account, not only the ones on screen, and above ten lines it queues
 *  itself in the background. */
export function useAutoReconcile() {
  return useCall<null, { bank_account: string; from_date: string; to_date: string }>({
    url: `${TOOL}.auto_reconcile_vouchers`,
    method: 'POST',
    immediate: false,
  })
}

/** The desk address of a document, for "open in desk" links. */
export function deskUrl(doctype: string, name: string): string {
  return `/app/${doctype.toLowerCase().replace(/ /g, '-')}/${encodeURIComponent(name)}`
}

/* -------------------------------------------------------------------------- */
/* Importing a statement                                                       */
/* -------------------------------------------------------------------------- */

const IMPORT = 'commons.banking.statement_import'

/** Whether the page offers the import: bank transactions, a Claude key, and
 *  create on Bank Transaction. The server's answer, since only it can see
 *  whether a key is set. */
const importAvailableCall = useCall<boolean>({ url: `${METHOD}/${IMPORT}.import_available` })
export const importAvailable = computed(() => Boolean(importAvailableCall.data))

/** What the file picker offers. The server decides by the file's contents. */
export const ACCEPTED_STATEMENTS =
  '.xlsx,.xls,.csv,application/pdf,image/jpeg,image/png,image/webp,image/gif'

/**
 * Hand a statement over to be read, and get back a token to ask after it. A
 * multipart upload through frappe-ui's helper, as Document Capture sends
 * scans, so the file goes as it is. `/api/method` because the helper unwraps
 * v1's `message`.
 *
 * The reading itself happens in a background job, because copying a long PDF
 * can take Claude longer than a web request is allowed to last. See
 * `commons.banking.statement_import`.
 */
export async function startReading(file: File): Promise<string> {
  const answer = (await upload(file, {
    upload_endpoint: `/api/method/${IMPORT}.start_reading`,
    private: true,
  })) as unknown as { token: string }
  return answer.token
}

export interface ReadingState {
  status: 'queued' | 'reading' | 'done' | 'failed'
  /** What the job is doing: `copying` a PDF or photo, or for a spreadsheet
   *  working out its `columns` and then reading its `rows`. */
  step: 'copying' | 'columns' | 'rows' | null
  /** Rows read so far. */
  rows: number
  result?: StatementReading
  error?: string
}

export function useReadingStatus() {
  const call = useCall<ReadingState, { token: string }>({
    url: `${METHOD}/${IMPORT}.reading_status`,
    immediate: false,
  })
  return {
    async check(token: string): Promise<ReadingState> {
      return fetchRows(call, { token })
    },
  }
}

/** The lines already on an account over a stretch of dates, drafts included,
 *  for telling which statement rows are already imported. Cancelled lines are
 *  left out: those were deliberately taken back. */
export function useExistingLines() {
  const call = documentList<ExistingLine>(BANK_TRANSACTION)
  return {
    async load(bankAccount: string, from: string, to: string): Promise<ExistingLine[]> {
      return fetchRows(call, {
        fields: JSON.stringify(['name', 'date', 'deposit', 'withdrawal', 'description', 'reference_number']),
        filters: JSON.stringify([
          ['bank_account', '=', bankAccount],
          ['docstatus', 'in', [0, 1]],
          ['date', 'between', [from, to]],
        ]),
        limit: PAGE.transactions,
      })
    },
  }
}

/** The account's own number and currency: what a statement's account number
 *  is checked against, and the currency new lines are given, which ERPNext
 *  requires to be the GL account's. */
export function useAccountIdentity() {
  const bank = documentList<{ bank_account_no: string | null; iban: string | null }>('Bank Account')
  const gl = documentList<{ account_currency: string | null }>('Account')
  return {
    async load(account: BankAccountRow): Promise<{ numbers: (string | null)[]; currency: string | null }> {
      const [bankRows, glRows] = await Promise.all([
        fetchRows(bank, {
          fields: JSON.stringify(['bank_account_no', 'iban']),
          filters: JSON.stringify([['name', '=', account.name]]),
          limit: 1,
        }),
        account.account
          ? fetchRows(gl, {
              fields: JSON.stringify(['account_currency']),
              filters: JSON.stringify([['name', '=', account.account]]),
              limit: 1,
            })
          : [],
      ])
      return {
        numbers: [bankRows[0]?.bank_account_no ?? null, bankRows[0]?.iban ?? null],
        currency: glRows[0]?.account_currency ?? null,
      }
    },
  }
}

/** `insert_many` takes at most this many documents a request. */
const INSERT_CHUNK = 200

/**
 * Insert and submit Bank Transactions, through `frappe.client.insert_many`,
 * which runs each one's validation and permission check. One request per 200,
 * and each request is one transaction: a refusal stops there, and says how
 * many went in before it.
 */
export function useImportTransactions() {
  const call = useCall<string[], { docs: string }>({
    url: `${CLIENT}.insert_many`,
    method: 'POST',
    immediate: false,
  })
  return {
    async run(docs: object[]): Promise<{ created: string[]; error: Error | null }> {
      const created: string[] = []
      for (let start = 0; start < docs.length; start += INSERT_CHUNK) {
        const done = await write(call, { docs: JSON.stringify(docs.slice(start, start + INSERT_CHUNK)) })
        if (!done.ok) return { created, error: done.error }
        created.push(...(done.data ?? []))
      }
      return { created, error: null }
    },
  }
}
