import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import {
  decisionButton as buildDecisionButton,
  decisionButtons as buildDecisionButtons,
  styleTheme,
  type BadgeTheme,
  type Decision,
  type DecisionButton,
} from '../workflowStyle'

/**
 * A section of the requests app, as the pages use it.
 *
 * Leave and expenses are the same page twice: a permissions call, the employee
 * behind the session, your own list, an approvals queue with per-row buttons,
 * and a label for each row. The two data modules said all of that separately
 * and nearly identically — the second one's comments cited the first as their
 * argument, which is how you know. The server's half of the same duplication is
 * `tbs_commons.requests.approvals`; this is the browser's half.
 *
 * What a section supplies is the part that is genuinely its own: which endpoint
 * answers each question, what a row of its list carries, and what its outcomes
 * are called in English. Everything else — when to fire the employee read, what
 * counts as "the answer is in", how a row reads, which button is the solid one
 * — is settled here, once, for both.
 *
 * Procurement is not built from this. Its queue is grouped by the department
 * whose budget it spends and its permissions payload answers a different
 * question (workflow access, not an approve right), so it keeps its own module
 * and shares only `workflowStyle` with these two.
 */

/**
 * Why there is no employee record, when `myEmployee` is null.
 *
 * `missing` sends the reader to HR and `forbidden` to whoever administers
 * permissions, which is the whole reason the server distinguishes them — one
 * message for both told a user whose access had been revoked to ask HR to
 * create a record that already names them. See `session_employee_access`.
 */
export type EmployeeAccess = 'visible' | 'forbidden' | 'missing'

export interface RequestWorkflowState {
  state: string
  doc_status: number
  style: string | null
}

export interface RequestWorkflow {
  name: string
  workflow_state_field: string
  states: RequestWorkflowState[]
  transitions: { state: string; action: string; next_state: string }[]
}

