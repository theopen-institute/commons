<template>
  <AppPageHeader>
    <div class="flex min-w-0 items-center gap-3">
      <span class="text-lg font-semibold text-ink-gray-8">Expense Claim</span>
      <RequestTabs section="expense" />
    </div>
    <template #actions>
      <Button
        v-if="employee && expenseCan.request"
        variant="solid"
        icon-left="lucide-plus"
        label="Claim expenses"
        @click="showClaim = true"
      />
    </template>
  </AppPageHeader>

  <div class="px-5 py-4">
    <!-- The permission answer refused rather than arrived: say so, instead of
         leaving a skeleton up for a reply that is never coming. -->
    <div v-if="expensePermissionsError" class="mx-auto max-w-3xl">
      <ErrorMessage :message="expensePermissionsError.message" class="mb-3" />
      <Button
        label="Try again"
        variant="subtle"
        @click="reloadExpensePermissions()"
      />
    </div>

    <div
      v-else-if="!myEmployeeLoaded || !expensePermissionsLoaded"
      class="mx-auto max-w-3xl space-y-3"
    >
      <Skeleton v-for="n in 3" :key="n" class="h-20 w-full rounded-4" />
    </div>

    <PermissionNotice v-else-if="!expenseCan.read" what="see expense claims" />

    <!-- A claim is raised against an Employee record, so nothing on this page
         works without one — but who to ask depends on why it is absent, which
         is why the server distinguishes the two. See
         `session_employee_access`. -->
    <div
      v-else-if="!employee && expenseCan.employee_access === 'forbidden'"
      class="mx-auto mt-16 max-w-md text-center"
    >
      <span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
      <p class="mt-2 text-base-medium text-ink-gray-7">
        Your employee record isn't available to you
      </p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        It exists and it's yours, but your account can't read it — so expenses
        can't be claimed against it. Ask whoever administers permissions here,
        not HR.
      </p>
    </div>

    <div v-else-if="!employee" class="mx-auto mt-16 max-w-md text-center">
      <span class="lucide-user-x mx-auto size-8 text-ink-gray-4" />
      <p class="mt-2 text-base-medium text-ink-gray-7">
        Your login isn't linked to an employee record
      </p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        Expenses are claimed against an employee, so ask HR to set the
        <span class="text-ink-gray-7">User account</span> field on yours to
        {{ user.name }}.
      </p>
    </div>

    <div v-else class="mx-auto max-w-3xl">
      <!-- HRMS's own totals, over every claim this employee has ever made —
           not a sum of the twenty rows below, which is a different number. -->
      <section v-if="summaryRows.length">
        <h2 class="text-base-medium text-ink-gray-8">Totals</h2>
        <div class="mt-3 grid gap-3 sm:grid-cols-3">
          <div
            v-for="row in summaryRows"
            :key="row.label"
            class="rounded-4 border border-outline-gray-1 px-4 py-3"
          >
            <div class="truncate text-p-sm text-ink-gray-6">{{ row.label }}</div>
            <div class="mt-1 text-xl font-semibold text-ink-gray-8">
              {{ formatCurrency(row.amount, summary.data?.currency) }}
            </div>
            <div v-if="row.note" class="mt-1 text-p-sm text-ink-gray-5">
              {{ row.note }}
            </div>
          </div>
        </div>
      </section>

      <section class="mt-8">
        <div class="flex items-center justify-between">
          <h2 class="text-base-medium text-ink-gray-8">Claims</h2>
          <Button
            variant="ghost"
            icon-left="lucide-refresh-cw"
            label="Refresh"
            :loading="claims.loading"
            @click="refresh"
          />
        </div>

        <ErrorMessage
          v-if="claims.error"
          :message="claims.error.message"
          class="mt-3"
        />
        <ErrorMessage
          v-if="claimLines.error"
          :message="claimLines.error.message"
          class="mt-3"
        />

        <div v-if="claims.loading && !claims.data" class="mt-3 space-y-2">
          <Skeleton v-for="n in 3" :key="n" class="h-16 w-full rounded-4" />
        </div>

        <div
          v-else-if="claims.data?.length === 0"
          class="mt-3 rounded-4 border border-dashed border-outline-gray-2 px-4 py-10 text-center"
        >
          <p class="text-base-medium text-ink-gray-7">Nothing claimed yet</p>
          <p class="mt-1 text-p-sm text-ink-gray-5">
            Claim what you spent and follow it here until you're paid back.
          </p>
        </div>

        <ul v-else-if="claims.data" class="mt-3 space-y-3">
          <li
            v-for="claim in claims.data"
            :key="claim.name"
            class="rounded-4 border border-outline-gray-1"
          >
            <!-- Two lines on a phone, one from `sm` up: beside a title and a
                 summary line in 390px of viewport, the status and the chevron
                 leave the text about half the row. -->
            <button
              type="button"
              class="flex w-full flex-col items-start gap-2 p-4 text-left sm:flex-row sm:justify-between sm:gap-3"
              @click="toggle(claim.name)"
            >
              <div class="w-full min-w-0 sm:w-auto">
                <div class="truncate text-base-medium text-ink-gray-8">
                  {{ formatCurrency(claim.total_claimed_amount, claim.currency) }}
                  claimed
                </div>
                <div class="mt-0.5 text-p-sm text-ink-gray-5">{{ claim.name }}</div>
                <!-- Each fact answers a separate question and is read one at a
                     time, so they are separate elements: each stays whole when
                     the row wraps, which at 390px it does. -->
                <div
                  class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-p-sm text-ink-gray-5"
                >
                  <span>{{ pluralise(lineCount(claim.name), 'expense') }}</span>
                  <span>{{ formatDate(claim.posting_date) }}</span>
                  <span v-if="allowedDiffers(claim)">
                    {{
                      formatCurrency(claim.total_sanctioned_amount, claim.currency)
                    }}
                    allowed
                  </span>
                </div>
              </div>
              <!-- Still hard against the right edge on its own line: the chevron
                   is the reveal affordance, and it should not move to the middle
                   of the card when the row wraps. -->
              <div
                class="flex w-full shrink-0 items-center justify-between gap-2 sm:w-auto sm:justify-end"
              >
                <Badge v-if="reimbursement(claim)" theme="gray" variant="subtle">
                  {{ reimbursement(claim) }}
                </Badge>
                <Badge :theme="expenseStatus(claim).theme" variant="subtle">
                  {{ expenseStatus(claim).label }}
                </Badge>
                <span
                  class="size-4 text-ink-gray-5"
                  :class="
                    expanded === claim.name
                      ? 'lucide-chevron-up'
                      : 'lucide-chevron-down'
                  "
                />
              </div>
            </button>

            <div
              v-if="expanded === claim.name"
              class="border-t border-outline-gray-1 p-4"
            >
              <ExpenseClaimLines
                :lines="byClaim.get(claim.name) ?? []"
                :currency="claim.currency"
                :settled="claim.docstatus === 1"
              />

              <dl class="mt-4 grid gap-3 text-p-sm sm:grid-cols-2">
                <div>
                  <dt class="text-ink-gray-5">Approver</dt>
                  <dd class="text-ink-gray-8">
                    {{ claim.expense_approver || 'Not named' }}
                  </dd>
                </div>
                <div v-if="claim.docstatus === 1">
                  <dt class="text-ink-gray-5">Reimbursed</dt>
                  <dd class="text-ink-gray-8">
                    {{
                      formatCurrency(claim.total_amount_reimbursed, claim.currency)
                    }}
                    of
                    {{ formatCurrency(claim.grand_total, claim.currency) }}
                  </dd>
                </div>
                <div v-if="claim.remark" class="sm:col-span-2">
                  <dt class="text-ink-gray-5">Notes</dt>
                  <dd class="whitespace-pre-line text-ink-gray-8">
                    {{ claim.remark }}
                  </dd>
                </div>
              </dl>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <ExpenseClaimDialog
      v-if="employee"
      v-model:open="showClaim"
      :employee="employee.name"
      @created="refresh"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, Skeleton } from 'frappe-ui'
