import { computed, ref, watch } from 'vue'

/**
 * Which of `Commons Settings`' optional features this site has switched on, as
 * far as the browser needs to know. Today that is only Bikram Sambat.
 *
 * Three places can answer, and the first one present wins:
 *
 * - `frappe.boot.commons_features`, on a desk page -- the desk islands, where
 *   there is no shell and asking for one would be a request per page load.
 *   `commons.commons_core.settings.extend_bootinfo` puts it there.
 * - `window.shell.features`, the www page's boot data in a production SPA.
 * - the shell as `data/shell.ts` fetches it, on the Vite dev server, which
 *   serves `index.html` without the Jinja pass. Imported lazily so that an
 *   island never loads the shell for the sake of one flag; in the SPA the module
 *   is already loaded and the import costs nothing.
 *
 * Off until an answer says otherwise, the server's own default.
 */

interface Features {
  bikram_sambat?: boolean
}

type DeskWindow = Window & { frappe?: { boot?: { commons_features?: Features } } }

const desk = (window as DeskWindow).frappe?.boot?.commons_features
const booted = desk ?? window.shell?.features

const bikramSambat = ref(Boolean(booted?.bikram_sambat))

if (booted === undefined) {
  void import('./shell').then(({ features }) =>
    watch(features, (value) => (bikramSambat.value = Boolean(value.bikram_sambat)), {
      immediate: true,
    }),
  )
}

/** Whether this site uses the Bikram Sambat calendar alongside the Gregorian. */
export const bikramSambatEnabled = computed(() => bikramSambat.value)
