import { computed } from 'vue'
import { upload, useCall } from 'frappe-ui'
import { user } from './session'
import { pollReading, readingDeadlineMs, type JobState } from './backgroundReading'
import {
  offeredKinds,
  type CaptureKind,
  type ExpenseReading,
  type InvoicePayload,
  type Reading,
  type Totals,
} from './captureRules'
import { permissionCall } from './permissions'

/**
 * The document capture page's reads and writes.
 *
 * Every scan is a `Captured Document` first, uploaded here or emailed in, and
 * read in a background job by `commons.document_capture.capture`. So the page
 * uploads, asks after the capture until it is read (`waitForReading`), and
 * opens the dialog for what it became. The dialogs then call the kind's own
 * module (`purchase_invoice`, `expense_claim`), whose `create` attaches the
 * scan to the draft and marks the capture drafted, in the same transaction.
 *
 * The scan goes to `capture.upload` through frappe-ui's upload helper,
 * pointed at that endpoint instead of Frappe's. It is a multipart request, so
 * the file is sent as it is, and the helper refuses a file over the site's
 * upload limit before sending it. The helper's `doctype` field is what the
 * scan should become.
 */

const METHOD = '/api/v2/method'
const CAPTURE = 'commons.document_capture.capture'
const INVOICES = 'commons.document_capture.purchase_invoice'
const EXPENSES = 'commons.document_capture.expense_claim'

export const PURCHASE_INVOICE = 'Purchase Invoice' satisfies CaptureKind
export const EXPENSE_CLAIM = 'Expense Claim' satisfies CaptureKind

export type { CaptureKind }

/** How each kind is named to the person choosing one. */
export const KIND_LABELS: Record<CaptureKind, { noun: string; hint: string }> = {
  [PURCHASE_INVOICE]: {
    noun: "Supplier's invoice",
    hint: 'Drafted as a purchase invoice for accounts to check and submit.',
  },
  [EXPENSE_CLAIM]: {
    noun: 'Expense receipt',
    hint: 'Drafted as your own expense claim, for your approver.',
  },
}

/* -------------------------------------------------------------------------- */
/* Who the page is for                                                         */
/* -------------------------------------------------------------------------- */

/** Which kinds of scan this person may capture here: the server's own test,
 *  `capture.kinds`, which leaves out a kind Document Capture Settings has
 *  switched off. */
const contextCall = useCall<{ kinds: string[]; hourly_limit: number }>({
  url: `${METHOD}/${CAPTURE}.context`,
})

/** Whether the dialog offers to make a supplier the site does not have yet. */
const canCreateSupplierCall = permissionCall('Supplier', 'create')

export const captureCan = computed(() => {
  const kinds = offeredKinds(contextCall.data?.kinds)
  return {
    kinds,
    capture: kinds.length > 0,
    invoices: kinds.includes(PURCHASE_INVOICE),
    expenses: kinds.includes(EXPENSE_CLAIM),
    createSupplier: Boolean(canCreateSupplierCall.data?.has_permission),
  }
})

/** What the capture page waits on before it offers the upload. The sidebar
 *  row does not: it takes the same answer from the shell (`serverGate` in
 *  `data/shell.ts`), along with whether the site has a Claude key. */
export const captureGate = {
  visible: computed(() => captureCan.value.capture),
  resolved: computed(() => contextCall.isFinished),
}

/* -------------------------------------------------------------------------- */
/* The scan                                                                    */
/* -------------------------------------------------------------------------- */

/** What the file picker offers. The server decides by the file's contents,
 *  not by this. */
export const ACCEPTED_SCANS = 'image/jpeg,image/png,image/webp,image/gif,application/pdf'

/** Where a reading has got to, as `capture.status` answers: what the job is
 *  doing and how many lines Claude has copied so far. The result is the
 *  kind's own reading. */
export interface CaptureReadingState extends JobState<Reading | ExpenseReading> {
  step: 'reading' | null
  lines: number
}

/** The server's `JOB_TIMEOUT` for reading a scan, in seconds. */
const JOB_TIMEOUT_S = 420

