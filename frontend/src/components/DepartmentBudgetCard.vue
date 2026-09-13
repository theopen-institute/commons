<template>
  <div class="rounded-3 bg-surface-gray-1 p-3 text-p-sm">
    <p class="font-semibold text-ink-gray-8">{{ summary.department }} budget <span v-if="!summary.missing">· {{ summary.fiscal_year }}</span></p>
    <p v-if="summary.missing" class="mt-2 text-ink-red-4">No annual budget is configured. Procurement approval can proceed; Finance must create the allocation before Material Request submission.</p>
    <template v-else>
      <p v-if="summary.inactive" class="mt-2 text-ink-red-4">Finance must reconcile submitted Material Requests before further Material Requests can be submitted.</p>
      <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <div v-for="entry in entries" :key="entry.label">
          <dt class="text-ink-gray-6">{{ entry.label }}</dt>
          <dd class="font-medium text-ink-gray-9">{{ formatCurrency(entry.value ?? 0, summary.currency) }}</dd>
        </div>
      </dl>
      <p v-if="(summary.projected_available ?? 0) < 0" class="mt-2 text-ink-red-4">
        Provisional shortfall: {{ formatCurrency(-(summary.projected_available ?? 0), summary.currency) }}. This is a forecast; the hard limit is checked on Material Request submission.
      </p>
      <details v-if="requestName" class="mt-2" @toggle="loadDocuments">
        <summary class="cursor-pointer text-ink-gray-7">Submitted Material Requests</summary>
        <p v-if="documents.loading">Loading…</p>
        <p v-if="documents.error" class="text-ink-red-4">Could not load supporting documents.</p>
        <ul v-if="documents.data" class="mt-2 space-y-1">
          <li v-for="doc in documents.data" :key="`${doc.doctype}:${doc.name}`">
            <a :href="`/app/${doc.doctype.toLowerCase().replaceAll(' ', '-')}/${encodeURIComponent(doc.name)}`" target="_blank" rel="noopener noreferrer" class="underline">{{ doc.doctype }} · {{ doc.name }}</a>
            — {{ formatCurrency(doc.amount, summary.currency) }}
          </li>
        </ul>
        <p class="mt-1 text-ink-gray-5">Only submitted Material Requests you can read are listed.</p>
      </details>
      <p class="mt-2 text-ink-gray-5">MR quantity × submitted rate in company currency. Outstanding Procurement Requests are provisional only.</p>
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
  { label: 'Submitted MR usage', value: props.summary.used },
  { label: 'Outstanding procurement (provisional)', value: props.summary.provisional },
  { label: 'Available', value: props.summary.available },
  { label: 'This request still outstanding', value: props.summary.request_amount },
  { label: 'Projected available (including this request)', value: props.summary.projected_available },
])
</script>
