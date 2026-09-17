<template>
  <div class="overflow-x-auto rounded-4 border border-outline-gray-1">
    <table class="w-full min-w-[26rem] text-left">
      <thead class="bg-surface-gray-2">
        <tr class="text-p-sm text-ink-gray-6">
          <th class="px-3 py-2 font-normal">Expense</th>
          <th class="px-3 py-2 text-right font-normal">Claimed</th>
          <th v-if="showSanctioned" class="px-3 py-2 text-right font-normal">
            {{ editable ? 'Allow' : 'Sanctioned' }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="line in lines"
          :key="line.name"
          class="border-t border-outline-gray-1 align-top"
        >
          <td class="px-3 py-2">
            <div class="text-base text-ink-gray-8">{{ line.expense_type }}</div>
            <!-- Rendered as text, never as markup: the stored field is a Text
                 Editor and the server flattens it on the way out. -->
            <div
              v-if="line.description"
              class="mt-0.5 whitespace-pre-line text-p-sm text-ink-gray-6"
            >
              {{ line.description }}
            </div>
            <div v-if="line.expense_date" class="mt-0.5 text-p-sm text-ink-gray-5">
              {{ formatDate(line.expense_date) }}
            </div>
          </td>
          <td
            class="whitespace-nowrap px-3 py-2 text-right text-base text-ink-gray-7"
          >
            {{ formatCurrency(line.amount, currency) }}
          </td>
          <td v-if="showSanctioned" class="px-3 py-2 text-right">
            <!-- An approver may allow less than was claimed. The figure travels
                 with the decision in one call, and HRMS revalidates it there:
                 anything above the claim is refused on the save. -->
            <FormControl
              v-if="editable"
              :model-value="allowed(line)"
              type="number"
              size="sm"
              min="0"
              :max="line.amount"
              step="0.01"
              class="ml-auto w-28 [&_input]:text-right"
              :aria-label="`Amount allowed for ${line.expense_type}`"
              @update:model-value="(value: string | number) => set(line, value)"
            />
            <span
              v-else
              class="whitespace-nowrap text-base"
              :class="
                line.sanctioned_amount < line.amount
                  ? 'text-ink-amber-3'
                  : 'text-ink-gray-7'
              "
            >
              {{ formatCurrency(line.sanctioned_amount, currency) }}
            </span>
          </td>
        </tr>
      </tbody>
      <tfoot v-if="lines.length > 1">
        <tr class="border-t border-outline-gray-2 bg-surface-gray-1">
          <td class="px-3 py-2 text-p-sm text-ink-gray-6">Total</td>
          <td
            class="whitespace-nowrap px-3 py-2 text-right text-base-medium text-ink-gray-8"
          >
            {{ formatCurrency(claimedTotal, currency) }}
          </td>
          <td
            v-if="showSanctioned"
            class="whitespace-nowrap px-3 py-2 text-right text-base-medium text-ink-gray-8"
          >
            {{ formatCurrency(sanctionedTotal, currency) }}
          </td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import { formatCurrency, formatDate } from '@/data/format'
import type { ExpenseClaimLine } from '@/data/expense'

const props = withDefaults(
  defineProps<{
    lines: ExpenseClaimLine[]
    /** From the claim, not the session: amounts read in the document's currency. */
    currency?: string | null
    /** Whether the claim has been settled, so what was allowed is an answer
     *  rather than a copy of what was asked for. */
    settled?: boolean
    /** Whether this user is the one settling it, and may change the figures. */
    editable?: boolean
  }>(),
  { currency: null, settled: false, editable: false },
)

/**
 * What the approver is allowing, per row, where it differs from what the claim
 * already says.
 *
 * Only the rows actually changed, keyed by the row's own name. The server
 * refuses a name the claim does not have — a figure that was silently dropped
 * would read on screen as an approval of the full amount — so sending the whole
 * table would turn a claim edited since the queue loaded into a failed decision
 * rather than a partial one.
 */
const sanctioned = defineModel<Record<string, number>>('sanctioned', {
  default: () => ({}),
})

// Shown once there is a second figure worth reading: while a claim is still a
// draft, "sanctioned" is only a copy of what was asked for.
const showSanctioned = computed(() => props.editable || props.settled)

function allowed(line: ExpenseClaimLine): number {
  return sanctioned.value[line.name] ?? line.sanctioned_amount
}

function set(line: ExpenseClaimLine, value: string | number) {
  const amount = Number(value)
  const next = { ...sanctioned.value }
  // Back to what the claim says is not a change, so it is not sent as one.
  if (!Number.isFinite(amount) || amount === line.sanctioned_amount) {
    delete next[line.name]
  } else {
    next[line.name] = amount
  }
  sanctioned.value = next
}

const claimedTotal = computed(() =>
  props.lines.reduce((total, line) => total + line.amount, 0),
)

const sanctionedTotal = computed(() =>
  props.lines.reduce((total, line) => total + allowed(line), 0),
)
</script>
