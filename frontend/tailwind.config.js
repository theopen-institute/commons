import frappeUIPreset, { content as frappeUIContent } from 'frappe-ui/tailwind'

/** @type {import('tailwindcss').Config} */
export default {
  presets: [frappeUIPreset],
  // Tailwind v3 does not merge `content` from a preset, so frappe-ui's own
  // source globs have to be listed here or half the espresso utilities the
  // components emit never get compiled.
  content: [...frappeUIContent, './index.html', './src/**/*.{vue,js,ts}'],
}
