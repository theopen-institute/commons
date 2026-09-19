<template>
	<!-- One sidebar row, whichever kind of thing it opens. Grouped rows and rows
       that stand on their own are the same row in different company, and the
       badge belongs to the row rather than to the group, so this is the one
       place any of it is written down. -->
	<SidebarItem
		:label="entry.label"
		:icon="entry.icon"
		:to="entry.to"
		:active="isCurrentEntry(entry, route)"
	>
		<!-- An approver should see the number without opening anything. The same
         badge appears again on the tab that acts on it; see
         `data/requests/sections.ts`, which both read. -->
		<template v-if="entry.section?.canApprove.value && entry.section.pending.value" #suffix>
			<Badge theme="amber" variant="subtle">
				{{ entry.section.pending.value }}{{ entry.section.atCeiling.value ? '+' : '' }}
			</Badge>
		</template>
	</SidebarItem>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Badge, SidebarItem } from 'frappe-ui'
import { isCurrentEntry, type NavEntry } from '@/data/shell'

defineProps<{ entry: NavEntry }>()

const route = useRoute()
</script>
