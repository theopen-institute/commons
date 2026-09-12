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
        @click="refresh"
      />
    </div>
  </PageHeader>

  <div class="px-5 py-4">
    <div v-if="!procurementPermissionsLoaded" class="mx-auto max-w-3xl space-y-2">
      <Skeleton v-for="n in 3" :key="n" class="h-40 w-full rounded-4" />
    </div>

    <PermissionNotice
      v-else-if="!procurementCan.approve"
      what="approve procurement requests"
      who="a Purchase Manager or a System Manager"
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
        <Skeleton v-for="n in 3" :key="n" class="h-40 w-full rounded-4" />
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
          {{
            tab === 'pending' ? 'Nothing waiting on you' : 'Nothing decided yet'
          }}
        </p>
        <p class="text-p-sm text-ink-gray-5">
          {{
            tab === 'pending'
              ? 'Procurement requests naming you as approver land here.'
              : 'Requests you approve or turn down move here.'
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
              <Avatar :label="requesterName(request)" size="lg" />
              <div class="min-w-0">
                <div class="truncate text-base-medium text-ink-gray-8">
                  {{ requestLabel(request) }}
                </div>
                <div class="mt-0.5 text-p-sm text-ink-gray-5">
                  {{ requesterName(request) }} ·
                  {{ request.purpose }} · needed
                  {{ formatDate(request.schedule_date) }}
                  <template v-if="request.department">
                    · {{ request.department }}
                  </template>
                </div>
              </div>
            </div>
            <div class="text-right">
              <Badge :theme="procurementStatus(request).theme" variant="subtle">
                {{ procurementStatus(request).label }}
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
            v-if="request.status === 'Rejected' && request.rejection_reason"
            class="mt-3"
            theme="red"
            title="Turned down"
            :description="request.rejection_reason"
          />

          <div v-if="isPending(request)" class="mt-4 flex flex-wrap items-center gap-2">
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
              label="Turn down"
              icon-left="lucide-x"
              :loading="deciding === `${request.name}:Rejected`"
              :disabled="Boolean(deciding)"
              @click="decide(request, 'Rejected')"
            />
            <span class="ml-auto text-p-sm text-ink-gray-5">
              Requested {{ formatDate(request.transaction_date) }}
            </span>
          </div>
        </li>
      </ul>
    </div>

    <!-- A reason is optional on the doctype but asked for here: a turned-down
         request is the one outcome the requester has to act on, and "no" with
         nothing after it tells them nothing. -->
    <Dialog
      v-model:open="showReject"
      title="Turn down this request"
      :actions="rejectActions"
    >
      <div class="space-y-4">
        <!-- "sees", not "is told": nothing emails them. The reason shows on
             their own list, which is the whole reason to write one. -->
        <p class="text-p-base text-ink-gray-6">
          {{ rejectTarget ? requesterName(rejectTarget) : 'The requester' }}
          sees this on their requests, and it closes the request — they would
          have to raise a new one.
        </p>
        <FormControl
          v-model="rejectReason"
          type="textarea"
          label="Why"
          :rows="3"
          placeholder="Over budget this term, buy from the framework instead, …"
        />
      </div>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Dialog,
  ErrorMessage,
  FormControl,
  PageHeader,
  Skeleton,
  TabButtons,
  toast,
  type DialogAction,
} from 'frappe-ui'
import { user } from '@/data/session'
import {
  procurementCan,
  procurementPermissionsLoaded,
  procurementStatus,
  reloadProcurementPermissions,
  requestLabel,
  useProcurementApprovals,
  useProcurementDecision,
  useProcurementRequestLines,
  type ProcurementRequestRow,
} from '@/data/procurement'
import { formatCurrency, formatDate } from '@/data/format'
import ProcurementLines from '@/components/ProcurementLines.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

const tab = ref<'pending' | 'decided'>('pending')

// Held back until the answer arrives, so the page never flashes controls (or a
// refusal) it then takes away.
const canApprove = computed(
  () => procurementPermissionsLoaded.value && procurementCan.value.approve,
)

const requests = useProcurementApprovals({
  decided: () => tab.value === 'decided',
  approver: () => user.value.name,
})

const { byRequest } = useProcurementRequestLines(() =>
  (requests.data ?? []).map((request) => request.name),
)

const decision = useProcurementDecision()

// Keyed by request and decision so only the button that was pressed spins.
const deciding = ref('')

const showReject = ref(false)
const rejectReason = ref('')
const rejectTarget = ref<ProcurementRequestRow | null>(null)

const pendingCount = computed(() =>
  tab.value === 'pending'
    ? (requests.data?.length ?? 0)
    : procurementCan.value.pending_approvals,
)

function requesterName(request: ProcurementRequestRow) {
  return request.requested_by ?? 'Someone'
}

function isPending(request: ProcurementRequestRow) {
  return request.docstatus === 0 && request.status === 'Pending Approval'
}

function decide(
  request: ProcurementRequestRow,
  verdict: 'Approved' | 'Rejected',
) {
  if (verdict === 'Rejected') {
    rejectTarget.value = request
    rejectReason.value = ''
    showReject.value = true
    return
  }
  submitDecision(request, verdict)
}

const rejectActions = computed<DialogAction[]>(() => [
  {
    label: 'Turn it down',
    variant: 'solid',
    theme: 'red',
    onClick: async ({ close }) => {
      const request = rejectTarget.value
      if (!request) return
      const done = await submitDecision(request, 'Rejected', rejectReason.value)
      if (done) close()
    },
  },
])

async function submitDecision(
  request: ProcurementRequestRow,
  verdict: 'Approved' | 'Rejected',
  reason?: string,
): Promise<boolean> {
  deciding.value = `${request.name}:${verdict}`
  try {
    const result = await decision.submit({
      name: request.name,
      decision: verdict,
      reason: reason || undefined,
    })
    // `submit` resolves null on failure; the reason renders above the list.
    if (!result) return false
    toast.success(
      verdict === 'Approved'
        ? `${requestLabel(request)} approved`
        : `${requestLabel(request)} turned down`,
    )
    refresh()
    return true
  } finally {
    deciding.value = ''
  }
}

function refresh() {
  requests.reload()
  // The sidebar badge counts pending approvals, so it moves too.
  reloadProcurementPermissions()
}
</script>
