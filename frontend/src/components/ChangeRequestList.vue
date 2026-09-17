<template>
	<section>
		<div class="flex flex-wrap items-center justify-between gap-3">
			<h2 class="text-lg font-semibold text-ink-gray-9">
				{{ settled ? 'Change Request History' : 'Pending Change Requests' }}
			</h2>
			<div class="flex items-center gap-2">
				<TabButtons
					v-model="tab"
					:options="[
						{ label: 'Pending', value: 'pending' },
						{ label: 'History', value: 'history' },
					]"
				/>
				<Button
					variant="ghost"
					icon-left="lucide-refresh-cw"
					label="Refresh"
					:loading="loading"
					@click="emit('refresh')"
				/>
			</div>
		</div>

		<div v-if="loading" class="mt-3 space-y-2">
			<Skeleton v-for="n in 2" :key="n" class="h-24 w-full rounded-4" />
		</div>

		<div
			v-else-if="!requests.length"
			class="mt-3 rounded-4 border border-dashed border-outline-gray-2 px-4 py-10 text-center"
		>
			<p class="text-base-medium text-ink-gray-7">
				{{ settled ? 'Nothing settled yet' : 'Nothing waiting on a review' }}
			</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				{{
					settled
						? 'Requests that have been approved, turned down or withdrawn show up here, along with whatever the reviewer said about them.'
						: 'What you have sent and nobody has decided yet shows up here. Once a request is settled it moves to History.'
				}}
			</p>
		</div>

		<ul v-else class="mt-3 space-y-3">
			<li
				v-for="row in requests"
				:key="row.name"
				class="rounded-4 border border-outline-gray-1 p-4"
			>
				<div class="flex flex-wrap items-start justify-between gap-3">
					<div class="min-w-0">
						<div class="text-base-medium text-ink-gray-8">
							{{ summary(row) }}
						</div>
						<div class="mt-0.5 text-p-sm text-ink-gray-5">
							{{ row.reference_title }} · sent {{ formatDate(row.posting_date) }}
						</div>
					</div>
					<Badge :theme="requestStatus(row).theme" variant="subtle">
						{{ requestStatus(row).label }}
					</Badge>
				</div>

				<ChangeDiff v-if="row.changes.length" :changes="row.changes" class="mt-3" />

				<p v-if="row.reason" class="mt-3 text-p-sm text-ink-gray-6">{{ row.reason }}</p>

				<!-- Why it went the way it did. Worth more than the badge when the
				     answer was no. -->
				<p
					v-if="row.review_note"
					class="mt-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
				>
					<span class="text-ink-gray-5">Reviewer:</span> {{ row.review_note }}
				</p>

				<!-- The requester's own way out of something they have thought better
				     of. Which outcomes they may apply is the server's answer per row,
				     so a site whose workflow offers none simply gets no buttons. -->
				<div v-if="row.can_decide" class="mt-4 flex items-center gap-2">
					<Button
						v-for="button in decisionButtons(row.actions, decisions)"
						:key="button.decision"
						variant="subtle"
						:theme="button.theme"
						:label="button.label"
						:icon-left="button.icon"
						:loading="working === `${row.name}:${button.decision}`"
						:disabled="Boolean(working)"
						@click="withdraw(row, button)"
					/>
				</div>
			</li>
		</ul>
	</section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Badge, Button, Skeleton, TabButtons, dialog, toast } from 'frappe-ui'
import ChangeDiff from './ChangeDiff.vue'
import {
	decisionButtons,
	requestStatus,
	useDecision,
	type ChangeRequest,
	type Decision,
	type DecisionButton,
} from '@/data/selfService'
import { formatDate, pluralise } from '@/data/format'

defineProps<{
	requests: ChangeRequest[]
	loading?: boolean
	/** The outcomes the server will accept, in the order to offer them. */
	decisions: Decision[]
}>()

/** Which list is on screen. The page owns the fetch; this owns the switch. */
const tab = defineModel<'pending' | 'history'>('tab', { required: true })

const settled = computed(() => tab.value === 'history')

const emit = defineEmits<{ refresh: [] }>()

const decision = useDecision()
// Keyed by request and outcome so only the button pressed spins.
const working = ref('')

// What the request asked for, in its own terms. A deletion carries no rows, so
// counting changes would describe it as nothing at all.
function summary(row: ChangeRequest): string {
	if (row.request_type === 'New') return 'New record'
	if (row.request_type === 'Delete') return 'Removal'
	return pluralise(row.changes.length, 'change')
}

function withdraw(row: ChangeRequest, button: DecisionButton) {
	dialog.danger({
		title: `${button.label} request`,
		message: `${button.label} this request? It stops being reviewed, and nothing about your records changes.`,
		confirmLabel: button.label,
		onConfirm: async () => {
			working.value = `${row.name}:${button.decision}`
			try {
				const result = await decision.submit({
					name: row.name,
					decision: button.decision,
				})
				// Throwing keeps the dialog open and renders the reason inline.
				if (!result) throw decision.error ?? new Error('Could not withdraw the request')
				toast.success('Request withdrawn')
				emit('refresh')
			} finally {
				working.value = ''
			}
		},
	})
}
</script>
