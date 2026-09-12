<template>
  <Dialog
    v-model:open="open"
    title="New procurement request"
    :actions="actions"
    size="3xl"
  >
    <div class="space-y-4">
      <p class="text-p-base text-ink-gray-6">
        Say what you need and roughly what it costs. Your approver decides
        before anything is bought.
      </p>

      <!-- No Purpose picker: the doctype defaults it to Purchase, which is
           what every request raised here is. The other purposes are stock
           movements, and those are made in the desk by the people who do
           them. The grid keeps the date at half width. -->
      <div class="grid gap-4 sm:grid-cols-2">
        <FormControl
          v-model="form.schedule_date"
          type="date"
          label="Needed by"
          :error="errors.schedule_date"
          required
        />
      </div>

      <section>
        <div class="flex items-end justify-between">
          <div>
            <h3 class="text-base-medium text-ink-gray-8">What you need</h3>
            <p class="mt-0.5 text-p-sm text-ink-gray-5">
              Describe each thing in your own words. Procurement matches it to
              the catalogue when they price it.
            </p>
          </div>
          <Button
            variant="subtle"
            icon-left="lucide-plus"
            label="Add line"
            @click="addLine"
          />
        </div>

        <ErrorMessage v-if="errors.items" :message="errors.items" class="mt-2" />

        <ul class="mt-3 space-y-3">
          <li
            v-for="(line, index) in form.items"
            :key="line.key"
            class="rounded-4 border border-outline-gray-1 p-3"
          >
            <div class="flex items-center justify-between">
              <span class="text-p-sm text-ink-gray-5">Line {{ index + 1 }}</span>
              <Button
                variant="ghost"
                theme="red"
                icon="lucide-trash-2"
                :disabled="form.items.length === 1"
                @click="form.items.splice(index, 1)"
              />
            </div>

            <!-- No catalogue item picker: a requester is not expected to know
                 the item codes, and the doctype leaves `item_code` optional so
                 procurement can add it when they price the request. -->
            <FormControl
              v-model="line.item_name"
              class="mt-2"
              type="text"
              label="What is it"
              placeholder="e.g. Brass fittings, 12mm"
              :error="lineErrors[index]?.item_name"
              required
            />

            <!-- The server adds the scheme to a bare host, so a link pasted
                 from the address bar is accepted as typed. -->
            <FormControl
              v-model="line.reference_url"
              class="mt-3"
              type="text"
              label="Link"
              placeholder="Optional — a product page, quote or spec"
              :error="lineErrors[index]?.reference_url"
            />

            <div class="mt-3 grid gap-3 sm:grid-cols-3">
              <FormControl
                v-model.number="line.qty"
                type="number"
                label="Quantity"
                min="0"
                :error="lineErrors[index]?.qty"
              />
              <LinkControl
                v-model="line.uom"
                doctype="UOM"
                label="Unit"
                :error="lineErrors[index]?.uom"
              />
              <FormControl
                v-model.number="line.estimated_rate"
                type="number"
                :label="priceLabel"
                min="0"
                :description="lineTotal(line)"
              />
            </div>
          </li>
        </ul>

        <div
          v-if="estimatedTotal > 0"
          class="mt-3 flex items-baseline justify-between rounded-4 bg-surface-gray-2 px-3 py-2"
        >
          <span class="text-p-sm text-ink-gray-6">Estimated total</span>
          <span class="text-base-medium text-ink-gray-8">
            {{ formatCurrency(estimatedTotal, currency) }}
          </span>
        </div>
      </section>

      <FormControl
        v-model="form.justification"
        type="textarea"
        label="Why it's needed"
        :rows="3"
        placeholder="Optional, but it is what your approver reads first."
      />

      <LinkControl
        v-model="form.approver"
        doctype="User"
        label="Approver"
        :query="APPROVER_QUERY"
        :filters="approverFilters"
        :error="errors.approver"
        description="Anyone who can decide procurement requests. Defaults to whoever approves your expenses."
        required
      />

      <ErrorMessage v-if="newRequest.error" :message="newRequest.error.message" />
      <ErrorMessage v-if="send.error" :message="send.error.message" />

      <!-- The two steps are separate writes, so the second can fail on its
           own. Say what actually happened rather than leaving a draft the
           requester thinks was sent. -->
      <Alert
        v-if="savedDraft && send.error"
        theme="amber"
        title="Saved, but not sent"
        :description="`${savedDraft} is in your list as a draft. Try sending it again.`"
      />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  Alert,
  Button,
  Dialog,
  ErrorMessage,
  FormControl,
  useNewDoc,
  toast,
  type DialogAction,
} from 'frappe-ui'
import LinkControl from './LinkControl.vue'
import { formatCurrency } from '@/data/format'
import { procurementCan, useSendProcurementRequest } from '@/data/procurement'
import type { MyEmployee } from '@/data/leave'

const APPROVER_QUERY = 'tbsapp.api.get_procurement_approvers'

const props = defineProps<{
  /** For the approver default and the department. Absent for a login with no
   *  employee record — procurement, unlike leave, still works without one. */
  employee: MyEmployee | null
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ created: [name: string] }>()

interface LineForm {
  /** Local only, for `v-for` — rows have no name until the server makes one. */
  key: number
  item_name: string
  reference_url: string
  qty: number
  uom: string
  estimated_rate: number
}

