<template>
	<AppPageHeader>
		<div class="flex min-w-0 items-center gap-3">
			<span class="text-lg font-semibold text-ink-gray-8">Procurement Request</span>
			<RequestTabs section="procurement" />
		</div>
		<template #actions>
			<Button
				v-if="procurementCan.request"
				variant="solid"
				icon-left="lucide-plus"
				label="New request"
				@click="openNewRequest"
			/>
		</template>
	</AppPageHeader>

	<div class="px-5 py-4">
		<RequestGate
			:error="procurementPermissionsError"
			:loaded="procurementPermissionsLoaded"
			:permitted="procurementCan.read"
			what="see procurement requests"
			who="your system administrator"
			@retry="reloadProcurementPermissions()"
		>
			<!-- Deliberately no EmployeeRequired, unlike leave and expenses: a
			     request is raised by a user, not against an employee record, so a
			     bursar or an office manager without one can still raise it. The
			     employee record, when there is one, only supplies defaults. -->
			<div class="mx-auto max-w-3xl">
				<div class="flex items-center justify-between">
					<h2 class="text-base-medium text-ink-gray-8">Requests</h2>
					<Button
						variant="ghost"
						icon-left="lucide-refresh-cw"
						label="Refresh"
						:loading="requests.loading"
						@click="refresh"
					/>
				</div>

				<ErrorMessage v-if="requests.error" :message="requests.error.message" class="mt-3" />
				<ErrorMessage
					v-if="requestLines.error"
					:message="requestLines.error.message"
					class="mt-3"
				/>

				<div v-if="requests.loading && !requests.data" class="mt-3 space-y-2">
					<Skeleton v-for="n in 3" :key="n" class="h-16 w-full rounded-4" />
				</div>

				<div
					v-else-if="requests.data?.length === 0"
					class="mt-3 rounded-4 border border-dashed border-outline-gray-2 px-4 py-10 text-center"
				>
					<p class="text-base-medium text-ink-gray-7">Nothing requested yet</p>
					<p class="mt-1 text-p-sm text-ink-gray-5">
						Ask for something and follow its progress here.
					</p>
				</div>

				<ul v-else-if="requests.data" class="mt-3 space-y-3">
					<li
						v-for="request in requests.data"
						:key="request.name"
						class="rounded-4 border border-outline-gray-1"
					>
						<!-- Opens the request in its review dialog, which is where its
						     lines are read and where it is edited or moved along the
						     workflow. The row used to unfold in place with those
						     buttons in it, and a transition was applied on one click.

						     Two lines on a phone, one from `sm` up. The status and the
						     chevron are a fixed ~140px between them; beside a title and a
						     summary line in 390px of viewport they leave the text about
						     half the row, which is where the reading actually happens. -->
						<button
							type="button"
							class="flex w-full flex-col items-start gap-2 p-4 text-left sm:flex-row sm:justify-between sm:gap-3"
							@click="review.show(request)"
						>
							<div class="w-full min-w-0 sm:w-auto">
								<div class="truncate text-base-medium text-ink-gray-8">
									{{ requestLabel(request) }}
								</div>
								<!-- The id names the request; the facts under it answer
								     separate questions and are read one at a time, so they
								     are separate elements rather than one run-on line. Each
								     stays whole when the row wraps, which at 390px it does:
								     as a single string "about NPR 35" broke across two
								     lines between the two words that make it a price. -->
								<div class="mt-0.5 text-p-sm text-ink-gray-5">{{ request.name }}</div>
								<div
									class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-p-sm text-ink-gray-5"
								>
									<span>{{ pluralise(lineCount(request.name), 'line') }}</span>
									<span>Needed {{ formatDate(request.schedule_date) }}</span>
									<span v-if="request.total_estimated_cost">
										About
										{{ formatCurrency(request.total_estimated_cost, request.currency) }}
									</span>
								</div>
							</div>
							<!-- Still hard against the right edge on its own line: the
							     chevron is the affordance that opens the request, and it
							     should not move to the middle of the card when the row
							     wraps. -->
							<div
								class="flex w-full shrink-0 items-center justify-between gap-2 sm:w-auto sm:justify-end"
							>
								<Badge
									:theme="procurementStatus(request, procurementWorkflow).theme"
									variant="subtle"
								>
									{{ procurementStatus(request, procurementWorkflow).label }}
								</Badge>
								<span class="lucide-chevron-right size-4 text-ink-gray-5" />
							</div>
						</button>
					</li>
				</ul>
			</div>
		</RequestGate>

		<ProcurementReviewDialog
			v-model:open="review.open"
			:request="review.row"
			:lines="review.row ? (byRequest.get(review.row.name) ?? []) : []"
			:lines-loaded="review.row ? linesLoaded(review.row) : false"
			:actions="review.row ? availableActions(review.row) : []"
			:gone="review.gone"
			@settled="refresh"
			@edit="editRequest"
		/>

		<ProcurementRequestDialog
			v-model:open="showRequest"
			:request="editingRequest"
			:lines="editingRequest ? (byRequest.get(editingRequest.name) ?? []) : []"
			:workflow-actions="editingRequest ? availableActions(editingRequest) : []"
			@created="refresh"
		/>
	</div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Badge, Button, ErrorMessage, Skeleton } from 'frappe-ui'
