import { computed, watch } from 'vue'
import { useCall } from 'frappe-ui'
import { user } from './session'
import type { Decision } from './workflowStyle'

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
  /** `link` only — the doctype to search. */
  doctype: string | null
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
  /** The page's field layout, in order: which sections, which fields, and for
   *  each the label, control, options and mandatory flag resolved from the
   *  doctype's own meta. The page draws from this and names no field of its
   *  own — see `Self Service Record`. */
  sections: RecordSection[]
  registered: string[]
  decisions: Decision[]
  page_length: number
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
export function useSelfServiceRecords<T>(doctype: string, limit = 20) {
  // Deliberately uncached, for the reason `session.ts` gives: a persisted cache
  // is keyed by the browser rather than the user, so the next person to log in
  // on this machine would get a stale-first render of someone else's answer.
  const permissionsCall = useCall<SelfServicePermissions, { doctype: string }>({
    url: '/api/v2/method/tbs_commons.self_service.api.get_change_permissions',
    params: { doctype },
  })

  const can = computed(() => permissionsCall.data ?? NO_PERMISSIONS)

  /** Settled or refused, not merely arrived: a call that fails never sets
   *  `data`, and a page gating its skeleton on that waits for ever. */
  const permissionsLoaded = computed(() => permissionsCall.isFinished)
  const permissionsError = computed(() => permissionsCall.error ?? null)

  const recordsCall = useCall<T[], { filters: string; fields: string; limit: string }>({
    // Frappe's own document API. Everything about who may see what is settled by
    // the framework on the way in.
    url: `/api/v2/document/${doctype}`,
    params: () => ({
      filters: JSON.stringify({
        [can.value.owner_field ?? 'name']: can.value.owner_value ?? user.value.name,
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
    { immediate: true },
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
        !can.value.owner_value),
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
