import { useIntervalFn } from '@vueuse/core'

/**
 * What the two personal sidebar widgets -- Notifications and To Do -- share.
 *
 * They are the same row twice over: a count that decides whether the row is
 * drawn at all, and a panel that is only worth re-reading when somebody looks
 * at it. Everything else about them is their own.
 */

/** The desk stops counting out loud at 99, and so does the badge here. */
export const badgeLabel = (count: number) =>
  count > 99 ? '99+' : String(count)

/**
 * How often an idle sidebar re-reads its count, in milliseconds.
 *
 * The desk keeps these live over its socket.io connection; frappe-ui removed
 * its own socket helper, and standing one up is more than these two rows are
 * worth, so they poll instead. A minute is slow enough to be nearly free and
 * quick enough that a row does not sit missing for a whole working session.
 */
const POLL_INTERVAL = 60_000

/**
 * Re-read `reload` on a slow interval, but never while the tab is in the
 * background -- a browser left open on a second monitor would otherwise keep
 * asking all day for an answer nobody is reading.
 */
export function usePollWhileVisible(reload: () => unknown) {
  useIntervalFn(() => {
    if (document.visibilityState === 'visible') reload()
  }, POLL_INTERVAL)
}
