<template>
  <div class="rounded-3 bg-surface-gray-1 p-3 text-p-sm">
    <p class="font-semibold text-ink-gray-8">{{ summary.department }} budget <span v-if="!summary.missing">· {{ summary.fiscal_year }}</span></p>
    <p v-if="summary.missing" class="mt-2 text-ink-red-4">No annual budget is configured. Finance must create the allocation before approval.</p>
    <template v-else>
      <p v-if="summary.inactive" class="mt-2 text-ink-red-4">Finance must reconcile opening spending and commitments before approvals can continue.</p>
      <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <div v-for="entry in entries" :key="entry.label">
          <dt class="text-ink-gray-6">{{ entry.label }}</dt>
          <dd class="font-medium text-ink-gray-9">{{ formatCurrency(entry.value ?? 0, summary.currency) }}</dd>
        </div>
      </dl>
      <p v-if="(summary.after_approval ?? 0) < 0" class="mt-2 text-ink-red-4">
        Budget shortfall: {{ formatCurrency(-(summary.after_approval ?? 0), summary.currency) }}. Approval will be blocked.
      </p>
      <details v-if="requestName" class="mt-2" @toggle="loadDocuments">
        <summary class="cursor-pointer text-ink-gray-7">Supporting documents</summary>
        <p v-if="documents.loading">Loading…</p>
        <p v-if="documents.error" class="text-ink-red-4">Could not load supporting documents.</p>
        <ul v-if="documents.data" class="mt-2 space-y-1">
          <li v-for="doc in documents.data" :key="`${doc.doctype}:${doc.name}`">
            <a :href="`/app/${doc.doctype.toLowerCase().replaceAll(' ', '-')}/${encodeURIComponent(doc.name)}`" target="_blank" rel="noopener noreferrer" class="underline">{{ doc.doctype }} · {{ doc.name }}</a>
            — {{ formatCurrency(doc.amount, summary.currency) }}
          </li>
        </ul>
        <p class="mt-1 text-ink-gray-5">Original document amounts; linked stages replace one another. Only documents you can read are listed.</p>
      </details>
      <p class="mt-2 text-ink-gray-5">Net purchase values, excluding taxes. Availability is checked again when you approve.</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { createResource } from 'frappe-ui'
import type { DepartmentBudgetSummary } from '@/data/procurement'
import { formatCurrency } from '@/data/format'
const props = defineProps<{ summary: DepartmentBudgetSummary; requestName?: string }>()
const documents = createResource({ url: 'tbs_commons.budget.get_budget_documents' })
function loadDocuments(event: Event) {
  if ((event.target as HTMLDetailsElement).open && props.requestName) {
    documents.submit({ request: props.requestName })
  }
}
const entries = computed(() => [
  { label: 'Annual budget', value: props.summary.budget },
  { label: 'Spent', value: props.summary.spent },
  { label: 'Approved, awaiting order', value: props.summary.reserved },
  { label: 'Outstanding orders', value: props.summary.committed },
  { label: 'Available', value: props.summary.available },
  { label: props.summary.already_reserved ? 'Approved amount' : 'This request', value: props.summary.request_amount },
  ...(!props.summary.already_reserved ? [{ label: 'Available after approval', value: props.summary.after_approval }] : []),
])
</script>

