<!--
  Create a Payment Entry or a Journal Entry from a line, and reconcile it.

  ERPNext's own functions do the work (see `useCreatePaymentEntry` and
  `useCreateJournalEntry` in `data/reconciliation.ts`); the form collects
  their arguments, with the line's own values filled in.

  It also asks for every accounting dimension the company makes mandatory,
  such as Department. ERPNext refuses a voucher whose GL entries leave one out,
  and a bank line's own entry is against a Balance Sheet account, so on a
  company that requires one for both kinds of account, every entry from a
  statement line needs it. The company's default is filled in where there is
  one.
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
        v-for="dimension in dimensions"
        :key="dimension.fieldname"
        v-model="dimensionValues[dimension.fieldname]"
        :doctype="dimension.document_type"
        :label="dimension.label"
        :filters="{ company: transaction.company }"
        :disabled="busy"
        required
        :description="`Required on this company's ${dimension.mandatory_for_pl && dimension.mandatory_for_bs ? 'entries' : dimension.mandatory_for_pl ? 'income and expense entries' : 'balance sheet entries'}`"
      />
      <LinkControl
        v-if="mode === 'payment'"
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

    <ErrorMessage v-if="dimensionsError" :message="dimensionsError" />

    <ErrorMessage v-if="problem" :message="problem" />

    <div class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-1 pt-3">
      <p class="text-p-sm tabular-nums text-ink-gray-6">
        {{ mode === 'payment' ? (transaction.deposit > 0 ? 'Receive' : 'Pay') : 'Book' }}
        {{ formatExact(transaction.unallocated_amount, transaction.currency) }}
      </p>
      <div class="flex gap-2">
        <Button
          variant="subtle"
          label="Make draft"
          :disabled="!ready || (busy && !drafting)"
          :loading="busy && drafting"
          :title="`Create the ${mode === 'payment' ? 'payment' : 'journal'} entry as a draft, without submitting it or matching it to this line`"
          @click="save(true)"
        />
        <Button
          variant="solid"
          :label="mode === 'payment' ? 'Create payment entry and reconcile' : 'Create journal entry and reconcile'"
          :disabled="!ready || (busy && drafting)"
          :loading="busy && !drafting"
          @click="save(false)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Button, ErrorMessage, FormControl, toast } from 'frappe-ui'
import LinkControl from '@/components/LinkControl.vue'
import { formatExact } from '@/data/format'
import {
  requiredDimensions,
  useAccountingDimensions,
  useCreateJournalEntry,
  useCreatePaymentEntry,
  type AccountingDimension,
} from '@/data/reconciliation'
import { proposedReference, type TransactionRow } from '@/data/reconciliationRules'

const props = defineProps<{
  transaction: TransactionRow
  mode: 'payment' | 'journal'
}>()

const emit = defineEmits<{
  done: [unallocated: number]
  dirty: [dirty: boolean]
  /** A draft was created; nothing was posted or matched. */
  drafted: []
}>()

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
/** Which button the write in progress came from, for its spinner. */
const drafting = ref(false)
const problem = ref('')

const createPayment = useCreatePaymentEntry()
const createJournal = useCreateJournalEntry()
const dimensionSource = useAccountingDimensions()
const dimensions = ref<AccountingDimension[]>([])
const dimensionValues = reactive<Record<string, string | null>>({})
const dimensionsError = ref('')

/** The company's mandatory dimensions, with its defaults filled in. Asked
 *  again only when the company changes: every line of one account has one. */
async function loadDimensions() {
  const company = props.transaction.company
  dimensionsError.value = ''
  if (!company) return
  try {
    dimensions.value = requiredDimensions(await dimensionSource.load(company))
  } catch (error) {
    dimensionsError.value = `The company's accounting dimensions could not be read: ${(error as Error).message}`
    dimensions.value = []
  }
  for (const dimension of dimensions.value) {
    if (!dimensionValues[dimension.fieldname]) dimensionValues[dimension.fieldname] = dimension.default
  }
}

watch(() => props.transaction.company, loadDimensions, { immediate: true })

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
  if (dimensions.value.some((dimension) => !dimensionValues[dimension.fieldname])) return false
  if (props.mode === 'payment') return Boolean(partyType.value && party.value)
  return Boolean(account.value && (!partyType.value || party.value))
})

/** Create the entry and reconcile it, or with `draft` create it as a draft:
 *  the same document, inserted but not submitted and not matched. The line
 *  stays open; the draft can be finished from the board ("Include drafts",
 *  then "Submit and match") or from the desk. */
async function save(draft: boolean) {
  busy.value = true
  drafting.value = draft
  problem.value = ''
  const values = Object.fromEntries(dimensions.value.map((d) => [d.fieldname, dimensionValues[d.fieldname] ?? null]))
  try {
    const done =
      props.mode === 'payment'
        ? await createPayment.run(
            {
              bank_transaction_name: props.transaction.name,
              posting_date: postingDate.value,
              reference_date: referenceDate.value,
              reference_number: referenceNumber.value,
              mode_of_payment: modeOfPayment.value || undefined,
              party_type: partyType.value!,
              party: party.value!,
              cost_center: costCenter.value || undefined,
            },
            values,
            draft,
          )
        : await createJournal.run(
            {
              transaction: props.transaction,
              account: account.value!,
              entry_type: entryType.value,
              posting_date: postingDate.value,
              reference_date: referenceDate.value,
              reference_number: referenceNumber.value,
              party_type: partyType.value,
              party: party.value,
            },
            values,
            draft,
          )
    if (draft) {
      if (!done.ok || !done.name) {
        problem.value = done.error?.message || 'The draft could not be created'
        return
      }
      toast.success(
        `Draft ${entryLabel()} ${done.name} created. The line stays open until it is submitted and matched.`,
      )
      reset()
      emit('drafted')
      return
    }
    if (!done.ok || done.unallocated === null) {
      problem.value = done.error?.message || 'The entry could not be created'
      return
    }
    toast.success(props.mode === 'payment' ? 'Payment entry created and reconciled' : 'Journal entry created and reconciled')
    emit('done', done.unallocated)
  } finally {
    busy.value = false
  }
}

function entryLabel() {
  return props.mode === 'payment' ? 'payment entry' : 'journal entry'
}
</script>
