import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import {
  decisionButton as buildDecisionButton,
  decisionButtons as buildDecisionButtons,
  styleTheme,
  type BadgeTheme,
  type Decision,
  type DecisionButton,
} from './workflowStyle'

export type { DecisionButton }

/**
 * The employee behind this login, as the leave pages use it.
 *
 * Two fields, because two is what they read: the record a request is raised
 * against, and the approver it defaults to. The old endpoint fetched seven and
 * derived an eighth, and nothing rendered any of the other six.
 */
export interface MyEmployee {
  name: string
  leave_approver: string | null
}

/** What to ask the document API for. Not a permission boundary — Frappe drops
 *  fields the caller may not read from the select on its own — so the page is
 *  free to name the two it draws. */
const EMPLOYEE_FIELDS = ['name', 'leave_approver']

/** Likewise for an application row: exactly what `MyLeave` puts on screen. */
const APPLICATION_FIELDS = [
  'name',
  'leave_type',
  'description',
  'posting_date',
  'from_date',
  'to_date',
  'total_leave_days',
  'status',
  'docstatus',
]

/**
 * One outcome an approver may be offered. The shared shape -- see `Decision` in
 * `workflowStyle`, which procurement's and profile's vocabularies use too.
 */
export type LeaveDecision = Decision

/**
 * Why there is no employee record, when `myEmployee` is null.
 *
 * `missing` sends the reader to HR and `forbidden` to whoever administers
 * permissions, which is the whole reason the server distinguishes them — one
 * message for both told a user whose access had been revoked to ask HR to
 * create a record that already names them. See `session_employee_access`.
 */
export type EmployeeAccess = 'visible' | 'forbidden' | 'missing'

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

export interface LeavePermissions {
  read: boolean
  request: boolean
  /** What makes an Employee row this session's own. The server's predicate, not
   *  this page's: `user_id` names the login and `status` rules out a leaver, and
   *  a filter written here would be the second place that rule lived. */
  employee_filters: Record<string, string>
  employee_access: EmployeeAccess
  /** The active Workflow, if the site runs one. Its states and their styling are
   *  what a row fetched through the document API is labelled from. */
  workflow: LeaveWorkflow | null
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
  /** How this row reads, in the server's words and the site's styling.
   *
   *  Present only on approvals-queue rows, which the server decorates because
   *  what a reviewer may do to a row is a permission question anyway. Rows the
   *  page fetches for itself arrive without them and are labelled by
   *  `leaveStatus`, from the same workflow states and decision styles the
   *  server would have used. */
  status_label?: string
  status_style?: string | null
  /** Whether *this* user may decide *this* application. Only the approvals
   *  queue fills it in; the server settles it again before writing anything. */
  can_decide?: boolean
  /** The outcomes this user may apply to *this* row, named as the server names
   *  them. Transitions from the active Workflow where a site runs one. */
  actions?: string[]
  /** The workflow's state column, whatever a site named it. Not knowable
   *  statically, which is why it is reached by index rather than by name. */
  [key: string]: unknown
}

const leavePermissionsCall = useCall<LeavePermissions>({
  url: '/api/v2/method/tbs_commons.leave.api.get_leave_permissions',
})

const NO_LEAVE_PERMISSIONS: LeavePermissions = {
  read: false,
  request: false,
  employee_filters: {},
  // Before the answer is in, say nothing rather than accuse anyone: `missing`
  // is the state the page renders with no explanation attached to it.
  employee_access: 'missing',
  workflow: null,
  approve: false,
  pending_approvals: 0,
  decisions: [],
  page_length: 0,
  approver_mandatory: true,
  approver_query: '',
}

export const leaveCan = computed(
  () => leavePermissionsCall.data ?? NO_LEAVE_PERMISSIONS
)

/**
 * Whether the answer is in — settled or refused, not merely arrived.
 *
 * Deliberately not `data != null`: a call that fails never sets `data`, and a
 * page gating its skeleton on that sits in the skeleton for ever with nothing
 * to show for it. `leavePermissionsError` is what it should say instead.
 */
export const leavePermissionsLoaded = computed(
  () => leavePermissionsCall.isFinished
)

export const leavePermissionsError = computed(
  () => leavePermissionsCall.error ?? null
)

export function reloadLeavePermissions() {
  return leavePermissionsCall.reload()
}

/**
 * The Employee record behind the session user, through Frappe's document API.
 *
 * Every permission the site has configured applies on the way in — role
 * permissions, User Permissions, and this app's own gate — without this module
 * restating any of them. The filter is the server's (`employee_filters`), so
 * what counts as "mine" is still settled in one place.
 *
 * Nothing is asked for unless the server has already said there is a readable
 * record. `employee_access` is that answer, and firing the read regardless
 * would spend a round trip to rediscover it.
 */
const myEmployeeCall = useCall<
  MyEmployee[],
  { filters: string; fields: string; limit: string }
