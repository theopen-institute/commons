import { computed, type ComputedRef } from 'vue'
import { can, permissionsLoaded } from './session'
import { leaveCan, leavePermissionsLoaded } from './leave'

/**
 * The app registry.
 *
 * `hooks.py` puts one tile on the desk apps screen per entry here, and this is
 * the frontend half of the same split: a route belongs to exactly one app
 * (`meta.app`), and the sidebar shows only that app's navigation. The two
 * halves have to agree on the keys and the landing routes.
 */
export type AppKey = 'employees' | 'leave'

export interface AppDefinition {
  key: AppKey
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
    title: 'TBS Employees',
    logo: '/assets/tbsapp/images/tbsapp-employees-logo.svg',
    home: '/employees',
    available: computed(() => can.value.read),
    resolved: computed(() => permissionsLoaded.value),
  },
  leave: {
    key: 'leave',
    title: 'TBS Leave',
    logo: '/assets/tbsapp/images/tbsapp-leave-logo.svg',
    home: '/leave',
    available: computed(() => leaveCan.value.read),
    resolved: computed(() => leavePermissionsLoaded.value),
  },
}

export const appList = [apps.employees, apps.leave]

/** Apps this user can actually open — what the switcher offers. */
export const availableApps = computed(() =>
  appList.filter((app) => app.available.value),
)

export const appsResolved = computed(() =>
  appList.every((app) => app.resolved.value),
)
