<!--
  One leave application, and the only place on the approvals page where it is
  decided. See `RequestReviewDialog` for why the list no longer decides.

  There is nothing to draft here: `decide_leave_application` takes the
  application and the outcome, and nothing else an approver could type.
-->

<template>
  <RequestReviewDialog
    v-model:open="open"
    :title="request ? `${request.employee_name}'s leave` : 'Leave request'"
    :message="request ? `Requested ${formatDate(request.posting_date)}` : ''"
    :buttons="reviewButtons"
    :running="deciding"
    :error="attempted ? decision.error?.message : null"
    :gone="gone"
    @choose="choose"
  >
    <template v-if="request">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="flex min-w-0 items-start gap-3">
          <Avatar :label="request.employee_name" size="lg" />
          <div class="min-w-0">
            <div class="truncate text-base-medium text-ink-gray-8">
              {{ request.leave_type }}
            </div>
            <div class="mt-0.5 text-p-sm text-ink-gray-5">
              {{ formatDateRange(request.from_date, request.to_date) }} ·
              {{ request.total_leave_days }}
              day{{ request.total_leave_days === 1 ? '' : 's' }}
              <template v-if="request.half_day"> · half day</template>
            </div>
          </div>
        </div>
        <Badge :theme="leaveStatus(request).theme" variant="subtle">
          {{ leaveStatus(request).label }}
        </Badge>
      </div>

      <p
        v-if="request.description"
        class="whitespace-pre-line text-p-base text-ink-gray-7"
      >
        {{ request.description }}
      </p>

      <!-- Whose decision this is, when it is not this user's own queue. -->
      <p
        v-if="request.leave_approver && request.leave_approver !== user.name"
        class="text-p-sm text-ink-gray-5"
      >
        Assigned to
        {{ request.leave_approver_name || request.leave_approver }}
      </p>
    </template>
  </RequestReviewDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Avatar, Badge, toast } from 'frappe-ui'
import { user } from '@/data/session'
import {
  decisionButtons,
  leaveCan,
  leaveStatus,
  useLeaveDecision,
  type LeaveApplicationRow,
} from '@/data/requests/leave'
import { useRowDecision } from '@/data/requests/review'
import { formatDate, formatDateRange } from '@/data/format'
import RequestReviewDialog from './RequestReviewDialog.vue'

const props = defineProps<{
  request: LeaveApplicationRow | null
  /** The list no longer has this application. See `useReviewTarget`. */
  gone?: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

/** After every decision that reached the server, written or refused. */
const emit = defineEmits<{ settled: [] }>()

// The dialog's own call, so the reason a decision was refused renders beside
// the buttons that were refused rather than above a list the dialog covers.
const decision = useLeaveDecision()

// A call keeps its last error until it is next submitted, and a reason left
// over from another application — or from before the dialog was last closed —
// is not an answer about this one.
const attempted = ref(false)
watch(
  () => [open.value, props.request?.name],
  () => (attempted.value = false),
)

const { deciding, decide } = useRowDecision({
  call: decision,
  params: (request: LeaveApplicationRow, verdict) => ({
    name: request.name,
    decision: verdict,
  }),
  confirmation: (request, button) => ({
    title: `${button.label} leave`,
    message: `${button.label} ${request.employee_name}'s ${request.leave_type} for ${formatDateRange(request.from_date, request.to_date)}? They are notified, and the application is settled with that decision.`,
    confirmLabel: `${button.label} leave`,
  }),
  // The outcome in the server's own words, so a site whose workflow calls it
  // something else is quoted rather than paraphrased.
  succeeded: (request, result) =>
    toast.success(`${request.employee_name}'s leave is now ${result.status}`),
  settled: () => emit('settled'),
})

// Drawn from the server's answer for this row, not from its docstatus: whether
// this user decides this application, and which outcomes it accepts — a
// workflow's permitted transitions, or the vocabulary less anything HRMS would
// refuse, self-approval say — is a question only the server can settle.
const buttons = computed(() =>
  props.request?.can_decide
    ? decisionButtons(props.request.actions, leaveCan.value.decisions)
    : [],
)

const reviewButtons = computed(() =>
  buttons.value.map((button) => ({ ...button, key: button.decision })),
)

function choose(key: string, close: () => void) {
  const button = buttons.value.find((candidate) => candidate.decision === key)
  if (!props.request || !button) return
  attempted.value = true
  decide(props.request, button, close)
}
</script>
