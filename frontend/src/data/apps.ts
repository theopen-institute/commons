import { computed, type ComputedRef } from 'vue'
import { can, permissionsLoaded } from './session'
import { leaveCan, leavePermissionsLoaded } from './leave'
import { procurementCan, procurementPermissionsLoaded } from './procurement'

/**
 * The app registry.
 *
 * `hooks.py` puts one tile on the desk apps screen per entry here, and this is
 * the frontend half of the same split: a route belongs to exactly one app
 * (`meta.app`), and the sidebar shows only that app's navigation. The two
 * halves have to agree on the keys and the landing routes.
 */

/**
 * What the three apps are sections of.
 *
 * The desk sidebar names a workspace over the app it belongs to -- "Budget"
 * over "ERPNext" -- and the header here does the same with `title` over this.
 * The desk tiles carry the long form ("TBS Procurement"), because on the apps
 * screen there is nothing above them to say whose they are.
 */
export const SUITE_TITLE = 'TBS Commons'

export type AppKey = 'employees' | 'leave' | 'procurement'

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
  employees: {
    key: 'employees',
    title: 'Employees',
    logo: '/assets/tbsapp/images/tbsapp-employees-logo.svg',
    home: '/employees',
    available: computed(() => can.value.read),
    resolved: computed(() => permissionsLoaded.value),
  },
  leave: {
    key: 'leave',
    title: 'Leave',
    logo: '/assets/tbsapp/images/tbsapp-leave-logo.svg',
    home: '/leave',
    available: computed(() => leaveCan.value.read),
    resolved: computed(() => leavePermissionsLoaded.value),
  },
  procurement: {
    key: 'procurement',
    title: 'Procurement',
    logo: '/assets/tbsapp/images/tbsapp-procurement-logo.svg',
    home: '/procurement',
    available: computed(() => procurementCan.value.read),
    resolved: computed(() => procurementPermissionsLoaded.value),
  },
}

export const appList = [apps.employees, apps.leave, apps.procurement]

/** Apps this user can actually open — what the switcher offers. */
export const availableApps = computed(() =>
  appList.filter((app) => app.available.value),
)

export const appsResolved = computed(() =>
  appList.every((app) => app.resolved.value),
)
