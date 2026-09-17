import { computed, type ComputedRef } from 'vue'
import { leaveCan, leavePermissionsLoaded } from './leave'
import { expenseCan, expensePermissionsLoaded } from './expense'
import { procurementCan, procurementPermissionsLoaded } from './procurement'
import { navLoaded, navRecords } from './selfService'

/**
 * The app registry.
 *
 * `hooks.py` puts one tile on the desk apps screen per entry here, and this is
 * the frontend half of the same split: a route belongs to exactly one app
 * (`meta.app`), and the sidebar shows only that app's navigation. The two
 * halves have to agree on the keys and the landing routes.
 *
 * There is one app, `requests`, and everything in it is something a person
 * raises about themselves and waits on an approver for: their profile, their
 * bank accounts, their leave, their expenses, their purchases. Each keeps its own route and its
 * own permission check; what they share is the sidebar, where each gets a
 * labelled section.
 *
 * The registry stays a registry with one entry rather than being dissolved into
 * the router. It is what `meta.app` points at, what the header names, and what
 * `hooks.py` mirrors on the desk apps screen -- and a second app would be an
 * entry here rather than that structure being rebuilt. The `Employees`
 * directory used to be the other one.
 */

/**
 * What the apps are sections of.
 *
 * The desk sidebar names a workspace over the app it belongs to -- "Budget"
 * over "ERPNext" -- and the header here does the same with `title` over this.
 */
export const SUITE_TITLE = 'TBS Commons'

export type AppKey = 'requests'

export interface AppDefinition {
  key: AppKey
  /** The section's own name. Read under `SUITE_TITLE`, never beside it. */
  title: string
  logo: string
  /** Where the apps-screen tile lands, and where the switcher goes. */
  home: string
  /** Whether this user can use the app at all; drives the switcher. */
  available: ComputedRef<boolean>
  /** False until the permission answer is in, so nothing flashes. */
  resolved: ComputedRef<boolean>
}

export const apps: Record<AppKey, AppDefinition> = {
  requests: {
    key: 'requests',
    title: 'Requests',
    logo: '/assets/tbs_commons/images/tbs_commons-procurement-logo.svg',
    // Not a section route: either section may be the one this user can open,
    // so the tile lands on a redirect that picks. See RequestsHome.vue.
    home: '/requests',
    available: computed(
      () =>
        navRecords.value.length > 0 ||
        leaveCan.value.read ||
        expenseCan.value.read ||
        procurementCan.value.read
    ),
    resolved: computed(
      () =>
        navLoaded.value &&
        leavePermissionsLoaded.value &&
        expensePermissionsLoaded.value &&
        procurementPermissionsLoaded.value
    ),
  },
}

export const appList = [apps.requests]

/**
 * Where `/requests` and the apps-screen tile actually land, in sidebar order.
 * Null until every permission answer is in, so nothing redirects early.
 */
export const firstRequestSection = computed<string | null>(() => {
  if (!apps.requests.resolved.value) return null
  // The self-service pages first when there are any: `/profile` itself works out
  // which one this user can open, so landing there costs nothing when they can
  // open none.
  if (navRecords.value.length) return '/profile'
  if (leaveCan.value.read) return '/leave'
  if (expenseCan.value.read) return '/expenses'
  if (procurementCan.value.read) return '/procurement'
  return null
})

/** Apps this user can actually open — what the switcher offers. */
export const availableApps = computed(() =>
  appList.filter((app) => app.available.value)
)

export const appsResolved = computed(() =>
  appList.every((app) => app.resolved.value)
)
