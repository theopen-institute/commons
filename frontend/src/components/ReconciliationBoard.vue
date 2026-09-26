<!--
  Both halves of what is left to reconcile, side by side: statement lines the
  books have no entry for, and entries the statement has no line for.

  A line and an entry for the same money cancel out between the books and the
  bank, so pairing them never moves the difference above; it only empties
  both columns. Whatever is left in either column after that is what a
  difference, if any, is made of.

  Drafts, when included, sit in the right-hand column marked as such and are
  left out of its total: they are not in the ledger, so they are not part of
  the sum. A line paired with one is matched by submitting it (see the pair
  dialog).

  Pairing is by dragging one onto the other, in either direction, or with the
  Match button on a likely pair. Neither writes: both open
  `ReconciliationPairDialog`, and the match is made there on Save, per the
  modal rule. A statement line clicked on its own opens the line's dialog as
  before, for everything else: a loan repayment, a new payment or journal entry.
-->

<template>
  <div class="grid gap-4 lg:grid-cols-2">
    <section v-for="column in columns" :key="column.side" class="min-w-0">
      <header class="mb-1.5 flex items-baseline justify-between gap-2 text-p-sm">
        <h3 class="font-medium text-ink-gray-7">{{ column.title }}</h3>
        <span class="tabular-nums text-ink-gray-5">
          {{ column.count }} · {{ signed(column.total) }}
          <template v-if="column.drafts"> · {{ pluralise(column.drafts, 'draft') }}</template>
        </span>
      </header>

      <div
        v-if="!column.rows.length"
        class="rounded-4 border border-dashed border-outline-gray-2 px-4 py-6 text-center text-p-sm text-ink-gray-5"
      >
        {{ column.empty }}
      </div>

      <ul v-else class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2">
        <li
          v-for="row in column.rows"
          :key="row.key"
          draggable="true"
          class="flex items-center gap-3 px-3 py-2"
          :class="[rowClass(row), row.side === 'statement' ? 'cursor-pointer' : 'cursor-default']"
          @dragstart="startDrag($event, row)"
          @dragend="dragging = null; over = null"
          @dragover="allowDrop($event, row)"
          @dragleave="over === row.key && (over = null)"
          @drop="drop($event, row)"
          @click="row.side === 'statement' && emit('open', row.line!)"
        >
          <!-- The handle is where the grab cursor shows: a click anywhere else
               on a statement line opens it. The whole row still drags, so a
               drag that starts beside the handle is not lost. -->
          <span
            class="-my-2 -ml-1 flex shrink-0 cursor-grab items-center self-stretch px-1 text-ink-gray-4 hover:text-ink-gray-6 active:cursor-grabbing"
            title="Drag onto its match"
            @click.stop
          >
            <span class="lucide-grip-vertical size-4" />
          </span>
          <div class="min-w-0 flex-1">
            <div class="flex items-baseline gap-2 text-p-sm">
              <span class="shrink-0 tabular-nums text-ink-gray-6">{{ formatDate(row.date) }}</span>
              <span class="truncate text-ink-gray-8" :title="row.title">{{ row.title }}</span>
            </div>
            <div class="flex flex-wrap items-center gap-x-2 text-p-xs text-ink-gray-5">
              <span v-if="row.detail" class="truncate">{{ row.detail }}</span>
              <a
                v-if="row.side === 'books'"
                :href="deskUrl(row.entry!.doctype, row.entry!.name)"
                target="_blank"
                class="inline-flex items-center gap-0.5 hover:text-ink-gray-7"
                draggable="false"
                @click.stop
              >
                {{ row.entry!.name }} <span class="lucide-external-link size-3" />
              </a>
              <Badge v-if="row.entry?.draft" label="Draft" theme="gray" size="sm" />
              <span v-if="row.partner" class="inline-flex items-center gap-1 text-ink-blue-7">
                <span class="lucide-link size-3" /> Likely {{ row.partnerLabel }}
              </span>
            </div>
          </div>
          <span
            class="shrink-0 text-p-sm tabular-nums"
            :class="[row.amount > 0 ? 'text-ink-green-7' : 'text-ink-gray-8', row.entry?.draft ? 'opacity-70' : '']"
          >
            {{ signed(row.amount) }}
          </span>
          <Button
            v-if="row.partner && row.side === 'statement'"
            size="sm"
            variant="subtle"
            label="Match"
            @click.stop="pairKeys(row.key, row.partner)"
          />
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { formatDate, formatExact, pluralise } from '@/data/format'
import { deskUrl } from '@/data/reconciliation'
import { likelyPairs, meaningfulReference, money, type BookEntry, type TransactionRow } from '@/data/reconciliationRules'

const props = defineProps<{
  lines: TransactionRow[]
  entries: BookEntry[]
  names: Record<string, string>
  currency: string | null
}>()

const emit = defineEmits<{
  open: [line: TransactionRow]
  /** A line and an entry to match. Opens the pair dialog; writes nothing. */
  pair: [line: TransactionRow, entry: BookEntry]
}>()

