import { defineComponent, h, type Component } from 'vue'
import { FrappeUIProvider } from 'frappe-ui'
import { mountVueIsland, type IslandContext } from '@framework/ui/island'

/**
 * An island entry's `mount` export, for one of this app's page-sized screens.
 *
 *     export const mount = pageIsland(BankReconciliationScreen)
 *
 * The same entry serves every desk host there will be: `commons.pseudo_islands`
 * on Frappe v16, and the "Frappe UI" Page type on v17 (frappe develop's
 * `ui/island/decisions/0012-a-desk-page-can-be-an-island.md`). None of this
 * file is a v16 shim; it stays when that module goes.
 *
 * It adds three things to the screen, none of which the SPA needs, because
 * `App.vue` and the www page already do them there:
 *
 * - `FrappeUIProvider`, for toasts and the imperative dialogs. Inside a shadow
 *   root it is the island's own; nothing reaches it from the page.
 * - A frame that scrolls. The desk gives a page island a bounded box
 *   (`island_page.scss`), and the island scrolls its own body in it.
 * - The CSRF token. frappe-ui reads `window.csrf_token`, which the www page
 *   sets and the desk does not: the desk keeps it on `frappe.csrf_token`, and
 *   renews it there. Without this every write from an island is refused.
 */
export function pageIsland(screen: Component) {
  const Frame = defineComponent({
    name: 'CommonsIslandFrame',
    // Everything the host passes is the screen's: its props and its listeners.
    inheritAttrs: false,
    setup(_, { attrs }) {
      return () =>
        h(FrappeUIProvider, null, {
          default: () => h('div', { class: 'h-full overflow-y-auto' }, [h(screen, attrs)]),
        })
    },
  })

  return (el: HTMLElement, context: IslandContext) => {
    bridgeCsrfToken()
    return mountVueIsland(el, { ...context, component: Frame })
  }
}

function bridgeCsrfToken() {
  const page = window as Window & { frappe?: { csrf_token?: string } }
  if (page.csrf_token && page.csrf_token !== '{{ csrf_token }}') return
  if (!page.frappe?.csrf_token) return
  // A getter, so a renewed token reaches the next request too.
  Object.defineProperty(window, 'csrf_token', {
    configurable: true,
    get: () => page.frappe?.csrf_token,
  })
}