interface RequestForm {
  /** Only ever filled by the insert's response — never posted. */
  name?: string
  company?: string
  schedule_date: string
  justification: string
  approver: string
  items: LineForm[]
}

let nextKey = 0

function blankLine(): LineForm {
  return {
    key: nextKey++,
    item_name: '',
    reference_url: '',
    qty: 1,
    uom: procurementCan.value.default_uom ?? '',
    estimated_rate: 0,
  }
}

function blankForm(): RequestForm {
  return {
    // Omitted rather than guessed when the server had no answer: Frappe then
    // applies the user's own default, and says so if there isn't one.
    company: procurementCan.value.default_company ?? undefined,
    // `purpose` is deliberately absent, like `status`: the doctype defaults it
    // to Purchase, and a copy of that default here would be one more place to
    // change it.
    schedule_date: '',
    justification: '',
    // `status` is deliberately absent: it is permlevel 1, so a requester's
    // value would be dropped anyway, and it defaults to Draft.
    approver: props.employee?.expense_approver ?? '',
    items: [blankLine()],
  }
}

const form = reactive<RequestForm>(blankForm())
const newRequest = useNewDoc<RequestForm>('Procurement Request', form)
const send = useSendProcurementRequest()

const submitAttempted = ref(false)
/** Set once the insert succeeds, so a failed send can be retried alone. */
const savedDraft = ref('')

const approverFilters = computed(() => ({ employee: props.employee?.name }))

const currency = computed(() => procurementCan.value.default_currency)

const estimatedTotal = computed(() =>
  form.items.reduce(
    (total, line) => total + (line.qty || 0) * (line.estimated_rate || 0),
    0,
  ),
)

// The code, not a symbol: the company currency can be one the viewer's locale
// has no symbol for, and a bare number is the thing an approver misreads.
const priceLabel = computed(() =>
  currency.value
    ? `Estimated price each (${currency.value})`
    : 'Estimated price each',
)

function lineTotal(line: LineForm): string {
  const amount = (line.qty || 0) * (line.estimated_rate || 0)
  return amount ? formatCurrency(amount, currency.value) : ''
}

function addLine() {
  form.items.push(blankLine())
}

const today = new Date().toISOString().slice(0, 10)

const lineProblems = computed(() =>
  form.items.map((line) => {
    const found: Record<string, string> = {}
    if (!line.item_name) found.item_name = 'Say what it is'
    // Only the shape is checked here. The server adds a missing scheme and has
    // the last word on whether the link is one.
    if (line.reference_url && /\s/.test(line.reference_url.trim())) {
      found.reference_url = 'A link has no spaces in it'
    }
    if (!line.qty || line.qty <= 0) found.qty = 'How many?'
    if (!line.uom) found.uom = 'Pick a unit'
    return found
  }),
)

const problems = computed(() => {
  const found: Record<string, string> = {}
  if (!form.schedule_date) found.schedule_date = 'When do you need it?'
  else if (form.schedule_date < today) {
    found.schedule_date = 'That date has already passed'
  }
  if (!form.approver) found.approver = 'Pick an approver'
  // The banner names the required fields only when one is actually missing:
  // a line held up by nothing but a malformed link would be told to fill in
  // things it already has.
  if (lineProblems.value.some((line) => Object.keys(line).length)) {
    found.items = lineProblems.value.some(
      (line) => line.item_name || line.qty || line.uom,
    )
      ? 'Every line needs a name, a quantity and a unit'
      : 'Check the lines below'
  }
  return found
})

const errors = computed(() => (submitAttempted.value ? problems.value : {}))
const lineErrors = computed(() =>
  submitAttempted.value ? lineProblems.value : [],
)

// Rebuilt on open, not on close. A dialog that keeps the last request's lines
// is a trap — the next one starts half-filled with things already bought — and
// the defaults it starts from (company, unit) arrive with the permissions call,
// which has not landed when this component is first created.
watch(open, (isOpen) => {
  if (!isOpen) return
  Object.assign(form, blankForm())
  submitAttempted.value = false
  savedDraft.value = ''
  send.reset()
})

async function sendForApproval(name: string, close: () => void) {
  const sent = await send.submit({ name })
  // `submit` resolves null on failure; the reason renders in the dialog.
  if (!sent) return
  toast.success('Request sent for approval')
  emit('created', name)
  close()
}

async function save(close: () => void) {
  submitAttempted.value = true
  if (Object.keys(problems.value).length) return

  // A retry after the send failed: the document exists, only the handover
  // didn't happen.
  if (savedDraft.value) {
    await sendForApproval(savedDraft.value, close)
    return
  }

  try {
    const created = await newRequest.submit()
    // `submit` rejects rather than resolving a nameless document, so by here
    // the insert has a name.
    savedDraft.value = created.name!
    await sendForApproval(savedDraft.value, close)
  } catch {
    // `newRequest.error` renders the server's reason inline — a missing
    // company or an unknown unit is worth reading in full.
  }
}

const actions = computed<DialogAction[]>(() => [
  {
    label: savedDraft.value ? 'Send again' : 'Send request',
    variant: 'solid',
    // No `loading` here: Dialog drives it off the awaited `onClick`.
    onClick: ({ close }) => save(close),
  },
])
</script>
