import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import {
  decisionButtons as buildDecisionButtons,
  styleTheme,
  type BadgeTheme,
  type Decision,
  type DecisionButton,
} from './workflowStyle'
import { user } from './session'

/**
 * One self-service record type, read the way every one of them is read.
 *
 * The section is generic on the server (`tbs_commons.self_service`), and this is
 * the client half of the same idea: a record type is a doctype plus a policy,
 * and everything a page needs to show one -- which fields, which rows are mine,
 * whether I may see them at all -- arrives from that policy rather than being
 * written into the page.
 *
 * Nothing here reads a record through an endpoint of this app's. The policy
 * comes from a whitelisted method because it *is* the server's answer; the
 * records come from Frappe's own document API, so role permissions, User
 * Permissions and the app's gate all apply without this file restating any of
 * them. The owner filter finds the right rows. It is not what keeps anyone out
 * of the wrong ones, and is not trusted to be.
 */

/** One field as the server says it should be drawn. */
export interface RecordField {
  fieldname: string
  label: string
  /** Control to render. `text` for anything this app has no better idea about,
   *  which reads as a plain value on a read-only page. */
  type: string
  /** `select` only. */
  options: string[]
  /** `link` only — the doctype to search. Null on a free-form field, which is
   *  drawn as a text box precisely because there is nothing to search yet. */
  doctype: string | null
  /** Whether the owner types this value rather than picking it. Set where the
   *  document a Link points at may not exist yet, or may be invisible to them —
   *  whoever reviews the request creates it. */
  free_text: boolean
  required: boolean
  description: string | null
  /** Whether the owner may propose a change to this field. */
  proposable: boolean
}

export interface RecordSection {
  title: string
  fields: RecordField[]
}

export interface SelfServicePermissions {
  /** Whether this user may use the section at all -- a permission, and what the
   *  navigation offers on. */
  read: boolean
  /** Read permission on the record doctype itself, which `read` is not -- that
   *  one is about change requests. Gates the document-API call: without it the
   *  page fires a request the framework answers with a bare 403, where the
   *  point is to explain rather than to relay a stack trace. */
  can_read_records: boolean
  /** Whether they own any record of this type that they may read. */
  has_record: boolean
  /** Why there is nothing to show, when there is nothing. `forbidden` means the
   *  records are there and the site is withholding them. */
  record_access: 'visible' | 'forbidden' | 'missing'
  request: boolean
  review: boolean
  pending_reviews: number
  /** Fieldnames the server will accept a proposal for. Empty for a record type
   *  this section only reads. */
  proposable: string[]
  /** What the page may show. The server's, so a field that has no business on a
   *  self-service page cannot appear by a page choosing for itself. */
  display: string[]
  /** How the policy finds this user's rows, and what that field should equal --
   *  their login for a policy that names its owner directly, the owning record's
   *  name for one that chains. Both the server's, so a page filtering through
   *  the document API asks the same question without knowing which shape it is. */
  owner_field: string | null
  owner_value: string | null
  record_filters: Record<string, string | number | boolean | null>
  /** Whether one record is expected or several. */
  singular: boolean
  /** Whether an owner may ask for a record of this type to be created, or one
   *  of theirs removed. Both off unless the configuration turns them on. */
  allow_new: boolean
  allow_delete: boolean
  /** How this record type introduces and excuses itself. Configuration, so a
   *  page can send somebody to payroll where a generic line would send them to
   *  the wrong place. */
  label: string | null
  slug: string | null
  read_only_notice: string | null
  empty_notice: string | null
  /** The page's field layout, in order: which sections, which fields, and for
   *  each the label, control, options and mandatory flag resolved from the
   *  doctype's own meta. The page draws from this and names no field of its
   *  own — see `Self Service Record`. */
  sections: RecordSection[]
  registered: string[]
  decisions: Decision[]
  page_length: number
}

/**
 * Whether a stored value counts as filled.
 *
 * Frappe writes an empty field as `null` from Python and `''` from a form, and
 * a page that treated those differently would show one of them as a change.
 */
