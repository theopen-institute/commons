import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import {
  buttonTheme,
  styleTheme,
  themeIcon,
  type BadgeTheme,
  type ButtonTheme,
} from './workflowStyle'

export interface MyEmployee {
  name: string
  employee_name: string
  department: string | null
  company: string
  leave_approver: string | null
  leave_approver_name?: string
  /** Borrowed by procurement as the default approver — see `get_procurement_approvers`. */
  expense_approver: string | null
  image: string | null
}

/**
 * One outcome an approver may be offered.
 *
 * All three fields are the server's. `style` is the site's -- a Workflow State's
 * where a workflow is running, and the app's default otherwise -- and `confirm`
 * says whether this outcome deserves a second look before it is written. That
 * used to be inferred here from the button's own colour, which meant a site that
 * added an outcome silently got whatever the inference happened to decide.
 */
export interface LeaveDecision {
  value: string
  style: string | null
  confirm: boolean
}

export interface LeavePermissions {
  read: boolean
  request: boolean
  approve: boolean
  pending_approvals: number
  /** The outcomes the server will accept, in the order they should be offered. */
  decisions: LeaveDecision[]
  /** How many rows a queue returns. The badge counts to the same ceiling. */
  page_length: number
  /** Whether HR Settings makes the approver mandatory. The form asks rather
   *  than assuming: a site that made it optional is one where a blank field
   *  must be allowed through. */
  approver_mandatory: boolean
  /** The link query that resolves candidate approvers, named by the server so a
   *  site can point it somewhere else. */
  approver_query: string
}

/** One row of a leave application list. */
export interface LeaveApplicationRow {
  name: string
  employee: string
  employee_name: string
  leave_type: string
  from_date: string
  to_date: string
  total_leave_days: number
  half_day: 0 | 1
  description: string | null
  status: string
  docstatus: 0 | 1 | 2
  leave_approver: string | null
  leave_approver_name: string | null
  posting_date: string
  /** How this row reads, in the server's words and the site's styling. Settled
   *  there because `status` alone is not the answer -- an unsubmitted
   *  application is pending whatever its status field says. */
  status_label: string
  status_style: string | null
  /** Whether *this* user may decide *this* application. Only the approvals
   *  queue fills it in; the server settles it again before writing anything. */
  can_decide?: boolean
  /** The outcomes this user may apply to *this* row, named as the server names
   *  them. Transitions from the active Workflow where a site runs one. */
  actions?: string[]
}

const myEmployeeCall = useCall<MyEmployee | null>({
  url: '/api/v2/method/tbs_commons.leave.api.get_my_employee',
})

/** The Employee record behind the session user — `null` when none is linked. */
export const myEmployee = computed(() => myEmployeeCall.data ?? null)
export const myEmployeeLoaded = computed(() => myEmployeeCall.isFinished)

const leavePermissionsCall = useCall<LeavePermissions>({
  url: '/api/v2/method/tbs_commons.leave.api.get_leave_permissions',
})

const NO_LEAVE_PERMISSIONS: LeavePermissions = {
  read: false,
  request: false,
  approve: false,
  pending_approvals: 0,
  decisions: [],
  page_length: 0,
  approver_mandatory: true,
  approver_query: '',
}

export const leaveCan = computed(
  () => leavePermissionsCall.data ?? NO_LEAVE_PERMISSIONS,
)

/**
 * Whether the answer is in — settled or refused, not merely arrived.
 *
 * Deliberately not `data != null`: a call that fails never sets `data`, and a
 * page gating its skeleton on that sits in the skeleton for ever with nothing
 * to show for it. `leavePermissionsError` is what it should say instead.
 */
export const leavePermissionsLoaded = computed(
  () => leavePermissionsCall.isFinished,
)

export const leavePermissionsError = computed(
  () => leavePermissionsCall.error ?? null,
)

export function reloadLeavePermissions() {
  return leavePermissionsCall.reload()
}

/**
 * The session user's own leave applications, newest first.
 *
 * No employee argument: the server resolves the Employee behind the session
 * itself, so there is no window in which this page could ask for somebody
 * else's — or, before the employee had loaded, for everybody's.
 */
export function useMyLeaveApplications() {
  return useCall<LeaveApplicationRow[]>({
    url: '/api/v2/method/tbs_commons.leave.api.get_my_leave_applications',
  })
}

/**
 * Applications this user has to decide, or ones already decided.
 *
 * What counts as either is the server's to say — see `get_leave_approval_queue`.
 * Building the filters here instead let "waiting on you" mean one thing on this
 * page and a slightly different thing in the badge counting it.
 */
