import { defineConfig } from 'vitest/config'
import path from 'path'

/**
 * Its own config rather than a `test` block in `vite.config.js`.
 *
 * That file's first plugin is `frappe-ui/vite`, which reads doctype JSON out of
 * the bench and writes `src/types/doctypes.ts` when the config loads. A unit
 * test run has no business touching the bench, and on a checkout without one it
 * would be the thing that failed rather than the tests.
 *
 * What is tested here is deliberately narrow: the modules under `src/data` that
 * are pure — arithmetic and shaping, with nothing fetched. Those are the parts
 * that used to be Python and were pinned by a test suite there; see
 * `src/data/attendanceRegister.ts` for why they moved.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      // The Bikram Sambat tables, which `captureRules.ts` converts scanned
      // dates with. The same alias `vite.config.js` gives the app.
      '@bikram': path.resolve(__dirname, '../commons/public/js/bikram_sambat'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
