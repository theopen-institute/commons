<!--
  One bank account's statement lines for the period, oldest first.

  Read-only, like the attendance grid: a row opens the line's dialog and does
  nothing else. The desk tool put Match, Create and Update buttons on every
  row of its data table, and a row there was one misplaced click from a
  submitted voucher.

  The keyboard is what makes forty lines bearable. Up and down (or j and k)
  move through the lines and Enter opens one. The dialog then moves itself to
  the next open line after each reconciliation (see `BankReconciliation.vue`),
  so a statement can be worked from top to bottom without the mouse.
-->

<template>
  <div
    ref="container"
    class="overflow-x-auto rounded-4 border border-outline-gray-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
    tabindex="0"
    role="grid"
    aria-label="Statement lines"
    @keydown="onKey"
  >
    <table class="w-full border-separate border-spacing-0 text-p-sm">
      <thead>
        <tr class="text-left text-ink-gray-5">
          <th class="border-b border-outline-gray-2 px-3 py-2 font-medium">Date</th>
          <th class="border-b border-outline-gray-2 px-3 py-2 font-medium">Description</th>
          <th class="border-b border-outline-gray-2 px-3 py-2 text-right font-medium">Amount</th>
          <th class="hidden border-b border-outline-gray-2 px-3 py-2 text-right font-medium sm:table-cell">
            Unallocated
          </th>
          <th class="border-b border-outline-gray-2 px-3 py-2 font-medium">Status</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in rows"
          :key="row.name"
          :ref="(el) => (rowElements[index] = el as HTMLElement | null)"
          class="cursor-pointer"
          :class="index === cursor ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-1'"
          :aria-selected="index === cursor"
          @click="open(index)"
        >
          <td class="whitespace-nowrap border-b border-outline-gray-1 px-3 py-2 align-top tabular-nums text-ink-gray-7">
            {{ formatDate(row.date) }}
          </td>
          <td class="max-w-0 border-b border-outline-gray-1 px-3 py-2 align-top">
            <div class="truncate text-ink-gray-8" :title="row.description ?? ''">
              {{ row.description || '—' }}
            </div>
            <div class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-p-xs text-ink-gray-5">
              <span v-if="meaningfulReference(row.reference_number)">
                Ref {{ meaningfulReference(row.reference_number) }}
              </span>
              <span v-if="row.party">{{ row.party_type }}: {{ partyLabel(row) }}</span>
              <span
                v-if="hints[row.name]"
                class="inline-flex items-center gap-1 text-ink-blue-7"
                :title="hints[row.name].reasons.join(' · ')"
              >
                <span class="lucide-sparkles size-3" />
                {{ hints[row.name].label }}
              </span>
            </div>
          </td>
          <td
            class="whitespace-nowrap border-b border-outline-gray-1 px-3 py-2 text-right align-top tabular-nums"
            :class="row.deposit > 0 ? 'text-ink-green-7' : 'text-ink-gray-8'"
          >
            {{ row.deposit > 0 ? '+' : '−' }}{{ formatExact(Math.abs(amountOf(row)), row.currency) }}
          </td>
          <td
            class="hidden whitespace-nowrap border-b border-outline-gray-1 px-3 py-2 text-right align-top tabular-nums text-ink-gray-6 sm:table-cell"
          >
            {{ row.unallocated_amount > 0.005 ? formatExact(row.unallocated_amount, row.currency) : '—' }}
          </td>
          <td class="whitespace-nowrap border-b border-outline-gray-1 px-3 py-2 align-top">
            <Badge :theme="statusOf(row).theme" :label="statusOf(row).label" size="sm" />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Badge } from 'frappe-ui'
import { formatDate, formatExact } from '@/data/format'
import { amountOf, meaningfulReference, type TransactionRow } from '@/data/reconciliationRules'

export interface RowHint {
  label: string
  reasons: string[]
}

const props = defineProps<{
  rows: TransactionRow[]
  /** The likeliest loan for each open deposit, where there is one. */
  hints: Record<string, RowHint>
  /** Borrower and party names, for a party the line names by id. */
  names: Record<string, string>
}>()

const emit = defineEmits<{ open: [row: TransactionRow] }>()

const container = ref<HTMLElement | null>(null)
const rowElements = ref<(HTMLElement | null)[]>([])
const cursor = ref(-1)

// A new list is a new statement; a cursor left where it was would point at a
// different line.
watch(
  () => props.rows.map((row) => row.name).join(),
  () => {
    if (cursor.value >= props.rows.length) cursor.value = props.rows.length - 1
  },
)

function partyLabel(row: TransactionRow) {
  return (row.party && props.names[row.party]) || row.party
}

function statusOf(row: TransactionRow): { label: string; theme: 'green' | 'amber' | 'blue' | 'gray' } {
  if (row.unallocated_amount <= 0.005) return { label: 'Reconciled', theme: 'green' }
  if (row.allocated_amount > 0.005) return { label: 'Part matched', theme: 'blue' }
  return { label: 'Unreconciled', theme: 'amber' }
}

function open(index: number) {
  cursor.value = index
  emit('open', props.rows[index])
}

async function move(to: number) {
  if (!props.rows.length) return
  cursor.value = Math.max(0, Math.min(props.rows.length - 1, to))
  await nextTick()
  rowElements.value[cursor.value]?.scrollIntoView({ block: 'nearest' })
}

function onKey(event: KeyboardEvent) {
  if (event.metaKey || event.ctrlKey || event.altKey) return
  if (event.key === 'ArrowDown' || event.key === 'j') {
    event.preventDefault()
    move(cursor.value + 1)
  } else if (event.key === 'ArrowUp' || event.key === 'k') {
    event.preventDefault()
    move(cursor.value - 1)
  } else if (event.key === 'Enter' && cursor.value >= 0) {
    event.preventDefault()
    open(cursor.value)
  }
}

/** Put the keyboard on the list, at a given line. What the page calls after
 *  the dialog closes, so the next key press carries on where it left off. */
function focusRow(name?: string) {
  const index = name ? props.rows.findIndex((row) => row.name === name) : cursor.value
  if (index >= 0) move(index)
  container.value?.focus()
}

defineExpose({ focusRow })
</script>
