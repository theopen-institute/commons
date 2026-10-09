import { defineConfig } from 'vitest/config'
import path from 'path'

/**
 * Its own config rather than a `test` block in `vite.config.js`.
 *
 * That file's first plugin is `frappe-ui/vite`, which looks for the bench when
 * the config loads (its proxy reads `common_site_config.json`, its build finds
 * the app's output directory). A unit test run has no business touching the
 * bench, and on a checkout without one it would be the thing that failed rather
 * than the tests.
 *
 * What is tested here is deliberately narrow: the modules under `src/data` that
 * are pure — arithmetic and shaping, with nothing fetched, each beside its
 * `*.test.ts`. The attendance register's were Python, pinned by a test suite
 * there; see `src/data/attendanceRegister.ts` for why they moved.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      // The Bikram Sambat tables, which `captureRules.ts` converts scanned
      // dates with. The same alias `vite.config.js` gives the app.
      '@sambat': path.resolve(__dirname, '../commons/sambat/js'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
