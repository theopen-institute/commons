import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import { user } from './session'
import type { Employee } from '@/types/doctypes'
import {
  decisionButtons as buildDecisionButtons,
  styleTheme,
  type BadgeTheme,
  type Decision,
  type DecisionButton,
} from './workflowStyle'

export type { DecisionButton }

/**
 * The profile page's client state.
 *
 * The shape of this file is leave's, deliberately: both are self-service, both
 * ask the server what the user may do before drawing anything, and both take
 * their outcome vocabulary and its styling from whatever the site has
 * configured. What differs is the direction of the write. Leave creates a
 * document that *is* the thing being asked for; a change request creates a
 * document that describes an edit to a different one, and nothing here is
 * allowed to make that edit -- see `tbs_commons.self_service.api`.
 *
 * Everything below is the `Employee` half of a generic section. The server's
 * endpoints take a record type and answer from that doctype's policy (see
 * `tbs_commons.self_service.registry`); `RECORD` is where this page says which
 * one it is, and it is the only Employee-specific line in the file. A second
 * record type is a second module like this one and a page to go with it -- no
 * new request machinery, and nothing here to change.
 */

/** The record type this page reads and proposes against. */
const RECORD = 'Employee'

/** The employee record behind the session user, as this page shows it. */
export type MyProfile = Partial<Employee> & {
  name: string
  employee_name: string
  modified: string
}

/** One field a request proposes to change. */
export interface ProfileChangeRow {
  fieldname: string
  /** The field's label as it read when the change was proposed. */
  label: string | null
  /** What the employee record held. Captured by the server, never typed. */
  current_value: string | null
  proposed_value: string | null
}

/** One row of a profile change request list. */
export interface ProfileChangeRequest {
  name: string
  /** Which doctype this request changes. Always `Employee` on this page, but
   *  the request document is generic and says so. */
  reference_doctype: string
  reference_name: string
  /** How the record reads to a person, captured on the request so a queue need
   *  not load every referenced document. */
  reference_title: string
  requested_by: string
  reason: string | null
  review_note: string | null
  reviewed_by: string | null
  status: string
  docstatus: 0 | 1 | 2
  posting_date: string
  modified: string
  changes: ProfileChangeRow[]
  /** How this row reads, in the server's words and the site's styling. Settled
   *  there because `status` alone is not the answer -- a reversed request keeps
   *  the status it was approved with. */
  status_label: string
  status_style: string | null
  /** Whether this request is still awaiting a decision. Server-owned:
   *  `docstatus` cannot answer it, since a declined or withdrawn request stays
   *  at 0 so it can be amended. */
  open: boolean
  /** Whether *this* user may settle *this* request. The server settles it again
   *  before writing anything. */
  can_decide?: boolean
  /** The outcomes this user may apply to *this* row, named as the server names
   *  them. Transitions from the active Workflow where a site runs one. */
  actions?: string[]
}

export interface ProfilePermissions {
  /** Whether this user may use the section at all -- a permission, the way
   *  `leaveCan.read` is, and what the navigation offers on. Deliberately not
   *  conditioned on owning a record: a section that vanishes leaves someone
   *  unable to tell a missing feature from a missing permission, and it would
   *  take the review queue with it for a reviewer who is not an employee. */
  read: boolean
  /** Whether this user actually owns a record of this type. The page's
   *  question: profile, or the "your login isn't linked" notice. */
  has_record: boolean
  request: boolean
  review: boolean
  pending_reviews: number
  /** Fieldnames the server will accept a proposal for, from this record type's
   *  policy. The form offers the intersection of this and what
   *  `employeeFields.ts` knows how to draw, so a field can never be collected
   *  that the save would then refuse. */
  proposable: string[]
  /** What the page may show. The server's, so a field that has no business on
   *  a self-service page cannot appear by a frontend choosing for itself. */
  display: string[]
  /** How the policy finds the caller's own row, named by the server so this
   *  page hardcodes no Employee field. */
  owner_field: string | null
  record_filters: Record<string, string | number | boolean | null>
  /** Every record type registered for self service. Not used by this page --
   *  it knows it is Employee's -- but it is what a second page would read to
   *  know it has something to show. */
  registered: string[]
  /** The outcomes the server will accept, in the order they should be offered. */
  decisions: Decision[]
  /** How many rows a queue returns. The badge counts to the same ceiling. */
  page_length: number
}

