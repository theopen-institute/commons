import { computed } from 'vue'
import { useCall } from 'frappe-ui'

/** One of Session Default Settings' Link fields, with this user's value. */
export interface SessionDefault {
  fieldname: string
  doctype: string
  label: string
  value: string | null
}

/** A Navbar Settings row the SPA can follow: always a URL. */
export interface NavbarLink {
  label: string
  url: string
  new_tab: boolean
}

export interface UserMenuData {
  session_defaults: SessionDefault[]
  /** Whether the Session Defaults dialog links on to Session Default Settings. */
  session_defaults_settings: boolean
  help: NavbarLink[]
  settings: NavbarLink[]
}

declare global {
  interface Window {
    user_menu?: UserMenuData
  }
}

// Same split as `session.ts`: a production build has the www page's boot data on
// `window`, and the Vite dev server serves index.html without the Jinja pass, so
// there we ask.
const bootMenu = window.user_menu

const menuCall = useCall<UserMenuData>({
  url: '/api/v2/method/commons.commons_core.user_menu.get_user_menu',
  immediate: bootMenu === undefined,
})

/**
 * The site-configured parts of the sidebar's user menu: Session Defaults, and
 * the Navbar Settings rows under Help and after it. Only the rows that are
 * URLs -- the server leaves out the ones that are desk JavaScript. See
 * `commons/commons_core/user_menu.py`.
 */
export const userMenu = computed<UserMenuData>(
  () =>
    bootMenu ??
    menuCall.data ?? {
      session_defaults: [],
      session_defaults_settings: false,
      help: [],
      settings: [],
    },
)

const saveCall = useCall<string | null, { default_values: string }>({
  url: '/api/v2/method/frappe.core.doctype.session_default_settings.session_default_settings.set_session_default_values',
  method: 'POST',
  immediate: false,
})

/**
 * Save Session Defaults, the desk's own way: every listed field is sent, a
 * cleared one as "" -- which is how the server is told to drop it.
 *
 * Resolves whether the server said it saved. The endpoint answers "success" or
 * nothing at all: it swallows its own exceptions.
 */
export async function saveSessionDefaults(
  values: Record<string, string | null>,
) {
  const payload = Object.fromEntries(
    userMenu.value.session_defaults.map((field) => [
      field.fieldname,
      values[field.fieldname] ?? '',
    ]),
  )
  const result = await saveCall.submit({
    default_values: JSON.stringify(payload),
  })
  return result === 'success'
}

export const savingSessionDefaults = computed(() => saveCall.loading)
