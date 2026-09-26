<!--
	One procurement request, and the only place on either procurement page where
	a workflow action is applied to it. See `RequestReviewDialog` for why the
	lists no longer do.

	Shared by "My requests" and the approvals queue, which each carried their own
	copy of the action buttons and of the call behind them. There is nothing to
	draft: `apply_workflow` takes the document and the transition, and the
	reason a request was turned down is written by the workflow itself.
-->

<template>
	<RequestReviewDialog
		v-model:open="open"
		:title="request ? requestLabel(request) : 'Procurement request'"
		:message="request ? `${request.name} · Requested ${formatDate(request.transaction_date)}` : ''"
		:buttons="reviewButtons"
		:running="workflow.running.value"
		:error="attempted ? workflow.call.error?.message : null"
		:gone="gone"
		@choose="choose"
	>
		<template v-if="request">
			<div class="flex flex-wrap items-start justify-between gap-3">
				<div class="min-w-0 text-p-sm text-ink-gray-5">
					<div>Needed {{ formatDate(request.schedule_date) }}</div>
					<div v-if="request.department">{{ request.department }}</div>
				</div>
				<div class="text-right">
					<Badge :theme="procurementStatus(request, procurementWorkflow).theme" variant="subtle">
						{{ procurementStatus(request, procurementWorkflow).label }}
					</Badge>
					<div v-if="request.total_estimated_cost" class="mt-1 text-base-medium text-ink-gray-8">
						{{ formatCurrency(request.total_estimated_cost, request.currency) }}
					</div>
				</div>
			</div>

			<!-- The lines, not a count: what is being bought is the decision. -->
			<ProcurementLines :lines="lines" :currency="request.currency" />

			<dl class="grid gap-3 text-p-sm sm:grid-cols-2">
				<div>
					<dt class="text-ink-gray-5">Requested by</dt>
					<dd class="text-ink-gray-8">
						{{ request.requester_name || request.requested_by || 'Someone' }}
					</dd>
				</div>
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
				theme="red"
				title="Turned down"
				:description="request.rejection_reason"
			/>
		</template>

		<!-- Editing opens the request form, which saves through its own call and
		     offers the same transitions beside Save. -->
		<template v-if="request?.can_edit && !gone" #footer>
			<Button
				variant="subtle"
				icon-left="lucide-pencil"
				label="Edit"
				:disabled="!linesLoaded || Boolean(workflow.running.value)"
				@click="request && emit('edit', request)"
			/>
		</template>
	</RequestReviewDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Alert, Badge, Button } from 'frappe-ui'
import {
	procurementStatus,
	procurementWorkflow,
	requestLabel,
	workflowActionButtons,
	type AvailableWorkflowAction,
	type ProcurementRequestItemRow,
	type ProcurementRequestRow,
} from '@/data/requests/procurement'
import { useWorkflowAction } from '@/data/requests/review'
import { formatCurrency, formatDate } from '@/data/format'
import ProcurementLines from './ProcurementLines.vue'
import RequestReviewDialog from './RequestReviewDialog.vue'

const props = defineProps<{
	request: ProcurementRequestRow | null
	lines: ProcurementRequestItemRow[]
	/** Whether `lines` has arrived — the edit form is seeded from it. */
	linesLoaded: boolean
	/** The transitions this user may apply to this request, as the server sent them. */
	actions: AvailableWorkflowAction[]
	/** The list no longer has this request. See `useReviewTarget`. */
	gone?: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
	/** After every action that reached the server, applied or refused. */
	settled: []
	edit: [request: ProcurementRequestRow]
}>()

const workflow = useWorkflowAction({ settled: () => emit('settled') })

// A call keeps its last error until it is next submitted, and a reason left
// over from another request is not an answer about this one.
const attempted = ref(false)
watch(
	() => [open.value, props.request?.name],
	() => (attempted.value = false),
)

// Keyed by the action's own name, not the button's label. They are the same
// string today; the label is what a site could rename.
const reviewButtons = computed(() =>
	workflowActionButtons(props.actions, procurementWorkflow.value).map((button) => ({
		key: button.action.action,
		label: button.label,
		theme: button.theme,
		variant: button.variant,
	})),
)

function choose(key: string, close: () => void) {
	const action = props.actions.find((candidate) => candidate.action === key)
	if (!props.request || !action) return
	attempted.value = true
	workflow.apply(props.request, action, close)
}
</script>
