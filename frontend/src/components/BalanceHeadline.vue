<template>
  <div class="grid gap-3" :class="lending ? 'sm:grid-cols-2' : ''">
    <!-- The two are drawn as two, always, and never summed. A loan and an
         invoice are settled to different schedules and through different
         people, so a combined figure would be a number nobody could act on --
         which is the whole reason this section has two balances. -->
    <div class="rounded-4 border border-outline-gray-1 px-4 py-3">
      <div class="text-p-sm text-ink-gray-6">Account balance</div>
      <div class="mt-1 text-2xl font-semibold tabular-nums" :class="accountTone">
        {{ formatExact(balanceAmount(total.account), total.currency) }}
      </div>
      <div class="mt-1 text-p-sm text-ink-gray-5">{{ accountNote }}</div>
    </div>

    <div v-if="lending" class="rounded-4 border border-outline-gray-1 px-4 py-3">
      <div class="text-p-sm text-ink-gray-6">Loan balance</div>
      <div class="mt-1 text-2xl font-semibold tabular-nums text-ink-gray-8">
        {{ formatExact(total.loans, total.currency) }}
      </div>
      <!-- Said on the figure itself rather than in a footnote. It is the
           outstanding principal, and a reader who took it for a payoff quote
           would be short by whatever interest has accrued since the last
           demand -- see `commons/statement/loans.py`. -->
      <div class="mt-1 text-p-sm text-ink-gray-5">
        {{ total.loans ? 'Outstanding principal, before interest' : 'Nothing outstanding' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatExact } from '@/data/format'
import {
  balanceAmount,
  directionLabel,
  inReadersFavour,
  type StatementTotal,
} from '@/data/statement'

/**
 * The two figures at the top of the page, for one currency.
 *
 * "Account" is everything the ledger holds — fees, invoices, payments, credit
 * notes, journal entries — because every one of those is a `GL Entry` against
 * the party and there is no reason for a reader to see them as four things.
 * "Loan" is the one that is genuinely separate, and it is separate here for the
 * same reason it is separate in the accounts.
 */
const props = defineProps<{
  total: StatementTotal
  /** Whether this site lends at all. Without it there is one figure, not a
   *  second one reading zero — a loan balance of nought is only worth saying to
   *  somebody who could have had one. */
  lending: boolean
}>()

// Which way the figure runs is the server's answer (`total.direction`) rather
// than something worked out here from its sign: the sign alone cannot say,
// because a receivable and a payable balance run opposite ways, and the print
// format needs the same answer. All this component picks is the English.
const accountNote = computed(() => directionLabel(props.total.direction))

const accountTone = computed(() =>
  inReadersFavour(props.total.direction) ? 'text-ink-green-3' : 'text-ink-gray-8',
)
</script>
