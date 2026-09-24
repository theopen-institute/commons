<!--
  Where the account stands today, whatever period is on screen.

  Two questions a bookkeeper opens this page with, before choosing any dates:
  how far behind is the reconciliation, and do the bank and the books agree?
  The first is the statement's latest line and how much of it is accounted
  for. The second is the books' balance two ways, with and without the entries
  no statement line has matched yet, set against the bank's latest recorded
  closing balance. The arithmetic is `standing` in `reconciliationRules.ts`.
-->

<template>
  <section class="rounded-4 border border-outline-gray-2 px-4 py-3">
    <div v-if="!standing" class="space-y-2">
      <Skeleton class="h-5 w-72 rounded-4" />
      <Skeleton class="h-12 w-full rounded-4" />
    </div>

    <template v-else>
      <div class="flex flex-wrap items-start gap-x-8 gap-y-2 text-p-sm">
        <div class="flex items-start gap-2">
          <span class="lucide-calendar-clock mt-0.5 size-4 shrink-0" :class="stale ? 'text-ink-amber-7' : 'text-ink-gray-5'" />
          <div>
            <div class="text-ink-gray-5">Statement recorded to</div>
            <div class="text-ink-gray-8">
              <template v-if="standing.lastLineDate">
                {{ formatDate(standing.lastLineDate) }}
                <span :class="stale ? 'text-ink-amber-7' : 'text-ink-gray-5'">· {{ ago(standing.daysSinceLastLine!) }}</span>
              </template>
              <template v-else>No statement lines yet</template>
            </div>
          </div>
        </div>

        <div class="flex items-start gap-2">
          <span
            class="mt-0.5 size-4 shrink-0"
            :class="standing.openCount ? 'lucide-list-todo text-ink-amber-7' : 'lucide-circle-check text-ink-green-7'"
          />
          <div>
            <div class="text-ink-gray-5">Reconciled to</div>
            <div class="text-ink-gray-8">
              <template v-if="!standing.reconciledThrough">—</template>
              <template v-else-if="!standing.openCount">
                {{ formatDate(standing.reconciledThrough) }}, every line
              </template>
              <template v-else>
                {{ formatDate(standing.reconciledThrough) }}
                <button type="button" class="text-ink-amber-7 underline decoration-dotted" @click="emit('showOpen')">
                  · {{ pluralise(standing.openCount, 'line') }} open ({{ signed(standing.openNet) }})
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <div class="text-p-xs text-ink-gray-5">Book balance today</div>
          <div class="text-base-medium tabular-nums text-ink-gray-8">{{ figure(standing.book) }}</div>
          <div class="text-p-xs text-ink-gray-5">Every entry posted, reconciled or not</div>
        </div>
        <div>
          <div class="text-p-xs text-ink-gray-5">Cleared balance today</div>
          <div class="text-base-medium tabular-nums text-ink-gray-8">{{ figure(standing.cleared) }}</div>
          <div class="text-p-xs text-ink-gray-5">
            <template v-if="standing.awaitingStatement">
              Leaves out {{ signed(standing.awaitingStatement) }} not yet on a statement line
            </template>
            <template v-else>Only entries matched to the statement</template>
          </div>
        </div>

        <!-- The verdict. Green only when the bank's own figure has been
             recorded and the books explain it to the unit. -->
        <div
          class="rounded-4 px-3 py-2"
          :class="
            !standing.check
              ? 'bg-surface-gray-1'
              : standing.check.unexplained === 0
                ? 'bg-surface-green-2'
                : 'bg-surface-amber-2'
          "
        >
          <template v-if="!standing.check">
            <div class="text-p-sm text-ink-gray-7">No statement balance recorded</div>
            <button type="button" class="text-p-xs text-ink-gray-6 underline" @click="emit('record')">
              Record the bank's closing balance to check against it
            </button>
          </template>
          <template v-else-if="standing.check.unexplained === 0">
            <div class="flex items-center gap-1.5 text-p-sm font-medium text-ink-green-7">
              <span class="lucide-circle-check size-4" /> Matches the statement
            </div>
            <div class="text-p-xs text-ink-gray-6">
              {{ figure(standing.check.statement) }} on {{ formatDate(standing.check.date) }}
            </div>
          </template>
          <template v-else>
            <div class="flex items-center gap-1.5 text-p-sm font-medium text-ink-amber-7">
              <span class="lucide-triangle-alert size-4" /> {{ signed(standing.check.unexplained) }} unexplained
            </div>
            <div class="text-p-xs text-ink-gray-6" :title="checkDetail">
              Statement {{ figure(standing.check.statement) }} on {{ formatDate(standing.check.date) }}; the books
              account for {{ figure(standing.check.expected) }}
            </div>
          </template>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Skeleton } from 'frappe-ui'
import { formatDate, formatExact, pluralise } from '@/data/format'
import type { Standing } from '@/data/reconciliationRules'

const props = defineProps<{
  standing: Standing | null
  currency: string | null
}>()

const emit = defineEmits<{
  /** Record a statement balance; the page opens the dialog for it. */
  record: []
  /** Show the open lines, whatever their dates. */
  showOpen: []
}>()

/** A statement more than a month behind. Banks issue them monthly, so past
 *  that a whole statement is missing rather than merely late. */
const stale = computed(() => (props.standing?.daysSinceLastLine ?? 0) > 35)

function figure(value: number | null) {
  return value === null ? '—' : formatExact(value, props.currency)
}

function signed(value: number) {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatExact(Math.abs(value), props.currency)}`
}

function ago(days: number) {
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}

const checkDetail = computed(() => {
  const check = props.standing?.check
  if (!check) return ''
  return (
    'On that date the bank should hold what the books have cleared, plus the open statement lines up to it. ' +
    'A difference means a line was never imported, or an entry was matched to the wrong line.'
  )
})
</script>
