<template>
	<!-- Deliberately bare: this is a redirect with a heartbeat, not a page. -->
	<div class="flex h-full items-center justify-center">
		<div v-if="!shellResolved" class="flex items-center gap-2 text-ink-gray-5">
			<Spinner class="size-4" />
			<span class="text-p-base">Loading…</span>
		</div>
		<div v-else class="max-w-md px-5 text-center">
			<span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
			<p class="mt-2 text-base-medium text-ink-gray-7">Nothing to show you</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				No workspace here has a page your account can open. Ask an HR Manager or a System Manager
				for access.
			</p>
		</div>
	</div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { Spinner } from 'frappe-ui'
import { landingRoute, shellResolved } from '@/data/shell'

const router = useRouter()

// The apps-screen tile lands here rather than on a page, because which page
// this user can open is a permission call away -- so a component redirects, not
// a route. Where it goes is the first row of the first workspace they have; see
// `landingRoute`.
watch(
	landingRoute,
	(destination) => {
		if (destination) router.replace(destination)
	},
	{ immediate: true }
)
</script>
