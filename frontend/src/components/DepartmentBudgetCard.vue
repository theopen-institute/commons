<template>
  <div class="rounded-3 bg-surface-gray-1 p-3 text-p-sm">
    <p class="font-semibold text-ink-gray-8">{{ summary.department }} budget <span v-if="!summary.missing">· {{ summary.fiscal_year }}</span></p>

    <!-- What the figures mean is the server's to say: each notice is written
         beside the gate that makes it true (see `budget.summary_notices`), so a
         change to what approval actually enforces cannot leave this card
         promising the old rule. Warnings lead, footnotes follow the figures. -->
    <p
      v-for="notice in warnings"
      :key="notice.message"
      class="mt-2 text-ink-red-4"
    >
      {{ notice.message }}
    </p>

    <template v-if="!summary.missing">
      <dl class="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <div v-for="entry in entries" :key="entry.label">
          <dt class="text-ink-gray-6">{{ entry.label }}</dt>
          <dd class="font-medium text-ink-gray-9">{{ formatCurrency(entry.value ?? 0, summary.currency) }}</dd>
        </div>
      </dl>
      <details v-if="requestName" class="mt-2" @toggle="loadDocuments">
        <summary class="cursor-pointer text-ink-gray-7">Submitted Material Requests</summary>
        <p v-if="documents.loading">Loading…</p>
        <p v-if="documents.error" class="text-ink-red-4">Could not load supporting documents.</p>
        <ul v-if="documents.data" class="mt-2 space-y-1">
          <li v-for="doc in documents.data" :key="`${doc.doctype}:${doc.name}`">
            <!-- The link is the server's: turning a doctype name into a desk
                 route is core's convention, not this card's to reimplement. -->
            <a :href="doc.url" target="_blank" rel="noopener noreferrer" class="underline">{{ doc.doctype }} · {{ doc.name }}</a>
            — {{ formatCurrency(doc.amount, summary.currency) }}
          </li>
        </ul>
        <p class="mt-1 text-ink-gray-5">Only submitted Material Requests you can read are listed.</p>
      </details>
      <p
        v-for="notice in footnotes"
        :key="notice.message"
        class="mt-2 text-ink-gray-5"
      >
        {{ notice.message }}
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useCall } from 'frappe-ui'
import type { DepartmentBudgetSummary } from '@/data/procurement'
import { formatCurrency } from '@/data/format'

interface BudgetDocument {
  doctype: string
  name: string
  amount: number
  /** Where it opens in the desk. Built by the server — see `get_budget_documents`. */
  url: string
}

const props = defineProps<{ summary: DepartmentBudgetSummary; requestName?: string }>()

// `useCall`, like the rest of the app, rather than a bare resource.
const documents = useCall<BudgetDocument[], { request: string }>({
  url: '/api/v2/method/tbs_commons.procurement.budget.get_budget_documents',
  immediate: false,
})

// Once, not on every toggle: closing and reopening the drawer is not a request
// for fresher figures, and the card is redrawn whenever the queue reloads.
function loadDocuments(event: Event) {
  if (!(event.target as HTMLDetailsElement).open) return
  if (!props.requestName || documents.data || documents.loading) return
  documents.submit({ request: props.requestName })
}
const notices = computed(() => props.summary.notices ?? [])
const warnings = computed(() =>
  notices.value.filter((notice) => notice.severity === 'warning'),
)
const footnotes = computed(() =>
  notices.value.filter((notice) => notice.severity !== 'warning'),
)
const entries = computed(() => [
  { label: 'Annual budget', value: props.summary.annual },
  { label: 'Spent', value: props.summary.spent },
  { label: 'Committed', value: props.summary.committed },
  { label: 'Remaining', value: props.summary.remaining },
  { label: 'Open requests', value: props.summary.open_requests },
])
</script>