// Declared before the record call below, and that order is load-bearing: the
// watch that kicks that call off is `immediate`, so it reads `profileCan` while
// this module is still evaluating. Below this point that is a const in its
// temporal dead zone, and the page dies on load rather than misbehaving later.
// Deliberately uncached, for the reason `session.ts` gives: a persisted cache is
// keyed by the browser rather than the user, so the next person to log in on
// this machine would get a stale-first render of someone else's answer.
const permissionsCall = useCall<ProfilePermissions, { doctype: string }>({
  url: '/api/v2/method/tbs_commons.self_service.api.get_change_permissions',
  params: { doctype: RECORD },
})

const NO_PROFILE_PERMISSIONS: ProfilePermissions = {
  read: false,
  has_record: false,
  request: false,
  review: false,
  pending_reviews: 0,
  proposable: [],
  display: [],
  owner_field: null,
  record_filters: {},
  registered: [],
  decisions: [],
  page_length: 0,
}

export const profileCan = computed(
  () => permissionsCall.data ?? NO_PROFILE_PERMISSIONS
)

/**
 * Whether the answer is in — settled or refused, not merely arrived. A call that
 * fails never sets `data`, so gating a skeleton on that leaves it up for a reply
 * that is never coming; `profilePermissionsError` is what to say instead.
 */
export const profilePermissionsLoaded = computed(
  () => permissionsCall.isFinished
)

export const profilePermissionsError = computed(
  () => permissionsCall.error ?? null
)

export function reloadProfilePermissions() {
  return permissionsCall.reload()
}

/**
 * The session user's own record, read through the ordinary document API.
 *
 * Deliberately not a whitelisted endpoint of this app's. A method that resolved
 * the record server-side would be a method deciding for itself whether to hand
 * it over, and the one that used to do this answered to no permission at all --
 * so an administrator who gated the Employee role still had employees reading
 * their own record. A list query runs the whole permission stack instead: role
 * permissions, User Permissions and the app's own gate. A user the site
 * withholds the record from gets an empty list, and the page says so.
 *
 * The filter is the same shape the server's policy describes (`owner_field`,
 * `record_filters`), and it is here to find the right row -- not to keep anyone
 * out of the wrong one. That is the permission stack's job, which is the point.
 */
const profileCall = useCall<
  MyProfile[],
  { filters: string; fields: string; limit: string }
>({
  // Frappe's own document API, not a method of this app's. Everything about who
  // may see what is settled by the framework on the way in.
  url: `/api/v2/document/${RECORD}`,
  params: () => ({
    filters: JSON.stringify({
      [profileCan.value.owner_field ?? 'user_id']: user.value.name,
      ...profileCan.value.record_filters,
    }),
    fields: JSON.stringify(profileCan.value.display),
    limit: '1',
  }),
  // Nothing to ask for until the policy has arrived with the fields to ask for.
  immediate: false,
})

// The policy answers first; the record is fetched once it has. One extra round
// trip, in exchange for the field list staying the server's.
watch(
  () => profileCan.value.display.length,
  (ready) => {
    if (ready) profileCall.reload()
  },
  { immediate: true }
)

/** The session user's own record — `null` when they have none, or when the
 *  site does not let them read it. */
export const myProfile = computed(() => profileCall.data?.[0] ?? null)

/** Settled only once the policy is in *and* the record call has finished, so
 *  the page does not flash "no record" while the fields are still on their way. */
export const myProfileLoaded = computed(
  () => profilePermissionsLoaded.value && profileCall.isFinished
)
export const myProfileError = computed(() => profileCall.error ?? null)

export function reloadMyProfile() {
  return profileCall.reload()
}

/**
 * The session user's own change requests, newest first.
 *
 * No employee argument: the server resolves the Employee behind the session
 * itself, so there is no window in which this could ask for somebody else's —
 * or, before the profile had loaded, for everybody's.
 */
