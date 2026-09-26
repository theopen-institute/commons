<!--
  Match a line to vouchers that are already on the books.

  ERPNext's candidate search (`get_linked_payments`) with its own ranking,
  and with loan repayments added from the page's own read, because lending's
  part of that search cannot be used (see `data/reconciliation.ts`). Ticking a
  row only selects it. The Match button writes, and says how much it will
  account for before it is pressed.
-->

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-end gap-x-4 gap-y-2">
      <div class="flex flex-wrap gap-x-3 gap-y-1">
        <Checkbox
          v-for="option in typeOptions"
          :key="option.key"
          :model-value="types.includes(option.key)"
          :label="option.label"
          :disabled="busy"
          @update:model-value="(on) => toggleType(option.key, Boolean(on))"
        />
        <Checkbox v-model="exactMatch" label="Exact amount only" :disabled="busy" />
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3 sm:w-96">
      <FormControl v-model="from" type="date" label="Posted from" :disabled="busy" />
      <FormControl v-model="to" type="date" label="to" :disabled="busy" />
    </div>

    <ErrorMessage v-if="searchError" :message="searchError" />

    <div v-if="searching" class="space-y-2">
      <Skeleton class="h-9 w-full rounded-4" />
      <Skeleton class="h-9 w-full rounded-4" />
    </div>
    <div
      v-else-if="!candidates.length"
      class="rounded-4 border border-dashed border-outline-gray-2 px-4 py-6 text-center text-p-sm text-ink-gray-5"
    >
      Nothing on the books matches this line in that period. Widen the dates, or create the voucher from
      another tab.
    </div>
    <ul v-else class="max-h-80 divide-y divide-outline-gray-1 overflow-y-auto rounded-4 border border-outline-gray-2">
      <li v-for="row in candidates" :key="`${row.doctype}:${row.name}`">
        <label class="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-surface-gray-1">
          <Checkbox
            :model-value="isSelected(row)"
            :disabled="busy"
            @update:model-value="(on) => toggle(row, Boolean(on))"
          />
          <div class="min-w-0 flex-1">
            <div class="truncate text-p-sm text-ink-gray-8">
              {{ row.doctype }} <span class="font-medium">{{ row.name }}</span>
              <a
                :href="deskUrl(row.doctype, row.name)"
                target="_blank"
                class="ml-1 text-ink-gray-4 hover:text-ink-gray-7"
                :aria-label="`Open ${row.name} in the desk`"
                @click.stop
              >
                <span class="lucide-external-link inline-block size-3" />
              </a>
            </div>
            <div class="truncate text-p-xs text-ink-gray-5">
              {{ formatDate(row.reference_date || row.posting_date) }}
              <template v-if="row.party"> · {{ row.party_type }}: {{ names[row.party] ?? row.party }}</template>
              <template v-if="row.reference_no"> · Ref {{ row.reference_no }}</template>
            </div>
          </div>
          <span
            v-if="row.rank > 1"
            class="shrink-0 text-p-xs text-ink-gray-5"
            :title="`Matches on ${row.rank - 1} of reference, party and amount`"
          >
            {{ '●'.repeat(row.rank - 1) }}
          </span>
          <span class="shrink-0 text-p-sm tabular-nums text-ink-gray-8">
            {{ formatExact(row.paid_amount, row.currency || transaction.currency) }}
          </span>
        </label>
      </li>
    </ul>

    <ErrorMessage v-if="problem" :message="problem" />

    <div class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-1 pt-3">
      <p class="text-p-sm tabular-nums text-ink-gray-6">
        <template v-if="selected.length">
          {{ formatExact(selectedTotal, transaction.currency) }} selected of
          {{ formatExact(transaction.unallocated_amount, transaction.currency) }} left on the line
        </template>
        <template v-else>Tick the vouchers this line pays or received.</template>
      </p>
      <Button
        variant="solid"
        :label="selected.length ? `Match ${pluralise(selected.length, 'voucher')}` : 'Match'"
        :disabled="!selected.length"
        :loading="busy"
        @click="save"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { watchDebounced } from '@vueuse/core'
import { Button, Checkbox, ErrorMessage, FormControl, Skeleton } from 'frappe-ui'
import { formatDate, formatExact, pluralise } from '@/data/format'
import {
  deskUrl,
  useCandidates,
  useReconcileVouchers,
  VOUCHER_TYPES,
  write,
  type LoanBook,
  type VoucherKey,
} from '@/data/reconciliation'
import {
  mergeCandidates,
  money,
  repaymentCandidates,
  type Candidate,
  type TransactionRow,
} from '@/data/reconciliationRules'
import { toastWithLinks } from '@/data/toastLinks'

