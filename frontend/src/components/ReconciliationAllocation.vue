<!--
  What a new payment entry is booked against: the party's outstanding
  invoices, each with the amount of this payment allocated to it.

  The proposal (`proposeAllocation`) is only a starting point: the invoice
  whose outstanding amount is exactly the payment, or else the oldest first.
  Every amount can be changed or cleared, and what is left over is shown as
  unallocated, which ERPNext books as an advance on the party. Nothing is
  written from here; the entry tab sends the allocation with the payment
  entry when it is created or drafted.
-->

<template>
  <section class="space-y-2">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="text-p-sm font-medium text-ink-gray-7">Booked against</h3>
      <div v-if="documents.length" class="flex gap-1">
        <Button size="sm" variant="ghost" label="Oldest first" :disabled="disabled" @click="oldestFirst" />
        <Button size="sm" variant="ghost" label="Clear" :disabled="disabled" @click="allocation = {}" />
      </div>
    </div>

    <div v-if="loading" class="space-y-1.5">
      <Skeleton class="h-8 w-full rounded-4" />
      <Skeleton class="h-8 w-full rounded-4" />
    </div>
    <ErrorMessage v-else-if="error" :message="error" />
    <p
      v-else-if="!documents.length"
      class="rounded-4 border border-dashed border-outline-gray-2 px-3 py-3 text-p-sm text-ink-gray-5"
    >
      Nothing is outstanding for this party. The payment will be booked as unallocated, an advance they can
      use against a later invoice.
    </p>

    <div v-else class="max-h-60 overflow-auto rounded-4 border border-outline-gray-2">
      <table class="w-full border-separate border-spacing-0 text-p-sm">
        <thead class="sticky top-0 bg-surface-white">
          <tr class="text-left text-ink-gray-5">
            <th class="w-full border-b border-outline-gray-2 px-3 py-1.5 font-medium">Document</th>
            <th class="border-b border-outline-gray-2 px-2 py-1.5 font-medium">Due</th>
            <th class="border-b border-outline-gray-2 px-2 py-1.5 text-right font-medium">Total</th>
            <th class="border-b border-outline-gray-2 px-2 py-1.5 text-right font-medium">Outstanding</th>
            <th class="border-b border-outline-gray-2 px-3 py-1.5 text-right font-medium">Allocate</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="document in documents"
            :key="documentKey(document)"
            :class="allocation[documentKey(document)] ? 'bg-surface-green-2' : ''"
          >
            <td class="max-w-0 border-b border-outline-gray-1 px-3 py-1.5">
              <a
                :href="deskUrl(document.voucher_type, document.voucher_no)"
                target="_blank"
                class="inline-flex items-center gap-0.5 font-medium text-ink-gray-8 hover:underline"
              >
                {{ document.voucher_no }} <span class="lucide-external-link size-3" />
              </a>
              <div class="truncate text-p-xs text-ink-gray-5">
                {{ document.voucher_type }}
                <template v-if="document.posting_date"> · {{ formatDate(document.posting_date) }}</template>
                <template v-if="document.bill_no"> · Bill {{ document.bill_no }}</template>
                <template v-if="document.payment_term"> · {{ document.payment_term }}</template>
              </div>
            </td>
            <td class="whitespace-nowrap border-b border-outline-gray-1 px-2 py-1.5 tabular-nums text-ink-gray-6">
              {{ document.due_date ? formatDate(document.due_date) : '—' }}
            </td>
            <td class="whitespace-nowrap border-b border-outline-gray-1 px-2 py-1.5 text-right tabular-nums text-ink-gray-6">
              {{ formatExact(document.invoice_amount, document.currency || currency) }}
            </td>
            <td class="whitespace-nowrap border-b border-outline-gray-1 px-2 py-1.5 text-right tabular-nums text-ink-gray-8">
              {{ formatExact(document.outstanding_amount, document.currency || currency) }}
            </td>
            <td class="border-b border-outline-gray-1 px-3 py-1">
              <div class="w-28">
                <TextInput
                  :model-value="allocation[documentKey(document)] ?? ''"
                  type="number"
                  min="0"
                  step="0.01"
                  size="sm"
                  :disabled="disabled"
                  :aria-label="`Allocate to ${document.voucher_no}`"
                  @update:model-value="(value) => set(document, value)"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="documents.length" class="flex flex-wrap justify-between gap-2 text-p-sm tabular-nums">
      <span class="text-ink-gray-6">
        {{ formatExact(check.total, currency) }} allocated of {{ formatExact(amount, currency) }}
      </span>
      <span v-if="check.unallocated > 0" class="text-ink-gray-6">
        {{ formatExact(check.unallocated, currency) }} left unallocated, as an advance
      </span>
    </div>
    <ul v-if="check.errors.length" class="space-y-0.5 text-p-sm text-ink-red-7">
      <li v-for="problem in check.errors" :key="problem">{{ problem }}</li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, ErrorMessage, Skeleton, TextInput } from 'frappe-ui'
import { formatDate, formatExact } from '@/data/format'
import { deskUrl } from '@/data/reconciliation'
import {
  allocateOldestFirst,
  checkAllocation,
  documentKey,
  type OutstandingDocument,
} from '@/data/paymentAllocation'

const props = defineProps<{
  documents: OutstandingDocument[]
  /** The payment's amount: what there is to allocate. */
  amount: number
  currency: string | null
  loading: boolean
  error: string
  disabled?: boolean
}>()

const allocation = defineModel<Record<string, number>>({ required: true })

const check = computed(() => checkAllocation(props.documents, allocation.value, props.amount))

defineExpose({ check })

function set(document: OutstandingDocument, value: unknown) {
  const next = { ...allocation.value }
  const number = Number(value)
  if (value === '' || value === null || !Number.isFinite(number) || number === 0) delete next[documentKey(document)]
  else next[documentKey(document)] = number
  allocation.value = next
}

function oldestFirst() {
  allocation.value = allocateOldestFirst(props.documents, props.amount)
}
</script>
