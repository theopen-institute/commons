<template>
  <AppPageHeader>
    <div class="flex items-center gap-2">
      <span class="text-lg font-semibold text-ink-gray-8">Approvals</span>
      <Badge v-if="pendingCount" theme="amber" variant="subtle">
        {{ pendingCount }}{{ pendingAtCeiling ? '+' : '' }} waiting
      </Badge>
    </div>
    <template #actions>
      <!-- Nothing to filter or refresh when the list itself is withheld. -->
      <div v-if="canApprove" class="flex items-center gap-2">
        <TabButtons
          v-model="tab"
          :options="[
            { label: 'Pending', value: 'pending' },
            { label: 'Decided', value: 'decided' },
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
    <div v-if="leavePermissionsError" class="mx-auto max-w-3xl">
      <ErrorMessage
        :message="leavePermissionsError.message"
        class="mb-3"
      />
      <Button label="Try again" variant="subtle" @click="reloadLeavePermissions()" />
    </div>

    <div
      v-else-if="!leavePermissionsLoaded"
      class="mx-auto max-w-3xl space-y-2"
    >
      <Skeleton v-for="n in 3" :key="n" class="h-28 w-full rounded-4" />
    </div>

    <PermissionNotice
      v-else-if="!leaveCan.approve"
      what="approve leave"
    />

    <div v-else class="mx-auto max-w-3xl">
      <ErrorMessage
        v-if="requests.error"
        :message="requests.error.message"
        class="mb-3"
      />
      <ErrorMessage
        v-if="decision.error"
        :message="decision.error.message"
        class="mb-3"
      />

      <div v-if="requests.loading && !requests.data" class="space-y-2">
        <Skeleton v-for="n in 3" :key="n" class="h-28 w-full rounded-4" />
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
          {{ tab === 'pending' ? 'Nothing waiting on you' : 'Nothing decided yet' }}
        </p>
        <p class="text-p-sm text-ink-gray-5">
          {{
            tab === 'pending'
              ? 'Leave requests naming you as approver land here.'
              : 'Requests you approve or deny move here.'
          }}
        </p>
      </div>

      <ul v-else-if="requests.data" class="space-y-3">
        <li
          v-for="request in requests.data"
          :key="request.name"
          class="rounded-4 border border-outline-gray-1 p-4"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="flex min-w-0 items-start gap-3">
              <Avatar :label="request.employee_name" size="lg" />
              <div class="min-w-0">
                <div class="truncate text-base-medium text-ink-gray-8">
                  {{ request.employee_name }}
                </div>
                <div class="mt-0.5 text-p-sm text-ink-gray-5">
                  {{ request.leave_type }} ·
                  {{ formatDateRange(request.from_date, request.to_date) }} ·
                  {{ request.total_leave_days }}
                  day{{ request.total_leave_days === 1 ? '' : 's' }}
                </div>
              </div>
            </div>
            <Badge :theme="leaveStatus(request).theme" variant="subtle">
              {{ leaveStatus(request).label }}
            </Badge>
          </div>

          <p
            v-if="request.description"
            class="mt-3 whitespace-pre-line text-p-base text-ink-gray-7"
          >
            {{ request.description }}
          </p>

          <!-- Whose decision this is, when it is not this user's own queue. -->
          <p
            v-if="
              request.leave_approver && request.leave_approver !== user.name
            "
            class="mt-3 text-p-sm text-ink-gray-5"
          >
            Assigned to
            {{ request.leave_approver_name || request.leave_approver }}
          </p>

          <!-- Drawn from the server's answer for this row, not from its
               docstatus: whether this user decides this application is a
               question only the server can settle. -->
          <div v-if="request.can_decide" class="mt-4 flex items-center gap-2">
            <Button
              v-for="button in buttonsFor(request)"
              :key="button.decision"
              :variant="button.variant"
              :theme="button.theme"
              :label="button.label"
              :icon-left="button.icon"
              :loading="deciding === `${request.name}:${button.decision}`"
              :disabled="Boolean(deciding)"
              @click="decide(request, button)"
            />
            <span class="ml-auto text-p-sm text-ink-gray-5">
              Requested {{ formatDate(request.posting_date) }}
            </span>
          </div>
          <p v-else class="mt-4 text-p-sm text-ink-gray-5">
            Requested {{ formatDate(request.posting_date) }}
          </p>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Avatar,
  Badge,
  Button,
  ErrorMessage,
  Skeleton,
  TabButtons,
  dialog,
  toast,
} from 'frappe-ui'
import { user } from '@/data/session'
import {
  decisionButtons,
  leaveCan,
  leavePermissionsError,
  leavePermissionsLoaded,
  leaveStatus,
  reloadLeavePermissions,
  reloadLeaveWorkflow,
  useLeaveApprovalQueue,
  useLeaveDecision,
  type DecisionButton,
  type LeaveApplicationRow,
} from '@/data/leave'
import { formatDate, formatDateRange } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

const tab = ref<'pending' | 'decided'>('pending')

// Held back until the answer arrives, so the page never flashes controls (or a
// refusal) it then takes away.
const canApprove = computed(
  () => leavePermissionsLoaded.value && leaveCan.value.approve,
)

const requests = useLeaveApprovalQueue(() => tab.value === 'decided')

const decision = useLeaveDecision()

// Keyed by request and decision so only the button that was pressed spins.
const deciding = ref('')

// The outcomes *this row* accepts, which the server settles per row: a
// workflow's permitted transitions where one is running, and otherwise the
// vocabulary less anything HRMS would refuse — self-approval, say.
function buttonsFor(request: LeaveApplicationRow) {
  return decisionButtons(request.actions, leaveCan.value.decisions)
}

const pendingCount = computed(() =>
  tab.value === 'pending'
    ? (requests.data?.length ?? 0)
    : leaveCan.value.pending_approvals,
)

// Both numbers stop at the same ceiling, so a queue that is full says so
// rather than quietly claiming that is all there is.
const pendingAtCeiling = computed(
  () => pendingCount.value >= leaveCan.value.page_length,
)

async function decide(request: LeaveApplicationRow, button: DecisionButton) {
  // Whether an outcome needs confirming arrives with it. The application is
  // written with that decision on it, and that is not something the page can
  // walk back on the approver's behalf.
  if (button.confirm) {
    dialog.danger({
      title: `${button.label} leave`,
      message: `${button.label} ${request.employee_name}'s ${request.leave_type} for ${formatDateRange(request.from_date, request.to_date)}? They are notified, and the application is settled with that decision.`,
      confirmLabel: `${button.label} leave`,
      onConfirm: () => submitDecision(request, button.decision),
    })
    return
  }
  await submitDecision(request, button.decision)
}

async function submitDecision(request: LeaveApplicationRow, verdict: string) {
  deciding.value = `${request.name}:${verdict}`
  try {
    const result = await decision.submit({ name: request.name, decision: verdict })
    // `submit` resolves null on failure; the reason renders above the list.
    if (!result) throw decision.error ?? new Error('Could not save the decision')
    // The outcome in the server's own words, so a site whose workflow calls it
    // something else is quoted rather than paraphrased.
    toast.success(
      `${request.employee_name}'s leave is now ${result.status}`,
    )
    refresh()
  } finally {
    deciding.value = ''
  }
}

function refresh() {
  requests.reload()
  // The sidebar badge counts pending approvals, so it moves too — and a
  // workflow's states are what the next row's label and buttons come from.
  reloadLeavePermissions()
  reloadLeaveWorkflow()
}
</script>