export function useMyProfileChanges() {
  return useCall<ProfileChangeRequest[], { doctype: string }>({
    url: '/api/v2/method/tbs_commons.self_service.api.get_my_changes',
    params: { doctype: RECORD },
  })
}

/**
 * Requests waiting on a decision, or ones already settled.
 *
 * What counts as either is the server's to say — see `get_profile_review_queue`.
 * Building the filters here instead would let "waiting" mean one thing on the
 * page and a slightly different thing in the badge counting it.
 */
export function useProfileReviewQueue(decided: MaybeRefOrGetter<boolean>) {
  // No `doctype`: the queue spans every registered record type, so a reviewer
  // sees everything waiting on them rather than one doctype's worth.
  const queue = useCall<ProfileChangeRequest[], { decided: number }>({
    url: '/api/v2/method/tbs_commons.self_service.api.get_change_queue',
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

/**
 * Raise a change request against the employee behind this session.
 *
 * Through a whitelisted method rather than the document API: which fields a
 * request may set, which employee it is for, and which fieldnames its rows may
 * name are all the server's to decide — see `request_profile_change`.
 */
export function useRequestProfileChange() {
  return useCall<{ name: string }, { doctype: string; doc: string }>({
    url: '/api/v2/method/tbs_commons.self_service.api.request_change',
    method: 'POST',
    immediate: false,
  })
}

/** The record type a request from this page is raised against. */
export const recordType = RECORD

/**
 * Settle a request, by whatever route the site has configured — a Workflow
 * transition where one is running, a status change and a submit where none is.
 * One call either way, because the two halves are one action for the reviewer.
 */
export function useProfileDecision() {
  return useCall<
    { name: string; status: string; docstatus: number },
    { name: string; decision: string; note?: string }
  >({
    url: '/api/v2/method/tbs_commons.self_service.api.decide_change',
    method: 'POST',
    immediate: false,
  })
}

export interface ProfileWorkflow {
  name: string
  workflow_state_field: string
  states: { state: string; doc_status: number; style: string | null }[]
  transitions: { state: string; action: string; next_state: string }[]
}

const workflowCall = useCall<ProfileWorkflow | null>({
  url: '/api/v2/method/tbs_commons.self_service.api.get_change_workflow',
})

/** The active Workflow, if the site runs one. The pages need no knowledge of it
 *  — every row already carries its own label, style and permitted actions — but
 *  reloading it keeps those answers fresh after a transition. */
export const profileWorkflow = computed(() => workflowCall.data ?? null)

export function reloadProfileWorkflow() {
  return workflowCall.reload()
}

/**
 * How a request reads to a person.
 *
 * Both halves arrive: the server settles the label, because `status` alone is
 * not the answer, and the style, because a site running a Workflow styles its
 * own states. All that is left here is the mapping from that style to a badge.
 */
export function profileStatus(row: {
  status_label: string
  status_style: string | null
}): { label: string; theme: BadgeTheme } {
  return { label: row.status_label, theme: styleTheme(row.status_style) }
}

/**
 * Wording, and only wording.
 *
 * The keys cover both routes the server can take: a Workflow sends its action
 * names (`Approve`, `Withdraw`), and a site running none sends the status the
 * request would land in (`Approved`, `Withdrawn`). An outcome neither list
 * knows keeps the server's name for it, which is what a site that added one
 * would want it called.
 */
const DECISION_LABELS: Record<string, string> = {
  Approve: 'Apply',
  Approved: 'Apply',
  Reject: 'Decline',
  Rejected: 'Decline',
  Withdraw: 'Withdraw',
  Withdrawn: 'Withdraw',
  Reverse: 'Reverse',
  Reversed: 'Reverse',
}

/** The buttons for one row: the outcomes the server said this row accepts. */
export function decisionButtons(
  offered: string[] | undefined,
  vocabulary: Decision[]
): DecisionButton[] {
  return buildDecisionButtons(offered, vocabulary, DECISION_LABELS)
}

/** A stored field value as a person reads it. Frappe's empty is `null` or `''`;
 *  both mean the same thing on screen, and it is not "null". */
export function displayValue(value: unknown): string {
  const text = value == null ? '' : String(value)
  return text.trim() || '—'
}