import { user } from '@/data/session'
import {
  expenseCan,
  expensePermissionsError,
  expensePermissionsLoaded,
  expenseStatus,
  myEmployee,
  myEmployeeLoaded,
  reimbursement,
  reloadExpensePermissions,
  useExpenseClaimLines,
  useExpenseClaimSummary,
  useMyExpenseClaims,
  type ExpenseClaimRow,
} from '@/data/expense'
import { formatCurrency, formatDate, pluralise } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ExpenseClaimDialog from '@/components/ExpenseClaimDialog.vue'
import ExpenseClaimLines from '@/components/ExpenseClaimLines.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'
import RequestTabs from '@/components/RequestTabs.vue'

const showClaim = ref(false)
const expanded = ref('')

const employee = computed(() => myEmployee.value)

const claims = useMyExpenseClaims()

// Every claim's expenses in one call, so the count in a collapsed row is right
// before it is opened — and opening one costs nothing. It refetches itself
// whenever the claim list refreshes, which is why `refresh` below does not ask
// it to: two overlapping fetches abort each other.
const { lines: claimLines, byClaim } = useExpenseClaimLines(() =>
  (claims.data ?? []).map((claim) => claim.name),
)

const summary = useExpenseClaimSummary()

// The employee arrives a beat after the page, and HRMS's summary endpoint
// refuses a session with no employee behind it — so it waits for one rather
// than firing into a throw.
watch(
  () => employee.value?.name,
  (name) => {
    if (name) summary.reload()
  },
  { immediate: true },
)

const summaryRows = computed(() => {
  const data = summary.data
  if (!data) return []
  const rows: { label: string; amount: number; note?: string }[] = []
  if (data.total_pending_amount) {
    rows.push({ label: 'Awaiting a decision', amount: data.total_pending_amount })
  }
  if (data.total_approved_amount) {
    const claimed = data.total_claimed_in_approved ?? 0
    rows.push({
      label: 'Approved',
      amount: data.total_approved_amount,
      // Only when the two differ: saying "of X claimed" when nothing was
      // trimmed is a second copy of the same number.
      note:
        claimed > data.total_approved_amount
          ? `of ${formatCurrency(claimed, data.currency)} claimed`
          : undefined,
    })
  }
  if (data.total_rejected_amount) {
    rows.push({ label: 'Declined', amount: data.total_rejected_amount })
  }
  return rows
})

function lineCount(name: string) {
  return byClaim.value.get(name)?.length ?? 0
}

function toggle(name: string) {
  expanded.value = expanded.value === name ? '' : name
}

/** Whether the approver allowed something other than what was asked for. Until
 *  a claim is settled the two are the same number, and printing both says
 *  nothing. */
function allowedDiffers(claim: ExpenseClaimRow) {
  return (
    claim.docstatus === 1 &&
    claim.total_sanctioned_amount !== claim.total_claimed_amount
  )
}

function refresh() {
  claims.reload()
  if (employee.value?.name) summary.reload()
}
</script>
