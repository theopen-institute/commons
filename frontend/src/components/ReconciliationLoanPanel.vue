<!--
  Book a deposit as loan repayments, and reconcile them, in one Save.

  The desk way is five screens: note the amount and date, open Loan Repayment,
  pick the loan (which means knowing whose QR payment this was), type the
  amount and the date, submit, come back to the reconciliation tool, find the
  line again and match it. This is one panel. It says whose payment it
  probably is and why, and it books exactly the repayment the desk would
  (`commons.banking.reconciliation.create_loan_repayments`).

  Everything here is a draft until the button at the bottom is pressed. Adding
  a loan adds a line to the draft and writes nothing.
-->

<template>
  <div class="space-y-4">
    <!-- A repayment already on the books is a better answer than a new one:
         booking a second would record the same money twice. -->
    <div
      v-if="existing.length"
      class="flex items-start gap-2 rounded-4 border border-outline-amber-3 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8"
    >
      <span class="lucide-triangle-alert mt-0.5 size-4 shrink-0 text-ink-amber-7" />
      <div class="min-w-0 flex-1">
        {{ existing.length === 1 ? 'A repayment' : `${existing.length} repayments` }} of exactly this
        amount {{ existing.length === 1 ? 'is' : 'are' }} already booked and not yet matched to a statement line
        ({{ existing.map((row) => row.name).join(', ') }}).
        Match {{ existing.length === 1 ? 'it' : 'one' }} instead of booking another.
      </div>
      <Button size="sm" variant="subtle" label="Match" @click="emit('switch', 'match')" />
    </div>

    <section v-if="suggestions.length">
      <h3 class="mb-1.5 text-p-sm font-medium text-ink-gray-7">Likely borrowers</h3>
      <ul class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2">
        <li
          v-for="suggestion in suggestions.slice(0, 4)"
          :key="suggestion.loan"
          class="flex items-center gap-3 px-3 py-2"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-p-base text-ink-gray-8">
              {{ borrowerOf(suggestion.loan) }}
              <span class="text-p-sm text-ink-gray-5">· {{ suggestion.loan }}</span>
            </div>
            <div class="mt-0.5 flex flex-wrap gap-1">
              <Badge
                v-for="reason in suggestion.reasons"
                :key="reason"
                :label="reason"
                theme="blue"
                size="sm"
              />
            </div>
          </div>
          <div class="shrink-0 text-right text-p-sm tabular-nums text-ink-gray-6">
            {{ formatExact(outstanding[suggestion.loan], transaction.currency) }}
            <div class="text-p-xs text-ink-gray-5">outstanding</div>
          </div>
          <Button
            size="sm"
            :variant="isChosen(suggestion.loan) ? 'ghost' : 'subtle'"
            :label="isChosen(suggestion.loan) ? 'Added' : 'Add'"
            :disabled="isChosen(suggestion.loan) || busy"
            @click="addLine(suggestion.loan)"
          />
        </li>
      </ul>
    </section>

    <section>
      <h3 class="mb-1.5 text-p-sm font-medium text-ink-gray-7">
        {{ suggestions.length ? 'Or find a loan' : 'Find the loan' }}
      </h3>
      <TextInput
        v-model="query"
        placeholder="Borrower's name, id or loan number"
        :disabled="busy"
      >
        <template #prefix><span class="lucide-search size-4 text-ink-gray-5" /></template>
      </TextInput>
      <ul
        v-if="query.trim()"
        class="mt-1.5 max-h-56 divide-y divide-outline-gray-1 overflow-y-auto rounded-4 border border-outline-gray-2"
      >
        <li
          v-for="loan in searchResults"
          :key="loan.name"
          class="flex items-center gap-3 px-3 py-1.5"
        >
          <div class="min-w-0 flex-1 truncate text-p-sm text-ink-gray-8">
            {{ borrowerOf(loan.name) }}
            <span class="text-ink-gray-5">· {{ loan.name }} · {{ loan.status }}</span>
          </div>
          <span class="shrink-0 text-p-sm tabular-nums text-ink-gray-6">
            {{ formatExact(outstanding[loan.name], transaction.currency) }}
          </span>
          <Button
            size="sm"
            variant="ghost"
            :label="isChosen(loan.name) ? 'Added' : 'Add'"
            :disabled="isChosen(loan.name) || busy"
            @click="addLine(loan.name)"
          />
        </li>
        <li v-if="!searchResults.length" class="px-3 py-2 text-p-sm text-ink-gray-5">
          No open loan matches “{{ query.trim() }}”
        </li>
      </ul>
      <p v-else-if="!book.loans.length" class="mt-1.5 text-p-sm text-ink-gray-5">
        There are no open loans for this bank account's company.
      </p>
    </section>

    <section v-if="lines.length">
      <h3 class="mb-1.5 text-p-sm font-medium text-ink-gray-7">Repayments to book</h3>
      <ul class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2">
        <li v-for="(line, index) in lines" :key="line.loan" class="flex items-center gap-3 px-3 py-2">
          <div class="min-w-0 flex-1">
            <div class="truncate text-p-base text-ink-gray-8">{{ borrowerOf(line.loan) }}</div>
            <div class="text-p-xs text-ink-gray-5">
              {{ line.loan }} · {{ formatExact(outstanding[line.loan], transaction.currency) }} outstanding
            </div>
          </div>
          <div class="w-36 shrink-0">
            <TextInput
              v-model.number="line.amount"
              type="number"
              min="0"
              step="0.01"
              :disabled="busy"
              :aria-label="`Amount repaid on ${line.loan}`"
            />
          </div>
          <Button
            size="sm"
            variant="ghost"
            icon="lucide-x"
            :aria-label="`Remove ${line.loan}`"
            :disabled="busy"
            @click="lines.splice(index, 1)"
          />
        </li>
      </ul>

      <div class="mt-3 grid gap-3 sm:grid-cols-2">
        <FormControl
          v-model="reference"
          label="Reference"
          :disabled="busy"
          description="Kept on each repayment. The statement's own, or its description."
        />
        <div class="text-p-sm text-ink-gray-6 sm:pt-6">
          <div class="flex justify-between tabular-nums">
            <span>Deposit left to account for</span>
            <span>{{ formatExact(transaction.unallocated_amount, transaction.currency) }}</span>
          </div>
          <div class="flex justify-between tabular-nums">
            <span>These repayments</span>
            <span>{{ formatExact(check.total, transaction.currency) }}</span>
          </div>
          <div
            class="flex justify-between font-medium tabular-nums"
            :class="check.remaining < 0 ? 'text-ink-red-7' : 'text-ink-gray-8'"
          >
            <span>Left after booking</span>
            <span>{{ formatExact(check.remaining, transaction.currency) }}</span>
          </div>
        </div>
      </div>

      <ul v-if="check.warnings.length" class="mt-2 space-y-0.5 text-p-sm text-ink-amber-7">
        <li v-for="warning in check.warnings" :key="warning">
          {{ warning }}. Lending books the excess as owed back to the borrower.
        </li>
      </ul>
    </section>

    <ErrorMessage v-if="problem" :message="problem" />

    <div class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-1 pt-3">
      <p class="text-p-xs text-ink-gray-5">
        Value date {{ formatDate(transaction.date) }}. Lending posts the entry to the ledger today.
      </p>
      <div class="flex gap-2">
        <Button
          v-if="lines.length"
          variant="ghost"
          label="Clear"
          :disabled="busy"
          @click="reset"
        />
        <Button
          variant="solid"
          :label="saveLabel"
          :loading="busy"
          :disabled="!lines.length || check.errors.length > 0"
          :title="check.errors.join(' · ')"
          @click="save"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, FormControl, TextInput, toast } from 'frappe-ui'
