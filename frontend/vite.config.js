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
    },
  },
})