>({
  url: '/api/v2/document/Employee',
  params: () => ({
    filters: JSON.stringify(leaveCan.value.employee_filters),
    fields: JSON.stringify(EMPLOYEE_FIELDS),
    limit: '1',
  }),
  immediate: false,
})

watch(
  () => leaveCan.value.employee_access,
  (access) => {
    if (access === 'visible') myEmployeeCall.reload()
  },
  { immediate: true }
)

/** The Employee record behind the session user — `null` when none is readable. */
export const myEmployee = computed(() => myEmployeeCall.data?.[0] ?? null)

/**
 * Both answers in.
 *
 * There is nothing to wait for when the server has already said the record is
 * absent or withheld: no read was issued, so `isFinished` would never come.
 */
export const myEmployeeLoaded = computed(
  () =>
    leavePermissionsLoaded.value &&
    (leaveCan.value.employee_access !== 'visible' || myEmployeeCall.isFinished)
)

/**
 * The session user's own leave applications, newest first.
 *
 * Filtered on the employee rather than the login, because leave is requested
 * against an employee record. The read waits for that employee: an unfiltered
 * one would be everybody's, which is exactly what an approver would get.
 */
export function useMyLeaveApplications() {
  const applications = useCall<
    LeaveApplicationRow[],
    { filters: string; fields: string; order_by: string; limit: string }
  >({
    url: '/api/v2/document/Leave Application',
    params: () => ({
      filters: JSON.stringify({ employee: myEmployee.value?.name }),
      // The workflow's state column where a site runs one, so a row can be
      // labelled with the state rather than with `status`.
      fields: JSON.stringify(
        leaveCan.value.workflow
          ? [...APPLICATION_FIELDS, leaveCan.value.workflow.workflow_state_field]
          : APPLICATION_FIELDS
      ),
      order_by: 'from_date desc',
      limit: String(leaveCan.value.page_length || 20),
    }),
    immediate: false,
  })
  watch(
    () => myEmployee.value?.name,
    (name) => {
      if (name) applications.reload()
    },
    { immediate: true }
  )
  return applications
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
    { immediate: true }
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
  employee: MaybeRefOrGetter<string | undefined>
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

// No workflow description is fetched here, deliberately. Every row already
// arrives carrying its own label, style and permitted actions — the server
// settles all three, because `status` alone is not the answer and a site running
// a Workflow styles its own states — so nothing on these pages ever read the
// workflow itself. Reloading it after a decision refreshed nothing; reloading
// the queue is what moves the labels.

export interface LeaveStatusDisplay {
  label: string
  theme: BadgeTheme
}

/**
 * How a leave application reads to a person.
 *
 * An approvals-queue row arrives already settled -- the server decorates those,
 * because what a reviewer may do to a row is a permission question and has to be
 * answered there anyway -- and this just maps the style to a badge.
 *
 * A row the page fetched for itself arrives with neither, and is labelled here.
 * Worth being explicit about what that does and does not move off the server:
 * every *name* and every *style* is still the site's, read out of the workflow
 * states and the decision vocabulary the permissions endpoint sends. What is
 * stated here is the docstatus rule -- 2 is cancelled, 0 is still pending
 * whatever `status` says -- which is Frappe's document lifecycle rather than
 * anything a site configures.
 */
export function leaveStatus(
  row: LeaveApplicationRow,
  permissions: LeavePermissions = leaveCan.value
): LeaveStatusDisplay {
  if (row.status_label) {
    return { label: row.status_label, theme: styleTheme(row.status_style) }
  }

  const workflow = permissions.workflow
  if (workflow) {
    const state = row[workflow.workflow_state_field] as string | undefined
    const style =
      workflow.states.find((row) => row.state === state)?.style ?? null
    return { label: state || row.status, theme: styleTheme(style) }
  }

  if (row.docstatus === 2) return { label: 'Cancelled', theme: styleTheme(null) }
  if (row.docstatus === 0) return { label: 'Pending', theme: styleTheme('Warning') }

  // The outcome's own styling, as the server sent it -- so a site that renamed
  // an outcome or restyled it gets that here without an edit.
  const decision = permissions.decisions.find((row2) => row2.value === row.status)
  return { label: row.status, theme: styleTheme(decision?.style ?? null) }
}

/** Wording, and only wording. An outcome this does not know keeps the server's
 *  name for it, which is what a site that added one would want it called. */
const DECISION_LABELS: Record<string, string> = {
  Approved: 'Approve',
  Rejected: 'Deny',
}

/** How a leave decision button reads. The shape and the one-solid-button rule
 *  are shared (`workflowStyle`); leave supplies only its own wording. */
export function decisionButton(decision: LeaveDecision): DecisionButton {
  return buildDecisionButton(decision, DECISION_LABELS)
}

/** The buttons for one row: the outcomes the server said this row accepts. */
export function decisionButtons(
  offered: string[] | undefined,
  vocabulary: LeaveDecision[]
): DecisionButton[] {
  return buildDecisionButtons(offered, vocabulary, DECISION_LABELS)
}
