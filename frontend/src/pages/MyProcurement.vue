<template>
  <PageHeader>
    <span class="text-lg font-semibold text-ink-gray-8">My requests</span>
    <Button
      v-if="procurementCan.request"
      variant="solid"
      icon-left="lucide-plus"
      label="New request"
      @click="showRequest = true"
    />
  </PageHeader>

  <div class="px-5 py-4">
    <div v-if="!procurementPermissionsLoaded" class="mx-auto max-w-3xl space-y-3">
      <Skeleton v-for="n in 3" :key="n" class="h-20 w-full rounded-4" />
    </div>

    <PermissionNotice
      v-else-if="!procurementCan.read"
      what="see procurement requests"
      who="a Purchase Manager or a System Manager"
    />

    <!-- Deliberately no "your login isn't linked to an employee" gate, unlike
         leave: a request is raised by a user, not against an employee record,
         so a bursar or an office manager without one can still raise it. The
         employee record, when there is one, only supplies defaults. -->
    <div v-else class="mx-auto max-w-3xl">
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

      <ErrorMessage
        v-if="requests.error"
        :message="requests.error.message"
        class="mt-3"
      />
      <ErrorMessage v-if="send.error" :message="send.error.message" class="mt-3" />

      <div v-if="requests.loading && !requests.data" class="mt-3 space-y-2">
        <Skeleton v-for="n in 3" :key="n" class="h-16 w-full rounded-4" />
      </div>

      <div
        v-else-if="requests.data?.length === 0"
        class="mt-3 rounded-4 border border-dashed border-outline-gray-2 px-4 py-10 text-center"
      >
        <p class="text-base-medium text-ink-gray-7">Nothing requested yet</p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Ask for something and it shows up here, with whatever your approver
          decides.
        </p>
      </div>

      <ul v-else-if="requests.data" class="mt-3 space-y-3">
        <li
          v-for="request in requests.data"
          :key="request.name"
          class="rounded-4 border border-outline-gray-1"
        >
          <button
            type="button"
            class="flex w-full items-start justify-between gap-3 p-4 text-left"
            @click="toggle(request.name)"
          >
            <div class="min-w-0">
              <div class="truncate text-base-medium text-ink-gray-8">
                {{ requestLabel(request) }}
              </div>
              <div class="mt-0.5 text-p-sm text-ink-gray-5">
                {{ request.name }} ·
                {{ pluralise(lineCount(request.name), 'line') }} ·
                needed {{ formatDate(request.schedule_date) }}
                <template v-if="request.total_estimated_cost">
                  · about
                  {{
                    formatCurrency(
                      request.total_estimated_cost,
                      request.currency,
                    )
                  }}
                </template>
              </div>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <Badge :theme="procurementStatus(request).theme" variant="subtle">
                {{ procurementStatus(request).label }}
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
              <div>
                <dt class="text-ink-gray-5">Purpose</dt>
                <dd class="text-ink-gray-8">{{ request.purpose }}</dd>
              </div>
              <div v-if="request.justification" class="sm:col-span-2">
                <dt class="text-ink-gray-5">Why it's needed</dt>
                <dd class="whitespace-pre-line text-ink-gray-8">
                  {{ request.justification }}
                </dd>
              </div>
            </dl>

            <Alert
              v-if="request.status === 'Rejected'"
              class="mt-4"
              theme="red"
              title="Turned down"
              :description="
                request.rejection_reason || 'No reason was recorded.'
              "
            />

            <!-- A draft is one made in the desk, or one whose send failed
                 after the save. Either way it is going nowhere until it is
                 handed over, so the way to do that is here. -->
            <div
              v-if="request.status === 'Draft'"
              class="mt-4 flex items-center gap-2"
            >
              <Button
                variant="solid"
                icon-left="lucide-send"
                label="Send for approval"
                :loading="sending === request.name"
                :disabled="!request.approver || Boolean(sending)"
                @click="sendRequest(request)"
              />
              <span v-if="!request.approver" class="text-p-sm text-ink-gray-5">
                Name an approver in the desk first.
              </span>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <ProcurementRequestDialog
      v-model:open="showRequest"
      :employee="myEmployee"
      @created="refresh"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  Alert,
  Badge,
  Button,
  ErrorMessage,
  PageHeader,
  Skeleton,
  toast,
} from 'frappe-ui'
import { user } from '@/data/session'
import { myEmployee } from '@/data/leave'
import {
  procurementCan,
  procurementPermissionsLoaded,
  procurementStatus,
  reloadProcurementPermissions,
  requestLabel,
  useMyProcurementRequests,
  useProcurementRequestLines,
  useSendProcurementRequest,
  type ProcurementRequestRow,
} from '@/data/procurement'
import { formatCurrency, formatDate, pluralise } from '@/data/format'
import ProcurementLines from '@/components/ProcurementLines.vue'
import ProcurementRequestDialog from '@/components/ProcurementRequestDialog.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

const showRequest = ref(false)
const expanded = ref('')
const sending = ref('')

const requests = useMyProcurementRequests(() => user.value.name)

// Every request's lines in one call, so the count in a collapsed row is right
// before it is opened — and opening one costs nothing. It refetches itself
// when the set of requests changes, which is why `refresh` below does not ask
// it to: two overlapping fetches abort each other.
const { byRequest } = useProcurementRequestLines(() =>
  (requests.data ?? []).map((request) => request.name),
)

function lineCount(name: string) {
  return byRequest.value.get(name)?.length ?? 0
}

function toggle(name: string) {
  expanded.value = expanded.value === name ? '' : name
}

const send = useSendProcurementRequest()

async function sendRequest(request: ProcurementRequestRow) {
  sending.value = request.name
  try {
    const sent = await send.submit({ name: request.name })
    // `submit` resolves null on failure; the reason renders above the list.
    if (!sent) return
    toast.success(`Sent to ${request.approver_name || request.approver}`)
    refresh()
  } finally {
    sending.value = ''
  }
}

function refresh() {
  requests.reload()
  // The approver's own sidebar badge counts pending requests, and a requester
  // can be an approver too.
  reloadProcurementPermissions()
}
</script>
