<template>
	<PageHeader>
		<div class="flex items-center gap-2">
			<span class="text-lg font-semibold text-ink-gray-8">Approvals</span>
			<Badge v-if="pendingCount" theme="amber" variant="subtle">
				{{ pendingCount }} waiting
			</Badge>
		</div>
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
	</PageHeader>

	<div class="px-5 py-4">
		<div v-if="!procurementPermissionsLoaded" class="mx-auto max-w-3xl space-y-2">
			<Skeleton v-for="n in 3" :key="n" class="h-40 w-full rounded-4" />
		</div>

		<PermissionNotice
			v-else-if="!procurementCan.workflow_access"
			what="use procurement workflow tasks"
			who="your system administrator"
		/>

		<div v-else class="mx-auto max-w-3xl">
			<ErrorMessage v-if="requests.error" :message="requests.error.message" class="mb-3" />
			<ErrorMessage
				v-if="workflowAction.error"
				:message="workflowAction.error.message"
				class="mb-3"
			/>
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

			<ul v-else class="space-y-3">
				<li
					v-for="request in requestRows"
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
									<template v-if="request.department">
										· {{ request.department }}
									</template>
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

					<DepartmentBudgetCard v-if="request.budget_summary" :summary="request.budget_summary" :request-name="request.name" class="mt-3" />

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

					<div
						v-if="request.can_edit || availableActions(request).length"
						class="mt-4 flex flex-wrap items-center gap-2"
					>
						<Button
							v-if="request.can_edit"
							variant="subtle"
							icon-left="lucide-pencil"
							label="Edit"
							:disabled="requestLines.loading || !byRequest.has(request.name)"
							@click="editRequest(request)"
						/>
						<div class="ml-auto flex flex-wrap items-center gap-2">
							<Button
								v-for="action in availableActions(request)"
								:key="action.action"
								variant="solid"
								:theme="workflowActionTheme(action, procurementWorkflow)"
								:label="action.action"
								:loading="runningAction === `${request.name}:${action.action}`"
								:disabled="Boolean(runningAction)"
								@click="applyAction(request, action)"
							/>
						</div>
						<!-- The action group above carries the row's only auto margin;
						     a second one here would split the free space between the
						     two, stranding the buttons mid-row instead of right. -->
						<span class="text-p-sm text-ink-gray-5">
							Requested {{ formatDate(request.transaction_date) }}
						</span>
					</div>
				</li>
			</ul>
		</div>

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
	PageHeader,
	Skeleton,
	TabButtons,
	toast,
} from 'frappe-ui'
import {
	procurementCan,
	procurementPermissionsLoaded,
	procurementStatus,
	procurementWorkflow,
	reloadProcurementPermissions,
	reloadProcurementWorkflow,
	requestLabel,
	useApplyProcurementWorkflow,
	useProcurementRequestLines,
	useProcurementWorkflowQueue,
	workflowActionTheme,
	type AvailableWorkflowAction,
	type ProcurementRequestRow,
} from '@/data/procurement'
import { formatCurrency, formatDate } from '@/data/format'
import DepartmentBudgetCard from '@/components/DepartmentBudgetCard.vue'
import ProcurementLines from '@/components/ProcurementLines.vue'
import ProcurementRequestDialog from '@/components/ProcurementRequestDialog.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

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

const { lines: requestLines, byRequest } = useProcurementRequestLines(() =>
	requestRows.value.map((request) => request.name),
)

const workflowAction = useApplyProcurementWorkflow()

// Keyed by request and decision so only the button that was pressed spins.
const runningAction = ref('')

const pendingCount = computed(() =>
	tab.value === 'pending'
		? requestRows.value.length
		: procurementCan.value.pending_workflow_actions,
)

function requesterName(request: ProcurementRequestRow) {
	return request.requester_name || request.requested_by || 'Someone'
}

function availableActions(request: ProcurementRequestRow) {
	return requests.data?.actions[request.name] ?? []
}

function editRequest(request: ProcurementRequestRow) {
	editingRequest.value = request
	showEdit.value = true
}

async function applyAction(request: ProcurementRequestRow, action: AvailableWorkflowAction) {
	runningAction.value = `${request.name}:${action.action}`
	try {
		const result = await workflowAction.submit({
			doc: JSON.stringify({ doctype: 'Procurement Request', name: request.name }),
			action: action.action,
		})
		if (!result) return
		toast.success(`${action.action} applied to ${requestLabel(request)}`)
		refresh()
	} finally {
		requests.reload()
		runningAction.value = ''
	}
}

function refresh() {
	requests.reload()
	reloadProcurementPermissions()
	reloadProcurementWorkflow()
}
</script>
