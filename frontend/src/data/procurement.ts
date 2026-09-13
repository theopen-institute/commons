import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'

export interface ProcurementPermissions {
  read: boolean
  request: boolean
  workflow_access: boolean
  pending_workflow_actions: number
  /** What a new request is raised against. Null when the site has several
   *  companies and this user has no default — the form then leaves it to
   *  Frappe, which says so if it cannot decide either. */
  default_company: string | null
  default_currency: string | null
  default_department: string | null
  default_approver: string | null
  default_uom: string
}

/** One row of a procurement request list. */
export interface DepartmentBudgetSummary {
  inactive?: boolean
  missing: boolean
  department: string
  name?: string
  fiscal_year?: string
  currency?: string
  budget?: number
  used?: number
  provisional?: number
  available?: number
  request_amount?: number
  projected_available?: number
}

export interface ProcurementRequestRow {
  budget_summary?: DepartmentBudgetSummary | null
  name: string
  title: string | null
  company: string
  currency: string | null
  transaction_date: string
  schedule_date: string | null
  requested_by: string | null
  requester_name: string | null
  department: string | null
  approver: string | null
  approver_name: string | null
  justification: string | null
  rejection_reason: string | null
  total_qty: number
  total_estimated_cost: number
  can_edit: boolean
  status: string
  workflow_state: string
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
  /** How much Resources has committed through submitted Material Requests. Counted
   *  live by the server — no stored field backs it. */
  committed_qty: number
  /** What is still to be committed: `qty` less `committed_qty`, never negative. */
  uncommitted_qty: number
  estimated_rate: number
  verified_rate: number
  estimated_cost: number
}

const permissionsCall = useCall<ProcurementPermissions>({
  url: '/api/v2/method/tbs_commons.api.get_procurement_permissions',
})

const NO_PERMISSIONS: ProcurementPermissions = {
  read: false,
  request: false,
  workflow_access: false,
  pending_workflow_actions: 0,
  default_company: null,
  default_currency: null,
  default_department: null,
  default_approver: null,
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

export interface ProcurementWorkflowState {
  state: string
  doc_status: number
  style: string | null
}

export interface ProcurementWorkflowTransition {
  state: string
  action: string
  next_state: string
}

export interface ProcurementWorkflow {
  name: string
  workflow_state_field: string
  initial_actions: AvailableWorkflowAction[]
  states: ProcurementWorkflowState[]
  transitions: ProcurementWorkflowTransition[]
}

export interface AvailableWorkflowAction {
  action: string
  next_state: string
}

const workflowCall = useCall<ProcurementWorkflow | null>({
  url: '/api/v2/method/tbs_commons.api.get_procurement_workflow',
})

export const procurementWorkflow = computed(() => workflowCall.data ?? null)

export function reloadProcurementWorkflow() {
  return workflowCall.reload()
}

/** Own requests, with amendments displayed in their cancelled ancestor's place. */
export function useMyProcurementRequests() {
  return useCall<ProcurementRequestRow[]>({
    url: '/api/v2/method/tbs_commons.api.get_my_procurement_requests',
  })
}

export function useProcurementWorkflowQueue(
  decided: MaybeRefOrGetter<boolean>,
) {
  const queue = useCall<
    {
      requests: ProcurementRequestRow[]
      actions: Record<string, AvailableWorkflowAction[]>
    },
    { decided: number }
  >({
    url: '/api/v2/method/tbs_commons.api.get_procurement_workflow_queue',
    params: () => ({ decided: toValue(decided) ? 1 : 0 }),
    immediate: false,
  })
  watch(
    () => toValue(decided),
    () => queue.reload(),
    { immediate: true },
  )
  return queue
}

export function useProcurementRequestTransitions(
  parents: MaybeRefOrGetter<string[]>,
) {
  const transitions = useCall<
    Record<string, AvailableWorkflowAction[]>,
    { requests: string }
  >({
    url: '/api/v2/method/tbs_commons.api.get_procurement_request_transitions',
    params: () => ({ requests: JSON.stringify(toValue(parents)) }),
    immediate: false,
  })
  watch(
    () => toValue(parents),
    (names) => {
      if (names.length) transitions.reload()
    },
    { immediate: true },
  )
  return transitions
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
    url: '/api/v2/method/tbs_commons.api.get_procurement_request_lines',
    params: () => ({ requests: JSON.stringify(toValue(parents)) }),
    immediate: false,
  })

  // Reload lines whenever the parent list refreshes, even if its names are
  // unchanged: quantities, rates and commitments may have changed.
  watch(
    () => toValue(parents),
    (names) => {
      if (names.length) lines.reload()
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

export function useApplyProcurementWorkflow() {
  return useCall<ProcurementRequestRow, { doc: string; action: string }>({
    url: '/api/v2/method/frappe.model.workflow.apply_workflow',
    method: 'POST',
    immediate: false,
  })
}

export function useSaveProcurementRequest() {
  return useCall<ProcurementRequestRow, { doc: string; action?: string }>({
    url: '/api/v2/method/tbs_commons.api.save_procurement_request',
    method: 'POST',
    immediate: false,
  })
}

export interface ProcurementStatusDisplay {
  label: string
  theme: 'gray' | 'blue' | 'green' | 'amber' | 'red'
}

const WORKFLOW_STYLE_THEMES: Record<string, ProcurementStatusDisplay['theme']> =
  {
    Primary: 'blue',
    Info: 'blue',
    Success: 'green',
    Warning: 'amber',
    Danger: 'red',
    Inverse: 'gray',
  }

/**
 * How a request reads to a person.
 *
 * The label and style both come from the active Frappe Workflow. The fallback
 * covers sites that have the doctype but have not configured a workflow.
 */
export function procurementStatus(
  row: ProcurementRequestRow,
  workflow: ProcurementWorkflow | null,
): ProcurementStatusDisplay {
  const style = workflow?.states.find(
    (state) => state.state === row.workflow_state,
  )?.style
  return {
    label: row.workflow_state || row.status,
    theme: WORKFLOW_STYLE_THEMES[style ?? ''] ?? 'gray',
  }
}

export function workflowActionTheme(
  action: AvailableWorkflowAction,
  workflow: ProcurementWorkflow | null,
): 'gray' | 'blue' | 'green' | 'red' {
  const style = workflow?.states.find(
    (state) => state.state === action.next_state,
  )?.style
  const themes = {
    Primary: 'blue',
    Info: 'blue',
    Success: 'green',
    Danger: 'red',
  } as const
  return themes[style as keyof typeof themes] ?? 'gray'
}

/** What a row is called when nobody typed a title. */
export function requestLabel(row: ProcurementRequestRow): string {
  return row.title || row.name
}
