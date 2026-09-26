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
   *  Read by everything in this app that offers the desk, because for somebody
   *  whose roles do not open it every one of those is a dead end: half of what
   *  the search bar offers (doctype lists, new documents, the documents Global
   *  Search finds, all of which open at `/app`), the Home crumb beside a page
   *  title, and the desk destinations in the sidebar's menu. See
   *  `hasDeskAccess`. */
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

/** Whether to offer the desk at all. See `UserInfo.desk_access` for what the
 *  flag means and who asks. */
export const hasDeskAccess = computed(() => user.value.desk_access)

const logoutCall = useCall({
  url: '/api/v2/method/logout',
  method: 'POST',
  immediate: false,
})

/**
 * Ends the session, then leaves for the login page.
 *
 * Only once the session is known to be over. `submit` resolves whether or not
 * the POST was accepted, and a refused one — an expired CSRF token, a dropped
 * connection — used to land the user on `/login` still signed in, where the
 * login page shows them straight back in. Frappe's own `/logout` page is the
 * fallback: a fresh page load, so it carries a fresh CSRF token, and it posts
 * the logout itself before sending them on. Not `/?cmd=web_logout`, the older
 * answer: that method is POST-only now and a navigation to it is refused.
 */
export async function logout() {
  await logoutCall.submit()
  window.location.href = logoutCall.error ? '/logout' : '/login'
}
