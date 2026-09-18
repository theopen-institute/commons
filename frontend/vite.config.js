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
    },
  },
  server: {
    fs: {
      // That alias points outside this Vite root, so the dev server has to be
      // told it may serve it. The production build inlines the module and never
      // consults this.
      allow: ['..'],
    },
  },
})
