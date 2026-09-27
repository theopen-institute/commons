// Types for the part of `@framework/ui` this app imports. The package ships
// plain JavaScript, here and on v17 alike, so its JSDoc is restated here. The
// shapes are those of `ui/island/mount.js` and `ui/island/context.js`.

declare module '@framework/ui/island' {
  import type { App, Component } from 'vue'

  /** The ambient context a host gives every island; `useHost()` returns it. */
  export interface IslandHost {
    locale?: string
    timezone?: string | null
    user?: string | null
    base_url?: string
    /** Routes the host to one of its own pages. */
    navigate?: (route: string) => void
    /** The host's live theme, added by `mountVueIsland`. */
    theme?: string
  }

  /** What the host loop hands an island's `mount(el, context)`. */
  export interface IslandContext {
    host?: IslandHost
    props?: Record<string, unknown>
    styles?: string[]
  }

  export interface IslandHandle {
    app: App
    shadow_root: ShadowRoot
    update(props: Record<string, unknown>): void
    unmount(): void
  }

  export function mountVueIsland(
    el: HTMLElement,
    options: IslandContext & {
      component: Component
      configure?: (app: App) => void
      routes?: unknown[]
    },
  ): Promise<IslandHandle>

  export const hostKey: symbol
  export function useHost(): IslandHost
}
