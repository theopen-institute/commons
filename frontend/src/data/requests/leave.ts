import { toValue, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import { createRequestSection, type RequestRow } from './section'
import type { Decision, DecisionButton } from '../workflowStyle'

export type { DecisionButton }
export type { EmployeeAccess, RequestWorkflow as LeaveWorkflow } from './section'
export type { RequestPermissions as LeavePermissions } from './section'

/**
 * Leave, as the pages use it.
 *
 * The shape is `createRequestSection`, shared with expenses — see its comments
 * for what each of the exports below is and why it behaves as it does. What is
 * here is leave's own: which endpoints answer, what a row carries, what the
 * outcomes are called, and the two HRMS calculations nothing else needs.
 */

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

/** One outcome an approver may be offered. The shared shape -- see `Decision` in
 *  `workflowStyle`, which procurement's and profile's vocabularies use too. */
export type LeaveDecision = Decision

/** One row of a leave application list. */
export interface LeaveApplicationRow extends RequestRow {
  leave_type: string
  from_date: string
  to_date: string
  total_leave_days: number
  half_day: 0 | 1
  description: string | null
  status: string
  leave_approver: string | null
  leave_approver_name: string | null
  posting_date: string
}

const section = createRequestSection<MyEmployee, LeaveApplicationRow>({
  module: 'tbs_commons.requests.leave',
  doctype: 'Leave Application',
  decisionField: 'status',
  endpoints: {
    permissions: 'get_leave_permissions',
    queue: 'get_leave_approval_queue',
    decide: 'decide_leave_application',
    request: 'request_leave',
  },
  employeeFields: ['name', 'leave_approver'],
  rowFields: [
    'name',
    'leave_type',
    'description',
    'posting_date',
    'from_date',
    'to_date',
    'total_leave_days',
    'status',
    'docstatus',
  ],
  orderBy: 'from_date desc',
  decisionLabels: { Approved: 'Approve', Rejected: 'Deny' },
})

export const leaveCan = section.can
export const leavePermissionsLoaded = section.permissionsLoaded
export const leavePermissionsError = section.permissionsError
export const reloadLeavePermissions = section.reloadPermissions
export const myEmployee = section.myEmployee
export const myEmployeeLoaded = section.myEmployeeLoaded
export const useMyLeaveApplications = section.useMine
export const useLeaveApprovalQueue = section.useApprovalQueue
export const leaveStatus = section.status
export const decisionButton = section.decisionButton
export const decisionButtons = section.decisionButtons

export const useRequestLeave = section.useRequest
export const useLeaveDecision = () =>
  section.useDecision<
    { name: string; status: string; docstatus: number },
    { name: string; decision: string }
  >()

// No workflow description is fetched here, deliberately. Every row already
// arrives carrying its own label, style and permitted actions — the server
// settles all three, because the decision field alone is not the answer and a
// site running a Workflow styles its own states — so nothing on these pages ever
// read the workflow itself. Reloading it after a decision refreshed nothing;
// reloading the queue is what moves the labels.

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
