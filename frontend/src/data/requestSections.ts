import { computed, type ComputedRef } from 'vue'
import { expenseCan } from './expense'
import { leaveCan } from './leave'
import { procurementCan } from './procurement'

/**
 * The three things a person raises and waits on an approver for.
 *
 * Each is one page with two tabs -- what I raised, and what I have to decide --
 * rather than two sidebar rows, because they are two views of one job and an
 * approver who has just decided something wants their own list next, not a
 * different page.
 *
 * The tabs stay two routes, so a queue can still be linked to and a reload
 * comes back where it was; what this module holds is the half both the sidebar
 * and the tab switcher need and would otherwise each state for themselves --
 * where a section lives, whether this user has it at all, and how many
 * decisions are waiting.
 */
export type RequestSectionKey = 'leave' | 'expense' | 'procurement'

export interface RequestSection {
  key: RequestSectionKey
  /** Said by the sidebar row, the page heading and the browser history alike. */
  label: string
  /** The row's mark, from the same lucide family as the rest of the sidebar. */
  icon: string
  /** Route names, not paths: the two tabs, in the order they are shown. */
  mineRoute: string
  approvalsRoute: string
  /** What the "mine" tab is called. Each section raises a different thing. */
  mineLabel: string
  /** Whether this user has the section at all. */
  visible: ComputedRef<boolean>
  /** Whether the approvals tab is theirs to open. */
  canApprove: ComputedRef<boolean>
  /** Decisions waiting on them, for the badge. 0 when none are. */
  pending: ComputedRef<number>
  /**
   * Whether that count is the server's ceiling rather than the whole of it --
   * a full queue says `20+` rather than quietly claiming that is all there is.
   */
  atCeiling: ComputedRef<boolean>
}

function atCeiling(pending: () => number, ceiling: () => number) {
  return computed(() => {
    const limit = ceiling()
    return Boolean(limit) && pending() >= limit
  })
}

export const requestSections: RequestSection[] = [
  {
    key: 'leave',
    label: 'Leave Request',
    icon: 'lucide-palmtree',
    mineRoute: 'MyLeave',
    approvalsRoute: 'LeaveApprovals',
    mineLabel: 'My leave',
    visible: computed(() => leaveCan.value.read),
    canApprove: computed(() => leaveCan.value.approve),
    pending: computed(() => leaveCan.value.pending_approvals),
    atCeiling: atCeiling(
      () => leaveCan.value.pending_approvals,
      () => leaveCan.value.page_length,
    ),
  },
  {
    key: 'expense',
    label: 'Expense Claim',
    icon: 'lucide-receipt',
    mineRoute: 'MyExpenses',
    approvalsRoute: 'ExpenseApprovals',
    mineLabel: 'My claims',
    visible: computed(() => expenseCan.value.read),
    canApprove: computed(() => expenseCan.value.approve),
    pending: computed(() => expenseCan.value.pending_approvals),
    atCeiling: atCeiling(
      () => expenseCan.value.pending_approvals,
      () => expenseCan.value.page_length,
    ),
  },
  {
    key: 'procurement',
    label: 'Procurement Request',
    icon: 'lucide-shopping-cart',
    mineRoute: 'MyProcurement',
    approvalsRoute: 'ProcurementApprovals',
    mineLabel: 'My requests',
    // Procurement's approvals are workflow actions rather than an approve
    // permission, so both the tab and its badge read the workflow's answer.
    visible: computed(() => procurementCan.value.read),
    canApprove: computed(() => procurementCan.value.workflow_access),
    pending: computed(() => procurementCan.value.pending_workflow_actions),
    atCeiling: atCeiling(
      () => procurementCan.value.pending_workflow_actions,
      () => procurementCan.value.page_length,
    ),
  },
]

export function requestSection(key: RequestSectionKey): RequestSection {
  const found = requestSections.find((section) => section.key === key)
  // Unreachable through the type, and worth saying out loud if a refactor ever
  // makes it reachable: a page with no section has no tabs and no title.
  if (!found) throw new Error(`No request section named ${key}`)
  return found
}
