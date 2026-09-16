<template>
	<AppPageHeader>
		<div class="flex items-center gap-2">
			<span class="text-lg font-semibold text-ink-gray-8">Change requests</span>
			<Badge v-if="pendingCount" theme="amber" variant="subtle">
				{{ pendingCount }}{{ pendingAtCeiling ? '+' : '' }} waiting
			</Badge>
		</div>
		<template #actions>
			<!-- Nothing to filter or refresh when the list itself is withheld. -->
			<div v-if="canReview" class="flex items-center gap-2">
				<TabButtons
					v-model="tab"
					:options="[
						{ label: 'Pending', value: 'pending' },
						{ label: 'Settled', value: 'settled' },
					]"
				/>
				<Button
					variant="ghost"
					icon-left="lucide-refresh-cw"
					label="Refresh"
					:loading="requests.loading"
					@click="refresh"
				/>
			</div>
		</template>
	</AppPageHeader>

	<div class="px-5 py-4">
		<!-- The permission answer refused rather than arrived: say so, instead of
         leaving a skeleton up for a reply that is never coming. -->
		<div v-if="profilePermissionsError" class="mx-auto max-w-3xl">
			<ErrorMessage :message="profilePermissionsError.message" class="mb-3" />
			<Button label="Try again" variant="subtle" @click="reloadProfilePermissions()" />
		</div>

		<div v-else-if="!profilePermissionsLoaded" class="mx-auto max-w-3xl space-y-2">
			<Skeleton v-for="n in 3" :key="n" class="h-32 w-full rounded-4" />
		</div>

		<PermissionNotice v-else-if="!profileCan.review" what="review profile changes" />

		<div v-else class="mx-auto max-w-3xl">
			<ErrorMessage v-if="requests.error" :message="requests.error.message" class="mb-3" />
			<ErrorMessage v-if="decision.error" :message="decision.error.message" class="mb-3" />

			<div v-if="requests.loading && !requests.data" class="space-y-2">
				<Skeleton v-for="n in 3" :key="n" class="h-32 w-full rounded-4" />
			</div>

			<div
				v-else-if="requests.data?.length === 0"
				class="mt-16 flex flex-col items-center gap-2 text-center"
			>
				<span
					class="size-8 text-ink-gray-4"
					:class="tab === 'pending' ? 'lucide-check-check' : 'lucide-inbox'"
				/>
				<p class="text-base-medium text-ink-gray-7">
					{{ tab === 'pending' ? 'Nothing waiting on you' : 'Nothing settled yet' }}
				</p>
				<p class="text-p-sm text-ink-gray-5">
					{{
						tab === 'pending'
							? 'Corrections employees propose to their own details land here.'
							: 'Requests you apply or decline move here.'
					}}
				</p>
			</div>

			<ul v-else-if="requests.data" class="space-y-3">
				<li
					v-for="row in requests.data"
					:key="row.name"
					class="rounded-4 border border-outline-gray-1 p-4"
				>
					<div class="flex flex-wrap items-start justify-between gap-3">
						<div class="flex min-w-0 items-start gap-3">
							<Avatar :label="row.reference_title" size="lg" />
							<div class="min-w-0">
								<div class="truncate text-base-medium text-ink-gray-8">
									{{ row.reference_title }}
								</div>
								<!-- The queue spans every record type registered for self
								     service, so a row says which one it is rather than
								     leaving the reviewer to infer it from the name. -->
								<div class="mt-0.5 text-p-sm text-ink-gray-5">
									{{ row.reference_doctype }} ·
									{{ pluralise(row.changes.length, 'change') }} · sent
									{{ formatDate(row.posting_date) }}
								</div>
							</div>
						</div>
						<Badge :theme="profileStatus(row).theme" variant="subtle">
							{{ profileStatus(row).label }}
						</Badge>
					</div>

					<!-- The decision is the diff. Everything else on the row is context
               for it, so it sits directly under the name. -->
					<ChangeDiff :changes="row.changes" class="mt-3" />

					<p
						v-if="row.reason"
						class="mt-3 whitespace-pre-line text-p-base text-ink-gray-7"
					>
						{{ row.reason }}
					</p>

					<p
						v-if="row.review_note"
						class="mt-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
					>
						{{ row.review_note }}
					</p>

					<!-- Drawn from the server's answer for this row, not from its
               docstatus: whether this user settles this request is a question
               only the server can answer. -->
					<div v-if="row.can_decide" class="mt-4 flex flex-wrap items-center gap-2">
						<Button
							v-for="button in decisionButtons(row.actions, profileCan.decisions)"
							:key="button.decision"
							:variant="button.variant"
							:theme="button.theme"
							:label="button.label"
							:icon-left="button.icon"
							:loading="deciding === `${row.name}:${button.decision}`"
							:disabled="Boolean(deciding)"
							@click="decide(row, button)"
						/>
					</div>
				</li>
			</ul>
		</div>

		<!-- The declining path's second look. A `dialog()` call could ask the
         question but has nowhere to type the answer, and the answer is the
         part that matters to whoever gets it. -->
		<Dialog
			v-model:open="noteOpen"
			:title="`${asked?.button.label} change request`"
			:actions="noteActions"
		>
			<div v-if="asked" class="space-y-4">
				<p class="text-p-base text-ink-gray-6">
					{{ asked.button.label }} {{ asked.row.reference_title }}'s
					{{ pluralise(asked.row.changes.length, 'change') }}? They see the outcome and
					your note, and their record keeps the values it has now.
				</p>
				<ChangeDiff :changes="asked.row.changes" />
				<FormControl
					v-model="note"
					type="textarea"
					label="Note"
					:rows="3"
					placeholder="Why — and what they could do about it. A bare refusal leaves them nothing to act on."
				/>
			</div>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
	Avatar,
	Badge,
	Button,
	Dialog,
	ErrorMessage,
	FormControl,
	Skeleton,
	TabButtons,
	toast,
	type DialogAction,
} from 'frappe-ui'
import {
	decisionButtons,
	profileCan,
	profilePermissionsError,
	profilePermissionsLoaded,
	profileStatus,
	reloadProfilePermissions,
	reloadProfileWorkflow,
	useProfileDecision,
	useProfileReviewQueue,
	type DecisionButton,
	type ProfileChangeRequest,
} from '@/data/profile'
import { formatDate, pluralise } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ChangeDiff from '@/components/ChangeDiff.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

