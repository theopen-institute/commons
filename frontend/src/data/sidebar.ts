import { breakpointsTailwind, useBreakpoints } from '@vueuse/core'
import { ref, watch } from 'vue'

/**
 * The sidebar's mobile state.
 *
 * Module state rather than provide/inject because the two halves are not
 * ancestor and descendant: the drawer is rendered by App.vue, and the
 * hamburger that opens it by whichever page's header is on screen.
 */

/**
 * The desk's own dividing line. `frappe.is_mobile()` is `window.innerWidth <
 * 768` (frappe/public/js/frappe/utils/common.js), and that is the width at
 * which its sidebar stops being a column in the layout and becomes a drawer
 * over it -- not a narrower column. Tailwind's `md` is the same 768px.
 */
const breakpoints = useBreakpoints(breakpointsTailwind)
export const isMobile = breakpoints.smaller('md')

/** Whether the drawer is open. Only meaningful while `isMobile`. */
export const sidebarOpen = ref(false)

export function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

export function closeSidebar() {
  sidebarOpen.value = false
}

// A drawer left open across the breakpoint would come back open the next time
// the window narrows, over a page the user has since navigated away from.
watch(isMobile, (mobile) => {
  if (!mobile) closeSidebar()
})
