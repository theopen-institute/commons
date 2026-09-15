<template>
  <PageHeader>
    <span class="text-lg font-semibold text-ink-gray-8">My leave</span>
    <Button
      v-if="employee && leaveCan.request"
      variant="solid"
      icon-left="lucide-plus"
      label="Request leave"
      @click="showRequest = true"
    />
  </PageHeader>

  <div class="px-5 py-4">
    <!-- The permission answer refused rather than arrived: say so, instead of
         leaving a skeleton up for a reply that is never coming. -->
    <div v-if="leavePermissionsError" class="mx-auto max-w-3xl">
      <ErrorMessage :message="leavePermissionsError.message" class="mb-3" />
      <Button label="Try again" variant="subtle" @click="reloadLeavePermissions()" />
    </div>

    <div
      v-else-if="!myEmployeeLoaded || !leavePermissionsLoaded"
      class="mx-auto max-w-3xl space-y-3"
    >
      <Skeleton v-for="n in 3" :key="n" class="h-20 w-full rounded-4" />
    </div>

    <PermissionNotice v-else-if="!leaveCan.read" what="see leave requests" />

    <!-- Leave is self-service, so it needs an Employee record pointing at this
         login. Nothing on this page works without one, and the fix is HR's. -->
    <div v-else-if="!employee" class="mx-auto mt-16 max-w-md text-center">
      <span class="lucide-user-x size-8 text-ink-gray-4" />
      <p class="mt-2 text-base-medium text-ink-gray-7">
        Your login isn't linked to an employee record
      </p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        Leave is requested against an employee, so ask HR to set the
        <span class="text-ink-gray-7">User account</span> field on yours to
        {{ user.name }}.
      </p>
    </div>

    <div v-else class="mx-auto max-w-3xl">
      <section v-if="balanceRows.length">
        <h2 class="text-base-medium text-ink-gray-8">Balance</h2>
        <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div
            v-for="row in balanceRows"
            :key="row.leaveType"
            class="rounded-4 border border-outline-gray-1 px-4 py-3"
          >
            <div class="truncate text-p-sm text-ink-gray-6">
              {{ row.leaveType }}
            </div>
            <div class="mt-1 text-xl font-semibold text-ink-gray-8">
              {{ row.remaining_leaves }}
              <span class="text-p-sm font-normal text-ink-gray-5">
                of {{ row.total_leaves }} left
              </span>
            </div>
            <div v-if="row.leaves_pending_approval" class="mt-1 text-p-sm text-ink-gray-5">
              {{ row.leaves_pending_approval }} awaiting approval
            </div>
          </div>
        </div>
      </section>

      <!-- No allocation means no balance to show; requests can still be made
           for types that don't need one, so this is a note, not a blocker. -->
      <Alert
        v-else-if="leaveDetails.isFinished"
        theme="gray"
        title="No leave allocated yet"
        description="Balances appear once HR allocates leave to you for this period. Leave types that don't draw on an allocation can still be requested."
      />

      <section class="mt-8">
        <div class="flex items-center justify-between">
          <h2 class="text-base-medium text-ink-gray-8">Requests</h2>
          <Button
            variant="ghost"
            icon-left="lucide-refresh-cw"
            label="Refresh"
            :loading="applications.loading"
            @click="refresh"
          />
        </div>

        <ErrorMessage
          v-if="applications.error"
          :message="applications.error.message"
          class="mt-3"
        />

        <div
          v-if="applications.loading && !applications.data"
          class="mt-3 space-y-2"
        >
          <Skeleton v-for="n in 3" :key="n" class="h-14 w-full rounded-4" />
        </div>

        <div
          v-else-if="applications.data?.length === 0"
          class="mt-3 rounded-4 border border-dashed border-outline-gray-2 px-4 py-10 text-center"
        >
          <p class="text-base-medium text-ink-gray-7">No leave requested yet</p>
          <p class="mt-1 text-p-sm text-ink-gray-5">
            Your requests and their outcomes show up here.
          </p>
        </div>

        <List
          v-else-if="applications.data"
          class="mt-3 list-row-px-3"
          :columns="{
            base: ['minmax(0,1fr)', '6rem'],
            md: ['minmax(0,1fr)', '10rem', '5rem', '6rem'],
          }"
          :row-height="56"
        >
          <ListHeader>
            <ListHeaderCell>Leave type</ListHeaderCell>
            <ListHeaderCell class="hidden md:flex">Dates</ListHeaderCell>
            <ListHeaderCell class="hidden md:flex justify-end">Days</ListHeaderCell>
            <ListHeaderCell class="justify-end">Status</ListHeaderCell>
          </ListHeader>
          <ListRows :items="applications.data" v-slot="{ item, value }">
            <ListRow :value="value">
              <ListCell>
                <div class="min-w-0">
                  <div class="truncate text-base text-ink-gray-8">
                    {{ item.leave_type }}
                  </div>
                  <div class="mt-0.5 truncate text-sm text-ink-gray-5">
                    {{ item.description || `Requested ${formatDate(item.posting_date)}` }}
                  </div>
                </div>
              </ListCell>
              <ListCell class="hidden md:flex">
                <span class="truncate text-base text-ink-gray-7">
                  {{ formatDateRange(item.from_date, item.to_date) }}
                </span>
              </ListCell>
              <ListCell class="hidden md:flex justify-end">
                <span class="text-base text-ink-gray-6">
                  {{ item.total_leave_days }}
                </span>
              </ListCell>
              <ListCell class="justify-end">
                <Badge :theme="leaveStatus(item).theme" variant="subtle">
                  {{ leaveStatus(item).label }}
                </Badge>
              </ListCell>
            </ListRow>
          </ListRows>
        </List>
      </section>
    </div>

    <LeaveRequestDialog
      v-if="employee"
      v-model:open="showRequest"
      :employee="employee"
      :balances="balances"
      @created="refresh"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Alert,
  Badge,
  Button,
  ErrorMessage,
  PageHeader,
  Skeleton,
} from 'frappe-ui'
import {
  List,
  ListCell,
  ListHeader,
  ListHeaderCell,
  ListRow,
  ListRows,
} from 'frappe-ui/list'
import { user } from '@/data/session'
import {
  leaveCan,
  leavePermissionsError,
  leavePermissionsLoaded,
  leaveStatus,
  myEmployee,
  myEmployeeLoaded,
  reloadLeavePermissions,
  reloadLeaveWorkflow,
  useLeaveDetails,
  useMyLeaveApplications,
} from '@/data/leave'
import { formatDate, formatDateRange } from '@/data/format'
import LeaveRequestDialog from '@/components/LeaveRequestDialog.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

const showRequest = ref(false)

const employee = computed(() => myEmployee.value)

// No employee argument: the server resolves the Employee behind the session
// itself, so this cannot ask for the wrong one -- or, before the employee has
// loaded, for everybody's.
const applications = useMyLeaveApplications()
const leaveDetails = useLeaveDetails(() => employee.value?.name)

// The employee arrives a beat after the page, so the balance call waits for it
// rather than firing with an empty name.
watch(
  () => employee.value?.name,
  (name) => {
    if (name) leaveDetails.reload()
  },
  { immediate: true },
)

const balances = computed(() => leaveDetails.data?.leave_allocation ?? {})

const balanceRows = computed(() =>
  Object.entries(balances.value).map(([leaveType, summary]) => ({
    leaveType,
    ...summary,
  })),
)

function refresh() {
  applications.reload()
  if (employee.value?.name) leaveDetails.reload()
  // A workflow's states are where a row's label and style come from.
  reloadLeaveWorkflow()
}
</script>