import { formatDate, formatExact, pluralise } from '@/data/format'
import { useCreateLoanRepayments, write, type LoanBook } from '@/data/reconciliation'
import {
  checkSplit,
  money,
  outstandingPrincipal,
  proposeAmount,
  proposedReference,
  type RepaymentLine,
  type Suggestion,
  type TransactionRow,
} from '@/data/reconciliationRules'

const props = defineProps<{
  transaction: TransactionRow
  book: LoanBook
  suggestions: Suggestion[]
}>()

const emit = defineEmits<{
  /** Something was written; carries the line's new unallocated amount. */
  done: [unallocated: number]
  dirty: [dirty: boolean]
  switch: [tab: 'match']
}>()

const create = useCreateLoanRepayments()
const lines = reactive<RepaymentLine[]>([])
const reference = ref('')
const query = ref('')
const busy = ref(false)
const problem = ref('')

const outstanding = computed<Record<string, number>>(() =>
  Object.fromEntries(props.book.loans.map((loan) => [loan.name, outstandingPrincipal(loan)])),
)

const loanByName = computed(() => new Map(props.book.loans.map((loan) => [loan.name, loan])))

function borrowerOf(loanName: string) {
  const loan = loanByName.value.get(loanName)
  if (!loan) return loanName
  return props.book.names[loan.applicant] ?? loan.applicant
}

