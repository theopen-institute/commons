<template>
  <div class="rounded-4 border border-outline-gray-1">
    <!-- What the two right-hand numbers are. A statement's columns are not
         self-evident until you have read one line of it, and this is cheaper
         than making every reader work it out from the first row. -->
    <div
      class="flex items-baseline justify-between gap-4 border-b border-outline-gray-1 px-4 py-2 text-p-sm text-ink-gray-5"
    >
      <span>{{ account.truncated ? `Latest ${account.lines.length}` : 'All activity' }}</span>
      <span class="shrink-0">Amount · Balance</span>
    </div>

    <ul>
      <!-- Where the statement starts from. Always drawn, even at zero: "you
           began this period owing nothing" is a fact the reader wants, and a
           statement whose first line is a charge reads as though the account
           had no history at all. -->
      <li
        class="flex items-baseline justify-between gap-4 border-b border-outline-gray-1 px-4 py-3"
      >
        <div class="min-w-0">
          <div class="text-base-medium text-ink-gray-7">
            {{ account.truncated ? 'Balance brought forward' : 'Opening balance' }}
          </div>
          <div v-if="account.truncated" class="mt-0.5 text-p-sm text-ink-gray-5">
            {{ pluralise(earlier, 'earlier entry', 'earlier entries') }}, not listed
          </div>
        </div>
        <div class="shrink-0 text-right tabular-nums text-ink-gray-7">
          {{ formatExact(account.opening, account.currency) }}
        </div>
      </li>

      <li
        v-for="line in account.lines"
        :key="line.name"
        class="flex items-start justify-between gap-4 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
      >
        <div class="min-w-0">
          <div class="truncate text-base-medium text-ink-gray-8">
            {{ describe(line) }}
          </div>
          <!-- Each fact is read on its own, so each is its own element: they
               stay whole when the row wraps, which at 390px it does. -->
          <div class="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-p-sm text-ink-gray-5">
            <span>{{ formatDate(line.date) }}</span>
            <span v-if="line.voucher_no">{{ line.voucher_no }}</span>
            <!-- Only where there is more than one account in play. A student
                 whose every line says "Debtors" learns nothing from it; a member
                 of staff whose payroll, income tax and social security are all
                 posted against them cannot read the statement without it. -->
            <span v-if="showAccounts">{{ line.account }}</span>
          </div>
          <p v-if="line.remarks" class="mt-1 text-p-sm text-ink-gray-5">
            {{ line.remarks }}
          </p>
        </div>
        <div class="shrink-0 text-right">
          <!-- Signed by what it does to the balance, not by which side of the
               books it was posted to. A payment from a customer and a payment
               to a supplier are opposite entries and both bring the balance
               down, and the reader is watching the balance. -->
          <div class="tabular-nums" :class="movementClass(line)">
            {{ movement(line) }}
          </div>
          <div class="mt-0.5 tabular-nums text-p-sm text-ink-gray-5">
            {{ formatExact(line.balance, account.currency) }}
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatDate, formatExact, pluralise } from '@/data/format'
import type { StatementAccount, StatementLine } from '@/data/statement'

/**
 * One account's movements, as a statement lists them.
 *
 * Deliberately not a table. A statement has four columns on paper and two on a
 * phone, and the version that works at 390px — what it was and when, against
 * what it cost and what you were left owing — is the same information in the
 * same order, so there is one layout here rather than a table and a stacked
 * copy of it that have to be kept saying the same thing.
 */
const props = defineProps<{ account: StatementAccount }>()

/** How many movements are folded into the opening rather than listed. */
const earlier = computed(() => props.account.entries - props.account.lines.length)

/**
 * Whether the lines on screen touch more than one ledger account.
 *
 * Judged on what is actually listed rather than on the whole history, which is
 * the honest question: the label is there to tell two lines apart, and lines
 * that are not drawn have none to tell apart.
 */
const showAccounts = computed(
  () => new Set(props.account.lines.map((line) => line.account)).size > 1,
)

/**
 * What a line was, in the reader's words rather than the ledger's.
 *
 * The voucher type is a doctype name — `Sales Invoice`, `Payment Entry`,
 * `Fees` — which reads well enough for most of them and is what the ledger
 * actually recorded, so it is shown as-is rather than translated through a map
 * that would go out of date the first time a site posted something new. An
 * opening entry says so instead: it is not a thing that happened, it is a
 * balance somebody carried in.
 */
function describe(line: StatementLine): string {
  if (line.is_opening) return 'Opening entry'
  return line.voucher_type || 'Ledger entry'
}

function movement(line: StatementLine): string {
  const amount = line.charged || line.paid
  const sign = line.charged ? '+' : '−'
  return `${sign}${formatExact(amount, props.account.currency)}`
}

function movementClass(line: StatementLine): string {
  // Colour carries no information the sign does not; it is there so a long
  // statement can be skimmed for the payments in it.
  return line.charged ? 'text-ink-gray-8' : 'text-ink-green-3'
}
</script>
