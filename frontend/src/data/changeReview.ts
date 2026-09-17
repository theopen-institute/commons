import { computed, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'
import {
  NO_PERMISSIONS,
  type ChangeRequest,
  type SelfServicePermissions,
} from './selfService'

/**
 * The reviewer's half of the self-service section.
 *
 * Separate from `selfService` because it is not about a record type. A reviewer
 * has one queue spanning every registered doctype, and one badge counting it --
 * asking the permissions endpoint per record type to find that out would be
 * three calls to answer one question.
 *
 * It names a doctype anyway, because the endpoint takes one and the answer to
 * "may I review" is the same whichever is named. `Employee` is the one every
 * site has.
 */
const ANY_RECORD = 'Employee'

const permissionsCall = useCall<SelfServicePermissions, { doctype: string }>({
  url: '/api/v2/method/tbs_commons.self_service.api.get_change_permissions',
  params: { doctype: ANY_RECORD },
})

export const reviewCan = computed(() => permissionsCall.data ?? NO_PERMISSIONS)
export const reviewPermissionsLoaded = computed(
  () => permissionsCall.isFinished
)
export const reviewPermissionsError = computed(
  () => permissionsCall.error ?? null
)

export function reloadReviewPermissions() {
  return permissionsCall.reload()
}

/**
 * Requests waiting on a decision, or ones already settled.
 *
 * What counts as either is the server's to say — see `get_change_queue`.
 * Building the filters here would let "waiting" mean one thing on the page and
 * a slightly different thing in the badge counting it.
 */
export function useReviewQueue(decided: MaybeRefOrGetter<boolean>) {
  const queue = useCall<ChangeRequest[], { decided: number }>({
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

// No workflow description is fetched here, deliberately. Every row arrives
// carrying its own label, style and permitted actions, so nothing on this page
// ever read the workflow itself — the call existed only to be reloaded, and
// reloading it refreshed nothing. Reloading the queue is what moves the labels.
