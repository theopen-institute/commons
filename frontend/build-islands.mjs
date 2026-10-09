// This app's desk islands, built by frappe develop's island preset
// (`@framework/ui/vite/island`, README "Desk islands"). One build for every
// entry, so the islands share their Vue and frappe-ui chunks. Output lands in
// sites/assets/commons/dist/island/, and each entry registers
// `<name>.island.js` and `<name>.island.css` in assets.json, which is what makes
// it an island: the entry name is the island's name.
//
//     node build-islands.mjs [--production] [--watch]
//
// `yarn build` in the app root runs this after the SPA; `bench watch` does not,
// so while working on an island run `yarn dev:islands` beside it.
//
// Nothing here is a v16 shim. On v17 `@framework/ui` is frappe's own
// (`link:../../frappe/ui`) and this file stays as it is.

import { loadConfigFromFile } from 'vite'
import { buildIslands } from '@framework/ui/vite/island'

const root = import.meta.dirname

// The preset runs Vite with `configFile: false`, so the SPA's aliases (`@`,
// `@sambat`, `@fuzzy-match`) are read from its config and handed over, rather
// than written out a second time.
const spa = await loadConfigFromFile(
  { command: 'build', mode: 'production' },
  'vite.config.js',
  root
)
const aliases = {
  name: 'commons-spa-aliases',
  config: () => ({ resolve: { alias: spa?.config.resolve?.alias ?? {} } }),
}

await buildIslands({
  app: 'commons',
  root,
  entries: {
    'commons.banking': 'src/islands/banking.ts',
    'commons.capture': 'src/islands/capture.ts',
    'commons.attendance': 'src/islands/attendance.ts',
  },
  plugins: [aliases],
  production: process.argv.includes('--production'),
  watch: process.argv.includes('--watch'),
})
