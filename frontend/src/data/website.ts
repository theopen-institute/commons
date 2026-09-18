import { computed } from 'vue'
import { useCall } from 'frappe-ui'

declare global {
  interface Window {
    website_button_url?: string
  }
}

// Same split as `session.ts`: a production build has the www page's boot data on
// `window`, and the Vite dev server serves index.html without the Jinja pass, so
// there we ask.
const bootTarget = window.website_button_url

const targetCall = useCall<string>({
  url: '/api/v2/method/tbs_commons.commons_core.website_link.get_website_button_url',
  immediate: bootTarget === undefined,
})

/**
 * Where the sidebar's "Website" button opens: Website Settings' Website Button
 * Target, or the site root when that is blank.
 *
 * Deliberately not the home page. `/` is resolved by Frappe's `get_home_page`
 * cascade -- Role home pages, then Portal Settings, then a hook, then Website
 * Settings -- and `frappe.auth` sends a fresh login through that same function,
 * so a button pointed by moving the home page moves where everyone lands at
 * login too. This setting is read here and by the desk sidebar, and nowhere in
 * the login path. See `tbs_commons/commons_core/website_link.py`.
 */
export const websiteUrl = computed<string>(
  () => (bootTarget ?? targetCall.data ?? '').trim() || window.location.origin,
)
