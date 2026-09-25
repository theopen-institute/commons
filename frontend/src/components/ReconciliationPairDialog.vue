<!--
  One statement line and one entry, to be matched. What a drop on the board
  opens: the pair side by side, whether the amounts agree, and a Save.

  The match is ERPNext's `reconcile_vouchers`, the same call the line dialog's
  Match tab makes. When the amounts differ it allocates the smaller and leaves
  the rest open on whichever side has more, which the dialog says before Save
  rather than after.
-->

<template>
  <Dialog
    v-model:open="open"
:title="entry?.draft ? 'Submit and match' : 'Match these'"
    :actions="actions"
    :dismissible="!busy"
    size="xl"
  >
    <div v-if="line && entry" class="space-y-3">
      <div class="grid gap-3 sm:grid-cols-2">
        <div class="rounded-4 border border-outline-gray-2 px-3 py-2">
          <div class="text-p-xs text-ink-gray-5">Statement line · {{ formatDate(line.date) }}</div>
          <div class="mt-0.5 break-words text-p-sm text-ink-gray-8">{{ line.description || line.name }}</div>
          <div class="mt-1 text-base-medium tabular-nums" :class="lineAmount > 0 ? 'text-ink-green-7' : 'text-ink-gray-8'">
            {{ signed(lineAmount) }}
          </div>
        </div>
        <div class="rounded-4 border border-outline-gray-2 px-3 py-2">
          <div class="text-p-xs text-ink-gray-5">{{ entry.doctype }} · {{ formatDate(entry.date) }}</div>
          <a
            :href="deskUrl(entry.doctype, entry.name)"
            target="_blank"
            class="mt-0.5 block text-p-sm text-ink-gray-8 hover:underline"
          >
            {{ entry.name }}<template v-if="entry.against"> · {{ entry.against }}</template>
          </a>
          <div class="mt-1 text-base-medium tabular-nums" :class="entryAmount > 0 ? 'text-ink-green-7' : 'text-ink-gray-8'">
            {{ signed(entryAmount) }}
          </div>
        </div>
      </div>

      <p v-if="!sameWay" class="text-p-sm text-ink-red-7">
        One is money in and the other money out, so they cannot be the same transaction.
      </p>
      <p v-else-if="difference === 0" class="flex items-center gap-1.5 text-p-sm text-ink-green-7">
        <span class="lucide-circle-check size-4" /> Same amount. Both leave their lists.
      </p>
      <p v-else class="text-p-sm text-ink-amber-7">
        The amounts differ by {{ formatExact(Math.abs(difference), currency) }}. ERPNext matches the smaller, and
        {{ Math.abs(lineAmount) > Math.abs(entryAmount) ? 'the rest of the statement line' : 'the rest of the entry' }}
        stays open to be matched with something else.
      </p>
      <p v-if="daysApart > 31" class="text-p-sm text-ink-gray-6">
        They are {{ daysApart }} days apart.
      </p>

      <p v-if="entry.draft" class="rounded-4 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7">
        {{ entry.name }} is a draft. Matching submits it first, as it now stands, which posts it to the ledger
        dated {{ formatDate(entry.date) }}. If anything on it needs changing,
        <a :href="deskUrl(entry.doctype, entry.name)" target="_blank" class="underline">edit it in the desk</a>
        first.
      </p>

      <ErrorMessage v-if="problem" :message="problem" />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, ErrorMessage, toast, type DialogAction } from 'frappe-ui'
import { formatDate, formatExact } from '@/data/format'
import { deskUrl, useReconcileVouchers, useSubmitAndReconcile, write } from '@/data/reconciliation'
import { daysBetween, money, type BookEntry, type TransactionRow } from '@/data/reconciliationRules'

const props = defineProps<{
  line: TransactionRow | null
  entry: BookEntry | null
  currency: string | null
}>()

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ done: [line: string, unallocated: number] }>()

const reconcile = useReconcileVouchers()
const submitAndReconcile = useSubmitAndReconcile()
const busy = ref(false)
const problem = ref('')

watch(open, (isOpen) => {
  if (isOpen) problem.value = ''
})

const lineAmount = computed(() =>
  props.line ? money(props.line.deposit > 0 ? props.line.unallocated_amount : -props.line.unallocated_amount) : 0,
)
const entryAmount = computed(() => (props.entry ? money(props.entry.debit - props.entry.credit) : 0))
const sameWay = computed(() => Math.sign(lineAmount.value) === Math.sign(entryAmount.value))
const difference = computed(() => money(Math.abs(lineAmount.value) - Math.abs(entryAmount.value)))
const daysApart = computed(() =>
  props.line && props.entry ? Math.abs(daysBetween(props.line.date, props.entry.date)) : 0,
)

function signed(value: number) {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatExact(Math.abs(value), props.currency)}`
}

const actions = computed<DialogAction[]>(() => [
  {
    label: props.entry?.draft ? 'Submit and match' : 'Match',
    variant: 'solid',
    disabled: !sameWay.value,
    loading: busy.value,
    onClick: async ({ close }) => {
      if (!props.line || !props.entry) return
      busy.value = true
      problem.value = ''
      try {
        const done = props.entry.draft
          ? await write(submitAndReconcile, {
              bank_transaction: props.line.name,
              voucher_type: props.entry.doctype,
              voucher: props.entry.name,
            })
          : await write(reconcile, {
              bank_transaction_name: props.line.name,
              vouchers: JSON.stringify([{ payment_doctype: props.entry.doctype, payment_name: props.entry.name }]),
            })
        if (!done.ok || !done.data) {
          problem.value = done.error?.message || 'These could not be matched'
          return
        }
        toast.success(
          `${props.entry.name} ${props.entry.draft ? 'submitted and ' : ''}matched to the statement line of ${formatDate(props.line.date)}`,
        )
        emit('done', props.line.name, done.data.unallocated_amount)
        close()
      } finally {
        busy.value = false
      }
    },
  },
])
</script>
