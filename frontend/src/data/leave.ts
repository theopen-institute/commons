import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useCall, useList } from 'frappe-ui'
import type { Filters } from 'frappe-ui'

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
  status: 'Open' | 'Approved' | 'Rejected' | 'Cancelled'
  docstatus: 0 | 1 | 2
  leave_approver: string | null
  leave_approver_name: string | null
  posting_date: string
}

const LIST_FIELDS = [
  'name',
  'employee',
  'employee_name',
  'leave_type',
  'from_date',
  'to_date',
  'total_leave_days',
  'half_day',
  'description',
  'status',
  'docstatus',
  'leave_approver',
  'leave_approver_name',
  'posting_date',
] as const

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
}

export const leaveCan = computed(
  () => leavePermissionsCall.data ?? NO_LEAVE_PERMISSIONS,
)

export const leavePermissionsLoaded = computed(
  () => leavePermissionsCall.data != null,
)

export function reloadLeavePermissions() {
  return leavePermissionsCall.reload()
}

/** The session user's own leave applications, newest first. */
export function useMyLeaveApplications(
  employee: MaybeRefOrGetter<string | undefined>,
) {
  return useList<LeaveApplicationRow>({
    doctype: 'Leave Application',
    fields: [...LIST_FIELDS],
    filters: () => {
      const name = toValue(employee)
      // An impossible filter rather than none: without it this would list
      // every application the user can read, which for an approver is
      // everyone's.
      return { employee: name || '__none__' } as Filters
    },
    orderBy: 'from_date desc',
    limit: 20,
  })
}

/**
 * Applications waiting on this user's decision — drafts where they are the
 * named approver. `docstatus: 0` is what "not yet decided" means here: a
 * decision is a status change *and* a submit, so anything submitted is done.
 */
export function usePendingApprovals(options: {
  decided: MaybeRefOrGetter<boolean>
  approver: MaybeRefOrGetter<string>
}) {
  return useList<LeaveApplicationRow>({
    doctype: 'Leave Application',
    fields: [...LIST_FIELDS],
    filters: () => {
      const filters: Filters = { leave_approver: toValue(options.approver) }
      filters.docstatus = toValue(options.decided) ? 1 : 0
      return filters
    },
    orderBy: () => (toValue(options.decided) ? 'modified desc' : 'from_date asc'),
    limit: 20,
  })
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
    { name: string; decision: 'Approved' | 'Rejected' }
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
