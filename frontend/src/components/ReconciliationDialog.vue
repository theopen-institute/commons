<!--
  One statement line, and every way of accounting for it.

  The desk tool spread this over a dialog with a radio group that swapped its
  fields about, a checkbox per voucher type, and a data table, and it lost
  everything typed whenever the type changed. Here each way is a tab, and each
  tab keeps its own draft and has its own button.

  Two things about how it behaves:

  * A write closes it. Whatever a tab creates or matches, the dialog closes
    and a toast links to the new document, so the reader sees what happened
    before choosing the next line. Previous and Next step through lines by hand.
  * Nothing is lost by accident. While a tab holds a draft, an outside click
    or Escape does not close the dialog, and Previous and Next are disabled.
-->

<template>
  <Dialog v-model:open="open" :dismissible="!dirty" size="4xl" position="top">
    <template #title>
      <div v-if="transaction" class="flex min-w-0 flex-wrap items-start justify-between gap-2 pr-8">
        <div class="min-w-0">
          <h2 class="text-lg font-semibold text-ink-gray-8">
            <span :class="transaction.deposit > 0 ? 'text-ink-green-7' : ''">
              {{ transaction.deposit > 0 ? '+' : '−' }}{{ formatExact(Math.abs(amountOf(transaction)), transaction.currency) }}
            </span>
            <span class="ml-2 text-base font-normal text-ink-gray-5">{{ formatDate(transaction.date) }}</span>
          </h2>
          <p class="mt-0.5 truncate text-p-sm text-ink-gray-6" :title="transaction.description ?? ''">
            {{ transaction.description || transaction.name }}
          </p>
          <p class="text-p-xs text-ink-gray-5">
            {{ transaction.name }}
            <template v-if="transaction.allocated_amount > 0.005">
              · {{ formatExact(transaction.unallocated_amount, transaction.currency) }} of it still to account for
            </template>
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <span v-if="position" class="mr-1 text-p-xs tabular-nums text-ink-gray-5">{{ position }}</span>
          <Button
            size="sm"
            variant="ghost"
            icon="lucide-chevron-left"
            aria-label="Previous line"
            :disabled="dirty || !hasPrevious"
            @click="emit('step', -1)"
          />
          <Button
            size="sm"
            variant="ghost"
            icon="lucide-chevron-right"
            aria-label="Next line"
            :disabled="dirty || !hasNext"
            @click="emit('step', 1)"
          />
        </div>
      </div>
    </template>

    <div v-if="transaction" class="space-y-4">
      <TabButtons v-model="tab" :options="tabOptions" />

      <!-- Mounted on first visit and kept, so a tab keeps its draft while
           another is looked at. -->
      <ReconciliationLoanPanel
        v-if="visited.loan"
        v-show="tab === 'loan'"
        :transaction="transaction"
        :book="book"
        :suggestions="suggestions"
        @dirty="(value) => (drafts.loan = value)"
        @done="done"
        @drafted="drafted"
        @switch="(to) => (tab = to)"
      />
      <ReconciliationMatchPanel
        v-if="visited.match"
        v-show="tab === 'match'"
        :transaction="transaction"
        :book="book"
        :lending="lending"
        :names="names"
        @dirty="(value) => (drafts.match = value)"
        @done="done"
      />
      <ReconciliationVoucherPanel
        v-if="visited.payment"
        v-show="tab === 'payment'"
        :transaction="transaction"
        mode="payment"
        @dirty="(value) => (drafts.payment = value)"
        @done="done"
        @drafted="drafted"
      />
      <ReconciliationVoucherPanel
        v-if="visited.journal"
        v-show="tab === 'journal'"
        :transaction="transaction"
        mode="journal"
        @dirty="(value) => (drafts.journal = value)"
        @done="done"
        @drafted="drafted"
      />
      <ReconciliationDetailsPanel
        v-if="visited.details"
        v-show="tab === 'details'"
        :transaction="transaction"
        @dirty="(value) => (drafts.details = value)"
        @updated="(values) => emit('updated', transaction!.name, values)"
      />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Button, Dialog, TabButtons } from 'frappe-ui'
