<template>
	<FrappeUIProvider>
		<DesktopShell>
			<template #sidebar>
				<AppSidebar />
				<!-- The desk's overlay, to the numbers: it starts where the drawer
             ends rather than lying under it, which is why it can sit a layer
             above (`z-index: 1021` over the drawer's 1020) and still leave the
             panel clickable. Tapping it closes, the desk's only way back out
             on a touch screen. -->
				<div
					v-if="isMobile && sidebarOpen"
					class="app-overlay fixed inset-y-0 z-[1021]"
					@click="closeSidebar"
				/>
			</template>
			<router-view />
		</DesktopShell>
	</FrappeUIProvider>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { onKeyStroke } from '@vueuse/core'
import { DesktopShell, FrappeUIProvider } from 'frappe-ui'
import AppSidebar from '@/components/AppSidebar.vue'
import { closeSidebar, isMobile, sidebarOpen } from '@/data/sidebar'
import { title } from '@/data/shell'

const route = useRoute()

// The browser tab, which said `Commons` from `index.html` whatever the site
// called itself. Watched rather than set once: in a production build the name
// is on `window` before this runs, but the dev server has to ask for it.
watch(title, (name) => (document.title = name), { immediate: true })

// Two ways out beyond the overlay. The desk leaves the drawer standing over
// the page it just navigated to, which on a phone hides the thing you asked
// for; a tapped row has done its job, so it closes.
watch(() => route.fullPath, closeSidebar)
onKeyStroke('Escape', () => closeSidebar())
</script>

<style scoped>
/*
  frappe/public/scss/desk/sidebar.scss, the mobile `.overlay`. The width is
  what is left of the viewport beside the drawer, and the grey is the desk's
  own -- not a themed token, in either app.
*/
.app-overlay {
	left: var(--sidebar-width);
	width: calc(100vw - var(--sidebar-width));
	background-color: rgba(128, 128, 128, 0.5);
}
</style>
