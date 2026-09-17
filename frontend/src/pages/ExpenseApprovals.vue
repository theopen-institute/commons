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
          :loading="claims.loading"
          @click="refresh"
        />
      </div>
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

    <div v-else-if="!expensePermissionsLoaded" class="mx-auto max-w-3xl space-y-2">
      <Skeleton v-for="n in 3" :key="n" class="h-28 w-full rounded-4" />
    </div>

    <PermissionNotice v-else-if="!expenseCan.approve" what="approve expenses" />

    <div v-else class="mx-auto max-w-3xl">
      <ErrorMessage
        v-if="claims.error"
        :message="claims.error.message"
        class="mb-3"
      />
      <ErrorMessage
        v-if="decision.error"
        :message="decision.error.message"
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
               An approver may allow less than was claimed; the figures they set
               travel with the decision in one call. -->
          <ExpenseClaimLines
            v-model:sanctioned="sanctioned[claim.name]"
            class="mt-3"
            :lines="byClaim.get(claim.name) ?? []"
            :currency="claim.currency"
            :settled="claim.docstatus === 1"
            :editable="Boolean(claim.can_decide)"
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

          <!-- Drawn from the server's answer for this row, not from its
               docstatus: whether this user settles this claim is a question
               only the server can settle. -->
          <div v-if="claim.can_decide" class="mt-4 flex flex-wrap items-center gap-2">
            <Button
              v-for="button in buttonsFor(claim)"
              :key="button.decision"
              :variant="button.variant"
              :theme="button.theme"
              :label="button.label"
              :icon-left="button.icon"
              :loading="deciding === `${claim.name}:${button.decision}`"
              :disabled="Boolean(deciding)"
              @click="decide(claim, button)"
            />
            <span
              v-if="trimmed(claim)"
              class="ml-auto text-p-sm text-ink-amber-3"
            >
              Allowing {{ formatCurrency(allowedTotal(claim), claim.currency) }}
            </span>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
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
  expenseCan,
  expensePermissionsError,
  expensePermissionsLoaded,
  expenseStatus,
  reloadExpensePermissions,
  useExpenseApprovalQueue,
  useExpenseClaimLines,
  useExpenseDecision,
  type DecisionButton,
  type ExpenseClaimRow,
} from '@/data/expense'
import { formatCurrency, formatDate, pluralise } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ExpenseClaimLines from '@/components/ExpenseClaimLines.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

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

const decision = useExpenseDecision()

/**
 * What this approver is allowing, per claim and then per expense row.
 *
 * Only the rows they actually changed — see `ExpenseClaimLines`, which keys
 * them by the expense's own name. Cleared whenever the queue reloads: figures
 * typed against a claim that has since been edited would be settling the wrong
 * expense, and the server refuses a row name the claim no longer has rather
 * than guessing which one was meant.
 */
const sanctioned = reactive<Record<string, Record<string, number>>>({})

watch(
  () => claims.data,
  (rows) => {
    for (const name of Object.keys(sanctioned)) delete sanctioned[name]
    for (const row of rows ?? []) sanctioned[row.name] = {}
  },
)

// Keyed by claim and decision so only the button that was pressed spins.
const deciding = ref('')

// The outcomes *this row* accepts, which the server settles per row: a
// workflow's permitted transitions where one is running, and otherwise the
// vocabulary less anything HRMS would refuse — a claim of the approver's own,
// on a site that forbids settling it, offers nothing at all.
function buttonsFor(claim: ExpenseClaimRow) {
  return decisionButtons(claim.actions, expenseCan.value.decisions)
}

function lineCount(name: string) {
  return byClaim.value.get(name)?.length ?? 0
}

/** Whether this approver has typed a figure other than the claim's own. */
function trimmed(claim: ExpenseClaimRow) {
  return Object.keys(sanctioned[claim.name] ?? {}).length > 0
}

/** What the claim would settle at, as it stands on screen. The figure that is
 *  actually written is the server's, from the same per-row amounts. */
function allowedTotal(claim: ExpenseClaimRow) {
  const changed = sanctioned[claim.name] ?? {}
  return (byClaim.value.get(claim.name) ?? []).reduce(
    (total, line) => total + (changed[line.name] ?? line.sanctioned_amount),
    0,
  )
}

const pendingCount = computed(() =>
  tab.value === 'pending'
    ? (claims.data?.length ?? 0)
    : expenseCan.value.pending_approvals,
)

// Both numbers stop at the same ceiling, so a queue that is full says so rather
// than quietly claiming that is all there is.
const pendingAtCeiling = computed(
  () => pendingCount.value >= expenseCan.value.page_length,
)

async function decide(claim: ExpenseClaimRow, button: DecisionButton) {
  // Whether an outcome needs confirming arrives with it. The claim is written
  // with that decision on it, and that is not something the page can walk back
  // on the approver's behalf.
  if (button.confirm) {
    dialog.danger({
      title: `${button.label} claim`,
      message: `${button.label} ${claim.employee_name}'s claim for ${formatCurrency(claim.total_claimed_amount, claim.currency)}? They are notified, and the claim is settled with that decision.`,
      confirmLabel: `${button.label} claim`,
      onConfirm: () => submitDecision(claim, button.decision),
    })
    return
  }
  await submitDecision(claim, button.decision)
}

async function submitDecision(claim: ExpenseClaimRow, verdict: string) {
  deciding.value = `${claim.name}:${verdict}`
  const changed = sanctioned[claim.name] ?? {}
  try {
    const result = await decision.submit({
      name: claim.name,
      decision: verdict,
      // Left out entirely when nothing was trimmed, so the common decision
      // carries no figures for the server to check row names against.
      ...(Object.keys(changed).length
        ? { sanctioned: JSON.stringify(changed) }
        : {}),
    })
    // `submit` resolves null on failure; the reason renders above the list.
    if (!result) throw decision.error ?? new Error('Could not save the decision')
    // The outcome in the server's own words, so a site whose workflow calls it
    // something else is quoted rather than paraphrased, and the amount as the
    // server totalled it rather than as the page added it up.
    toast.success(
      `${claim.employee_name}'s claim is now ${result.status} at ${formatCurrency(result.total_sanctioned_amount, result.currency)}`,
    )
    refresh()
  } finally {
    deciding.value = ''
  }
}

function refresh() {
  claims.reload()
  // The sidebar badge counts pending approvals, so it moves too.
  reloadExpensePermissions()
}
</script>
