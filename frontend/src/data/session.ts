import { computed } from 'vue'
import { useCall } from 'frappe-ui'

export interface UserInfo {
  name: string
  full_name: string
  user_image: string | null
}

export interface EmployeePermissions {
  read: boolean
  write: boolean
  create: boolean
  delete: boolean
}

declare global {
  interface Window {
    user?: string
    user_info?: UserInfo
    csrf_token?: string
    site_name?: string
  }
}

// A production build has the www page's boot data on `window` already. The
// Vite dev server serves index.html without the Jinja pass, so there we ask.
const bootUser = window.user_info

const sessionCall = useCall<UserInfo>({
  url: '/api/v2/method/tbsapp.api.get_session_user',
  immediate: !bootUser,
})

export const user = computed<UserInfo>(
  () =>
    bootUser ??
    sessionCall.data ?? { name: 'Guest', full_name: 'Guest', user_image: null },
)

// Deliberately uncached: a persisted cache is keyed by the browser, not the
// user, so the next person to log in on this machine would get a stale-first
// render of someone else's permissions — a create button that flashes up and
// then fails. The request is one small call at boot.
const permissionsCall = useCall<EmployeePermissions>({
  url: '/api/v2/method/tbsapp.api.get_employee_permissions',
})

const NO_PERMISSIONS: EmployeePermissions = {
  read: false,
  write: false,
  create: false,
  delete: false,
}

/**
 * What the session user may do with Employee records.
 *
 * Denies everything until the answer arrives: a button that appears and then
 * vanishes is worse than one that appears a beat late, and the server rechecks
 * every write regardless — this only decides what the UI offers.
 */
export const can = computed<EmployeePermissions>(
  () => permissionsCall.data ?? NO_PERMISSIONS,
)

export const permissionsLoaded = computed(() => permissionsCall.data != null)

export function reloadPermissions() {
  return permissionsCall.reload()
}

const logoutCall = useCall({
  url: '/api/v2/method/logout',
  method: 'POST',
  immediate: false,
})

/** Ends the session, then leaves for the login page. */
export async function logout() {
  await logoutCall.submit()
  window.location.href = '/login'
}
