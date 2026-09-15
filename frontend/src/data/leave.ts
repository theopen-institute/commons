import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'

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

export interface LeavePermissions {
  read: boolean
  request: boolean
  approve: boolean
  pending_approvals: number
  /** The outcomes the server will accept, in the order they should be offered. */
  decisions: string[]
  /** How many rows a queue returns. The badge counts to the same ceiling. */
  page_length: number
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
  /** Whether *this* user may decide *this* application. Only the approvals
   *  queue fills it in; the server settles it again before writing anything. */
  can_decide?: boolean
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

/** Approve or reject an application, and submit it, in one call. */
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

export interface LeaveStatusDisplay {
  label: string
  theme: 'gray' | 'blue' | 'green' | 'amber' | 'red'
}

/**
 * How a leave application reads to a person. `status` alone is not the answer:
 * an application is only really decided once it is submitted, so a draft is
 * "Pending" whatever its status field says.
 */
export function leaveStatus(row: {
  status: string
  docstatus: number
}): LeaveStatusDisplay {
  if (row.docstatus === 2) return { label: 'Cancelled', theme: 'gray' }
  if (row.docstatus === 0) return { label: 'Pending', theme: 'amber' }
  if (row.status === 'Approved') return { label: 'Approved', theme: 'green' }
  if (row.status === 'Rejected') return { label: 'Rejected', theme: 'red' }
  return { label: row.status, theme: 'gray' }
}

/**
 * How a decision button reads. The set of them comes from the server; only the
 * wording and the colour are the page's, and an outcome this does not know is
 * still offered, named as the server names it.
 */
export function decisionButton(decision: string): {
  label: string
  past: string
  theme: 'green' | 'red' | 'gray'
  variant: 'solid' | 'subtle'
  icon: string
} {
  if (decision === 'Approved') {
    return {
      label: 'Approve',
      past: 'approved',
      theme: 'green',
      variant: 'solid',
      icon: 'lucide-check',
    }
  }
  if (decision === 'Rejected') {
    return {
      label: 'Deny',
      past: 'denied',
      theme: 'red',
      variant: 'subtle',
      icon: 'lucide-x',
    }
  }
  return {
    label: decision,
    past: decision.toLowerCase(),
    theme: 'gray',
    variant: 'subtle',
    icon: 'lucide-circle-dot',
  }
}
