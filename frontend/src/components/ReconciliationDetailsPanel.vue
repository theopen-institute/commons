<!--
  The line itself: its full description, what is matched to it, and the two
  things ERPNext allows changing on a submitted line, its reference and its
  party.

  Unlinking is ERPNext's `remove_payment_entries`, the desk form's Unreconcile.
  It cancels nothing. The vouchers stay submitted and can be matched again,
  which is why it needs only a second press to confirm rather than more.
-->

<template>
  <div class="space-y-4">
    <section>
      <h3 class="mb-1 text-p-sm font-medium text-ink-gray-7">Description</h3>
      <p class="whitespace-pre-wrap break-words rounded-4 bg-surface-gray-1 px-3 py-2 font-mono text-p-sm text-ink-gray-8">
        {{ transaction.description || '—' }}
      </p>
    </section>

    <section>
      <h3 class="mb-1 text-p-sm font-medium text-ink-gray-7">Matched to this line</h3>
      <div v-if="linked.loading" class="space-y-2"><Skeleton class="h-8 w-full rounded-4" /></div>
      <p v-else-if="!vouchers.length" class="text-p-sm text-ink-gray-5">Nothing yet.</p>
      <ul v-else class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2">
        <li v-for="row in vouchers" :key="row.name" class="flex items-center gap-3 px-3 py-1.5 text-p-sm">
          <a
            :href="deskUrl(row.payment_document, row.payment_entry)"
            target="_blank"
            class="min-w-0 flex-1 truncate text-ink-gray-8 hover:underline"
          >
            {{ row.payment_document }} <span class="font-medium">{{ row.payment_entry }}</span>
          </a>
          <span class="shrink-0 text-p-xs text-ink-gray-5">{{ row.reconciliation_type }}</span>
          <span class="shrink-0 tabular-nums text-ink-gray-8">
            {{ formatExact(row.allocated_amount, transaction.currency) }}
          </span>
        </li>
      </ul>
      <div v-if="vouchers.length" class="mt-2 flex items-center gap-2">
        <Button
          size="sm"
          :variant="confirmUnlink ? 'solid' : 'subtle'"
          :theme="confirmUnlink ? 'red' : 'gray'"
          :label="confirmUnlink ? 'Unlink all: press again to confirm' : 'Unlink all'"
          icon-left="lucide-unlink"
          :loading="unlinking"
          @click="unlink"
        />
        <Button v-if="confirmUnlink" size="sm" variant="ghost" label="Keep" @click="confirmUnlink = false" />
      </div>
    </section>

    <section class="space-y-3">
      <h3 class="text-p-sm font-medium text-ink-gray-7">Reference and party</h3>
      <div class="grid gap-3 sm:grid-cols-2">
        <FormControl v-model="reference" label="Reference" class="sm:col-span-2" :disabled="saving" />
        <LinkControl v-model="partyType" doctype="Party Type" label="Party type" :disabled="saving" />
        <LinkControl
          v-if="partyType"
          :key="partyType"
          v-model="party"
          :doctype="partyType"
          label="Party"
          title-first
          :disabled="saving"
        />
      </div>
    </section>

    <ErrorMessage v-if="problem" :message="problem" />

    <div class="flex items-center justify-end gap-2 border-t border-outline-gray-1 pt-3">
      <Button v-if="dirty" variant="ghost" label="Undo changes" :disabled="saving" @click="reset" />
      <Button variant="solid" label="Save" :disabled="!dirty" :loading="saving" @click="save" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, ErrorMessage, FormControl, Skeleton, toast } from 'frappe-ui'
import LinkControl from '@/components/LinkControl.vue'
import { formatExact } from '@/data/format'
import {
  deskUrl,
  linkedVoucherParams,
  useLinkedVouchers,
  useUnlinkTransaction,
  useUpdateTransaction,
  write,
} from '@/data/reconciliation'
import type { TransactionRow } from '@/data/reconciliationRules'

const props = defineProps<{ transaction: TransactionRow }>()

const emit = defineEmits<{
  /** The line changed. Carries what changed, for the page to patch in. */
  updated: [values: Partial<TransactionRow>]
  dirty: [dirty: boolean]
}>()

const linked = useLinkedVouchers()
const vouchers = computed(() => linked.data ?? [])
const update = useUpdateTransaction()
const unlinker = useUnlinkTransaction()

const reference = ref('')
const partyType = ref<string | null>(null)
const party = ref<string | null>(null)
const saving = ref(false)
const unlinking = ref(false)
const confirmUnlink = ref(false)
const problem = ref('')

function reset() {
  reference.value = props.transaction.reference_number ?? ''
  partyType.value = props.transaction.party_type
  party.value = props.transaction.party
  problem.value = ''
  confirmUnlink.value = false
}

watch(
  () => [props.transaction.name, props.transaction.allocated_amount],
  () => {
    reset()
    linked.submit(linkedVoucherParams(props.transaction.name))
  },
  { immediate: true },
)

watch(partyType, (value, previous) => {
  if (previous !== undefined && value !== previous && value !== props.transaction.party_type) party.value = null
})

const dirty = computed(
  () =>
    reference.value !== (props.transaction.reference_number ?? '') ||
    (partyType.value || null) !== (props.transaction.party_type || null) ||
    (party.value || null) !== (props.transaction.party || null),
)
watch(dirty, (value) => emit('dirty', value), { immediate: true })

async function save() {
  saving.value = true
  problem.value = ''
  try {
    const done = await write(update, {
      bank_transaction_name: props.transaction.name,
      reference_number: reference.value,
      party_type: partyType.value || null,
      party: party.value || null,
    })
    if (!done.ok) {
      problem.value = done.error?.message || 'The line could not be saved'
      return
    }
    toast.success('Line updated')
    emit('updated', {
      reference_number: reference.value,
      party_type: partyType.value || null,
      party: party.value || null,
    })
  } finally {
    saving.value = false
  }
}

async function unlink() {
  if (!confirmUnlink.value) {
    confirmUnlink.value = true
    return
  }
  unlinking.value = true
  problem.value = ''
  try {
    const done = await unlinker.unlink(props.transaction.name)
    if (!done.ok) {
      problem.value = done.error?.message || 'The vouchers could not be unlinked'
      return
    }
    toast.success('Unlinked. The vouchers are still booked, and can be matched again.')
    confirmUnlink.value = false
    emit('updated', {})
  } finally {
    unlinking.value = false
  }
}
</script>