/** How long `waitForReading` waits before giving up. See `readingDeadlineMs`. */
export const READING_DEADLINE_MS = readingDeadlineMs(JOB_TIMEOUT_S)

const statusCall = useCall<CaptureReadingState, { name: string }>({
  url: `${METHOD}/${CAPTURE}.status`,
  immediate: false,
})

async function captureStatus(name: string): Promise<CaptureReadingState> {
  const state = await statusCall.submit({ name })
  if (state === null) throw statusCall.error ?? new Error('Could not ask after the reading.')
  return state
}

/**
 * Keep a scan as a capture of this kind and start reading it. Resolves with
 * the capture's name once it is stored and queued.
 *
 * `/api/method` rather than `/api/v2/method`: the helper unwraps a `message`,
 * which is where v1 puts the answer.
 */
export async function uploadScan(file: File, kind: CaptureKind): Promise<string> {
  const started = (await upload(file, {
    upload_endpoint: `/api/method/${CAPTURE}.upload`,
    doctype: kind,
    private: true,
  })) as unknown as { name: string }
  return started.name
}

/**
 * Wait for a capture's reading, and answer with what the dialog opens with.
 *
 * `onProgress` is told each answer while the job runs; `cancelled` ends the
 * wait early, and the promise then rejects with `ReadingCancelled`. The
 * capture is kept whatever happens here: a failed read can be read again from
 * the page's list.
 */
export async function waitForReading(
  name: string,
  options: { onProgress?: (state: CaptureReadingState) => void; cancelled?: () => boolean } = {},
): Promise<Reading | ExpenseReading> {
  const result = await pollReading<Reading | ExpenseReading, CaptureReadingState>({
    check: () => captureStatus(name),
    deadlineMs: READING_DEADLINE_MS,
    deadlineMessage:
      'The scan is taking far longer than it should to read. It is kept in the list below; try again in a few minutes.',
    failedMessage: 'That scan could not be read.',
    onProgress: options.onProgress,
    cancelled: options.cancelled,
  })
  if (result === null) throw new ReadingCancelled()
  return result
}

/** Thrown by `waitForReading` when its caller stopped waiting. Nothing to show. */
export class ReadingCancelled extends Error {
  constructor() {
    super('The reading was cancelled.')
    this.name = 'ReadingCancelled'
  }
}

/** The progress line for a reading, from the latest answer. Null before the
 *  first answer. */
export function readingProgressText(state: CaptureReadingState | null): string | null {
  if (!state) return null
  if (state.status === 'queued') return 'Waiting for the background worker to start the reading'
  if (state.lines) return `Claude has copied ${state.lines} ${state.lines === 1 ? 'line' : 'lines'} so far`
  return 'Claude is reading the scan'
}

/* -------------------------------------------------------------------------- */
/* The captures waiting                                                        */
/* -------------------------------------------------------------------------- */

export type CaptureState = 'queued' | 'reading' | 'done' | 'failed' | 'unread' | 'received'

export interface CaptureRow {
  name: string
  document_type: CaptureKind
  status: string
  /** Where it stands, with a job that died counted as failed. */
  state: CaptureState
  source: 'Upload' | 'Email'
  subject: string | null
  sender: string | null
  sender_name: string | null
  scan: string | null
  error: string | null
  owner: string
  creation: string
}

/** Captures this person may draft from that are not drafts yet, newest first:
 *  read and waiting to be checked, held unread, or failed. */
export function useWaitingCaptures() {
  const call = useCall<CaptureRow[]>({
    url: `${METHOD}/${CAPTURE}.waiting`,
    immediate: false,
  })
  return {
    load: () => call.submit(),
    rows: computed(() => call.data ?? []),
    loaded: computed(() => call.isFinished),
    loading: computed(() => call.loading),
    error: computed(() => call.error ?? null),
  }
}

/** Read a held or failed capture, or read it again, as `document_type`. */
export function useReadCapture() {
  return useCall<{ name: string }, { name: string; document_type: CaptureKind }>({
    url: `${METHOD}/${CAPTURE}.read`,
    method: 'POST',
    immediate: false,
  })
}

