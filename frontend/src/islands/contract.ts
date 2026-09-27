/**
 * What a page-sized screen of this app reports to whatever hosts it, and what
 * it is given.
 *
 * This is frappe develop's page-island contract (its
 * `ui/island/decisions/0010-a-page-island-reports-title-and-actions.md`),
 * written down on this side because a screen here has three hosts: the SPA's
 * own page, a desk Page through `commons.pseudo_islands` on Frappe v16, and
 * the "Frappe UI" Page type on v17. A screen draws no header. It emits `title`
 * and `actions`, and each host sets its own chrome from them. The desk puts
 * the title in the breadcrumb and the actions in the page's menu; the SPA puts
 * both in `AppPageHeader`.
 */

/**
 * One row of a page's actions. `onClick` runs in the screen; `href` is a URL
 * out of the host app, which the desk opens in a new tab.
 *
 * `primary` and `loading` are this app's, not the contract's: the SPA's header
 * draws a primary action as a button beside the menu, with its spinner, and a
 * desk host, which knows neither field, lists it in the menu like the rest.
 */
export type PageAction = {
  label: string
  icon?: string
  primary?: boolean
  loading?: boolean
} & ({ onClick: () => void; href?: never } | { href: string; onClick?: never })

/** The query string below a page, one string per key. */
export type ScreenQuery = Record<string, string>
