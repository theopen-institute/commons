import { computed } from 'vue'
import { upload, useCall } from 'frappe-ui'
import { user } from './session'
import { pollReading, readingDeadlineMs, type JobState } from './backgroundReading'
import type { InvoicePayload, Reading, Totals } from './captureRules'
import { permissionCall } from './permissions'

/**
 * The document capture page's reads and writes.
 *
 * Every call is to `commons.document_capture.purchase_invoice`, whose module
 * docstring gives the order (read, suggest, preview, create), except two
 * things Frappe already does:
 *
 * * attaching the scan to the new invoice, which is Frappe's own upload and
 *   checks write permission on that invoice, exactly as expense claim
 *   receipts do (see `attachToExpenseClaim`);
 * * listing the reader's drafts, which is the document API.
 *
 * The scan goes to `start_reading` through the same upload helper, pointed at
 * that endpoint instead of Frappe's. It is a multipart request, so the file is
 * sent as it is rather than base64-encoded in JSON. The helper also refuses a
 * file over the site's upload limit before sending it, and turns a server
 * refusal into a message. The reading itself happens in a background job,
 * which `readInvoice` asks after until it answers.
 */

const METHOD = '/api/v2/method'
const CAPTURE = 'commons.document_capture.purchase_invoice'

export const PURCHASE_INVOICE = 'Purchase Invoice'

/* -------------------------------------------------------------------------- */
/* Who the page is for                                                         */
/* -------------------------------------------------------------------------- */

/** Create on `Purchase Invoice`, the server's own test. See `can_capture`. */
const canCaptureCall = permissionCall(PURCHASE_INVOICE, 'create')

/** Whether the dialog offers to make a supplier the site does not have yet. */
const canCreateSupplierCall = permissionCall('Supplier', 'create')

export const captureCan = computed(() => ({
  capture: Boolean(canCaptureCall.data?.has_permission),
  createSupplier: Boolean(canCreateSupplierCall.data?.has_permission),
}))

/** What the capture page waits on before it offers the upload. The sidebar
 *  row does not: it takes the same answer from the shell (`serverGate` in
 *  `data/shell.ts`), along with whether the site has ERPNext and a Claude key. */
export const captureGate = {
  visible: computed(() => captureCan.value.capture),
  resolved: computed(() => canCaptureCall.isFinished),
}

/* -------------------------------------------------------------------------- */
/* The scan                                                                    */
/* -------------------------------------------------------------------------- */

/** What the file picker offers. The server decides by the file's contents,
 *  not by this. */
export const ACCEPTED_SCANS = 'image/jpeg,image/png,image/webp,image/gif,application/pdf'

/** Where a reading has got to, as `reading_status` answers: what the job is
 *  doing (`reading` the scan, then `matching` it to this site's companies and
 *  suppliers) and how many lines Claude has copied so far. */
export interface InvoiceReadingState extends JobState<Reading> {
  step: 'reading' | 'matching' | null
  lines: number
}

/** The server's `JOB_TIMEOUT` for reading a scan, in seconds. */
const JOB_TIMEOUT_S = 420

/** How long `readInvoice` waits before giving up. See `readingDeadlineMs`. */
export const INVOICE_READING_DEADLINE_MS = readingDeadlineMs(JOB_TIMEOUT_S)

const readingStatusCall = useCall<InvoiceReadingState, { token: string }>({
  url: `${METHOD}/${CAPTURE}.reading_status`,
  immediate: false,
})

async function readingStatus(token: string): Promise<InvoiceReadingState> {
  const state = await readingStatusCall.submit({ token })
  if (state === null) throw readingStatusCall.error ?? new Error('Could not ask after the reading.')
  return state
}

/**
 * Send a scan to be read, and wait for the reading.
 *
 * `/api/method` rather than `/api/v2/method` for the upload: the helper
 * unwraps a `message`, which is where v1 puts the answer, here a token.
 * `onProgress` is told each answer while the job runs; `cancelled` ends the
 * wait early, and the promise then rejects with `ReadingCancelled`.
 */
export async function readInvoice(
  file: File,
  options: { onProgress?: (state: InvoiceReadingState) => void; cancelled?: () => boolean } = {},
): Promise<Reading> {
  const started = (await upload(file, {
    upload_endpoint: `/api/method/${CAPTURE}.start_reading`,
    private: true,
  })) as unknown as { token: string }
  const result = await pollReading<Reading, InvoiceReadingState>({
    check: () => readingStatus(started.token),
    deadlineMs: INVOICE_READING_DEADLINE_MS,
    deadlineMessage: 'The scan is taking far longer than it should to read. Try again in a few minutes.',
    failedMessage: 'That scan could not be read.',
    onProgress: options.onProgress,
    cancelled: options.cancelled,
  })
  if (result === null) throw new ReadingCancelled()
  return result
}

/** Thrown by `readInvoice` when its caller stopped waiting. Nothing to show. */
export class ReadingCancelled extends Error {
  constructor() {
    super('The reading was cancelled.')
    this.name = 'ReadingCancelled'
  }
}

/** The progress line for a reading, from the latest answer. Null before the
 *  first answer. */
export function readingProgressText(state: InvoiceReadingState | null): string | null {
  if (!state) return null
  if (state.status === 'queued') return 'Waiting for the background worker to start the reading'
  if (state.step === 'matching') return "Matching the supplier and company to this site's records"
  if (state.lines) return `Claude has copied ${state.lines} ${state.lines === 1 ? 'line' : 'lines'} so far`
  return 'Claude is reading the scan'
}

/**
 * Attach the scan to the invoice it became.
 *
 * Only after the insert, because an attachment needs a document to hang on.
 * A failure here is reported, not thrown: the invoice already exists, and
 * saying the save failed would lead to a second one.
 */
export async function attachScan(invoice: string, file: File): Promise<string | null> {
  try {
    await upload(file, {
      doctype: PURCHASE_INVOICE,
      docname: invoice,
      private: true,
      folder: 'Home/Attachments',
    })
    return null
  } catch (error) {
    return error instanceof Error ? error.message : 'Upload failed'
  }
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
    url: `${METHOD}/${CAPTURE}.suggest`,
    method: 'POST',
    immediate: false,
  })
}

export function usePreview() {
  return useCall<Totals, { invoice: InvoicePayload; new_supplier: boolean }>({
    url: `${METHOD}/${CAPTURE}.preview`,
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
    { invoice: InvoicePayload; new_supplier: { supplier_name: string; tax_id: string } | null }
  >({
    url: `${METHOD}/${CAPTURE}.create`,
    method: 'POST',
    immediate: false,
  })
}

/** The desk address of a document, for "open in desk" links. */
export function deskUrl(doctype: string, name: string): string {
  return `/app/${doctype.toLowerCase().replace(/ /g, '-')}/${encodeURIComponent(name)}`
}

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
