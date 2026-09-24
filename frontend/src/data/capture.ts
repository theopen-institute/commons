import { computed } from 'vue'
import { upload, useCall } from 'frappe-ui'
import { user } from './session'
import type { InvoicePayload, Reading, Totals } from './captureRules'

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
 * The scan goes to `read_invoice` through the same upload helper, pointed at
 * that endpoint instead of Frappe's. It is a multipart request, so the file is
 * sent as it is rather than base64-encoded in JSON. The helper also refuses a
 * file over the site's upload limit before sending it, and turns a server
 * refusal into a message.
 */

const METHOD = '/api/v2/method'
const CLIENT = `${METHOD}/frappe.client`
const CAPTURE = 'commons.document_capture.purchase_invoice'

export const PURCHASE_INVOICE = 'Purchase Invoice'

/* -------------------------------------------------------------------------- */
/* Who the page is for                                                         */
/* -------------------------------------------------------------------------- */

function permissionCall(doctype: string, perm: string) {
  return useCall<{ has_permission: boolean }, { doctype: string; docname: string; perm_type: string }>({
    url: `${CLIENT}.has_permission`,
    params: { doctype, docname: '', perm_type: perm },
  })
}

/** Create on `Purchase Invoice`, the server's own test. See `can_capture`. */
const canCaptureCall = permissionCall(PURCHASE_INVOICE, 'create')

/** Whether the dialog offers to make a supplier the site does not have yet. */
const canCreateSupplierCall = permissionCall('Supplier', 'create')

export const captureCan = computed(() => ({
  capture: Boolean(canCaptureCall.data?.has_permission),
  createSupplier: Boolean(canCreateSupplierCall.data?.has_permission),
}))

/** What the sidebar row waits on. Whether the site has ERPNext and a Claude
 *  key is the shell's answer already (`commons.shell.pages.available`). */
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

/**
 * Send a scan to be read.
 *
 * `/api/method` rather than `/api/v2/method`: the upload helper unwraps a
 * `message`, which is where v1 puts the answer.
 */
export async function readInvoice(file: File): Promise<Reading> {
  const answer = await upload(file, {
    upload_endpoint: `/api/method/${CAPTURE}.read_invoice`,
    private: true,
  })
  return answer as unknown as Reading
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
