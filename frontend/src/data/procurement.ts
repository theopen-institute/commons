import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall, useList } from 'frappe-ui'
import type { Filters } from 'frappe-ui'

export interface ProcurementPermissions {
  read: boolean
  request: boolean
  approve: boolean
  pending_approvals: number
  /** What a new request is raised against. Null when the site has several
   *  companies and this user has no default — the form then leaves it to
   *  Frappe, which says so if it cannot decide either. */
  default_company: string | null
  default_currency: string | null
  default_uom: string
}

export type ProcurementStatus =
  | 'Draft'
  | 'Pending Approval'
  | 'Approved'
  | 'Rejected'
  | 'Partially Ordered'
  | 'Ordered'
  | 'Cancelled'

/** One row of a procurement request list. */
export interface ProcurementRequestRow {
  name: string
  title: string | null
  purpose: string
  company: string
  currency: string | null
  transaction_date: string
  schedule_date: string | null
  requested_by: string | null
  department: string | null
  approver: string | null
  approver_name: string | null
  justification: string | null
  rejection_reason: string | null
  total_qty: number
  total_estimated_cost: number
  status: ProcurementStatus
  docstatus: 0 | 1 | 2
  modified: string
}

/** One line of a request. `item_code` is deliberately optional. */
export interface ProcurementRequestItemRow {
  name: string
  /** The request this line belongs to. */
  parent: string
  idx: number
  item_code: string | null
  item_name: string | null
  /** Where the requester saw it. Normalised to carry a scheme on save. */
  reference_url: string | null
  item_group: string | null
  description: string | null
  preferred_supplier: string | null
  qty: number
  uom: string
  schedule_date: string | null
  /** How much of this line submitted Material Requests already carry. Counted
   *  live by the server — no stored field backs it. */
  ordered_qty: number
  /** What is still to be ordered: `qty` less `ordered_qty`, never negative. */
  pending_qty: number
  estimated_rate: number
  estimated_amount: number
}

const LIST_FIELDS = [
  'name',
  'title',
  'purpose',
  'company',
  'currency',
  'transaction_date',
  'schedule_date',
  'requested_by',
  'department',
  'approver',
  'approver_name',
  'justification',
  'rejection_reason',
  'total_qty',
  'total_estimated_cost',
  // No `per_ordered`: how much of a request has been ordered is counted from
  // its Material Requests on every read, not stored, so a list query cannot
  // ask for it. The line rows below carry the same count per item.
  'status',
  'docstatus',
  'modified',
] as const

const permissionsCall = useCall<ProcurementPermissions>({
  url: '/api/v2/method/tbsapp.api.get_procurement_permissions',
})

const NO_PERMISSIONS: ProcurementPermissions = {
  read: false,
  request: false,
  approve: false,
  pending_approvals: 0,
  default_company: null,
  default_currency: null,
  default_uom: '',
}

export const procurementCan = computed(
  () => permissionsCall.data ?? NO_PERMISSIONS,
)

export const procurementPermissionsLoaded = computed(
  () => permissionsCall.data != null,
)

export function reloadProcurementPermissions() {
  return permissionsCall.reload()
}

/** The session user's own requests, newest first. */
export function useMyProcurementRequests(
  user: MaybeRefOrGetter<string | undefined>,
) {
  return useList<ProcurementRequestRow>({
    doctype: 'Procurement Request',
    fields: [...LIST_FIELDS],
    filters: () => {
      const name = toValue(user)
      // An impossible filter rather than none: without it an approver would
      // see everyone's requests on their own page.
      return { requested_by: name || '__none__' } as Filters
    },
    orderBy: 'creation desc',
    limit: 20,
  })
}

/**
 * Requests waiting on this user's decision, or already decided by them.
 *
 * Pending means sent but not submitted: a decision is a status change *and* a
 * submit, so docstatus 0 with `Pending Approval` is the only undecided state.
 * A draft the requester has not sent yet deliberately does not appear.
 */
