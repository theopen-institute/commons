<template>
	<AppPageHeader>
		<div class="flex min-w-0 items-center gap-3">
			<span class="text-lg font-semibold text-ink-gray-8">Procurement Request</span>
			<RequestTabs section="procurement" />
		</div>
		<template #actions>
			<!-- Nothing to filter or refresh when the list itself is withheld. -->
			<div v-if="hasWorkflowAccess" class="flex items-center gap-2">
				<TabButtons
					v-model="tab"
					:options="[
						{ label: 'To do', value: 'pending' },
						{ label: 'History', value: 'decided' },
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
		<RequestGate
			:error="procurementPermissionsError"
			:loaded="procurementPermissionsLoaded"
			:permitted="procurementCan.workflow_access"
			what="use procurement workflow tasks"
			who="your system administrator"
			row-class="h-40"
			@retry="reloadProcurementPermissions()"
		>
			<div class="mx-auto max-w-3xl">
				<ErrorMessage v-if="requests.error" :message="requests.error.message" class="mb-3" />
				<ErrorMessage
					v-if="requestLines.error"
					:message="requestLines.error.message"
					class="mb-3"
				/>

				<div v-if="requests.loading && !requests.data" class="space-y-2">
					<Skeleton v-for="n in 3" :key="n" class="h-40 w-full rounded-4" />
				</div>

				<div
					v-else-if="requestRows.length === 0"
					class="mt-16 flex flex-col items-center gap-2 text-center"
				>
					<span
						class="size-8 text-ink-gray-4"
						:class="tab === 'pending' ? 'lucide-check-check' : 'lucide-inbox'"
					/>
					<p class="text-base-medium text-ink-gray-7">
						{{ tab === 'pending' ? 'Nothing waiting on you' : 'No workflow history yet' }}
					</p>
					<p class="text-p-sm text-ink-gray-5">
						{{
							tab === 'pending'
								? 'Workflow actions assigned to you appear here.'
								: 'Workflow actions you complete appear here.'
						}}
					</p>
				</div>

				<!-- Grouped by department because that is what a budget belongs to, and
				     so what an approver is deciding against. -->
				<ul v-else class="space-y-8">
					<li v-for="group in departmentGroups" :key="group.key">
						<div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
							<h2 class="text-base-medium text-ink-gray-8">
								{{ group.department || 'No department' }}
							</h2>
							<span class="text-p-sm text-ink-gray-5">
								{{ group.requests.length }}
								{{ group.requests.length === 1 ? 'request' : 'requests' }}
								<template v-if="group.estimate !== null">
									· {{ formatCurrency(group.estimate, group.currency) }}
								</template>
							</span>
						</div>

						<!-- Once per department, not once per request: every request below
						     it is charged to this same allocation. Any of them resolves it,
						     so the first stands for the group in the drill-down. -->
						<DepartmentBudgetCard
							v-if="group.summary"
							:summary="group.summary"
							:request-name="group.requests[0]"
							class="mt-2"
						/>

						<ul class="mt-3 space-y-3">
							<li
								v-for="request in groupRequests(group)"
								:key="request.name"
								class="rounded-4 border border-outline-gray-1 p-4"
							>
								<div class="flex flex-wrap items-start justify-between gap-3">
									<div class="flex min-w-0 items-start gap-3">
										<Avatar :label="requesterName(request)" size="lg" />
										<div class="min-w-0">
											<div class="truncate text-base-medium text-ink-gray-8">
												{{ requestLabel(request) }}
											</div>
											<div class="mt-0.5 text-p-sm text-ink-gray-5">
												{{ requesterName(request) }} · Needed
												{{ formatDate(request.schedule_date) }}
											</div>
										</div>
									</div>
									<div class="text-right">
										<Badge
											:theme="procurementStatus(request, procurementWorkflow).theme"
											variant="subtle"
										>
											{{ procurementStatus(request, procurementWorkflow).label }}
										</Badge>
										<div
											v-if="request.total_estimated_cost"
											class="mt-1 text-base-medium text-ink-gray-8"
										>
											{{
												formatCurrency(request.total_estimated_cost, request.currency)
											}}
										</div>
									</div>
								</div>

								<p
									v-if="request.justification"
									class="mt-3 whitespace-pre-line text-p-base text-ink-gray-7"
								>
									{{ request.justification }}
								</p>

								<!-- The lines, not a count: what is being bought is the decision. -->
								<ProcurementLines
									class="mt-3"
									:lines="byRequest.get(request.name) ?? []"
									:currency="request.currency"
								/>

								<Alert
									v-if="request.rejection_reason"
									class="mt-3"
									theme="red"
									title="Turned down"
									:description="request.rejection_reason"
								/>

								<!-- Only opens the request: its workflow actions, and the
								     edit form, are reached from the review dialog, and a
								     transition is applied by a button pressed there rather
								     than on one click from a card in a long queue. -->
								<div class="mt-4 flex items-center gap-2">
									<span class="text-p-sm text-ink-gray-5">
										Requested {{ formatDate(request.transaction_date) }}
									</span>
									<Button
										v-if="request.can_edit || availableActions(request).length"
										class="ml-auto"
										variant="subtle"
										icon-left="lucide-eye"
										label="Review"
										@click="review.show(request)"
									/>
								</div>
							</li>
						</ul>
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
			v-model:open="showEdit"
			:request="editingRequest"
			:lines="editingRequest ? (byRequest.get(editingRequest.name) ?? []) : []"
			:workflow-actions="editingRequest ? availableActions(editingRequest) : []"
			@created="refresh"
		/>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
	Alert,
	Avatar,
	Badge,
	Button,
	ErrorMessage,
	Skeleton,
	TabButtons,
} from 'frappe-ui'
import {
	procurementCan,
	procurementPermissionsError,
	procurementPermissionsLoaded,
	procurementStatus,
	procurementWorkflow,
	reloadProcurementPermissions,
	requestLabel,
	useProcurementRequestLines,
	useProcurementWorkflowQueue,
	type DepartmentRequestGroup,
	type ProcurementRequestRow,
} from '@/data/requests/procurement'
import { useReviewTarget } from '@/data/requests/review'
import { formatCurrency, formatDate } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import DepartmentBudgetCard from '@/components/DepartmentBudgetCard.vue'
import ProcurementLines from '@/components/ProcurementLines.vue'
import ProcurementRequestDialog from '@/components/ProcurementRequestDialog.vue'
import ProcurementReviewDialog from '@/components/ProcurementReviewDialog.vue'
import RequestGate from '@/components/RequestGate.vue'
import RequestTabs from '@/components/RequestTabs.vue'

