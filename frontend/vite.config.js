import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import frappeui from 'frappe-ui/vite'

export default defineConfig({
  plugins: [
    frappeui({
      // Drives the dev-server banner and the built page's destination:
      // ../commons/www/commons.html, which hooks.py routes /commons/* to.
      frontendRoute: '/commons',
      frappeTypes: {
        // Employee lives in erpnext; the generator reads the doctype JSON out
        // of the bench and writes src/types/doctypes.ts on dev start.
        input: {
          erpnext: ['employee'],
        },
      },
    }),
    vue(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      // The Bikram Sambat conversions and their calendar table, shared verbatim
      // with the desk. They sit under `commons/public/js/` because that is the
      // only tree esbuild globs for the desk bundle, but the two files behind
      // this alias are plain ES modules with no jQuery and no `frappe` — which
      // is what lets the SPA import the same calendar the desk fields use
      // instead of carrying a second copy of a 130-year almanac table.
      '@bikram': path.resolve(__dirname, '../commons/public/js/bikram_sambat'),
      // The desk's fuzzy matcher -- the thing that decides what the Awesome Bar
      // puts at the top when you type three letters. Aliased for the same
      // reason as the calendar above: it is a plain ES module with no jQuery
      // and no `frappe` in it, so the SPA can rank its results with the same
      // scorer the desk ranks its own with instead of carrying a second copy
      // that drifts. `apps/frappe` is a sibling of this app in every bench, and
      // frappe is a hard dependency of this one, so the path is as safe as the
      // relative import above; if it ever moves, the build says so.
      '@fuzzy-match': path.resolve(
        __dirname,
        '../../frappe/frappe/public/js/frappe/ui/toolbar/fuzzy_match.js',
      ),
    },
  },
  server: {
    fs: {
      // Those aliases point outside this Vite root, so the dev server has to
      // be told it may serve them -- this app's own tree, and the one file of
      // frappe's the search bar borrows. The production build inlines both
      // modules and never consults this.
      allow: ['..', '../../frappe'],
    },
  },
})