const props = defineProps<{
  transaction: TransactionRow
  book: LoanBook
  lending: boolean
  names: Record<string, string>
}>()

const emit = defineEmits<{ done: [unallocated: number]; dirty: [dirty: boolean] }>()

const typeOptions = computed(() => [
  ...VOUCHER_TYPES.filter(
    // ERPNext's own rules: invoices only match the side they can be paid on.
    (option) =>
      !(option.key === 'sales_invoice' && props.transaction.deposit <= 0) &&
      !(option.key === 'purchase_invoice' && props.transaction.withdrawal <= 0),
  ),
  ...(props.lending && props.transaction.deposit > 0
    ? [{ key: 'loan_repayment' as const, label: 'Loan Repayment' }]
    : []),
])

const types = ref<VoucherKey[]>([])
const exactMatch = ref(false)
const from = ref('')
const to = ref('')
const candidates = ref<Candidate[]>([])
const selected = ref<Candidate[]>([])
const searching = ref(false)
const searchError = ref('')
const busy = ref(false)
const problem = ref('')

const finder = useCandidates()
const reconcile = useReconcileVouchers()

function shift(date: string, days: number) {
  const [y, m, d] = date.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

// Three months either side of the line by default. A cheque is presented
// weeks after it is written, and a transfer is often booked a few days late.
watch(
  () => props.transaction.name,
  () => {
    types.value = ['payment_entry', 'journal_entry', ...(props.lending ? (['loan_repayment'] as const) : [])]
    exactMatch.value = false
    from.value = shift(props.transaction.date, -90)
    to.value = shift(props.transaction.date, 90)
    selected.value = []
    problem.value = ''
  },
  { immediate: true },
)

function toggleType(key: VoucherKey, on: boolean) {
  types.value = on ? [...types.value, key] : types.value.filter((type) => type !== key)
}

async function search() {
  if (!from.value || !to.value) return
  searching.value = true
  searchError.value = ''
  try {
    const erpnext = await finder.search({
      transaction: props.transaction.name,
      types: types.value,
      exactMatch: exactMatch.value,
      from: from.value,
      to: to.value,
    })
    const loans = types.value.includes('loan_repayment')
      ? repaymentCandidates(
          props.transaction,
          props.book.uncleared.filter((row) => {
            const date = row.value_date.slice(0, 10)
            return date >= from.value && date <= to.value
          }),
          exactMatch.value,
        )
      : []
    // ERPNext takes what other lines already hold off each voucher, and keeps
    // the ones left with nothing. Nothing can be matched against those.
    candidates.value = mergeCandidates(erpnext, loans).filter((row) => money(row.paid_amount) > 0)
    selected.value = selected.value.filter((row) => candidates.value.some((c) => same(c, row)))
  } catch (error) {
    searchError.value = (error as Error).message
    candidates.value = []
  } finally {
    searching.value = false
  }
}

watchDebounced(
  () => [props.transaction.name, types.value.join(), exactMatch.value, from.value, to.value],
  search,
  { debounce: 250, immediate: true },
)

function same(a: Candidate, b: Candidate) {
  return a.doctype === b.doctype && a.name === b.name
}

function isSelected(row: Candidate) {
  return selected.value.some((other) => same(other, row))
}

function toggle(row: Candidate, on: boolean) {
  selected.value = on ? [...selected.value, row] : selected.value.filter((other) => !same(other, row))
}

const selectedTotal = computed(() => money(selected.value.reduce((sum, row) => sum + row.paid_amount, 0)))

watch(
  () => selected.value.length > 0,
  (value) => emit('dirty', value),
  { immediate: true },
)

async function save() {
  if (!selected.value.length) return
  busy.value = true
  problem.value = ''
  try {
    const done = await write(reconcile, {
      bank_transaction_name: props.transaction.name,
      vouchers: JSON.stringify(
        selected.value.map((row) => ({ payment_doctype: row.doctype, payment_name: row.name })),
      ),
    })
    if (!done.ok || !done.data) {
      problem.value = done.error?.message || 'Those vouchers could not be matched'
      return
    }
    toastWithLinks(
      `${pluralise(selected.value.length, 'voucher')} matched:`,
      selected.value.map((row) => ({ doctype: row.doctype, name: row.name })),
    )
    selected.value = []
    emit('done', done.data.unallocated_amount)
  } finally {
    busy.value = false
  }
}
</script>
