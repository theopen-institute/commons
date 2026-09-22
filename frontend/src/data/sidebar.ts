import { breakpointsTailwind, useBreakpoints, useStorage } from '@vueuse/core'
import { computed, ref, watch } from 'vue'

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

/**
 * The sidebar's desktop state: a full column, or the desk's icon-only rail.
 *
 * Stored under the desk's own key, and in the desk's own sense of it -- the
 * desk writes `sidebar-expanded` from `expand_sidebar`
 * (frappe/public/js/frappe/ui/sidebar/sidebar.js) as a bare `true`/`false`,
 * which is what vueuse's boolean serializer reads and writes too. The two
 * panels are served from one origin (`/app` and `/commons`) and sit in the
 * same place on the screen, so a person who has narrowed one has said what
 * they want of the other. Give it a key of its own to split them again.
 */
const sidebarExpanded = useStorage('sidebar-expanded', true)

/** Whether the column is shrunk to icons. Only meaningful above `md`. */
export const sidebarCollapsed = computed({
  get: () => !sidebarExpanded.value,
  set: (collapsed) => {
    sidebarExpanded.value = !collapsed
  },
})

export function toggleSidebarCollapsed() {
  sidebarExpanded.value = !sidebarExpanded.value
}

/**
 * What the column currently measures, for the things laid out against its
 * right edge. A CSS length rather than a number so it stays the token the
 * sidebar itself is drawn from -- see `--sidebar-collapsed-width` in index.css.
 */
export const sidebarWidth = computed(() =>
  sidebarCollapsed.value ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)',
)