const existing = computed(() =>
  props.book.uncleared.filter(
    (row) => money(row.amount_paid) === money(props.transaction.unallocated_amount),
  ),
)

function isChosen(loan: string) {
  return lines.some((line) => line.loan === loan)
}

function addLine(loan: string) {
  if (isChosen(loan)) return
  const left = money(props.transaction.unallocated_amount - check.value.total)
  lines.push({ loan, amount: proposeAmount(left, outstanding.value[loan] ?? 0) })
  query.value = ''
}

const searchResults = computed(() => {
  const words = query.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return []
  return props.book.loans
    .filter((loan) => {
      const haystack = `${loan.name} ${loan.applicant} ${props.book.names[loan.applicant] ?? ''}`.toLowerCase()
      return words.every((word) => haystack.includes(word))
    })
    .slice(0, 20)
})

const check = computed(() =>
  checkSplit(lines, props.transaction.unallocated_amount, outstanding.value),
)

const saveLabel = computed(() =>
  lines.length > 1 ? `Book ${lines.length} repayments and reconcile` : 'Book repayment and reconcile',
)

function reset() {
  lines.splice(0, lines.length)
  reference.value = proposedReference(props.transaction)
  query.value = ''
  problem.value = ''
}

// A new line is a new draft. The best suggestion is put into it when the
// evidence is strong and nothing else comes close. That is still only a
// draft: nothing is booked until the button is pressed. A weak suggestion is
// listed and never pre-filled (see `suggestLoans`).
watch(
  () => props.transaction.name,
  () => {
    reset()
    const [best, second] = props.suggestions
    if (best?.strong && (!second || best.score - second.score >= 3)) addLine(best.loan)
  },
  { immediate: true },
)

const dirty = computed(() => lines.length > 0)
watch(dirty, (value) => emit('dirty', value), { immediate: true })

async function save() {
  if (!lines.length || check.value.errors.length) return
  busy.value = true
  problem.value = ''
  try {
    const done = await write(create, {
      bank_transaction: props.transaction.name,
      repayments: lines.map((line) => ({ loan: line.loan, amount: money(line.amount) })),
      reference_number: reference.value,
    })
    if (!done.ok || !done.data) {
      problem.value = done.error?.message || 'The repayments could not be booked'
      return
    }
    toast.success(
      `${pluralise(done.data.repayments.length, 'repayment')} booked and reconciled: ${done.data.repayments.join(', ')}`,
    )
    lines.splice(0, lines.length)
    emit('done', done.data.unallocated_amount)
  } finally {
    busy.value = false
  }
}
</script>
