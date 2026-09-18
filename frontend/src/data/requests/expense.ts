import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { upload, useCall } from 'frappe-ui'
import { createRequestSection, type RequestRow } from './section'
import type { Decision, DecisionButton } from '../workflowStyle'

export type { DecisionButton }
export type { EmployeeAccess, RequestWorkflow as ExpenseWorkflow } from './section'
export type { RequestPermissions as ExpensePermissions } from './section'

/**
 * Expenses, as the pages use them.
 *
 * The shape is `createRequestSection`, shared with leave — see its comments for
 * what each of the exports below is. Two things are this section's own, and
 * both are on the server for the same reason everything else is:
 *
 * - A claim is money. What it is priced at, which cost centre it is charged to
 *   and which account each expense books to are ERPNext's answers, settled by
 *   `request_expense_claim`. The desk collects all of that with a screenful of
 *   JavaScript; this form collects a date, a type, a description and an amount.
 * - An approver can allow less than was claimed. The figures go with the
 *   decision in one call, so the amount and the outcome land together and HRMS
 *   revalidates both.
 */

/** One outcome an approver may be offered. The shared shape — see `Decision`. */
export type ExpenseDecision = Decision

/** One expense type a claim may be raised against. */
export interface ExpenseClaimType {
  name: string
  description: string | null
}

/**
 * What a blank claim opens with.
 *
 * Its own call, made when the form opens, rather than part of the permissions
 * every page load fetches — the same split procurement settled on.
 *
 * `expense_types` is deliberately not every `Expense Claim Type` on the site:
 * one with no account configured for this company cannot be saved against, so
 * the server leaves it out and the form says the list is empty rather than
 * bouncing the claim back one failed save later.
 */
export interface ExpenseClaimDefaults {
  employee: string | null
  company: string | null
  currency: string | null
  approver: string | null
  expense_types: ExpenseClaimType[]
}

/** One row of an expense claim list. */
export interface ExpenseClaimRow extends RequestRow {
  department: string | null
  company: string
  currency: string | null
  posting_date: string
  remark: string | null
  /** What the approver settled, which is what a decision writes. */
  approval_status: string
  /** Whether an approved claim has been reimbursed yet — HRMS's own readout,
   *  and a different question from whether it was approved. */
  status: string
  expense_approver: string | null
  /** Only queue rows carry it: `Expense Claim` keeps no fetched name beside the
   *  approver link, the way `Leave Application` does. */
  expense_approver_name?: string | null
  total_claimed_amount: number
  total_sanctioned_amount: number
  total_amount_reimbursed: number
  grand_total: number
}

/** One expense on a claim. */
export interface ExpenseClaimLine {
  name: string
  /** The claim this expense belongs to. */
  parent: string
  idx: number
  expense_date: string | null
  expense_type: string
  /** Flattened to text by the server — the stored field is a Text Editor, and
   *  nothing on these pages renders markup it was handed. */
  description: string | null
  amount: number
  /** What the approver is allowing. Opens at `amount` and is settled downwards. */
  sanctioned_amount: number
}

const section = createRequestSection<{ name: string }, ExpenseClaimRow>({
  module: 'tbs_commons.requests.expense',
  doctype: 'Expense Claim',
  decisionField: 'approval_status',
  endpoints: {
    permissions: 'get_expense_permissions',
    queue: 'get_expense_approval_queue',
    decide: 'decide_expense_claim',
    request: 'request_expense_claim',
  },
  // Only the name: a claim is raised against an employee record and nothing
  // else on these pages reads it.
  employeeFields: ['name'],
  rowFields: [
    'name',
    'employee',
    'employee_name',
    'company',
    'currency',
    'posting_date',
    'remark',
    'approval_status',
    'status',
    'docstatus',
    'expense_approver',
    'total_claimed_amount',
    'total_sanctioned_amount',
    'total_amount_reimbursed',
    'grand_total',
  ],
  orderBy: 'posting_date desc, creation desc',
  decisionLabels: { Approved: 'Approve', Rejected: 'Decline' },
})

export const expenseCan = section.can
export const expensePermissionsLoaded = section.permissionsLoaded
export const expensePermissionsError = section.permissionsError
export const reloadExpensePermissions = section.reloadPermissions
export const myEmployee = section.myEmployee
export const myEmployeeLoaded = section.myEmployeeLoaded
export const useMyExpenseClaims = section.useMine
export const useExpenseApprovalQueue = section.useApprovalQueue
export const expenseStatus = section.status
export const decisionButton = section.decisionButton
export const decisionButtons = section.decisionButtons

export const useRequestExpenseClaim = section.useRequest

/**
 * Settle a claim. The sanctioned figures ride along on the same call, so the
 * amount and the outcome are written together.
 */