export function useDiscardCapture() {
  return useCall<null, { name: string }>({
    url: `${METHOD}/${CAPTURE}.discard`,
    method: 'POST',
    immediate: false,
  })
}

/** What the dialog opens with for a capture that has been read. */
export function useOpenCapture() {
  return useCall<Reading | ExpenseReading, { name: string }>({
    url: `${METHOD}/${CAPTURE}.open_capture`,
    immediate: false,
  })
}

/** Whether a stored scan is a PDF, by its URL: the server keeps the name. */
export function isPdfUrl(url: string | null | undefined): boolean {
  return (url ?? '').toLowerCase().split('?')[0].endsWith('.pdf')
}

/* -------------------------------------------------------------------------- */
/* The draft                                                                   */
/* -------------------------------------------------------------------------- */

export interface LineSuggestion {
  account: string | null
  reason: string
  review: boolean
}

export interface TaxOption {
  key: string
  label: string
  summary: string
}

export interface Suggestions {
  lines: LineSuggestion[]
  taxes: { options: TaxOption[]; suggested: string; reason: string }
  duplicates: string[]
  currency: string | null
}

export interface SuggestParams {
  company: string
  descriptions: string[]
  taxed: boolean
  supplier: string | null
  bill_no: string | null
}

export function useSuggest() {
  return useCall<Suggestions, SuggestParams>({
    url: `${METHOD}/${INVOICES}.suggest`,
    method: 'POST',
    immediate: false,
  })
}

export function usePreview() {
  return useCall<Totals, { invoice: InvoicePayload; new_supplier: boolean }>({
    url: `${METHOD}/${INVOICES}.preview`,
    method: 'POST',
    immediate: false,
  })
}

export interface Created {
  name: string
  supplier: string
  grand_total: number
  currency: string
}

export function useCreate() {
  return useCall<
    Created,
    {
      invoice: InvoicePayload
      new_supplier: { supplier_name: string; tax_id: string } | null
      capture: string
    }
  >({
    url: `${METHOD}/${INVOICES}.create`,
    method: 'POST',
    immediate: false,
  })
}

export interface ExpenseLinePayload {
  expense_date: string
  expense_type: string
  description: string
  amount: number
}

/** Raise the claimant's own claim from a receipt capture. */
export function useCreateExpenseClaim() {
  return useCall<
    { name: string; total_claimed_amount: number; currency: string | null },
    {
      capture: string
      claim: { doctype: 'Expense Claim'; expense_approver?: string; remark?: string; expenses: ExpenseLinePayload[] }
    }
  >({
    url: `${METHOD}/${EXPENSES}.create`,
    method: 'POST',
    immediate: false,
  })
}

/** The desk address of a document, for "open in desk" links. */
export { deskFormUrl as deskUrl } from './desk'

/* -------------------------------------------------------------------------- */
/* The reader's drafts                                                         */
/* -------------------------------------------------------------------------- */

export interface DraftRow {
  name: string
  supplier: string
  supplier_name: string | null
  bill_no: string | null
  posting_date: string
  grand_total: number
  currency: string
  company: string
}

/**
 * The reader's own unsubmitted purchase invoices, newest first.
 *
 * All of them, not only the ones made here: a draft typed in the desk is
 * waiting to be submitted just the same, and this is the list somebody working
 * through a pile of invoices comes back to.
 */
export function useMyDrafts() {
  const call = useCall<DraftRow[], { fields: string; filters: string; order_by: string; limit: number }>({
    url: `/api/v2/document/${encodeURIComponent(PURCHASE_INVOICE)}`,
    immediate: false,
  })
  async function load() {
    await call.submit({
      fields: JSON.stringify([
        'name',
        'supplier',
        'supplier_name',
        'bill_no',
        'posting_date',
        'grand_total',
        'currency',
        'company',
      ]),
      filters: JSON.stringify([
        ['owner', '=', user.value.name],
        ['docstatus', '=', 0],
      ]),
      order_by: 'creation desc',
      limit: 50,
    })
  }
  return {
    load,
    rows: computed(() => call.data ?? []),
    loaded: computed(() => call.isFinished),
    loading: computed(() => call.loading),
    error: computed(() => call.error ?? null),
  }
}
