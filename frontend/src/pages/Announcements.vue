<template>
	<PageHeader>
		<span class="text-lg font-semibold text-ink-gray-8">Announcements</span>
	</PageHeader>

	<div class="px-5 py-4">
		<div class="mx-auto max-w-3xl">
			<!-- Placeholder: there is nothing behind this yet, so the page shows the
           same empty state it will show once there is, rather than a notice
           about being unfinished. Nothing to gate either -- an announcement is
           for everyone who can open the app. -->
			<div class="mt-16 flex flex-col items-center gap-2 text-center">
				<span class="lucide-megaphone size-8 text-ink-gray-4" />
				<p class="text-base-medium text-ink-gray-7">No announcements</p>
				<p class="text-p-sm text-ink-gray-5">Important information will show up here.</p>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { PageHeader } from 'frappe-ui'
</script>
