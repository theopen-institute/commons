import { computed, ref, type Ref } from 'vue'
import { useCall } from 'frappe-ui'
import {
  OPEN_LOAN_STATUSES,
  type Candidate,
  type LoanRow,
  type RepaymentHistory,
  type RepaymentRow,
  type TransactionRow,
} from './reconciliationRules'

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

export function useBalances() {
  const opening = useCall<number, { bank_account: string; till_date: string; company: string }>({
    url: `${TOOL}.get_account_balance`,
    immediate: false,
  })
  const cleared = useCall<number, { bank_account: string; till_date: string; company: string }>({
    url: `${TOOL}.get_account_balance`,
    immediate: false,
  })
  const statement = useCall<
    { balance: number; date: string | null },
    { bank_account: string; date: string }
  >({ url: `${BANK_ACCOUNT_API}.get_closing_balance_as_per_statement`, immediate: false })

  const balances = ref<Balances>({ opening: null, cleared: null, statement: null, statementDate: null })
  const loading = ref(false)

  async function load(account: BankAccountRow | null, from: string, to: string) {
    if (!account?.company) return
    loading.value = true
    try {
      const [openingValue, clearedValue, statementValue] = await Promise.all([
        opening.submit({ bank_account: account.name, till_date: dayBefore(from), company: account.company }),
        cleared.submit({ bank_account: account.name, till_date: to, company: account.company }),
        statement.submit({ bank_account: account.name, date: to }),
      ])
      balances.value = {
        opening: openingValue,
        cleared: clearedValue,
        // A zero with no date is ERPNext's way of saying none was recorded.
        statement: statementValue?.date ? statementValue.balance : null,
        statementDate: statementValue?.date ?? null,
      }
    } finally {
      loading.value = false
    }
  }

  return { load, balances, loading }
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

function dayBefore(date: string): string {
  const [year, month, day] = date.split('-').map(Number)
  const previous = new Date(Date.UTC(year, month - 1, day - 1))
  return previous.toISOString().slice(0, 10)
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
  const older = documentList<{ name: string; date: string }>(BANK_TRANSACTION)
  const rows = ref<TransactionRow[]>([]) as Ref<TransactionRow[]>
  /** Unreconciled lines dated before the period, which the old tool simply
   *  did not show. The oldest date is what the page offers to widen to. */
  const earlier = ref<{ count: number; oldest: string | null }>({ count: 0, oldest: null })
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<Error | null>(null)

  async function load(bankAccount: string, from: string, to: string) {
    if (!bankAccount) return
    loading.value = true
    error.value = null
    try {
      const [lines, before] = await Promise.all([
        fetchRows(list, {
          fields: JSON.stringify(TRANSACTION_FIELDS),
          filters: JSON.stringify([
            ['bank_account', '=', bankAccount],
            ['docstatus', '=', 1],
            ['date', 'between', [from, to]],
          ]),
          order_by: 'date asc, creation asc',
          limit: PAGE.transactions,
        }),
        fetchRows(older, {
          fields: JSON.stringify(['name', 'date']),
          filters: JSON.stringify([
            ['bank_account', '=', bankAccount],
            ['docstatus', '=', 1],
            ['unallocated_amount', '>', 0],
            ['date', '<', from],
          ]),
          order_by: 'date asc',
          limit: PAGE.transactions,
        }),
      ])
      rows.value = lines
      earlier.value = { count: before.length, oldest: before[0]?.date ?? null }
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

  return { load, patch, rows, earlier, loading, loaded, error }
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
    { transaction: string; status: string; unallocated_amount: number; repayments: string[] },
    { bank_transaction: string; repayments: { loan: string; amount: number }[]; reference_number: string }
  >({ url: `${COMMONS}.create_loan_repayments`, method: 'POST', immediate: false })
}

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

export function useCreatePaymentEntry() {
  return useCall<ReconciledTransaction, PaymentEntryParams>({
    url: `${TOOL}.create_payment_entry_bts`,
    method: 'POST',
    immediate: false,
  })
}

export interface JournalEntryParams {
  bank_transaction_name: string
  second_account: string
  entry_type: string
  posting_date: string
  reference_number: string
  reference_date: string
  party_type?: string
  party?: string
  mode_of_payment?: string
}

export function useCreateJournalEntry() {
  return useCall<ReconciledTransaction, JournalEntryParams>({
    url: `${TOOL}.create_journal_entry_bts`,
    method: 'POST',
    immediate: false,
  })
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
