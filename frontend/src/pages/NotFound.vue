<template>
	<AppPageHeader>
		<span class="truncate text-lg font-semibold text-ink-gray-8">Not found</span>
	</AppPageHeader>

	<!-- The app's empty state, not a bare 404: the sidebar is still there, so
	     the way on is one click away, and this only has to say what happened. -->
	<div class="mx-auto mt-16 max-w-md px-5 text-center">
		<span class="lucide-search-x mx-auto size-8 text-ink-gray-4" />
		<p class="mt-2 text-base-medium text-ink-gray-7">Page not found</p>
		<p class="mt-1 text-p-sm text-ink-gray-5">
			There is no page at this address. It may have been renamed or removed, or the link may
			be mistyped.
		</p>
		<Button class="mt-4" variant="subtle" label="Go home" :route="{ path: '/' }" />
	</div>
</template>

<script setup lang="ts">
import { Button } from 'frappe-ui'
import AppPageHeader from '@/components/AppPageHeader.vue'
</script>