import ReconciliationDetailsPanel from '@/components/ReconciliationDetailsPanel.vue'
import ReconciliationLoanPanel from '@/components/ReconciliationLoanPanel.vue'
import ReconciliationMatchPanel from '@/components/ReconciliationMatchPanel.vue'
import ReconciliationVoucherPanel from '@/components/ReconciliationVoucherPanel.vue'
import { formatDate, formatExact } from '@/data/format'
import type { LoanBook } from '@/data/reconciliation'
import { amountOf, type Suggestion, type TransactionRow } from '@/data/reconciliationRules'

type Tab = 'loan' | 'match' | 'payment' | 'journal' | 'details'

const props = defineProps<{
  transaction: TransactionRow | null
  book: LoanBook
  suggestions: Suggestion[]
  /** Whether loan repayments can be booked here: lending is installed and
   *  this reader may submit a repayment. */
  lending: boolean
  names: Record<string, string>
  /** "3 of 12 open", or empty. */
  position: string
  hasPrevious: boolean
  hasNext: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  /** A write left the line with this much still to account for. */
  done: [name: string, unallocated: number]
  /** Reference, party or links changed. */
  updated: [name: string, values: Partial<TransactionRow>]
  step: [direction: 1 | -1]
  /** A draft was made from the line. It stays open; the page reads its
   *  drafts again so the new one is on the board. */
  drafted: []
}>()

const drafts = reactive<Record<Tab, boolean>>({
  loan: false,
  match: false,
  payment: false,
  journal: false,
  details: false,
})
const dirty = computed(() => Object.values(drafts).some(Boolean))
const visited = reactive<Record<Tab, boolean>>({
  loan: false,
  match: false,
  payment: false,
  journal: false,
  details: false,
})

const isOpenLine = computed(() => (props.transaction?.unallocated_amount ?? 0) > 0.005)
const isDeposit = computed(() => (props.transaction?.deposit ?? 0) > 0)

const tabOptions = computed(() => {
  if (!isOpenLine.value) return [{ value: 'details', label: 'Details', iconLeft: 'lucide-file-text' }]
  return [
    ...(props.lending && isDeposit.value
      ? [{ value: 'loan', label: 'Loan repayment', iconLeft: 'lucide-hand-coins' }]
      : []),
    { value: 'match', label: 'Match existing', iconLeft: 'lucide-link' },
    { value: 'payment', label: 'Payment entry', iconLeft: 'lucide-receipt' },
    { value: 'journal', label: 'Journal entry', iconLeft: 'lucide-book-open' },
    { value: 'details', label: 'Details', iconLeft: 'lucide-file-text' },
  ]
})

const tab = ref<Tab>('match')

/** Where a line opens. The loan tab for a deposit something points at, or for
 *  any deposit on a site that lends, because on these statements nearly every
 *  deposit is a repayment. Otherwise Match. */
function initialTab(): Tab {
  if (!isOpenLine.value) return 'details'
  if (props.lending && isDeposit.value) return 'loan'
  return 'match'
}

watch(
  () => props.transaction?.name,
  () => {
    for (const key of Object.keys(drafts) as Tab[]) {
      drafts[key] = false
      visited[key] = false
    }
    tab.value = initialTab()
    visited[tab.value] = true
  },
  { immediate: true },
)

watch(tab, (value) => (visited[value] = true))

// A line that has just been fully accounted for and stays on screen (the last
// one) is shown as it now is: details only.
watch(isOpenLine, (openLine) => {
  if (!openLine) tab.value = 'details'
})

function drafted() {
  for (const key of Object.keys(drafts) as Tab[]) drafts[key] = false
  emit('drafted')
}

function done(unallocated: number) {
  for (const key of Object.keys(drafts) as Tab[]) drafts[key] = false
  if (props.transaction) emit('done', props.transaction.name, unallocated)
}
</script>
