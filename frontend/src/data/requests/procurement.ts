import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import {
  buttonTheme,
  styleTheme,
  type BadgeTheme,
  type ButtonTheme,
} from '../workflowStyle'

export interface ProcurementPermissions {
  read: boolean
  request: boolean
  /** The active Workflow, if the site runs one. Carried here rather than
   *  fetched on its own: every page that reads it reads these permissions too,
   *  and the two were always reloaded together after acting on a request. */
  workflow: ProcurementWorkflow | null
  workflow_access: boolean
  pending_workflow_actions: number
  /** The link query that resolves candidate approvers, named by the server so a
   *  site can point it somewhere else. */
  approver_query: string
  /** How many rows a queue returns. The badge counts to the same ceiling. */
  page_length: number
}

/**
 * A line of the budget readout that is worth saying in words.
 *
 * Written by the server beside the gate that makes it true — see
 * `budget.summary_notices`. `severity` is a cue for how loudly to say it, not a
 * decision of the page's own.
 */
export interface BudgetNotice {
  severity: 'warning' | 'info'
  message: string
}

/** One row of a procurement request list. */
export interface DepartmentBudgetSummary {
  inactive?: boolean
  missing: boolean
  /** What the figures mean, in the server's words. */
  notices?: BudgetNotice[]
  department: string
  name?: string
  fiscal_year?: string
  currency?: string
  annual?: number
  spent?: number
  committed?: number
  remaining?: number
  open_requests?: number
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
  /** Summed from the item rows by the server on every read — no stored column
   *  backs it, so a list query cannot filter or sort on it. */
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
  description: string | null
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
  url: '/api/v2/method/tbs_commons.requests.procurement.get_procurement_permissions',
})

const NO_PERMISSIONS: ProcurementPermissions = {
  read: false,
  request: false,
  workflow: null,
  workflow_access: false,
  pending_workflow_actions: 0,
  approver_query: '',
  page_length: 0,
}

/**
 * What a blank request opens with.
 *
 * Its own call, made when the form opens, rather than part of the permissions
 * every page load fetches: these are four queries for a form most visits to the
 * section never draw. Every value may be null — a default nobody configured is
 * omitted rather than guessed, and Frappe applies the user's own or says it
 * cannot decide.
 */
export interface ProcurementRequestDefaults {
  company: string | null
  currency: string | null
  department: string | null
  approver: string | null
  uom: string | null
}

export function useProcurementRequestDefaults() {
  return useCall<ProcurementRequestDefaults>({
    url: '/api/v2/method/tbs_commons.requests.procurement.get_procurement_request_defaults',
    immediate: false,
  })
}

export const procurementCan = computed(
  () => permissionsCall.data ?? NO_PERMISSIONS,
)

/**
 * Whether the answer is in — settled or refused, not merely arrived.
 *
 * Deliberately not `data != null`: a call that fails never sets `data`, and a
 * page gating its skeleton on that sits in the skeleton for ever with nothing
 * to show for it. `procurementPermissionsError` is what it should say instead.
 */
export const procurementPermissionsLoaded = computed(
  () => permissionsCall.isFinished,
)

export const procurementPermissionsError = computed(
  () => permissionsCall.error ?? null,
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

/**
 * The active Workflow, if the site runs one.
 *
 * Read off the permissions payload rather than fetched separately. It is one
 * configuration, every page needed both halves of it, and a second call meant a
 * second thing to remember to reload — `reloadProcurementPermissions` now
 * refreshes this too.
 */
export const procurementWorkflow = computed(
  () => permissionsCall.data?.workflow ?? null,
)

/** Own requests, with amendments displayed in their cancelled ancestor's place. */
export function useMyProcurementRequests() {
  return useCall<ProcurementRequestRow[]>({
    url: '/api/v2/method/tbs_commons.requests.procurement.get_my_procurement_requests',
  })
}

/**
 * One department's share of an approval queue: the allocation being spent and
 * every request in front of the approver charged to it.
 *
 * Built by the server — see `group_by_department`. `estimate` is money weighed
 * against the allocation printed beside it, and two figures read together
 * should not be arrived at in two places by two rules.
 */
export interface DepartmentRequestGroup {
  key: string
  department: string | null
  summary: DepartmentBudgetSummary | null
  /** Request names, in queue order. The rows themselves are in `requests`. */
  requests: string[]
  /** What the group's requests would cost together. Null unless they share one
   *  currency — there is no honest single figure to print otherwise. */
  estimate: number | null
  currency: string | null
}

export interface ProcurementQueue {
  requests: ProcurementRequestRow[]
  actions: Record<string, AvailableWorkflowAction[]>
  groups: DepartmentRequestGroup[]
}

export function useProcurementWorkflowQueue(
  decided: MaybeRefOrGetter<boolean>,
) {
  const queue = useCall<ProcurementQueue, { decided: number }>({
    url: '/api/v2/method/tbs_commons.requests.procurement.get_procurement_workflow_queue',
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
    url: '/api/v2/method/tbs_commons.requests.procurement.get_procurement_request_transitions',
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
    url: '/api/v2/method/tbs_commons.requests.procurement.get_procurement_request_lines',
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
    url: '/api/v2/method/tbs_commons.requests.procurement.save_procurement_request',
    method: 'POST',
    immediate: false,
  })
}

export interface ProcurementStatusDisplay {
  label: string
  theme: BadgeTheme
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
    theme: styleTheme(style),
  }
}

export function workflowActionTheme(
  action: AvailableWorkflowAction,
  workflow: ProcurementWorkflow | null,
): ButtonTheme {
  return buttonTheme(
    workflow?.states.find((state) => state.state === action.next_state)?.style,
  )
}

export interface WorkflowActionButton {
  action: AvailableWorkflowAction
  label: string
  theme: ButtonTheme
  variant: 'solid' | 'subtle'
}

/**
 * How a row of workflow actions is drawn.
 *
 * Frappe UI gives a group exactly one solid button: the affirmative next step.
 * Turning a request down, cancelling it, and any transition the workflow left
 * unstyled all stay subtle, so the row reads as one call to action instead of
 * a wall of filled buttons competing with each other.
 */
export function workflowActionButtons(
  actions: AvailableWorkflowAction[],
  workflow: ProcurementWorkflow | null,
): WorkflowActionButton[] {
  let solidTaken = false
  return actions.map((action) => {
    const theme = workflowActionTheme(action, workflow)
    const solid = !solidTaken && (theme === 'green' || theme === 'blue')
    if (solid) solidTaken = true
    return {
      action,
      label: action.action,
      theme,
      variant: solid ? 'solid' : 'subtle',
    }
  })
}

/** What a row is called when nobody typed a title. */
export function requestLabel(row: ProcurementRequestRow): string {
  return row.title || row.name
}