export function useLeaveApprovalQueue(decided: MaybeRefOrGetter<boolean>) {
  const queue = useCall<LeaveApplicationRow[], { decided: number }>({
    url: '/api/v2/method/tbs_commons.leave.api.get_leave_approval_queue',
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

export interface LeaveAllocationSummary {
  total_leaves: number
  expired_leaves: number
  leaves_taken: number
  leaves_pending_approval: number
  remaining_leaves: number
}

export interface LeaveDetails {
  leave_allocation: Record<string, LeaveAllocationSummary>
  leave_approver: string | null
  lwps: string[]
}

/**
 * Balances per leave type, from HRMS's own calculation — it accounts for
 * carry-forward, expiry and pending applications, none of which is derivable
 * from the allocation total alone.
 */
export function useLeaveDetails(
  employee: MaybeRefOrGetter<string | undefined>,
) {
  return useCall<LeaveDetails, { employee: string; date: string }>({
    url: '/api/v2/method/hrms.hr.doctype.leave_application.leave_application.get_leave_details',
    params: () => ({
      employee: toValue(employee) ?? '',
      date: new Date().toISOString().slice(0, 10),
    }),
    immediate: false,
  })
}

/** Working days a range costs, per HRMS: holidays and half days included. */
export function useLeaveDayCount() {
  return useCall<
    number,
    {
      employee: string
      leave_type: string
      from_date: string
      to_date: string
      half_day: 0 | 1
      half_day_date?: string
    }
  >({
    url: '/api/v2/method/hrms.hr.doctype.leave_application.leave_application.get_number_of_leave_days',
    immediate: false,
  })
}

/**
 * Settle an application, by whatever route the site has configured — a Workflow
 * transition where one is running, a status change and a submit where none is.
 * One call either way, because the two halves are one action for the approver.
 */
export function useLeaveDecision() {
  return useCall<
    { name: string; status: string; docstatus: number },
    { name: string; decision: string }
  >({
    url: '/api/v2/method/tbs_commons.leave.api.decide_leave_application',
    method: 'POST',
    immediate: false,
  })
}

/**
 * Raise a leave application for the employee behind this session.
 *
 * Through a whitelisted method rather than the document API: which fields a
 * request may set, and which employee it is for, are the server's to decide —
 * see `request_leave`. A form that posts a document decides both for itself.
 */
export function useRequestLeave() {
  return useCall<{ name: string }, { doc: string }>({
    url: '/api/v2/method/tbs_commons.leave.api.request_leave',
    method: 'POST',
    immediate: false,
  })
}

export interface LeaveWorkflowState {
  state: string
  doc_status: number
  style: string | null
}

export interface LeaveWorkflow {
  name: string
  workflow_state_field: string
  states: LeaveWorkflowState[]
  transitions: { state: string; action: string; next_state: string }[]
}

const workflowCall = useCall<LeaveWorkflow | null>({
  url: '/api/v2/method/tbs_commons.leave.api.get_leave_workflow',
})

/** The active Workflow, if the site runs one. The pages need no knowledge of it
 *  — every row already carries its own label, style and permitted actions — but
 *  reloading it keeps those answers fresh after a transition. */
export const leaveWorkflow = computed(() => workflowCall.data ?? null)

export function reloadLeaveWorkflow() {
  return workflowCall.reload()
}

export interface LeaveStatusDisplay {
  label: string
  theme: BadgeTheme
}

/**
 * How a leave application reads to a person.
 *
 * Both halves arrive: the server settles the label, because `status` alone is
 * not the answer, and the style, because a site running a Workflow styles its
 * own states. All that is left here is the mapping from that style to a badge.
 */
export function leaveStatus(row: {
  status_label: string
  status_style: string | null
}): LeaveStatusDisplay {
  return { label: row.status_label, theme: styleTheme(row.status_style) }
}

/** Wording, and only wording. An outcome this does not know keeps the server's
 *  name for it, which is what a site that added one would want it called. */
const DECISION_LABELS: Record<string, string> = {
  Approved: 'Approve',
  Rejected: 'Deny',
}

export interface DecisionButton {
  decision: string
  label: string
  theme: ButtonTheme
  variant: 'solid' | 'subtle'
  icon: string
  /** Whether to ask again before writing it. The server's answer, not a guess
   *  read off the variant below. */
  confirm: boolean
}

/**
 * How a decision button reads.
 *
 * Which outcomes exist, how each is styled and which of them needs confirming
 * are all the server's. The wording is this file's, and the one solid button is
 * frappe-ui's convention: the affirmative outcome -- the one the server did not
 * ask to have confirmed -- is the call to action, and everything else stays
 * subtle so the row reads as one choice rather than a wall of filled buttons.
 */
export function decisionButton(decision: LeaveDecision): DecisionButton {
  const theme = buttonTheme(decision.style)
  return {
    decision: decision.value,
    label: DECISION_LABELS[decision.value] ?? decision.value,
    theme,
    variant: decision.confirm ? 'subtle' : 'solid',
    icon: themeIcon(theme),
    confirm: decision.confirm,
  }
}

/**
 * The buttons for one row: the outcomes the server said this row accepts, in
 * the order the vocabulary offers them, and at most one of them solid.
 */
export function decisionButtons(
  offered: string[] | undefined,
  vocabulary: LeaveDecision[],
): DecisionButton[] {
  let solidTaken = false
  return vocabulary
    .filter((decision) => offered?.includes(decision.value))
    .map((decision) => {
      const button = decisionButton(decision)
      if (button.variant !== 'solid') return button
      if (solidTaken) return { ...button, variant: 'subtle' as const }
      solidTaken = true
      return button
    })
}
