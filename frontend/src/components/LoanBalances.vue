<template>
  <ul class="space-y-3">
    <li
      v-for="loan in loans"
      :key="loan.loan"
      class="rounded-4 border border-outline-gray-1 px-4 py-3"
    >
      <div class="flex items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="truncate text-base-medium text-ink-gray-8">{{ loan.product }}</div>
          <div class="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-p-sm text-ink-gray-5">
            <span>{{ loan.loan }}</span>
            <span v-if="loan.disbursement_date">
              Disbursed {{ formatDate(loan.disbursement_date) }}
            </span>
            <span v-if="loan.rate_of_interest">{{ loan.rate_of_interest }}% interest</span>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="tabular-nums text-base-medium text-ink-gray-8">
            {{ formatExact(loan.outstanding, loan.currency) }}
          </div>
          <div class="mt-0.5 text-p-sm text-ink-gray-5">outstanding</div>
        </div>
      </div>

      <!-- What the outstanding figure is measured against. A borrower looking
           at a balance smaller than the loan they signed for wants to see
           whether that is because they have repaid or because the money has not
           all been handed over yet, and those are two different rows. -->
      <dl class="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-p-sm">
        <div class="flex gap-1.5">
          <dt class="text-ink-gray-5">{{ borrowedLabel(loan) }}</dt>
          <dd class="tabular-nums text-ink-gray-7">
            {{ formatExact(borrowed(loan), loan.currency) }}
          </dd>
        </div>
        <div class="flex gap-1.5">
          <dt class="text-ink-gray-5">Repaid</dt>
          <dd class="tabular-nums text-ink-gray-7">
            {{ formatExact(loan.repaid, loan.currency) }}
          </dd>
        </div>
        <div v-if="loan.written_off" class="flex gap-1.5">
          <dt class="text-ink-gray-5">Written off</dt>
          <dd class="tabular-nums text-ink-gray-7">
            {{ formatExact(loan.written_off, loan.currency) }}
          </dd>
        </div>
        <div class="flex gap-1.5">
          <dt class="text-ink-gray-5">Status</dt>
          <dd class="text-ink-gray-7">{{ loan.status }}</dd>
        </div>
      </dl>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { formatDate, formatExact } from '@/data/format'
import type { LoanBalance } from '@/data/statement'

/**
 * What is owed on loans, one card per loan.
 *
 * Read-only and deliberately shallow. A repayment schedule, the security behind
 * a loan and the demands raised against it are the lender's forms, and this
 * page is a statement rather than a way into them — so nothing here links out,
 * and the server sends no more than these figures.
 */
defineProps<{ loans: LoanBalance[] }>()

/**
 * What has actually been lent, and what the figure beside it is.
 *
 * A loan only partly paid out is still being disbursed, and its outstanding
 * balance is measured against what has left the building rather than against
 * what was sanctioned. Saying "Sanctioned 60,000" beside an outstanding of
 * 20,000 on such a loan invites the reader to conclude they have repaid 40,000.
 */
function borrowed(loan: LoanBalance): number {
  return loan.disbursed || loan.sanctioned
}

function borrowedLabel(loan: LoanBalance): string {
  return loan.disbursed && loan.disbursed < loan.sanctioned ? 'Disbursed so far' : 'Borrowed'
}
</script>
