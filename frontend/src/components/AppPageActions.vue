<template>
	<!-- One group, so the header keeps them together on the right rather than
       spreading them across its width. -->
	<div v-if="actions.length" class="flex items-center gap-1">
		<Button
			v-for="action in primary"
			:key="action.label"
			variant="ghost"
			:icon-left="action.icon"
			:label="action.label"
			:loading="action.loading"
			@click="run(action)"
		/>
		<!-- The occasional actions, out of the way of the everyday ones. -->
		<Dropdown v-if="menu.length" :options="menu" placement="right">
			<Button variant="ghost" icon="lucide-ellipsis" aria-label="More actions" />
		</Dropdown>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, Dropdown } from 'frappe-ui'
import type { PageAction } from '@/islands/contract'

/**
 * The actions a screen reports, drawn in the SPA's page header: the primary
 * ones as buttons, the rest behind "…". The desk draws the same list as its
 * page menu. See `islands/contract.ts`.
 */

const props = defineProps<{ actions: PageAction[] }>()

const primary = computed(() => props.actions.filter((action) => action.primary))

const menu = computed(() =>
	props.actions
		.filter((action) => !action.primary)
		.map((action) => ({ label: action.label, icon: action.icon, onClick: () => run(action) }))
)

function run(action: PageAction) {
	if (action.href) window.open(action.href, '_blank', 'noopener')
	else action.onClick?.()
}
</script>
