<template>
  <AppPageHeader>
    <div class="flex min-w-0 items-center gap-3">
      <span class="text-lg font-semibold text-ink-gray-8">Leave Request</span>
      <RequestTabs section="leave" />
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
    <RequestGate
      :error="leavePermissionsError"
      :loaded="leavePermissionsLoaded"
      :permitted="leaveCan.approve"
      what="approve leave"
      row-class="h-28"
      @retry="reloadLeavePermissions()"
    >
      <div class="mx-auto max-w-3xl">
        <ErrorMessage
          v-if="requests.error"
          :message="requests.error.message"
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

            <!-- Only opens the application: the decision is made in the dialog,
                 with the whole request in front of the approver, and never on
                 one click from a row read in passing. Offered where the server
                 says this user decides this row. -->
            <div class="mt-4 flex items-center gap-2">
              <span class="text-p-sm text-ink-gray-5">
                Requested {{ formatDate(request.posting_date) }}
              </span>
              <Button
                v-if="request.can_decide"
                class="ml-auto"
                variant="subtle"
                icon-left="lucide-eye"
                label="Review"
                @click="review.show(request)"
              />
            </div>
          </li>
        </ul>
      </div>
    </RequestGate>

    <LeaveReviewDialog
      v-model:open="review.open"
      :request="review.row"
      :gone="review.gone"
      @settled="refresh"
    />
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
} from 'frappe-ui'
import { user } from '@/data/session'
import {
  leaveCan,
  leavePermissionsError,
  leavePermissionsLoaded,
  leaveStatus,
  reloadLeavePermissions,
  useLeaveApprovalQueue,
} from '@/data/requests/leave'
import { useReviewTarget } from '@/data/requests/review'
import { formatDate, formatDateRange } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import LeaveReviewDialog from '@/components/LeaveReviewDialog.vue'
import RequestGate from '@/components/RequestGate.vue'
import RequestTabs from '@/components/RequestTabs.vue'

const tab = ref<'pending' | 'decided'>('pending')

// Held back until the answer arrives, so the page never flashes controls (or a
// refusal) it then takes away.
const canApprove = computed(
  () => leavePermissionsLoaded.value && leaveCan.value.approve,
)

const requests = useLeaveApprovalQueue(() => tab.value === 'decided')

// The application open for review, if any. Deciding it — and everything that
// needs, from the buttons to the reason a decision was refused — is the
// dialog's; the page only refreshes once a decision has reached the server.
const review = useReviewTarget(() => requests.data)

function refresh() {
  requests.reload()
  // The sidebar badge counts pending approvals, so it moves too.
  reloadLeavePermissions()
}
</script>
