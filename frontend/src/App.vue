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

		<!-- The two halves of the desk's search, mounted once for the app: they
         are summoned from a keystroke anywhere, from the sidebar, and from
         each other, so they belong to the shell rather than to a page. Global
         Search is absent entirely for somebody who cannot open the desk --
         every document it finds is a desk form. See `data/search.ts`. -->
		<AppSearchDialog />
		<AppGlobalSearch v-if="canSearchDesk" />
	</FrappeUIProvider>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { onKeyStroke } from '@vueuse/core'
import { DesktopShell, FrappeUIProvider } from 'frappe-ui'
import AppGlobalSearch from '@/components/AppGlobalSearch.vue'
import AppSearchDialog from '@/components/AppSearchDialog.vue'
import AppSidebar from '@/components/AppSidebar.vue'
import { closeSidebar, isMobile, sidebarOpen } from '@/data/sidebar'
import {
	canSearchDesk,
	openGlobalSearch,
	openSearch,
	recordVisit,
	searchOpen,
} from '@/data/search'
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

// Where you have been, for the search bar's recents. By path rather than full
// path, so arriving at a page with `?new=1` on it is the same visit as
// arriving without.
watch(() => route.path, recordVisit, { immediate: true })

// The desk's two search keys, bound for the whole app. Ctrl+K toggles the bar
// -- its own footer says it closes with the key that opened it -- and Ctrl+G
// goes straight to Global Search. Each dialog stops its own copy of these from
// reaching here, so the text you have typed is what gets handed over.
onKeyStroke(['k', 'K'], (event) => {
	if (!(event.ctrlKey || event.metaKey)) return
	event.preventDefault()
	if (searchOpen.value) searchOpen.value = false
	else openSearch()
})

onKeyStroke(['g', 'G'], (event) => {
	if (!(event.ctrlKey || event.metaKey)) return
	event.preventDefault()
	openGlobalSearch()
})
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