import {
	procurementCan,
	procurementPermissionsError,
	procurementPermissionsLoaded,
	procurementStatus,
	procurementWorkflow,
	reloadProcurementPermissions,
	requestLabel,
	useMyProcurementRequests,
	useProcurementRequestTransitions,
	useProcurementRequestLines,
	type ProcurementRequestRow,
} from '@/data/requests/procurement'
import { useReviewTarget } from '@/data/requests/review'
import { formatCurrency, formatDate, pluralise } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ProcurementRequestDialog from '@/components/ProcurementRequestDialog.vue'
import ProcurementReviewDialog from '@/components/ProcurementReviewDialog.vue'
import { useNewRequestQuery } from '@/data/requests/newRequest'
import RequestGate from '@/components/RequestGate.vue'
import RequestTabs from '@/components/RequestTabs.vue'

const showRequest = ref(false)

// `?new=1` from the search bar: it asked for this page so that this
// dialog could be opened. See `useNewRequestQuery`.
useNewRequestQuery(showRequest)
const editingRequest = ref<ProcurementRequestRow | null>(null)

const requests = useMyProcurementRequests()

// Every request's lines in one call, so the count in a row is right before it
// is opened — and opening one costs nothing. It refetches itself
// whenever the request list refreshes, which is why `refresh` below does not ask
// it to: two overlapping fetches abort each other.
const { lines: requestLines, byRequest } = useProcurementRequestLines(() =>
	(requests.data ?? []).map((request) => request.name),
)
const transitions = useProcurementRequestTransitions(() =>
	(requests.data ?? []).map((request) => request.name),
)

function lineCount(name: string) {
	return byRequest.value.get(name)?.length ?? 0
}

function openNewRequest() {
	editingRequest.value = null
	showRequest.value = true
}

// The request open in its review dialog, if any. Applying a transition to it
// is the dialog's; the page only refreshes once one has reached the server.
const review = useReviewTarget(() => requests.data)

// From the review dialog, which gives way to the form: one dialog at a time.
function editRequest(request: ProcurementRequestRow) {
	review.open = false
	editingRequest.value = request
	showRequest.value = true
}

// The edit form is seeded from the lines, so it waits for them.
function linesLoaded(request: ProcurementRequestRow) {
	return !requestLines.loading && byRequest.value.has(request.name)
}

function availableActions(request: ProcurementRequestRow) {
	return transitions.data?.[request.name] ?? []
}

function refresh() {
	requests.reload()
	// Refreshes the workflow description too -- it rides along on the payload.
	reloadProcurementPermissions()
}
</script>