export const useExpenseDecision = () =>
  section.useDecision<
    {
      name: string
      status: string
      docstatus: number
      total_sanctioned_amount: number
      currency: string | null
    },
    { name: string; decision: string; sanctioned?: string }
  >()

/**
 * The expenses on several claims at once, grouped by claim.
 *
 * One call for the whole page rather than one per card. It goes through a
 * whitelisted method rather than the document API because a child table read
 * over REST is permission-checked against the child doctype, which has no
 * permissions of its own — see `get_expense_claim_lines`.
 */
export function useExpenseClaimLines(claims: MaybeRefOrGetter<string[]>) {
  const lines = useCall<ExpenseClaimLine[], { claims: string }>({
    url: '/api/v2/method/tbs_commons.requests.expense.get_expense_claim_lines',
    params: () => ({ claims: JSON.stringify(toValue(claims)) }),
    immediate: false,
  })

  // Reload whenever the claim list refreshes, even if its names are unchanged:
  // a sanctioned amount may have moved since.
  watch(
    () => toValue(claims),
    (names) => {
      if (names.length) lines.reload()
    },
    { immediate: true },
  )

  const byClaim = computed(() => {
    const grouped = new Map<string, ExpenseClaimLine[]>()
    for (const line of lines.data ?? []) {
      const group = grouped.get(line.parent)
      if (group) group.push(line)
      else grouped.set(line.parent, [line])
    }
    return grouped
  })

  return { lines, byClaim }
}

/**
 * What this employee has claimed, allowed and been turned down for.
 *
 * HRMS's own arithmetic, over its own definition of each total — see
 * `hrms.api.get_expense_claim_summary`, which scopes itself to the employee
 * behind the session. Summing the rows on this page would have been a second
 * place those totals were worked out, and one that could only ever see the
 * page's own twenty.
 *
 * Every figure is null on a site where the employee has claimed nothing, which
 * is the answer rather than a zero: there is nothing to total.
 */
export interface ExpenseClaimSummary {
  total_pending_amount: number | null
  total_approved_amount: number | null
  total_rejected_amount: number | null
  total_claimed_in_approved: number | null
  currency: string | null
}

export function useExpenseClaimSummary() {
  return useCall<ExpenseClaimSummary>({
    url: '/api/v2/method/hrms.api.get_expense_claim_summary',
    immediate: false,
  })
}

export function useExpenseClaimDefaults() {
  return useCall<ExpenseClaimDefaults>({
    url: '/api/v2/method/tbs_commons.requests.expense.get_expense_claim_defaults',
    immediate: false,
  })
}

/** A file that did not make it onto the claim, and the server's reason. */
export interface FailedAttachment {
  file: string
  message: string
}

/**
 * Attach files to a claim that already exists.
 *
 * Frappe's own upload endpoint, not an endpoint of ours: it writes the `File`,
 * links it to the document, and — the part worth going through it for — refuses
 * unless the caller may write to that document. Whose claim this is, is already
 * a question the site has an answer to; asking it again here would be a second
 * answer to maintain.
 *
 * Private, because a receipt is a record of what somebody bought and where they
 * were. A public file in Frappe is readable by its URL alone, by anyone holding
 * it.
 *
 * Only after the claim is inserted, because an attachment needs something to
 * hang on. That ordering is why a failure here is reported rather than thrown:
 * the claim is raised by the time we get here, and telling the claimant it
 * failed would be a lie that costs them a duplicate claim. Each file is
 * attempted, and what failed comes back with its reason.
 */
export async function attachToExpenseClaim(
  claim: string,
  files: File[],
): Promise<FailedAttachment[]> {
  const failed: FailedAttachment[] = []
  // One at a time: a phone camera's worth of receipts uploaded at once is a
  // burst of large requests, and nothing here is waiting on the next one.
  for (const file of files) {
    try {
      await upload(file, {
        doctype: 'Expense Claim',
        docname: claim,
        private: true,
        folder: 'Home/Attachments',
      })
    } catch (error) {
      failed.push({
        file: file.name,
        message: error instanceof Error ? error.message : 'Upload failed',
      })
    }
  }
  return failed
}

/**
 * Whether a settled claim is still owed to the claimant, said in HRMS's words.
 *
 * `status` is derived by `ExpenseClaim.set_status` from the decision and what
 * has been reimbursed, and it answers a question the badge deliberately does
 * not: an approved claim can be Paid or Unpaid, and the person who is out of
 * pocket wants to know which. Only meaningful once the claim is submitted.
 */
export function reimbursement(row: ExpenseClaimRow): string | null {
  if (row.docstatus !== 1) return null
  return row.status === 'Paid' || row.status === 'Unpaid' ? row.status : null
}
