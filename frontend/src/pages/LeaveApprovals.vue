<template>
  <PageHeader>
    <div class="flex items-center gap-2">
      <span class="text-lg font-semibold text-ink-gray-8">Approvals</span>
      <Badge v-if="pendingCount" theme="amber" variant="subtle">
        {{ pendingCount }} waiting
      </Badge>
    </div>
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
        @click="requests.reload()"
      />
    </div>
  </PageHeader>

  <div class="px-5 py-4">
    <div v-if="!leavePermissionsLoaded" class="mx-auto max-w-3xl space-y-2">
      <Skeleton v-for="n in 3" :key="n" class="h-28 w-full rounded-4" />
    </div>

    <PermissionNotice
      v-else-if="!leaveCan.approve"
      action="approve leave for"
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

          <div v-if="request.docstatus === 0" class="mt-4 flex items-center gap-2">
            <Button
              variant="solid"
              label="Approve"
              icon-left="lucide-check"
              :loading="deciding === `${request.name}:Approved`"
              :disabled="Boolean(deciding)"
              @click="decide(request, 'Approved')"
            />
            <Button
              variant="subtle"
              theme="red"
              label="Deny"
              icon-left="lucide-x"
              :loading="deciding === `${request.name}:Rejected`"
              :disabled="Boolean(deciding)"
              @click="decide(request, 'Rejected')"
            />
            <span class="ml-auto text-p-sm text-ink-gray-5">
              Requested {{ formatDate(request.posting_date) }}
            </span>
          </div>
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
  PageHeader,
  Skeleton,
  TabButtons,
  dialog,
  toast,
} from 'frappe-ui'
import { user } from '@/data/session'
import {
  leaveCan,
  leavePermissionsLoaded,
  leaveStatus,
  reloadLeavePermissions,
  useLeaveDecision,
  usePendingApprovals,
  type LeaveApplicationRow,
} from '@/data/leave'
import { formatDate, formatDateRange } from '@/data/format'
import PermissionNotice from '@/components/PermissionNotice.vue'

const tab = ref<'pending' | 'decided'>('pending')

// Held back until the answer arrives, so the page never flashes controls (or a
// refusal) it then takes away.
const canApprove = computed(
  () => leavePermissionsLoaded.value && leaveCan.value.approve,
)

const requests = usePendingApprovals({
  decided: () => tab.value === 'decided',
  approver: () => user.value.name,
})

const decision = useLeaveDecision()

// Keyed by request and decision so only the button that was pressed spins.
const deciding = ref('')

const pendingCount = computed(() =>
  tab.value === 'pending'
    ? (requests.data?.length ?? 0)
    : leaveCan.value.pending_approvals,
)

async function decide(
  request: LeaveApplicationRow,
  verdict: 'Approved' | 'Rejected',
) {
  if (verdict === 'Rejected') {
    dialog.danger({
      title: 'Deny leave',
      message: `Deny ${request.employee_name}'s ${request.leave_type} for ${formatDateRange(request.from_date, request.to_date)}? They are notified, and it can't be reopened — they would need to request again.`,
      confirmLabel: 'Deny leave',
      onConfirm: () => submitDecision(request, verdict),
    })
    return
  }
  await submitDecision(request, verdict)
}

async function submitDecision(
  request: LeaveApplicationRow,
  verdict: 'Approved' | 'Rejected',
) {
  deciding.value = `${request.name}:${verdict}`
  try {
    const result = await decision.submit({ name: request.name, decision: verdict })
    // `submit` resolves null on failure; the reason renders above the list.
    if (!result) throw decision.error ?? new Error('Could not save the decision')
    toast.success(
      `${request.employee_name}'s leave ${verdict === 'Approved' ? 'approved' : 'denied'}`,
    )
    requests.reload()
    // The sidebar badge counts pending approvals, so it moves too.
    reloadLeavePermissions()
  } finally {
    deciding.value = ''
  }
}
</script>