export function useProcurementApprovals(options: {
  decided: MaybeRefOrGetter<boolean>
  approver: MaybeRefOrGetter<string>
}) {
  return useList<ProcurementRequestRow>({
    doctype: 'Procurement Request',
    fields: [...LIST_FIELDS],
    filters: () => {
      const filters: Filters = { approver: toValue(options.approver) }
      if (toValue(options.decided)) {
        filters.docstatus = 1
      } else {
        filters.docstatus = 0
        filters.status = 'Pending Approval'
      }
      return filters
    },
    orderBy: () =>
      toValue(options.decided) ? 'modified desc' : 'transaction_date asc',
    limit: 20,
  })
}

/**
 * The lines of several requests at once, grouped by request.
 *
 * One call for the whole page rather than one per card. It goes through a
 * whitelisted method rather than the list API because a child table read over
 * REST is permission-checked against the child doctype, which has no
 * permissions of its own — see `get_procurement_request_lines`.
 */
export function useProcurementRequestLines(
  parents: MaybeRefOrGetter<string[]>,
) {
  const lines = useCall<ProcurementRequestItemRow[], { requests: string }>({
    url: '/api/v2/method/tbsapp.api.get_procurement_request_lines',
    params: () => ({ requests: JSON.stringify(toValue(parents)) }),
    immediate: false,
  })

  // The requests arrive a beat after the page, so this waits for them rather
  // than firing with an empty list. This is the only thing that refetches the
  // lines — a caller reloading them as well would abort whichever call lost
  // the race, which surfaces as a console error on an otherwise fine page.
  watch(
    () => toValue(parents).join(','),
    (names) => {
      if (names) lines.reload()
    },
    { immediate: true },
  )

  const byRequest = computed(() => {
    const grouped = new Map<string, ProcurementRequestItemRow[]>()
    for (const line of lines.data ?? []) {
      const group = grouped.get(line.parent)
      if (group) group.push(line)
      else grouped.set(line.parent, [line])
    }
    return grouped
  })

  return { lines, byRequest }
}

/** Hand a draft to its approver. */
export function useSendProcurementRequest() {
  return useCall<
    { name: string; status: string; docstatus: number },
    { name: string }
  >({
    url: '/api/v2/method/tbsapp.api.send_procurement_request',
    method: 'POST',
    immediate: false,
  })
}

/** Approve or reject a request, and submit it, in one call. */
export function useProcurementDecision() {
  return useCall<
    { name: string; status: string; docstatus: number },
    { name: string; decision: 'Approved' | 'Rejected'; reason?: string }
  >({
    url: '/api/v2/method/tbsapp.api.decide_procurement_request',
    method: 'POST',
    immediate: false,
  })
}

export interface ProcurementStatusDisplay {
  label: string
  theme: 'gray' | 'blue' | 'green' | 'amber' | 'red'
}

/**
 * How a request reads to a person.
 *
 * `status` carries it alone here, unlike leave: the field is permlevel 1, so
 * only an approver can have written the decided values, and the ordering
 * states are derived server-side from what has actually been ordered.
 */
export function procurementStatus(row: {
  status: string
  docstatus: number
}): ProcurementStatusDisplay {
  switch (row.status) {
    case 'Draft':
      return { label: 'Draft', theme: 'gray' }
    case 'Pending Approval':
      return { label: 'Pending', theme: 'amber' }
    case 'Approved':
      return { label: 'Approved', theme: 'green' }
    case 'Rejected':
      return { label: 'Rejected', theme: 'red' }
    case 'Partially Ordered':
      return { label: 'Partly ordered', theme: 'blue' }
    case 'Ordered':
      return { label: 'Ordered', theme: 'blue' }
    case 'Cancelled':
      return { label: 'Cancelled', theme: 'gray' }
    default:
      return { label: row.status, theme: 'gray' }
  }
}

/** What a row is called when nobody typed a title. */
export function requestLabel(row: ProcurementRequestRow): string {
  return row.title || row.name
}
