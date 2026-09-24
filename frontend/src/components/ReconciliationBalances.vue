<!--
  The three figures a reconciliation is for: what the books say the bank held,
  what the bank says it held, and the difference, which is zero when the
  period is done.

  The desk tool asked for the statement's closing balance in a field it never
  saved, so it was typed again every time the tool was opened. Here it is
  recorded as a `Bank Account Balance`, through a dialog with a Save, and read
  back on every visit.
-->

<template>
  <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
    <div class="rounded-4 border border-outline-gray-2 px-3 py-2">
      <div class="text-p-xs text-ink-gray-5">Opening, as per books</div>
      <div class="mt-0.5 text-base-medium tabular-nums text-ink-gray-8">
        {{ figure(balances.opening) }}
      </div>
    </div>
    <div class="rounded-4 border border-outline-gray-2 px-3 py-2">
      <div class="text-p-xs text-ink-gray-5">Cleared balance, as per books</div>
      <div class="mt-0.5 text-base-medium tabular-nums text-ink-gray-8">
        {{ figure(balances.cleared) }}
      </div>
    </div>
    <button
      type="button"
      class="rounded-4 border border-outline-gray-2 px-3 py-2 text-left hover:bg-surface-gray-1"
      title="Record the bank's closing balance"
      @click="openDialog"
    >
      <div class="flex items-center justify-between text-p-xs text-ink-gray-5">
        <span>Closing, as per statement</span>
        <span class="lucide-pencil size-3" />
      </div>
      <div class="mt-0.5 text-base-medium tabular-nums text-ink-gray-8">
        {{ balances.statement === null ? 'Not recorded' : figure(balances.statement) }}
      </div>
      <div
        v-if="balances.statementDate && balances.statementDate !== to"
        class="text-p-xs text-ink-gray-5"
      >
        as of {{ formatDate(balances.statementDate) }}
      </div>
    </button>
    <div
      class="rounded-4 border px-3 py-2"
      :class="
        difference === null
          ? 'border-outline-gray-2'
          : difference === 0
            ? 'border-outline-green-3 bg-surface-green-2'
            : 'border-outline-amber-3 bg-surface-amber-2'
      "
    >
      <div class="text-p-xs text-ink-gray-5">Difference</div>
      <div class="mt-0.5 text-base-medium tabular-nums text-ink-gray-8">
        {{ difference === null ? '—' : figure(difference) }}
      </div>
    </div>
  </div>

  <Dialog
    v-model:open="dialogOpen"
    title="Statement closing balance"
    :message="`${bankAccount} · the balance the bank's statement shows at the end of a day`"
    :actions="actions"
    :dismissible="!busy"
  >
    <div class="space-y-3">
      <FormControl v-model="draftDate" type="date" label="Date" />
      <FormControl v-model="draftBalance" type="number" label="Closing balance" />
      <ErrorMessage v-if="problem" :message="problem" />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import { formatDate, formatExact } from '@/data/format'
import { useSetStatementBalance, write, type Balances } from '@/data/reconciliation'
import { money } from '@/data/reconciliationRules'

const props = defineProps<{
  balances: Balances
  bankAccount: string
  currency: string | null
  /** The period's last day, which the balance is recorded for by default. */
  to: string
}>()

const emit = defineEmits<{ saved: [] }>()

const difference = computed(() =>
  props.balances.statement === null || props.balances.cleared === null
    ? null
    : money(props.balances.statement - props.balances.cleared),
)

function figure(value: number | null) {
  return value === null ? '—' : formatExact(value, props.currency)
}

const setBalance = useSetStatementBalance()
const dialogOpen = ref(false)
const draftDate = ref('')
const draftBalance = ref<string | number>('')
const busy = ref(false)
const problem = ref('')

function openDialog() {
  draftDate.value = props.to
  draftBalance.value = props.balances.statementDate === props.to ? (props.balances.statement ?? '') : ''
  problem.value = ''
  dialogOpen.value = true
}

defineExpose({ openDialog })

const actions = computed<DialogAction[]>(() => [
  {
    label: 'Save',
    variant: 'solid',
    disabled: !draftDate.value || draftBalance.value === '',
    loading: busy.value,
    onClick: async ({ close }) => {
      busy.value = true
      problem.value = ''
      try {
        const done = await write(setBalance, {
          bank_account: props.bankAccount,
          date: draftDate.value,
          balance: Number(draftBalance.value),
        })
        if (!done.ok) {
          problem.value = done.error?.message || 'The balance could not be saved'
          return
        }
        toast.success('Statement balance saved')
        emit('saved')
        close()
      } finally {
        busy.value = false
      }
    },
  },
])
</script>
