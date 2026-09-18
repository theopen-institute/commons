<template>
	<div class="overflow-hidden rounded-4 border border-outline-gray-1">
		<table class="w-full text-left">
			<thead class="bg-surface-gray-2">
				<tr class="text-p-sm text-ink-gray-6">
					<th class="px-3 py-2 font-normal">Item</th>
					<th class="px-3 py-2 text-right font-normal">Qty</th>
					<th class="px-3 py-2 text-right font-normal">Estimate</th>
				</tr>
			</thead>
			<tbody>
				<tr
					v-for="line in lines"
					:key="line.name"
					class="border-t border-outline-gray-1 align-top"
				>
					<td class="px-3 py-2">
						<div class="text-base text-ink-gray-8">
							{{ line.item_name || line.item_code || 'Unnamed item' }}
						</div>
						<!-- A dash indicates that a SKU has not yet been identified. -->
						<div class="mt-0.5 text-p-sm text-ink-gray-5">
							<span v-if="line.item_code">{{ line.item_code }}</span>
							<span v-else>-</span>
						</div>
						<!-- `rel` because the link is whatever a requester pasted, and it
                 opens outside the site. -->
						<a
							v-if="line.reference_url"
							:href="line.reference_url"
							target="_blank"
							rel="noopener noreferrer nofollow"
							class="mt-0.5 inline-flex items-center gap-1 text-p-sm text-ink-blue-3 hover:underline"
						>
							{{ linkLabel(line.reference_url) }} ↗
						</a>
					</td>
					<td class="whitespace-nowrap px-3 py-2 text-right text-base text-ink-gray-7">
						{{ line.qty }} {{ line.uom }}
						<!-- Counted from the Material Requests themselves each time this
                 loads, so it keeps up with what purchasing has actually sent. -->
						<div v-if="line.committed_qty" class="text-p-sm text-ink-gray-5">
							{{ line.committed_qty }} committed<template
								v-if="line.uncommitted_qty"
							>
								· {{ line.uncommitted_qty }} to go</template
							>
						</div>
					</td>
					<td class="whitespace-nowrap px-3 py-2 text-right text-base text-ink-gray-7">
						{{
							line.estimated_cost
								? formatCurrency(line.estimated_cost, currency)
								: '—'
						}}
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup lang="ts">
import { formatCurrency } from '@/data/format'
import type { ProcurementRequestItemRow } from '@/data/requests/procurement'

/** The host, so an approver sees where a line's link goes before clicking it.
 *  Falls back to the raw string for anything `URL` cannot parse. */
function linkLabel(url: string): string {
	try {
		return new URL(url).hostname.replace(/^www\./, '')
	} catch {
		return url
	}
}

defineProps<{
	lines: ProcurementRequestItemRow[]
	/** From the request, not the session: amounts read in the document's currency. */
	currency?: string | null
}>()
</script>