const tab = ref<'pending' | 'settled'>('pending')

// Held back until the answer arrives, so the page never flashes controls (or a
// refusal) it then takes away.
const canReview = computed(() => profilePermissionsLoaded.value && profileCan.value.review)

const requests = useProfileReviewQueue(() => tab.value === 'settled')
const decision = useProfileDecision()

// Keyed by request and decision so only the button that was pressed spins.
const deciding = ref('')

const pendingCount = computed(() =>
	tab.value === 'pending' ? requests.data?.length ?? 0 : profileCan.value.pending_reviews
)

// Both numbers stop at the same ceiling, so a queue that is full says so rather
// than quietly claiming that is all there is.
const pendingAtCeiling = computed(() => pendingCount.value >= profileCan.value.page_length)

/**
 * What the declining path is asking for.
 *
 * Null when nothing is being asked. Held as one object rather than a row and a
 * button in separate refs so the dialog cannot render half of a question.
 */
const asked = ref<{ row: ProfileChangeRequest; button: DecisionButton } | null>(null)
const note = ref('')

const noteOpen = computed({
	get: () => asked.value !== null,
	set: (open: boolean) => {
		if (!open) asked.value = null
	},
})

async function decide(row: ProfileChangeRequest, button: DecisionButton) {
	// Whether an outcome needs confirming arrives with it. Applying one writes
	// the values onto the employee record, and declining one is the answer the
	// employee reads -- neither is something the page can walk back for them.
	//
	// The note is collected with the decision rather than left to a follow-up
	// somewhere else: "we need to see the passport first" is actionable and a
	// bare "Declined" is not, and sending them in one call means a refusal and
	// its reason land together or not at all.
	if (button.confirm) {
		note.value = ''
		asked.value = { row, button }
		return
	}
	await submitDecision(row, button, null)
}

const noteActions = computed<DialogAction[]>(() =>
	asked.value
		? [
				{
					label: asked.value.button.label,
					variant: 'solid',
					theme: asked.value.button.theme,
					loading: decision.loading,
					onClick: async ({ close }) => {
						const { row, button } = asked.value!
						await submitDecision(row, button, note.value.trim() || null)
						close()
					},
				},
		  ]
		: []
)

async function submitDecision(
	row: ProfileChangeRequest,
	button: DecisionButton,
	note: string | null
) {
	deciding.value = `${row.name}:${button.decision}`
	try {
		const result = await decision.submit({
			name: row.name,
			decision: button.decision,
			...(note ? { note } : {}),
		})
		// `submit` resolves null on failure; the reason renders above the list.
		if (!result) throw decision.error ?? new Error('Could not save the decision')
		// The outcome in the server's own words, so a site whose workflow calls it
		// something else is quoted rather than paraphrased.
		toast.success(`${row.reference_title}'s request is now ${result.status}`)
		refresh()
	} finally {
		deciding.value = ''
	}
}

function refresh() {
	requests.reload()
	// The sidebar badge counts pending reviews, so it moves too -- and a
	// workflow's states are what the next row's label and buttons come from.
	reloadProfilePermissions()
	reloadProfileWorkflow()
}
</script>