/** What `approvals.RequestType.permissions` sends, whichever section sent it. */
export interface RequestPermissions {
  read: boolean
  request: boolean
  /** What makes an Employee row this session's own. The server's predicate, not
   *  this page's: `user_id` names the login and `status` rules out a leaver, and
   *  a filter written here would be the second place that rule lived. */
  employee_filters: Record<string, string>
  employee_access: EmployeeAccess
  /** The active Workflow, if the site runs one. Its states and their styling are
   *  what a row fetched through the document API is labelled from. */
  workflow: RequestWorkflow | null
  approve: boolean
  pending_approvals: number
  /** The outcomes the server will accept, in the order they should be offered. */
  decisions: Decision[]
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

/** What every row of either section carries, whatever else it also has. */
export interface RequestRow {
  name: string
  employee: string
  employee_name: string
  docstatus: 0 | 1 | 2
  /** How this row reads, in the server's words and the site's styling.
   *
   *  Present only on approvals-queue rows, which the server decorates because
   *  what a reviewer may do to a row is a permission question anyway. Rows the
   *  page fetches for itself arrive without them and are labelled by `status`
   *  below, from the same workflow states and decision styles the server would
   *  have used. */
  status_label?: string
  status_style?: string | null
  /** Whether *this* user may decide *this* row. Only the approvals queue fills
   *  it in; the server settles it again before writing anything. */
  can_decide?: boolean
  /** The outcomes this user may apply to *this* row, named as the server names
   *  them. Transitions from the active Workflow where a site runs one. */
  actions?: string[]
  /** The workflow's state column, whatever a site named it. Not knowable
   *  statically, which is why it is reached by index rather than by name. */
  [key: string]: unknown
}

export interface StatusDisplay {
  label: string
  theme: BadgeTheme
}

export interface RequestSectionOptions {
  /** The dotted path of the server module behind the section, e.g.
   *  `tbs_commons.requests.leave`. Its endpoints are named below rather than
   *  derived, because they are named for what they do and not for a pattern. */
  module: string
  /** The doctype the user's own list is read from through the document API,
   *  where every permission the site has configured applies without this module
   *  restating any of them. */
  doctype: string
  /** The field a decision writes, and so what a row falls back to reading as
   *  once it is submitted. `status` for leave, `approval_status` for expenses. */
  decisionField: string
  endpoints: {
    permissions: string
    queue: string
    decide: string
    request: string
  }
  /** Employee fields this section's pages actually draw. Not a permission
   *  boundary — Frappe drops fields the caller may not read from the select on
   *  its own — so a page is free to name the ones it renders. */
  employeeFields: string[]
  /** Likewise for a row of the user's own list: exactly what it puts on screen. */
  rowFields: string[]
  /** How that list is ordered. */
  orderBy: string
  /** Wording, and only wording. An outcome this does not know keeps the server's
   *  name for it, which is what a site that added one would want it called. */
  decisionLabels: Record<string, string>
}

export function createRequestSection<
  Employee extends { name: string },
  Row extends RequestRow,
>(options: RequestSectionOptions) {
  const method = (name: string) =>
    `/api/v2/method/${options.module}.${name}`

  const permissionsCall = useCall<RequestPermissions>({
    url: method(options.endpoints.permissions),
  })

  const NONE: RequestPermissions = {
    read: false,
    request: false,
    employee_filters: {},
    // Before the answer is in, say nothing rather than accuse anyone: `missing`
    // is the state a page renders with no explanation attached to it.
    employee_access: 'missing',
    workflow: null,
    approve: false,
    pending_approvals: 0,
    decisions: [],
    page_length: 0,
    approver_mandatory: true,
    approver_query: '',
  }

  const can = computed(() => permissionsCall.data ?? NONE)

  /**
   * Whether the answer is in — settled or refused, not merely arrived.
   *
   * Deliberately not `data != null`: a call that fails never sets `data`, and a
   * page gating its skeleton on that sits in the skeleton for ever with nothing
   * to show for it. `permissionsError` is what it should say instead.
   */
  const permissionsLoaded = computed(() => permissionsCall.isFinished)
  const permissionsError = computed(() => permissionsCall.error ?? null)
  const reloadPermissions = () => permissionsCall.reload()

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
    Employee[],
    { filters: string; fields: string; limit: string }
  >({
    url: '/api/v2/document/Employee',
    params: () => ({
      filters: JSON.stringify(can.value.employee_filters),
      fields: JSON.stringify(options.employeeFields),
      limit: '1',
    }),
    immediate: false,
  })

  watch(
    () => can.value.employee_access,
    (access) => {
      if (access === 'visible') myEmployeeCall.reload()
    },
    { immediate: true },
  )

  /** The Employee record behind the session user — `null` when none is readable. */
  const myEmployee = computed(() => myEmployeeCall.data?.[0] ?? null)

  /**
   * Both answers in.
   *
   * There is nothing to wait for when the server has already said the record is
   * absent or withheld: no read was issued, so `isFinished` would never come.
   */
  const myEmployeeLoaded = computed(
    () =>
      permissionsLoaded.value &&
      (can.value.employee_access !== 'visible' || myEmployeeCall.isFinished),
  )

  /**
   * The session user's own requests, newest first.
   *
   * Filtered on the employee rather than the login, because these are raised
   * against an employee record. The read waits for that employee: an unfiltered
   * one would be everybody's, which is exactly what an approver would get.
   */
  function useMine() {
    const rows = useCall<
      Row[],
      { filters: string; fields: string; order_by: string; limit: string }
    >({
      url: `/api/v2/document/${options.doctype}`,
      params: () => ({
        filters: JSON.stringify({ employee: myEmployee.value?.name }),
        // The workflow's state column where a site runs one, so a row can be
        // labelled with the state rather than with the decision field.
        fields: JSON.stringify(
          can.value.workflow
            ? [...options.rowFields, can.value.workflow.workflow_state_field]
            : options.rowFields,
        ),
        order_by: options.orderBy,
        limit: String(can.value.page_length || 20),
      }),
      immediate: false,
    })
    watch(
      () => myEmployee.value?.name,
      (name) => {
        if (name) rows.reload()
      },
      { immediate: true },
    )
    return rows
  }

  /**
   * Rows this user has to decide, or ones already decided.
   *
   * What counts as either is the server's to say — see
   * `approvals.RequestType.approval_queue`. Building the filters here instead
   * let "waiting on you" mean one thing on this page and a slightly different
   * thing in the badge counting it.
   */
  function useApprovalQueue(decided: MaybeRefOrGetter<boolean>) {
    const queue = useCall<Row[], { decided: number }>({
      url: method(options.endpoints.queue),
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
   * Settle a row, by whatever route the site has configured — a Workflow
   * transition where one is running, a decision field and a submit where none
   * is. One call either way, because the two halves are one action for the
   * approver.
   */
  function useDecision<
    Result extends { name: string; status: string; docstatus: number },
    Params extends { name: string; decision: string },
  >() {
    return useCall<Result, Params>({
      url: method(options.endpoints.decide),
      method: 'POST',
      immediate: false,
    })
  }

  /**
   * Raise one for the employee behind this session.
   *
   * Through a whitelisted method rather than the document API: which fields a
   * request may set, and which employee it is for, are the server's to decide.
   * A form that posts a document decides both for itself.
   */
  function useRequest() {
    return useCall<{ name: string }, { doc: string }>({
      url: method(options.endpoints.request),
      method: 'POST',
      immediate: false,
    })
  }

  /**
   * How a row reads to a person.
   *
   * An approvals-queue row arrives already settled — the server decorates
   * those, because what a reviewer may do to a row is a permission question and
   * has to be answered there anyway — and this just maps the style to a badge.
   *
   * A row the page fetched for itself arrives with neither, and is labelled
   * here. Worth being explicit about what that does and does not move off the
   * server: every *name* and every *style* is still the site's, read out of the
   * workflow states and the decision vocabulary the permissions endpoint sends.
   * What is stated here is the docstatus rule — 2 is cancelled, 0 is still
   * pending whatever the decision field says — which is Frappe's document
   * lifecycle rather than anything a site configures.
   */
  function status(
    row: Row,
    permissions: RequestPermissions = can.value,
  ): StatusDisplay {
    if (row.status_label) {
      return { label: row.status_label, theme: styleTheme(row.status_style) }
    }

    const decided = row[options.decisionField] as string

    const workflow = permissions.workflow
    if (workflow) {
      const state = row[workflow.workflow_state_field] as string | undefined
      const style =
        workflow.states.find((one) => one.state === state)?.style ?? null
      return { label: state || decided, theme: styleTheme(style) }
    }

    if (row.docstatus === 2)
      return { label: 'Cancelled', theme: styleTheme(null) }
    if (row.docstatus === 0)
      return { label: 'Pending', theme: styleTheme('Warning') }

    // The outcome's own styling, as the server sent it — so a site that renamed
    // an outcome or restyled it gets that here without an edit.
    const decision = permissions.decisions.find((one) => one.value === decided)
    return { label: decided, theme: styleTheme(decision?.style ?? null) }
  }

  /** How one decision button reads. The shape and the one-solid-button rule are
   *  shared (`workflowStyle`); a section supplies only its own wording. */
  function decisionButton(decision: Decision): DecisionButton {
    return buildDecisionButton(decision, options.decisionLabels)
  }

  /** The buttons for one row: the outcomes the server said this row accepts. */
  function decisionButtons(
    offered: string[] | undefined,
    vocabulary: Decision[],
  ): DecisionButton[] {
    return buildDecisionButtons(offered, vocabulary, options.decisionLabels)
  }

  return {
    can,
    permissionsLoaded,
    permissionsError,
    reloadPermissions,
    myEmployee,
    myEmployeeLoaded,
    useMine,
    useApprovalQueue,
    useDecision,
    useRequest,
    status,
    decisionButton,
    decisionButtons,
  }
}
