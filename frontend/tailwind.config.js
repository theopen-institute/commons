import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'

/** @type {import('tailwindcss').Config} */
export default {
  presets: [frappeUIPreset],
  // Tailwind v3 does not merge `content` from a preset, so frappe-ui's own
  // source globs have to be listed here or half the espresso utilities the
  // components emit never get compiled.
  // `icons.py` is source as far as the build is concerned: the sidebar's
  // record rows wear an icon class that is configuration, stored per record and
  // sent down by the API, so the only literal any scanner can find is the list
  // of allowed names in that module. Without it Tailwind emits no rule for
  // `lucide-id-card` or `lucide-landmark` and both profile rows draw blank.
  content: [
    ...frappeUIContent,
    './index.html',
    './src/**/*.{vue,js,ts}',
    '../commons/self_service/icons.py',
  ],
}
