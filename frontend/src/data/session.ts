import { computed } from 'vue'
import { useCall } from 'frappe-ui'

export interface UserInfo {
  /** The Frappe user id. The email for everyone but Administrator. */
  name: string
  full_name: string
  email: string | null
  user_image: string | null
  /** Which of the desk's avatar palette entries this person gets. */
  avatar_color: string | null
  /** Whether any of this person's roles opens the desk.
   *
   *  Read by the search bar, and only there. Half of what the bar offers is the
   *  desk -- doctype lists, new documents, and the documents Global Search
   *  finds -- and every one of those opens at `/app`. For somebody who cannot
   *  go there they would all be dead ends, so the bar offers this app's own
   *  pages alone and the Global Search dialog is not mounted at all. */
  desk_access: boolean
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
  url: '/api/v2/method/commons.api.get_session_user',
  immediate: !bootUser,
})

export const user = computed<UserInfo>(
  () =>
    bootUser ??
    sessionCall.data ?? {
      name: 'Guest',
      full_name: 'Guest',
      email: null,
      user_image: null,
      avatar_color: null,
      desk_access: false,
    },
)

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