const tab = ref<'pending' | 'decided'>('pending')
const showEdit = ref(false)
const editingRequest = ref<ProcurementRequestRow | null>(null)

// Held back until the answer arrives, so the page never flashes controls (or a
// refusal) it then takes away.
const hasWorkflowAccess = computed(
	() => procurementPermissionsLoaded.value && procurementCan.value.workflow_access,
)

const requests = useProcurementWorkflowQueue(() => tab.value === 'decided')
const requestRows = computed(() => requests.data?.requests ?? [])
// Grouped by the server, which also prices each group against the allocation
// printed over it. `requestRows` stays the flat list the line fetch and the
// empty state are asking about.
const departmentGroups = computed(() => requests.data?.groups ?? [])

// A group carries request names, not rows: the page holds one list of requests
// and the grouping points into it.
const rowsByName = computed(
	() => new Map(requestRows.value.map((request) => [request.name, request])),
)

function groupRequests(group: DepartmentRequestGroup) {
	return group.requests
		.map((name) => rowsByName.value.get(name))
		.filter((request): request is ProcurementRequestRow => Boolean(request))
}

const { lines: requestLines, byRequest } = useProcurementRequestLines(() =>
	requestRows.value.map((request) => request.name),
)

// The request open in its review dialog, if any. Applying a transition to it
// is the dialog's; the page only refreshes once one has reached the server.
const review = useReviewTarget(requestRows)

function requesterName(request: ProcurementRequestRow) {
	return request.requester_name || request.requested_by || 'Someone'
}

function availableActions(request: ProcurementRequestRow) {
	return requests.data?.actions[request.name] ?? []
}

// The edit form is seeded from the lines, so it waits for them.
function linesLoaded(request: ProcurementRequestRow) {
	return !requestLines.loading && byRequest.value.has(request.name)
}

// From the review dialog, which gives way to the form: one dialog at a time.
function editRequest(request: ProcurementRequestRow) {
	review.open = false
	editingRequest.value = request
	showEdit.value = true
}

function refresh() {
	requests.reload()
	// Refreshes the workflow description too -- it rides along on the payload.
	reloadProcurementPermissions()
}
</script>
