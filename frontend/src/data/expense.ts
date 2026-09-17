import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { upload, useCall } from 'frappe-ui'
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
 * The expense section, built to the shape leave settled on — see `data/leave`,
 * whose comments argue for most of what is here. What a row reads as, which
 * outcomes it accepts and how many are waiting are all the server's answers.
 *
 * Two things are this section's own, and both are on the server for the same
 * reason everything else is:
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

/**
 * Why there is no employee record, when `myEmployee` is null.
 *
 * `missing` sends the reader to HR and `forbidden` to whoever administers
 * permissions. See `session_employee_access`.
 */
export type EmployeeAccess = 'visible' | 'forbidden' | 'missing'

export interface ExpenseWorkflowState {
  state: string
  doc_status: number
  style: string | null
}

export interface ExpenseWorkflow {
  name: string
  workflow_state_field: string
  states: ExpenseWorkflowState[]
  transitions: { state: string; action: string; next_state: string }[]
}

export interface ExpensePermissions {
  read: boolean
  request: boolean
  /** What makes an Employee row this session's own. The server's predicate, not
   *  this page's. */
  employee_filters: Record<string, string>
  employee_access: EmployeeAccess
  /** The active Workflow, if the site runs one. Its states and their styling are
   *  what a row fetched through the document API is labelled from. */
  workflow: ExpenseWorkflow | null
  approve: boolean
  pending_approvals: number
  /** The outcomes the server will accept, in the order they should be offered. */
  decisions: ExpenseDecision[]
  /** How many rows a queue returns. The badge counts to the same ceiling. */
  page_length: number
  /** Whether HR Settings makes the approver mandatory. */
  approver_mandatory: boolean
  /** The link query that resolves candidate approvers, named by the server so a
   *  site can point it somewhere else. */
  approver_query: string
}

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
export interface ExpenseClaimRow {
  name: string
  employee: string
  employee_name: string
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
  docstatus: 0 | 1 | 2
  expense_approver: string | null
  /** Only queue rows carry it: `Expense Claim` keeps no fetched name beside the
   *  approver link, the way `Leave Application` does. */
  expense_approver_name?: string | null
  total_claimed_amount: number
  total_sanctioned_amount: number
  total_amount_reimbursed: number
  grand_total: number
  /** How this row reads, in the server's words and the site's styling. Present
   *  only on approvals-queue rows; rows the page fetches for itself are
   *  labelled by `expenseStatus` from the same vocabulary. */
  status_label?: string
  status_style?: string | null
  /** Whether *this* user may settle *this* claim. Only the approvals queue
   *  fills it in; the server settles it again before writing anything. */
  can_decide?: boolean
  /** The outcomes this user may apply to *this* row, named as the server names
   *  them. Transitions from the active Workflow where a site runs one. */
  actions?: string[]
  /** The workflow's state column, whatever a site named it. */
  [key: string]: unknown
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

/** What a claim row carries. Not a permission boundary — Frappe drops fields the
 *  caller may not read from the select on its own. */
const CLAIM_FIELDS = [
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
]

const permissionsCall = useCall<ExpensePermissions>({
  url: '/api/v2/method/tbs_commons.expense.api.get_expense_permissions',
})

const NO_PERMISSIONS: ExpensePermissions = {
  read: false,
  request: false,
  employee_filters: {},
  // Before the answer is in, say nothing rather than accuse anyone.
  employee_access: 'missing',
  workflow: null,
  approve: false,
  pending_approvals: 0,
  decisions: [],
  page_length: 0,
  approver_mandatory: true,
  approver_query: '',
}

export const expenseCan = computed(
  () => permissionsCall.data ?? NO_PERMISSIONS,
)

/**
 * Whether the answer is in — settled or refused, not merely arrived.
 *
 * Deliberately not `data != null`: a call that fails never sets `data`, and a
 * page gating its skeleton on that sits in the skeleton for ever with nothing
 * to show for it. `expensePermissionsError` is what it should say instead.
 */
export const expensePermissionsLoaded = computed(
  () => permissionsCall.isFinished,
)

export const expensePermissionsError = computed(
  () => permissionsCall.error ?? null,
)

export function reloadExpensePermissions() {
  return permissionsCall.reload()
}

/**
 * The Employee record behind the session user, through Frappe's document API.
 *
 * Every permission the site has configured applies on the way in, without this
 * module restating any of them; the filter is the server's, so what counts as
 * "mine" is still settled in one place. Only the name is asked for — a claim is
 * raised against an employee record and nothing else on these pages reads it.
 *
 * Nothing is asked for unless the server has already said there is a readable
 * record; firing the read regardless would spend a round trip to rediscover it.
 */
const myEmployeeCall = useCall<
  { name: string }[],
  { filters: string; fields: string; limit: string }
>({
  url: '/api/v2/document/Employee',
  params: () => ({
    filters: JSON.stringify(expenseCan.value.employee_filters),
    fields: JSON.stringify(['name']),
    limit: '1',
  }),
  immediate: false,
})

watch(
  () => expenseCan.value.employee_access,
  (access) => {
    if (access === 'visible') myEmployeeCall.reload()
  },
  { immediate: true },
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
    expensePermissionsLoaded.value &&
    (expenseCan.value.employee_access !== 'visible' || myEmployeeCall.isFinished),
)

/**
 * The session user's own claims, newest first.
 *
 * Filtered on the employee rather than the login, because a claim is raised
 * against an employee record. The read waits for that employee: an unfiltered
 * one would be everybody's, which is exactly what an approver would get.
 */
export function useMyExpenseClaims() {
  const claims = useCall<
    ExpenseClaimRow[],
    { filters: string; fields: string; order_by: string; limit: string }
  >({
    url: '/api/v2/document/Expense Claim',
    params: () => ({
      filters: JSON.stringify({ employee: myEmployee.value?.name }),
      // The workflow's state column where a site runs one, so a row can be
      // labelled with the state rather than with the approval status.
      fields: JSON.stringify(
        expenseCan.value.workflow
          ? [...CLAIM_FIELDS, expenseCan.value.workflow.workflow_state_field]
          : CLAIM_FIELDS,
      ),
      order_by: 'posting_date desc, creation desc',
      limit: String(expenseCan.value.page_length || 20),
    }),
    immediate: false,
  })
  watch(
    () => myEmployee.value?.name,
    (name) => {
      if (name) claims.reload()
    },
    { immediate: true },
  )
  return claims
}

/**
 * Claims this user has to settle, or ones already settled.
 *
 * What counts as either is the server's to say — see
 * `get_expense_approval_queue`. Building the filters here instead let "waiting
 * on you" mean one thing on this page and a slightly different thing in the
 * badge counting it.
 */
export function useExpenseApprovalQueue(decided: MaybeRefOrGetter<boolean>) {
  const queue = useCall<ExpenseClaimRow[], { decided: number }>({
    url: '/api/v2/method/tbs_commons.expense.api.get_expense_approval_queue',
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
    url: '/api/v2/method/tbs_commons.expense.api.get_expense_claim_lines',
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
    url: '/api/v2/method/tbs_commons.expense.api.get_expense_claim_defaults',
    immediate: false,
  })
}

/**
 * Raise a claim for the employee behind this session.
 *
 * Through a whitelisted method rather than the document API: which fields a
 * claim may set, which employee it is for, and what it is priced at are the
 * server's to decide — see `request_expense_claim`.
 */
export function useRequestExpenseClaim() {
  return useCall<{ name: string }, { doc: string }>({
    url: '/api/v2/method/tbs_commons.expense.api.request_expense_claim',
    method: 'POST',
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
 * Settle a claim, by whatever route the site has configured — a Workflow
 * transition where one is running, an approval status and a submit where none
 * is. One call either way, and the sanctioned figures ride along on it so the
 * amount and the outcome are written together.
 */
export function useExpenseDecision() {
  return useCall<
    {
      name: string
      status: string
      docstatus: number
      total_sanctioned_amount: number
      currency: string | null
    },
    { name: string; decision: string; sanctioned?: string }
  >({
    url: '/api/v2/method/tbs_commons.expense.api.decide_expense_claim',
    method: 'POST',
    immediate: false,
  })
}

export interface ExpenseStatusDisplay {
  label: string
  theme: BadgeTheme
}

/**
 * How a claim reads to a person.
 *
 * An approvals-queue row arrives already settled — the server decorates those,
 * because what a reviewer may do to a row is a permission question and has to
 * be answered there anyway — and this just maps the style to a badge.
 *
 * A row the page fetched for itself is labelled here. Every *name* and every
 * *style* is still the site's, read out of the workflow states and the decision
 * vocabulary the permissions endpoint sends. What is stated here is the
 * docstatus rule — 2 is cancelled, 0 is still pending whatever the approval
 * status says — which is Frappe's document lifecycle rather than anything a
 * site configures.
 */
export function expenseStatus(
  row: ExpenseClaimRow,
  permissions: ExpensePermissions = expenseCan.value,
): ExpenseStatusDisplay {
  if (row.status_label) {
    return { label: row.status_label, theme: styleTheme(row.status_style) }
  }

  const workflow = permissions.workflow
  if (workflow) {
    const state = row[workflow.workflow_state_field] as string | undefined
    const style =
      workflow.states.find((one) => one.state === state)?.style ?? null
    return { label: state || row.approval_status, theme: styleTheme(style) }
  }

  if (row.docstatus === 2) return { label: 'Cancelled', theme: styleTheme(null) }
  if (row.docstatus === 0)
    return { label: 'Pending', theme: styleTheme('Warning') }

  // The outcome's own styling, as the server sent it — so a site that renamed
  // an outcome or restyled it gets that here without an edit.
  const decision = permissions.decisions.find(
    (one) => one.value === row.approval_status,
  )
  return { label: row.approval_status, theme: styleTheme(decision?.style ?? null) }
}

/**
 * Whether a settled claim is still owed to the claimant, said in HRMS's words.
 *
 * `status` is derived by `ExpenseClaim.set_status` from the decision and what
 * has been reimbursed, and it answers a question the badge above deliberately
 * does not: an approved claim can be Paid or Unpaid, and the person who is out
 * of pocket wants to know which. Only meaningful once the claim is submitted.
 */
export function reimbursement(row: ExpenseClaimRow): string | null {
  if (row.docstatus !== 1) return null
  return row.status === 'Paid' || row.status === 'Unpaid' ? row.status : null
}

/** Wording, and only wording. An outcome this does not know keeps the server's
 *  name for it, which is what a site that added one would want it called. */
const DECISION_LABELS: Record<string, string> = {
  Approved: 'Approve',
  Rejected: 'Decline',
}

/** How an expense decision button reads. The shape and the one-solid-button
 *  rule are shared (`workflowStyle`); expenses supply only their own wording. */
export function decisionButton(decision: ExpenseDecision): DecisionButton {
  return buildDecisionButton(decision, DECISION_LABELS)
}

/** The buttons for one row: the outcomes the server said this row accepts. */
export function decisionButtons(
  offered: string[] | undefined,
  vocabulary: ExpenseDecision[],
): DecisionButton[] {
  return buildDecisionButtons(offered, vocabulary, DECISION_LABELS)
}
