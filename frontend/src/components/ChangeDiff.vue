<template>
	<!-- The whole content of a change request is its before-and-after, so both
       the employee's own list and HR's queue render it the same way -- a
       reviewer and a requester arguing from differently-shaped summaries of
       the same rows is exactly the confusion this avoids. -->
	<ul class="space-y-1">
		<li
			v-for="change in changes"
			:key="change.fieldname"
			class="flex flex-wrap items-baseline gap-x-2 text-p-sm"
		>
			<span class="text-ink-gray-6">{{ change.label || change.fieldname }}</span>
			<span class="text-ink-gray-5 line-through">
				{{ displayValue(change.current_value) }}
			</span>
			<span class="lucide-arrow-right size-3 shrink-0 text-ink-gray-4" />
			<span class="text-base-medium text-ink-gray-8">
				{{ displayValue(change.proposed_value) }}
			</span>
		</li>
	</ul>
</template>

<script setup lang="ts">
import { displayValue, type ProfileChangeRow } from '@/data/profile'

defineProps<{ changes: ProfileChangeRow[] }>()
</script>
