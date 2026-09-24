<!--
  Create a Payment Entry or a Journal Entry from a line, and reconcile it.

  ERPNext's own `create_payment_entry_bts` and `create_journal_entry_bts`, each
  of which inserts, submits and reconciles in one call. The form here only
  collects their arguments, with the line's own values filled in.
-->

<template>
  <div class="space-y-3">
    <div class="grid gap-3 sm:grid-cols-2">
      <template v-if="mode === 'journal'">
        <LinkControl
          v-model="account"
          doctype="Account"
          label="Account"
          :filters="{ company: transaction.company, is_group: 0 }"
          :disabled="busy"
          required
          description="The other side of the entry"
        />
        <FormControl
          v-model="entryType"
          type="select"
          label="Entry type"
          :options="ENTRY_TYPES"
          :disabled="busy"
        />
      </template>

      <LinkControl
        v-model="partyType"
        doctype="Party Type"
        label="Party type"
        :disabled="busy"
        :required="mode === 'payment'"
      />
      <LinkControl
        v-if="partyType"
        :key="partyType"
        v-model="party"
        :doctype="partyType"
        label="Party"
        title-first
        :disabled="busy"
        :required="mode === 'payment'"
      />
      <div v-else class="hidden sm:block" />

      <FormControl v-model="postingDate" type="date" label="Posting date" :disabled="busy" />
      <FormControl v-model="referenceDate" type="date" label="Reference date" :disabled="busy" />
      <FormControl v-model="referenceNumber" label="Reference" :disabled="busy" class="sm:col-span-2" />
      <LinkControl
        v-model="modeOfPayment"
        doctype="Mode of Payment"
        label="Mode of payment"
        :disabled="busy"
      />
      <LinkControl
        v-if="mode === 'payment'"
        v-model="costCenter"
        doctype="Cost Center"
        label="Cost center"
        :filters="{ company: transaction.company, is_group: 0 }"
        :disabled="busy"
      />
    </div>

    <p
      v-if="mode === 'journal' && transaction.allocated_amount > 0.005"
      class="text-p-sm text-ink-amber-7"
    >
      Part of this line is already matched. ERPNext books a journal entry for the whole line
      ({{ formatExact(Math.abs(amountOf(transaction)), transaction.currency) }}) and reconciles only what is left.
    </p>

    <ErrorMessage v-if="problem" :message="problem" />

    <div class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-1 pt-3">
      <p class="text-p-sm tabular-nums text-ink-gray-6">
        {{ mode === 'payment' ? (transaction.deposit > 0 ? 'Receive' : 'Pay') : 'Book' }}
        {{ formatExact(mode === 'payment' ? transaction.unallocated_amount : Math.abs(amountOf(transaction)), transaction.currency) }}
      </p>
      <Button
        variant="solid"
        :label="mode === 'payment' ? 'Create payment entry and reconcile' : 'Create journal entry and reconcile'"
        :disabled="!ready"
        :loading="busy"
        @click="save"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, ErrorMessage, FormControl, toast } from 'frappe-ui'
import LinkControl from '@/components/LinkControl.vue'
import { formatExact } from '@/data/format'
import { useCreateJournalEntry, useCreatePaymentEntry, write } from '@/data/reconciliation'
import { amountOf, proposedReference, type TransactionRow } from '@/data/reconciliationRules'

const props = defineProps<{
  transaction: TransactionRow
  mode: 'payment' | 'journal'
}>()

const emit = defineEmits<{ done: [unallocated: number]; dirty: [dirty: boolean] }>()

/** `Journal Entry.voucher_type`, minus the ones a bank line is never. */
const ENTRY_TYPES = ['Bank Entry', 'Journal Entry', 'Contra Entry', 'Credit Card Entry', 'Cash Entry']

const account = ref<string | null>(null)
const entryType = ref('Bank Entry')
const partyType = ref<string | null>(null)
const party = ref<string | null>(null)
const postingDate = ref('')
const referenceDate = ref('')
const referenceNumber = ref('')
const modeOfPayment = ref<string | null>(null)
const costCenter = ref<string | null>(null)
const busy = ref(false)
const problem = ref('')

const createPayment = useCreatePaymentEntry()
const createJournal = useCreateJournalEntry()

// The line's own values, as ERPNext's dialog fills them: its date for both
// dates, its reference (or description), its party, and its transaction type
// as the mode of payment where it names one.
function reset() {
  account.value = null
  entryType.value = 'Bank Entry'
  partyType.value = props.transaction.party_type
  party.value = props.transaction.party
  postingDate.value = props.transaction.date
  referenceDate.value = props.transaction.date
  referenceNumber.value = proposedReference(props.transaction)
  modeOfPayment.value = null
  costCenter.value = null
  problem.value = ''
}

watch(() => [props.transaction.name, props.mode], reset, { immediate: true })

// A party left over from another party type is a name that means nothing.
watch(partyType, (value, previous) => {
  if (previous !== undefined && value !== previous) party.value = null
})

const dirty = computed(() =>
  Boolean(account.value) ||
  partyType.value !== props.transaction.party_type ||
  party.value !== props.transaction.party,
)
watch(dirty, (value) => emit('dirty', value), { immediate: true })

const ready = computed(() => {
  if (!postingDate.value || !referenceDate.value) return false
  if (props.mode === 'payment') return Boolean(partyType.value && party.value)
  return Boolean(account.value && (!partyType.value || party.value))
})

async function save() {
  busy.value = true
  problem.value = ''
  try {
    const common = {
      bank_transaction_name: props.transaction.name,
      posting_date: postingDate.value,
      reference_date: referenceDate.value,
      reference_number: referenceNumber.value,
      mode_of_payment: modeOfPayment.value || undefined,
    }
    const done =
      props.mode === 'payment'
        ? await write(createPayment, {
            ...common,
            party_type: partyType.value!,
            party: party.value!,
            cost_center: costCenter.value || undefined,
          })
        : await write(createJournal, {
            ...common,
            second_account: account.value!,
            entry_type: entryType.value,
            party_type: partyType.value || undefined,
            party: party.value || undefined,
          })
    if (!done.ok || !done.data) {
      problem.value = done.error?.message || 'The entry could not be created'
      return
    }
    toast.success(props.mode === 'payment' ? 'Payment entry created and reconciled' : 'Journal entry created and reconciled')
    emit('done', done.data.unallocated_amount)
  } finally {
    busy.value = false
  }
}
</script>
