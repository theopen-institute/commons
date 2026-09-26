<template>
  <AppPageHeader>
    <div class="flex min-w-0 items-center gap-3">
      <span class="text-lg font-semibold text-ink-gray-8">Expense Claim</span>
      <RequestTabs section="expense" />
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
          :loading="claims.loading"
          @click="refresh"
        />
      </div>
    </template>
  </AppPageHeader>

  <div class="px-5 py-4">
    <RequestGate
      :error="expensePermissionsError"
      :loaded="expensePermissionsLoaded"
      :permitted="expenseCan.approve"
      what="approve expenses"
      row-class="h-28"
      @retry="reloadExpensePermissions()"
    >
      <div class="mx-auto max-w-3xl">
        <ErrorMessage
          v-if="claims.error"
          :message="claims.error.message"
          class="mb-3"
        />
        <ErrorMessage
          v-if="claimLines.error"
          :message="claimLines.error.message"
          class="mb-3"
        />

        <div v-if="claims.loading && !claims.data" class="space-y-2">
          <Skeleton v-for="n in 3" :key="n" class="h-28 w-full rounded-4" />
        </div>

        <div
          v-else-if="claims.data?.length === 0"
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
                ? 'Expense claims naming you as approver land here.'
                : 'Claims you approve or decline move here.'
            }}
          </p>
        </div>

        <ul v-else-if="claims.data" class="space-y-3">
          <li
            v-for="claim in claims.data"
            :key="claim.name"
            class="rounded-4 border border-outline-gray-1 p-4"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="flex min-w-0 items-start gap-3">
                <Avatar :label="claim.employee_name" size="lg" />
                <div class="min-w-0">
                  <div class="truncate text-base-medium text-ink-gray-8">
                    {{ claim.employee_name }}
                  </div>
                  <div class="mt-0.5 text-p-sm text-ink-gray-5">
                    {{ formatCurrency(claim.total_claimed_amount, claim.currency) }}
                    ·
                    {{ pluralise(lineCount(claim.name), 'expense') }}
                    ·
                    {{ formatDate(claim.posting_date) }}
                  </div>
                </div>
              </div>
              <Badge :theme="expenseStatus(claim).theme" variant="subtle">
                {{ expenseStatus(claim).label }}
              </Badge>
            </div>

            <!-- The expenses themselves, which is what there is to decide about.
                 Read-only here: an approver who allows less than was claimed
                 types it in the review dialog, where the figures are a draft
                 until the decision that carries them. -->
            <ExpenseClaimLines
              class="mt-3"
              :lines="byClaim.get(claim.name) ?? []"
              :currency="claim.currency"
              :settled="claim.docstatus === 1"
            />

            <p
              v-if="claim.remark"
              class="mt-3 whitespace-pre-line text-p-base text-ink-gray-7"
            >
              {{ claim.remark }}
            </p>

            <!-- Whose decision this is, when it is not this user's own queue. -->
            <p
              v-if="claim.expense_approver && claim.expense_approver !== user.name"
              class="mt-3 text-p-sm text-ink-gray-5"
            >
              Assigned to
              {{ claim.expense_approver_name || claim.expense_approver }}
            </p>
            <p v-else-if="!claim.expense_approver" class="mt-3 text-p-sm text-ink-gray-5">
              Nobody was named as approver on this claim.
            </p>

            <!-- Only opens the claim: the decision, and any trimming of what
                 is allowed, happen in the dialog and are written by a button
                 pressed there. Offered where the server says this user settles
                 this claim. -->
            <div v-if="claim.can_decide" class="mt-4 flex justify-end">
              <Button
                variant="subtle"
                icon-left="lucide-eye"
                label="Review"
                @click="review.show(claim)"
              />
            </div>
          </li>
        </ul>
      </div>
    </RequestGate>

    <ExpenseReviewDialog
      v-model:open="review.open"
      :claim="review.row"
      :lines="review.row ? (byClaim.get(review.row.name) ?? []) : []"
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
  expenseCan,
  expensePermissionsError,
  expensePermissionsLoaded,
  expenseStatus,
  reloadExpensePermissions,
  useExpenseApprovalQueue,
  useExpenseClaimLines,
} from '@/data/requests/expense'
import { useReviewTarget } from '@/data/requests/review'
import { formatCurrency, formatDate, pluralise } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ExpenseClaimLines from '@/components/ExpenseClaimLines.vue'
import ExpenseReviewDialog from '@/components/ExpenseReviewDialog.vue'
import RequestGate from '@/components/RequestGate.vue'
import RequestTabs from '@/components/RequestTabs.vue'

const tab = ref<'pending' | 'decided'>('pending')

// Held back until the answer arrives, so the page never flashes controls (or a
// refusal) it then takes away.
const canApprove = computed(
  () => expensePermissionsLoaded.value && expenseCan.value.approve,
)

const claims = useExpenseApprovalQueue(() => tab.value === 'decided')

const { lines: claimLines, byClaim } = useExpenseClaimLines(() =>
  (claims.data ?? []).map((claim) => claim.name),
)

// The claim open for review, if any. Deciding it — the buttons, the amounts
// being allowed, the reason a decision was refused — is the dialog's, and so is
// the draft of those amounts: held there, per claim, a reload of this list
// cannot wipe it. The page only refreshes once a decision reaches the server.
const review = useReviewTarget(() => claims.data)

function lineCount(name: string) {
  return byClaim.value.get(name)?.length ?? 0
}

function refresh() {
  claims.reload()
  // The sidebar badge counts pending approvals, so it moves too.
  reloadExpensePermissions()
}
</script>