interface Row {
  side: 'statement' | 'books'
  key: string
  date: string
  title: string
  detail: string
  /** As the bank's balance sees it: money in positive. */
  amount: number
  line?: TransactionRow
  entry?: BookEntry
  /** The likely counterpart's key on the other side. */
  partner?: string
  partnerLabel?: string
}

const entryKey = (entry: BookEntry) => `${entry.doctype}:${entry.name}`

const pairs = computed(() => likelyPairs(props.lines, props.entries))
const partnerOfEntry = computed(() => new Map([...pairs.value].map(([line, entry]) => [entry, line])))

const lineRows = computed<Row[]>(() =>
  props.lines.map((line) => {
    const partner = pairs.value.get(line.name)
    const entry = partner ? props.entries.find((row) => entryKey(row) === partner) : undefined
    const reference = meaningfulReference(line.reference_number)
    return {
      side: 'statement',
      key: line.name,
      date: line.date,
      title: line.description || line.name,
      detail: [reference && `Ref ${reference}`, line.party && `${line.party_type}: ${props.names[line.party] ?? line.party}`]
        .filter(Boolean)
        .join(' · '),
      amount: money(line.deposit > 0 ? line.unallocated_amount : -line.unallocated_amount),
      line,
      partner,
      partnerLabel: entry ? `${entry.doctype} ${entry.name}` : undefined,
    }
  }),
)

const entryRows = computed<Row[]>(() =>
  props.entries.map((entry) => {
    const partner = partnerOfEntry.value.get(entryKey(entry))
    const line = partner ? props.lines.find((row) => row.name === partner) : undefined
    return {
      side: 'books',
      key: entryKey(entry),
      date: entry.date,
      title: entry.against || entry.doctype,
      detail: [entry.doctype, meaningfulReference(entry.reference) && `Ref ${meaningfulReference(entry.reference)}`]
        .filter(Boolean)
        .join(' · '),
      amount: money(entry.debit - entry.credit),
      entry,
      partner,
      partnerLabel: line ? `line of ${formatDate(line.date)}` : undefined,
    }
  }),
)

const columns = computed(() => [
  {
    side: 'statement' as const,
    title: 'On the statement, not in the books',
    empty: 'Every statement line here has its entry.',
    rows: lineRows.value,
    count: lineRows.value.length,
    total: money(lineRows.value.reduce((sum, row) => sum + row.amount, 0)),
    drafts: 0,
  },
  {
    side: 'books' as const,
    title: 'In the books, not on the statement',
    empty: 'Every entry here has its statement line.',
    rows: entryRows.value,
    // Drafts are listed but not counted: they are not in the ledger, so they
    // are not part of the balance check the column totals up to.
    count: entryRows.value.filter((row) => !row.entry?.draft).length,
    total: money(entryRows.value.filter((row) => !row.entry?.draft).reduce((sum, row) => sum + row.amount, 0)),
    drafts: entryRows.value.filter((row) => row.entry?.draft).length,
  },
])

function signed(value: number) {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatExact(Math.abs(value), props.currency)}`
}

/* -------------------------------------------------------------------------- */
/* Dragging                                                                    */
/* -------------------------------------------------------------------------- */

const dragging = ref<Row | null>(null)
const over = ref<string | null>(null)

/** Whether two rows can be matched: opposite sides, and money going the same
 *  way. A deposit is never the same money as a payment. */
function compatible(a: Row, b: Row) {
  return a.side !== b.side && Math.sign(a.amount) === Math.sign(b.amount)
}

function rowClass(row: Row) {
  const drag = dragging.value
  if (drag) {
    if (drag.key === row.key) return 'opacity-50'
    if (!compatible(drag, row)) return 'opacity-40'
    if (over.value === row.key) return 'bg-surface-blue-2 ring-2 ring-inset ring-outline-blue-3'
    return money(Math.abs(drag.amount)) === money(Math.abs(row.amount)) ? 'bg-surface-blue-2' : ''
  }
  if (row.entry?.draft) return 'bg-surface-gray-1'
  return row.side === 'statement' ? 'hover:bg-surface-gray-1' : ''
}

function startDrag(event: DragEvent, row: Row) {
  dragging.value = row
  event.dataTransfer?.setData('text/plain', row.key)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'link'
}

function allowDrop(event: DragEvent, row: Row) {
  if (!dragging.value || !compatible(dragging.value, row)) return
  event.preventDefault()
  over.value = row.key
}

function drop(event: DragEvent, row: Row) {
  event.preventDefault()
  const from = dragging.value
  dragging.value = null
  over.value = null
  if (from && compatible(from, row)) pairKeys(from.key, row.key)
}

function pairKeys(a: string, b: string) {
  const all = [...lineRows.value, ...entryRows.value]
  const rows = [all.find((row) => row.key === a), all.find((row) => row.key === b)]
  const line = rows.find((row) => row?.side === 'statement')?.line
  const entry = rows.find((row) => row?.side === 'books')?.entry
  if (line && entry) emit('pair', line, entry)
}
</script>
