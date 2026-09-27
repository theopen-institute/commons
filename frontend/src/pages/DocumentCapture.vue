<template>
	<AppPageHeader>
		<div class="flex min-w-0 items-center gap-3">
			<span class="text-lg font-semibold text-ink-gray-8">{{ title }}</span>
		</div>
		<template #actions>
			<AppPageActions :actions="actions" />
		</template>
	</AppPageHeader>

	<DocumentCaptureScreen
		@title="title = $event || 'Document Capture'"
		@actions="actions = $event"
	/>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppPageActions from '@/components/AppPageActions.vue'
import AppPageHeader from '@/components/AppPageHeader.vue'
import DocumentCaptureScreen from '@/screens/DocumentCaptureScreen.vue'
import type { PageAction } from '@/islands/contract'

/**
 * `/commons/capture`: the capture screen under the SPA's header. The screen is
 * also the `commons.capture` desk island, so it reports its title and actions
 * rather than drawing a header. See `screens/DocumentCaptureScreen.vue`.
 */

const title = ref('Document Capture')
const actions = ref<PageAction[]>([])
</script>