export function isFilled(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

export const NO_PERMISSIONS: SelfServicePermissions = {
  read: false,
  can_read_records: false,
  has_record: false,
  record_access: 'missing',
  request: false,
  review: false,
  pending_reviews: 0,
  proposable: [],
  display: [],
  owner_field: null,
  owner_value: null,
  record_filters: {},
  singular: false,
  allow_new: false,
  allow_delete: false,
  label: null,
  slug: null,
  read_only_notice: null,
  empty_notice: null,
  sections: [],
  registered: [],
  decisions: [],
  page_length: 0,
}

/**
 * The policy for one record type, and this user's rows of it.
 *
 * Declaration order inside here is load-bearing: the watch at the end is
 * `immediate`, so it runs while this function is still executing. Everything it
 * touches is declared above it.
 */
export function useSelfServiceRecords<T>(
  doctype: MaybeRefOrGetter<string>,
  limit = 20
) {
  // A getter, not a string: a page addressed by slug does not know its record
  // type until the navigation has loaded, and creating the calls twice -- once
  // empty, once for real -- is worse than letting them wait.
  const target = computed(() => toValue(doctype))
  // Deliberately uncached, for the reason `session.ts` gives: a persisted cache
  // is keyed by the browser rather than the user, so the next person to log in
  // on this machine would get a stale-first render of someone else's answer.
  const permissionsCall = useCall<SelfServicePermissions, { doctype: string }>({
    url: '/api/v2/method/tbs_commons.self_service.api.get_change_permissions',
    params: () => ({ doctype: target.value }),
    immediate: false,
  })

  watch(
    target,
    (name) => {
      if (name) permissionsCall.reload()
    },
    { immediate: true }
  )

  const can = computed(() => permissionsCall.data ?? NO_PERMISSIONS)

  /** Settled or refused, not merely arrived: a call that fails never sets
   *  `data`, and a page gating its skeleton on that waits for ever. */
  const permissionsLoaded = computed(
    () => Boolean(target.value) && permissionsCall.isFinished
  )
  const permissionsError = computed(() => permissionsCall.error ?? null)

  const recordsCall = useCall<
    T[],
    { filters: string; fields: string; limit: string }
  >({
    // Frappe's own document API. Everything about who may see what is settled by
    // the framework on the way in.
    // A computed ref, not a string: the doctype arrives with the navigation, and
    // a URL built at call time would be `/api/v2/document/` -- which answers with
    // a 404 page that the client then tries to parse as JSON.
    url: computed(() => `/api/v2/document/${target.value}`),
    params: () => ({
      filters: JSON.stringify({
        [can.value.owner_field ?? 'name']:
          can.value.owner_value ?? user.value.name,
        ...can.value.record_filters,
      }),
      fields: JSON.stringify(can.value.display),
      limit: String(limit),
    }),
    // Nothing to ask for until the policy has arrived with the fields to ask for
    // and the value to filter on.
    immediate: false,
  })

  // The policy answers first; the records are fetched once it has. One extra
  // round trip, in exchange for the field list staying the server's.
  watch(
    () =>
      [
        can.value.can_read_records,
        can.value.display.length,
        can.value.owner_value,
      ] as const,
    ([mayRead, fields, owner]) => {
      if (mayRead && fields && owner) recordsCall.reload()
    },
    { immediate: true }
  )

  const records = computed(() => recordsCall.data ?? [])

  /** Both answers in: the page should not flash "nothing here" while the field
   *  list is still on its way. */
  const recordsLoaded = computed(
    () =>
      permissionsLoaded.value &&
      // Nothing was asked for when the read is refused or there is no owner to
      // filter on, so there is nothing to wait for either.
      (recordsCall.isFinished ||
        !can.value.can_read_records ||
        !can.value.owner_value)
  )
  const recordsError = computed(() => recordsCall.error ?? null)

  function reload() {
    permissionsCall.reload()
    recordsCall.reload()
  }

  return {
    can,
    permissionsLoaded,
    permissionsError,
    reloadPermissions: () => permissionsCall.reload(),
    records,
    recordsLoaded,
    recordsError,
    reloadRecords: () => recordsCall.reload(),
    reload,
  }
}

/** One self-service page, as the sidebar should offer it. */
export interface NavRecord {
  doctype: string
  label: string
  slug: string
  icon: string | null
  singular: boolean
  /** Read permission on the record doctype. The row is offered either way --
   *  a page that vanishes leaves someone unable to tell a missing feature from
   *  a missing permission, and the page itself says which. */
  can_read: boolean
}

const navCall = useCall<NavRecord[]>({
  url: '/api/v2/method/tbs_commons.self_service.api.get_self_service_nav',
})

/** Every self-service page, in configured order. The sidebar reads this rather
 *  than naming pages, so a new record type is a desk entry and nothing else. */
export const navRecords = computed(() => navCall.data ?? [])
export const navLoaded = computed(() => navCall.isFinished)

export function reloadNav() {
  return navCall.reload()
}

export function navBySlug(slug: string) {
  return navRecords.value.find((row) => row.slug === slug) ?? null
}

/** One field a request proposes to change. */
export interface ChangeRow {
  fieldname: string
  label: string | null
  current_value: string | null
  proposed_value: string | null
}

/** One row of a change request list. */
export interface ChangeRequest {
  name: string
  request_type: 'Change' | 'New' | 'Delete'
  reference_doctype: string
  reference_name: string | null
  reference_title: string
  requested_by: string
  reason: string | null
  review_note: string | null
  reviewed_by: string | null
  status: string
  docstatus: 0 | 1 | 2
  posting_date: string
  modified: string
  changes: ChangeRow[]
  status_label: string
  status_style: string | null
  /** Whether this request is still awaiting a decision. Server-owned:
   *  `docstatus` cannot answer it, since a declined or withdrawn request stays
   *  at 0 so it can be amended. */
  open: boolean
  can_decide?: boolean
  actions?: string[]
}

/**
 * This user's own requests about one record type.
 *
 * Open ones by default; `decided` asks for the settled ones instead. Which is
 * which is the server's to say — see `get_my_changes`, which reads the same
 * predicate the review queue and the pending badge do, so "open" cannot come to
 * mean one thing on this page and another in the count beside it.
 */
export function useMyChanges(
  doctype: MaybeRefOrGetter<string>,
  decided: MaybeRefOrGetter<boolean> = false,
  enabled: MaybeRefOrGetter<boolean> = true
) {
  const target = computed(() => toValue(doctype))
  const settled = computed(() => toValue(decided))
  // History is only worth a round trip once somebody asks to see it, so the
  // caller can keep this list dormant until then.
  const active = computed(() => toValue(enabled))
  const call = useCall<ChangeRequest[], { doctype: string; decided: number }>({
    url: '/api/v2/method/tbs_commons.self_service.api.get_my_changes',
    params: () => ({ doctype: target.value, decided: settled.value ? 1 : 0 }),
    immediate: false,
  })
  watch(
    [target, settled, active],
    ([name, , on]) => {
      if (name && on) call.reload()
    },
    { immediate: true }
  )
  return call
}

/**
 * Raise a request. Which of the three shapes it is travels in the payload --
 * see `request_change`, which settles which record it may be about.
 */
export function useRaiseRequest() {
  return useCall<{ name: string }, { doctype: string; doc: string }>({
    url: '/api/v2/method/tbs_commons.self_service.api.request_change',
    method: 'POST',
    immediate: false,
  })
}

/** Settle a request, by whatever route the site has configured. */
export function useDecision() {
  return useCall<
    { name: string; status: string; docstatus: number },
    { name: string; decision: string; note?: string }
  >({
    url: '/api/v2/method/tbs_commons.self_service.api.decide_change',
    method: 'POST',
    immediate: false,
  })
}

/**
 * How a request reads to a person. Both halves arrive: the server settles the
 * label, because `status` alone is not the answer, and the style, because a site
 * running a Workflow styles its own states.
 */
export function requestStatus(row: {
  status_label: string
  status_style: string | null
}): { label: string; theme: BadgeTheme } {
  return { label: row.status_label, theme: styleTheme(row.status_style) }
}

/** Wording, and only wording. Covers both routes the server can take: a
 *  Workflow sends action names, a site running none sends the target status. */
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

export function decisionButtons(
  offered: string[] | undefined,
  vocabulary: Decision[]
): DecisionButton[] {
  return buildDecisionButtons(offered, vocabulary, DECISION_LABELS)
}

export type { Decision, DecisionButton }

/** A stored value as a person reads it. Frappe's empty is `null` or `''`; both
 *  mean the same thing on screen, and it is not "null". */
export function displayValue(value: unknown): string {
  const text = value == null ? '' : String(value)
  return text.trim() || '—'
}
