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
					v-if="workflowAction.error"
					:message="workflowAction.error.message"
					class="mt-3"
				/>
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
						<!-- Two lines on a phone, one from `sm` up. The status and the
						     chevron are a fixed ~140px between them; beside a title and a
						     summary line in 390px of viewport they leave the text about
						     half the row, which is where the reading actually happens. -->
						<button
							type="button"
							class="flex w-full flex-col items-start gap-2 p-4 text-left sm:flex-row sm:justify-between sm:gap-3"
							@click="toggle(request.name)"
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
							     chevron is the reveal affordance, and it should not move
							     to the middle of the card when the row wraps. -->
							<div
								class="flex w-full shrink-0 items-center justify-between gap-2 sm:w-auto sm:justify-end"
							>
								<Badge
									:theme="procurementStatus(request, procurementWorkflow).theme"
									variant="subtle"
								>
									{{ procurementStatus(request, procurementWorkflow).label }}
								</Badge>
								<span
									class="size-4 text-ink-gray-5"
									:class="
										expanded === request.name
											? 'lucide-chevron-up'
											: 'lucide-chevron-down'
									"
								/>
							</div>
						</button>

						<div
							v-if="expanded === request.name"
							class="border-t border-outline-gray-1 p-4"
						>
							<ProcurementLines
								:lines="byRequest.get(request.name) ?? []"
								:currency="request.currency"
							/>

							<dl class="mt-4 grid gap-3 text-p-sm sm:grid-cols-2">
								<div>
									<dt class="text-ink-gray-5">Approver</dt>
									<dd class="text-ink-gray-8">
										{{ request.approver_name || request.approver || 'Not named' }}
									</dd>
								</div>
								<div v-if="request.justification" class="sm:col-span-2">
									<dt class="text-ink-gray-5">Details</dt>
									<dd class="whitespace-pre-line text-ink-gray-8">
										{{ request.justification }}
									</dd>
								</div>
							</dl>

							<Alert
								v-if="request.rejection_reason"
								class="mt-4"
								theme="red"
								title="Turned down"
								:description="request.rejection_reason || 'No reason was recorded.'"
							/>

							<div
								v-if="request.can_edit || availableActions(request).length"
								class="mt-4 flex items-center gap-2"
							>
								<Button
									v-if="request.can_edit"
									variant="subtle"
									icon-left="lucide-pencil"
									label="Edit"
									:disabled="requestLines.loading || !byRequest.has(request.name)"
									@click="editRequest(request)"
								/>
								<div class="ml-auto flex items-center gap-2">
									<Button
										v-for="button in workflowActionButtons(
											availableActions(request),
											procurementWorkflow,
										)"
										:key="button.label"
										:variant="button.variant"
										:theme="button.theme"
										:label="button.label"
										:loading="runningAction === `${request.name}:${button.label}`"
										:disabled="Boolean(runningAction)"
										@click="applyAction(request, button.action)"
									/>
								</div>
							</div>
						</div>
					</li>
				</ul>
			</div>
		</RequestGate>

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
import { Alert, Badge, Button, ErrorMessage, Skeleton, toast } from 'frappe-ui'
import {
	procurementCan,
	procurementPermissionsError,
	procurementPermissionsLoaded,
	procurementStatus,
	procurementWorkflow,
	reloadProcurementPermissions,
	requestLabel,
	useApplyProcurementWorkflow,
	useMyProcurementRequests,
	useProcurementRequestTransitions,
	useProcurementRequestLines,
	workflowActionButtons,
	type AvailableWorkflowAction,
	type ProcurementRequestRow,
} from '@/data/requests/procurement'
import { formatCurrency, formatDate, pluralise } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ProcurementLines from '@/components/ProcurementLines.vue'
import ProcurementRequestDialog from '@/components/ProcurementRequestDialog.vue'
import { useNewRequestQuery } from '@/data/requests/newRequest'
import RequestGate from '@/components/RequestGate.vue'
import RequestTabs from '@/components/RequestTabs.vue'

const showRequest = ref(false)

// `?new=1` from the search bar: it asked for this page so that this
// dialog could be opened. See `useNewRequestQuery`.
useNewRequestQuery(showRequest)
const editingRequest = ref<ProcurementRequestRow | null>(null)
const expanded = ref('')
const runningAction = ref('')

const requests = useMyProcurementRequests()

// Every request's lines in one call, so the count in a collapsed row is right
// before it is opened — and opening one costs nothing. It refetches itself
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

function toggle(name: string) {
	expanded.value = expanded.value === name ? '' : name
}

function openNewRequest() {
	editingRequest.value = null
	showRequest.value = true
}

function editRequest(request: ProcurementRequestRow) {
	editingRequest.value = request
	showRequest.value = true
}

const workflowAction = useApplyProcurementWorkflow()

function availableActions(request: ProcurementRequestRow) {
	return transitions.data?.[request.name] ?? []
}

async function applyAction(request: ProcurementRequestRow, action: AvailableWorkflowAction) {
	runningAction.value = `${request.name}:${action.action}`
	try {
		const result = await workflowAction.submit({
			doc: JSON.stringify({ doctype: 'Procurement Request', name: request.name }),
			action: action.action,
		})
		if (!result) return
		toast.success(`${action.action} applied`)
		refresh()
	} finally {
		runningAction.value = ''
	}
}

function refresh() {
	requests.reload()
	// Refreshes the workflow description too -- it rides along on the payload.
	reloadProcurementPermissions()
}
</script>
