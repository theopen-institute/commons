/**
 * Desk addresses. Every link from this app into the desk is built here, so the
 * prefix lives in one place.
 *
 * Frappe 16.50 serves the desk at `/desk`; `/app/*` is now only a server-side
 * redirect to it (frappe/hooks.py, `website_redirects`), which costs a round
 * trip and a full reload on every click.
 *
 * Nothing but Vue is imported, on purpose: the data modules that link out
 * (and their tests) can take these without pulling in the session call.
 */
import { onScopeDispose, shallowRef, watchEffect } from 'vue'

/** The desk's root: its desktop, which Frappe's own menu calls "All apps". */
export const DESK = '/desk'

/** `frappe.router.slug`: how a doctype (or page) reads in a desk URL. */
export function deskSlug(name: string): string {
  return name.toLowerCase().replace(/ /g, '-')
}

/** A desk address from a path under it: `deskUrl('todo?status=Open')`. */
export function deskUrl(path = ''): string {
  const rest = path.replace(/^\/+/, '')
  return rest ? `${DESK}/${rest}` : DESK
}

/** A doctype's list in the desk. */
export function deskListUrl(doctype: string): string {
  return deskUrl(deskSlug(doctype))
}

/** One document's form in the desk. */
export function deskFormUrl(doctype: string, name: string): string {
  return deskUrl(`${deskSlug(doctype)}/${encodeURIComponent(name)}`)
}

/* -------------------------------------------------------------------------- */
/* "Open in desk"                                                             */
/* -------------------------------------------------------------------------- */

// Where the sidebar's "Open in desk" goes is said by the page on screen, not
// by a table in the sidebar. Two ways to say it, in order of precedence:
//
// - A page whose subject is only known once it has loaded -- a self-service
//   page, whose doctype comes from its configuration and whose record from
//   the server -- calls `useDeskTarget` from its setup.
// - A page whose subject is fixed declares it on its route, as `meta.desk`
//   (see `router.ts`).
//
// Anything else opens the desk's root.

interface Claim {
  url: string | null
}

const claim = shallowRef<Claim | null>(null)

/**
 * Says where "Open in desk" should go while the calling component is mounted.
 * `target` is re-read whenever what it reads changes; returning nothing falls
 * back to the route's own target.
 *
 * Ownership is by claim rather than a shared slot: on a navigation the next
 * page sets up before the last one unmounts, and the last one's clean-up must
 * not wipe what the next one just said.
 */
export function useDeskTarget(target: () => string | null | undefined) {
  let mine: Claim | null = null
  watchEffect(() => {
    // A fresh object each time, so whatever reads `claim` notices.
    mine = { url: target() || null }
    claim.value = mine
  })
  onScopeDispose(() => {
    if (claim.value === mine) claim.value = null
  })
}

/** Where "Open in desk" goes from a route: the page's claim, else its route's
 *  `meta.desk`, else the desk's root. */
export function deskTarget(route: { meta: { desk?: string } }): string {
  return claim.value?.url ?? route.meta.desk ?? DESK
}
