import { toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'

/**
 * The desk's notification widget, on this app's sidebar.
 *
 * The feed and its unread count come from `commons.core.notifications`, which
 * exists because the desk reads the two from different places -- an endpoint
 * for the rows, boot for the count -- and this app has no boot. Marking things
 * read is core's own, unchanged: those endpoints are already scoped to the
 * session user.
 */

export interface AppNotification {
  name: string
  /** Title or legacy subject, markup already taken off server-side. */
  text: string
  type: string | null
  document_type: string | null
  document_name: string | null
  source_doctype: string | null
  source_name: string | null
  /** An explicit destination, when the notification carries one. */
  link: string | null
  from_user: string | null
  read: boolean
  creation: string
  /** "2 hours ago", worked out server-side -- see the Python module for why. */
  when: string
}

export interface NotificationFeed {
  notifications: AppNotification[]
  /** Every unread one, not only those in `notifications`. */
  unread: number
}

export function useNotificationFeed(limit: MaybeRefOrGetter<number> = 20) {
  const feed = useCall<NotificationFeed, { limit: number }>({
    url: '/api/v2/method/commons.core.notifications.get_notification_feed',
    params: () => ({ limit: toValue(limit) }),
    immediate: false,
  })
  watch(
    () => toValue(limit),
    () => feed.reload(),
    { immediate: true },
  )
  return feed
}

export function useMarkNotificationRead() {
  return useCall<null, { docname: string }>({
    url: '/api/v2/method/frappe.desk.doctype.notification_log.notification_log.mark_as_read',
    method: 'POST',
    immediate: false,
  })
}

export function useMarkAllNotificationsRead() {
  return useCall({
    url: '/api/v2/method/frappe.desk.doctype.notification_log.notification_log.mark_all_as_read',
    method: 'POST',
    immediate: false,
  })
}

/** `frappe.router.slug`: how a doctype reads in a desk URL. */
function slug(name: string): string {
  return name.toLowerCase().replace(/ /g, '-')
}

/** `frappe.scrub`: how the timeline spells an entry's id. */
function scrub(name: string): string {
  return name.toLowerCase().replace(/ /g, '_').replace(/-/g, '_')
}

/**
 * Where a notification leads, by the desk widget's own rules: an explicit
 * `link` wins; otherwise the referenced document, or the Notification Log row
 * itself when it references nothing. A notification raised by one timeline
 * entry anchors to that entry, which is how the desk lands you on the comment
 * rather than the top of a long form.
 *
 * Every destination is a desk page, so the caller must not offer these to
 * somebody whose roles do not open the desk -- see `hasDeskAccess`.
 */
export function notificationDeskUrl(item: AppNotification): string {
  if (item.link) return item.link

  const doctype = item.document_type || 'Notification Log'
  const name = item.document_name || item.name
  const url = `/app/${slug(doctype)}/${encodeURIComponent(name)}`

  return item.source_doctype && item.source_name
    ? `${url}#${scrub(item.source_doctype)}-${item.source_name}`
    : url
}

/** The whole log in the desk, which is where "See all" goes. */
export const allNotificationsDeskUrl = '/app/notification-log'
