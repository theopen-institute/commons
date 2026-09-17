<template>
	<!-- Deliberately bare: this is a redirect with a heartbeat, not a page. -->
	<div class="flex h-full items-center justify-center">
		<div v-if="!navLoaded" class="flex items-center gap-2 text-ink-gray-5">
			<Spinner class="size-4" />
			<span class="text-p-base">Loading…</span>
		</div>
		<div v-else class="max-w-md px-5 text-center">
			<span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
			<p class="mt-2 text-base-medium text-ink-gray-7">Nothing to show you</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				Your account can't open any of your own records. Ask a System Manager for access.
			</p>
		</div>
	</div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { Spinner } from 'frappe-ui'
import { navLoaded, navRecords } from '@/data/selfService'

/**
 * Where `/profile` lands.
 *
 * Which page opens depends on what this user may read, and that is a permission
 * answer away -- so a component redirects rather than a route. The first row the
 * navigation offers wins, and the navigation is ordered by configuration.
 */
const router = useRouter()

watch(
	[navLoaded, navRecords],
	() => {
		const first = navRecords.value.find((row) => row.can_read) ?? navRecords.value[0]
		if (first) router.replace(`/profile/${first.slug}`)
	},
	{ immediate: true }
)
</script>
