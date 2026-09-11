import './index.css'

import { createApp } from 'vue'
import { useColorScheme } from 'frappe-ui'
import router from './router'
import App from './App.vue'

// The first call restores the saved light/dark preference and starts following
// the OS setting, so this is all the theme wiring the app needs.
useColorScheme()

createApp(App).use(router).mount('#app')
