<!--
  One expense claim, and the only place on the approvals page where it is
  decided or its figures changed. See `RequestReviewDialog` for why the list no
  longer decides.

  An approver may allow less than was claimed. The figures they type are a
  draft held here, for this claim only, and travel with the decision in one
  call; nothing is written before a decision button is pressed. The draft used
  to live on the page and was cleared whenever the queue reloaded — which every
  decision on any other claim did — so figures typed against one claim went
  while the approver was settling another.
-->

<template>
  <RequestReviewDialog
    v-model:open="open"
    :title="claim ? `${claim.employee_name}'s expense claim` : 'Expense claim'"
    :message="claim ? `Claimed ${formatDate(claim.posting_date)}` : ''"
    :buttons="reviewButtons"
    :running="deciding"
    :error="attempted ? decision.error?.message : null"
    :dismissible="!trimmed"
    :gone="gone"
    @choose="choose"
  >
    <template v-if="claim">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="flex min-w-0 items-start gap-3">
          <Avatar :label="claim.employee_name" size="lg" />
          <div class="min-w-0">
            <div class="truncate text-base-medium text-ink-gray-8">
              {{ formatCurrency(claim.total_claimed_amount, claim.currency) }}
            </div>
            <div class="mt-0.5 text-p-sm text-ink-gray-5">
              {{ pluralise(lines.length, 'expense') }}
              <template v-if="claim.department"> · {{ claim.department }}</template>
            </div>
          </div>
        </div>
        <Badge :theme="expenseStatus(claim).theme" variant="subtle">
          {{ expenseStatus(claim).label }}
        </Badge>
      </div>

      <!-- The expenses themselves, which is what there is to decide about. -->
      <ExpenseClaimLines
        v-model:sanctioned="sanctioned"
        :lines="lines"
        :currency="claim.currency"
        :settled="claim.docstatus === 1"
        :editable="editable"
      />

      <p
        v-if="claim.remark"
        class="whitespace-pre-line text-p-base text-ink-gray-7"
      >
        {{ claim.remark }}
      </p>

      <!-- Whose decision this is, when it is not this user's own queue. -->
      <p
        v-if="claim.expense_approver && claim.expense_approver !== user.name"
        class="text-p-sm text-ink-gray-5"
      >
        Assigned to
        {{ claim.expense_approver_name || claim.expense_approver }}
      </p>
      <p v-else-if="!claim.expense_approver" class="text-p-sm text-ink-gray-5">
        Nobody was named as approver on this claim.
      </p>
    </template>

    <template v-if="trimmed" #footer>
      <Button
        variant="ghost"
        label="Undo changes"
        :disabled="Boolean(deciding)"
        @click="sanctioned = {}"
      />
      <span class="text-p-sm text-ink-amber-3">
        Allowing {{ formatCurrency(allowedTotal, claim?.currency) }}
      </span>
    </template>
  </RequestReviewDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Avatar, Badge, Button, toast } from 'frappe-ui'
import { user } from '@/data/session'
import {
  decisionButtons,
  expenseCan,
  expenseStatus,
  useExpenseDecision,
  type ExpenseClaimLine,
  type ExpenseClaimRow,
} from '@/data/requests/expense'
import { useRowDecision } from '@/data/requests/review'
import { formatCurrency, formatDate, pluralise } from '@/data/format'
import ExpenseClaimLines from './ExpenseClaimLines.vue'
import RequestReviewDialog from './RequestReviewDialog.vue'

const props = defineProps<{
  claim: ExpenseClaimRow | null
  lines: ExpenseClaimLine[]
  /** The list no longer has this claim. See `useReviewTarget`. */
  gone?: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

/** After every decision that reached the server, written or refused. */
const emit = defineEmits<{ settled: [] }>()

// The dialog's own call, so the reason a decision was refused renders beside
// the figures and buttons it was refused over.
const decision = useExpenseDecision()

/**
 * What this approver is allowing, per expense row — only the rows actually
 * changed, keyed by the row's own name. See `ExpenseClaimLines`.
 */
const sanctioned = ref<Record<string, number>>({})

// A call keeps its last error until it is next submitted, and a reason left
// over from another claim is not an answer about this one.
const attempted = ref(false)

// A fresh draft each time a claim is opened. Keyed on the claim's name, not
// its row: the row is replaced every time the queue reloads, and a reload is
// not a reason to throw away what was typed.
watch(
  () => [open.value, props.claim?.name],
  ([isOpen]) => {
    attempted.value = false
    if (isOpen) sanctioned.value = {}
  },
)

// What a reload does take away is a row the claim no longer has. The server
// refuses a row name the claim does not carry rather than guess which expense
// was meant, so a figure for one that has gone would only fail the decision.
// An empty list is a fetch still in flight, not a claim with no expenses.
watch(
  () => props.lines,
  (lines) => {
    if (!lines.length) return
    const names = new Set(lines.map((line) => line.name))
    const kept = Object.fromEntries(
      Object.entries(sanctioned.value).filter(([name]) => names.has(name)),
    )
    if (Object.keys(kept).length !== Object.keys(sanctioned.value).length) {
      sanctioned.value = kept
    }
  },
)

const editable = computed(() => Boolean(props.claim?.can_decide) && !props.gone)

/** Whether this approver has typed a figure other than the claim's own. */
const trimmed = computed(() => Object.keys(sanctioned.value).length > 0)

/** What the claim would settle at, as it stands on screen. The figure that is
 *  actually written is the server's, from the same per-row amounts. */
const allowedTotal = computed(() =>
  props.lines.reduce(
    (total, line) => total + (sanctioned.value[line.name] ?? line.sanctioned_amount),
    0,
  ),
)

const { deciding, decide } = useRowDecision({
  call: decision,
  params: (claim: ExpenseClaimRow, verdict) => ({
    name: claim.name,
    decision: verdict,
    // Left out entirely when nothing was trimmed, so the common decision
    // carries no figures for the server to check row names against.
    ...(trimmed.value ? { sanctioned: JSON.stringify(sanctioned.value) } : {}),
  }),
  confirmation: (claim, button) => ({
    title: `${button.label} claim`,
    message: `${button.label} ${claim.employee_name}'s claim for ${formatCurrency(claim.total_claimed_amount, claim.currency)}? They are notified, and the claim is settled with that decision.`,
    confirmLabel: `${button.label} claim`,
  }),
  succeeded: (claim, result) => {
    // Written, so there is no draft left to protect.
    sanctioned.value = {}
    // The outcome in the server's own words, so a site whose workflow calls it
    // something else is quoted rather than paraphrased, and the amount as the
    // server totalled it rather than as the dialog added it up.
    toast.success(
      `${claim.employee_name}'s claim is now ${result.status} at ${formatCurrency(result.total_sanctioned_amount, result.currency)}`,
    )
  },
  settled: () => emit('settled'),
})

// Drawn from the server's answer for this row, not from its docstatus: which
// outcomes this user may apply to this claim is the server's to settle — a
// claim of the approver's own, on a site that forbids settling it, offers
// nothing at all.
const buttons = computed(() =>
  props.claim?.can_decide
    ? decisionButtons(props.claim.actions, expenseCan.value.decisions)
    : [],
)

const reviewButtons = computed(() =>
  buttons.value.map((button) => ({ ...button, key: button.decision })),
)

function choose(key: string, close: () => void) {
  const button = buttons.value.find((candidate) => candidate.decision === key)
  if (!props.claim || !button) return
  attempted.value = true
  decide(props.claim, button, close)
}
</script>
