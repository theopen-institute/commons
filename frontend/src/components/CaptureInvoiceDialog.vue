<!--
  One scanned invoice beside the draft Purchase Invoice it becomes.

  The scan on the left, the draft on the right, and nothing written until
  "Create draft invoice". Every figure the draft starts from is the scan's, and
  every suggestion says where it came from: the supplier matched by name or tax
  number, each account from an earlier invoice, the taxes from this supplier's
  last one. The reader checks them against the paper, which is next to them.

  The totals are ERPNext's own, from `preview`, which builds the same document
  `create` inserts. They are compared with the total printed on the scan, and a
  difference is shown but not corrected: the reader decides whether the draft
  or the scan has it wrong.

  Outside clicks and Escape do not close it, because a read costs money and a
  draft takes a few minutes to check. The close button does, and the page keeps
  the reading so it can be reopened as it was left.
-->

<template>
  <Dialog v-model:open="open" :dismissible="false" size="7xl" position="top" :actions="actions">
    <template #title>
      <div class="pr-8">
        <h2 class="text-lg font-semibold text-ink-gray-8">Draft a purchase invoice</h2>
        <p class="mt-0.5 text-p-sm text-ink-gray-5">
          Read from the scan by {{ reading?.model }}. Check each field against the scan. Nothing is saved
          until you create the draft.
        </p>
      </div>
    </template>

    <div v-if="reading" class="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <!-- The scan. Sticky on a wide screen, so it stays beside whichever
           part of the draft is being checked. -->
      <figure class="lg:sticky lg:top-0 lg:self-start">
        <div class="overflow-hidden rounded-4 border border-outline-gray-2 bg-surface-gray-2">
          <iframe v-if="isPdf" :src="scanUrl" class="h-[50vh] w-full lg:h-[75vh]" title="The scanned invoice" />
          <a v-else :href="scanUrl" target="_blank" rel="noopener" title="Open the scan full size">
            <img :src="scanUrl" alt="The scanned invoice" class="max-h-[50vh] w-full object-contain lg:max-h-[75vh]" />
          </a>
        </div>
        <figcaption class="mt-1 truncate text-p-xs text-ink-gray-5">
          {{ file?.name }} · attached to the invoice when it is created
        </figcaption>
      </figure>

      <div class="min-w-0 space-y-6">
        <!-- What should stop a reader before they read on. -->
        <div v-if="!scanned.is_invoice" :class="warningBox">
          <p class="text-base-medium text-ink-gray-8">This may not be a supplier's invoice</p>
          <p class="mt-0.5">Claude did not read it as one. Check the scan before going on.</p>
        </div>
        <div v-if="duplicates.length" :class="warningBox">
          <p class="text-base-medium text-ink-gray-8">This bill may already be booked</p>
          <p class="mt-0.5">
            {{ duplicates.length === 1 ? 'Invoice' : 'Invoices' }}
            <template v-for="(name, index) in duplicates" :key="name">
              <a :href="deskUrl(PURCHASE_INVOICE, name)" target="_blank" rel="noopener" class="underline">{{ name }}</a
              >{{ index < duplicates.length - 1 ? ', ' : '' }}
            </template>
            {{ duplicates.length === 1 ? 'has' : 'have' }} this supplier's bill number {{ draft.bill_no }}.
          </p>
        </div>
        <div v-if="scanned.notes.length" :class="warningBox">
          <p class="text-base-medium text-ink-gray-8">Worth checking against the paper</p>
          <!-- Rendered as text. These are the model's words about the scan. -->
          <ul class="mt-1 list-disc space-y-0.5 pl-4">
            <li v-for="(note, index) in scanned.notes" :key="index">{{ note }}</li>
          </ul>
        </div>

        <section>
          <h3 class="text-base-medium text-ink-gray-8">Billed to and from</h3>
          <div class="mt-3 space-y-3">
            <div>
              <FormControl
                v-model="draft.company"
                type="select"
                label="Company"
                :options="companyOptions"
                :error="errors.company"
                required
              />
              <p v-if="companyReason" class="mt-1 text-p-xs text-ink-gray-5">{{ companyReason }}</p>
            </div>

            <div>
              <p class="text-p-sm text-ink-gray-6">
                On the scan: <span class="text-ink-gray-8">{{ scanned.supplier.name || 'no supplier name' }}</span>
                <template v-if="scanned.supplier.tax_id"> · tax number {{ scanned.supplier.tax_id }}</template>
              </p>

              <template v-if="!draft.newSupplier">
                <LinkControl
                  v-model="supplier"
                  class="mt-2"
                  doctype="Supplier"
                  label="Supplier"
                  title-first
                  :error="errors.supplier"
                  required
                />
                <p v-if="chosenCandidate" class="mt-1 text-p-xs text-ink-gray-5">
                  Chosen because: {{ chosenCandidate.reason.toLowerCase() }}
                </p>
                <div v-if="otherCandidates.length" class="mt-2 flex flex-wrap items-center gap-2">
                  <span class="text-p-xs text-ink-gray-5">{{ draft.supplier ? 'Or' : 'Perhaps' }}:</span>
                  <Button
                    v-for="candidate in otherCandidates"
                    :key="candidate.name"
                    size="sm"
                    variant="subtle"
                    :label="candidate.supplier_name || candidate.name"
                    :title="candidate.reason"
                    @click="supplier = candidate.name"
                  />
                </div>
                <Button
                  v-if="captureCan.createSupplier"
                  class="mt-2"
                  size="sm"
                  variant="ghost"
                  icon-left="lucide-plus"
                  label="Add as a new supplier"
                  @click="startNewSupplier"
                />
              </template>

              <template v-else>
                <div class="mt-2 grid gap-3 sm:grid-cols-2">
                  <FormControl
                    v-model="draft.newSupplier.supplier_name"
                    label="New supplier's name"
                    :error="errors.supplier"
                    required
                  />
                  <FormControl v-model="draft.newSupplier.tax_id" label="Tax number (PAN/VAT)" />
                </div>
                <p class="mt-1 text-p-xs text-ink-gray-5">
                  Created with the invoice. Add its address and contacts in the desk afterwards.
                </p>
                <Button
                  class="mt-1"
                  size="sm"
                  variant="ghost"
                  label="Choose an existing supplier instead"
                  @click="draft.newSupplier = null"
                />
              </template>
            </div>
          </div>
        </section>

        <section>
          <h3 class="text-base-medium text-ink-gray-8">The bill</h3>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <FormControl v-model="draft.bill_no" label="Supplier's invoice number" />
            <div>
              <BikramDatePicker v-model="draft.bill_date" label="Invoice date" />
              <p v-if="scanned.invoice_date" class="mt-1 text-p-xs text-ink-gray-5">
                Printed {{ printedDate(scanned.invoice_date) }}
                <template v-if="!isoDate(scanned.invoice_date)">, which is not a date. Enter it by hand.</template>
              </p>
            </div>
            <div>
              <BikramDatePicker v-model="draft.posting_date" label="Posting date" :error="errors.posting_date" required />
              <p class="mt-1 text-p-xs text-ink-gray-5">When it goes into the books. The invoice's date unless you change it.</p>
            </div>
            <div>
              <BikramDatePicker v-model="draft.due_date" label="Due date" :error="errors.due_date" />
              <p v-if="scanned.due_date" class="mt-1 text-p-xs text-ink-gray-5">
                Printed {{ printedDate(scanned.due_date) }}
              </p>
            </div>
          </div>
        </section>

        <section>
          <div class="flex items-center justify-between">
            <h3 class="text-base-medium text-ink-gray-8">What was bought</h3>
            <span v-if="suggest.loading" class="text-p-xs text-ink-gray-5">Suggesting accounts…</span>
          </div>
          <ErrorMessage v-if="errors.lines" :message="errors.lines" class="mt-2" />
          <ErrorMessage v-if="suggest.error" :message="`No suggestions: ${suggest.error.message}`" class="mt-2" />

          <ul class="mt-3 space-y-3">
            <li v-for="(line, index) in draft.lines" :key="line.key" class="rounded-4 border border-outline-gray-1 p-3">
              <div class="flex items-start gap-2">
                <FormControl
                  v-model="line.description"
                  class="min-w-0 flex-1"
                  :label="`Line ${index + 1}`"
                  :error="errors[`description-${index}`]"
                />
                <Button
                  class="mt-5"
                  variant="ghost"
                  theme="red"
                  icon="lucide-trash-2"
                  :aria-label="`Remove line ${index + 1}`"
                  @click="removeLine(index)"
                />
              </div>

              <div class="mt-2 grid grid-cols-3 gap-3">
                <FormControl
                  v-model.number="line.qty"
                  type="number"
                  label="Quantity"
                  min="0"
                  step="any"
                  :error="errors[`qty-${index}`]"
                />
                <FormControl
                  v-model.number="line.rate"
                  type="number"
                  label="Rate"
                  step="0.01"
                  :error="errors[`rate-${index}`]"
                />
                <FormControl
                  v-model.number="line.amount"
                  type="number"
                  label="Row total"
                  step="0.01"
                  :placeholder="String(lineAmount(line))"
                />
              </div>

              <!-- A row whose figures do not multiply out. Flagged rather than
                   corrected, with a button for each figure it could trust. -->
              <div v-if="lineProblem(line)" class="mt-2 rounded-4 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8">
                <p>{{ lineProblem(line) }}</p>
                <div class="mt-1.5 flex flex-wrap gap-2">
                  <Button
                    v-for="fix in lineFixes(line)"
                    :key="fix.label"
                    size="sm"
                    variant="subtle"
                    :label="fix.label"
                    @click="Object.assign(line, fix.values)"
                  />
                </div>
              </div>

              <LinkControl
                :model-value="line.expense_account || null"
                class="mt-2"
                doctype="Account"
                label="Account"
                :filters="{ company: draft.company, is_group: 0 }"
                :disabled="!draft.company"
                :error="errors[`account-${index}`]"
                @update:model-value="(value) => chooseAccount(line, value)"
              />
              <p
                v-if="line.reason"
                class="mt-1 text-p-xs"
                :class="line.review ? 'text-ink-amber-3' : 'text-ink-gray-5'"
              >
                {{ line.review ? 'Check this: ' : '' }}{{ line.reason }}
              </p>
            </li>
          </ul>

          <p v-if="subtotalMatches === false" :class="[warningBox, 'mt-3']">
            The row totals add up to {{ formatExact(rowsTotal, currency) }}, but the scan's subtotal is
            {{ formatExact(scanned.subtotal, currency) }}. A line may be missing, extra or misread.
          </p>

          <Button class="mt-3" variant="subtle" icon-left="lucide-plus" label="Add line" @click="addLine" />
        </section>

        <section>
          <h3 class="text-base-medium text-ink-gray-8">Tax and discount</h3>
          <p v-if="scanned.taxes.length" class="mt-1 text-p-sm text-ink-gray-6">
            On the scan:
            <template v-for="(tax, index) in scanned.taxes" :key="index">
              {{ tax.label }} {{ formatExact(tax.amount, currency) }}{{ index < scanned.taxes.length - 1 ? ' · ' : '' }}
            </template>
          </p>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <FormControl
                :model-value="draft.taxes"
                type="select"
                label="Taxes"
                :options="taxOptions"
                :disabled="!suggestions"
                @update:model-value="chooseTaxes"
              />
              <p v-if="taxReason" class="mt-1 text-p-xs text-ink-gray-5">{{ taxReason }}</p>
            </div>
            <FormControl
              v-model.number="draft.discount_amount"
              type="number"
              label="Discount on the invoice"
              min="0"
              step="0.01"
              placeholder="None"
            />
          </div>
        </section>

        <section>
          <h3 class="text-base-medium text-ink-gray-8">Totals</h3>
          <div class="mt-3 rounded-4 border border-outline-gray-1">
            <div v-if="!totals" class="px-3 py-3 text-p-sm text-ink-gray-5">
              <template v-if="preview.loading">Working out the totals…</template>
              <template v-else-if="previewProblem">{{ previewProblem }}</template>
              <template v-else>The totals appear once there is a supplier and every line has an account.</template>
            </div>
            <table v-else class="w-full text-base">
              <tbody class="text-ink-gray-7">
                <tr>
                  <td class="px-3 py-1.5">Net total</td>
                  <td class="px-3 py-1.5 text-right tabular-nums">{{ formatExact(totals.net_total, totals.currency) }}</td>
                </tr>
                <tr v-if="totals.discount_amount">
                  <td class="px-3 py-1.5">Discount</td>
                  <td class="px-3 py-1.5 text-right tabular-nums">−{{ formatExact(totals.discount_amount, totals.currency) }}</td>
                </tr>
                <tr v-for="(tax, index) in totals.taxes" :key="index">
                  <td class="px-3 py-1.5">{{ tax.description }}</td>
                  <td class="px-3 py-1.5 text-right tabular-nums">{{ formatExact(tax.amount, totals.currency) }}</td>
                </tr>
                <tr class="border-t border-outline-gray-1 text-base-medium text-ink-gray-8">
                  <td class="px-3 py-2">Grand total</td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ formatExact(totals.grand_total, totals.currency) }}</td>
                </tr>
                <tr v-if="totals.rounded_total !== null && totals.rounded_total !== totals.grand_total">
                  <td class="px-3 py-1.5">Rounded</td>
                  <td class="px-3 py-1.5 text-right tabular-nums">{{ formatExact(totals.rounded_total, totals.currency) }}</td>
                </tr>
              </tbody>
            </table>
            <!-- The draft against the scan, a stage at a time, so a total that
                 is out can be traced to where it goes out. -->
            <table v-if="totals" class="w-full border-t border-outline-gray-1 text-p-sm">
              <thead>
                <tr class="text-ink-gray-5">
                  <th class="px-3 pb-1 pt-2 text-left font-normal">Against the scan</th>
                  <th class="px-3 pb-1 pt-2 text-right font-normal">Scan</th>
                  <th class="px-3 pb-1 pt-2 text-right font-normal">This draft</th>
                  <th class="w-8" />
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="check in stageChecks"
                  :key="check.key"
                  :class="check.matches === false ? 'bg-surface-amber-2 text-ink-gray-8' : 'text-ink-gray-7'"
                >
                  <td class="px-3 py-1.5">
                    {{ check.label }}
                    <span v-if="check.source" class="text-ink-gray-5">· {{ check.source }}</span>
                  </td>
                  <td class="px-3 py-1.5 text-right tabular-nums">
                    {{ check.scan === null ? '—' : formatExact(check.scan, totals.currency) }}
                  </td>
                  <td class="px-3 py-1.5 text-right tabular-nums">{{ formatExact(check.draft, totals.currency) }}</td>
                  <td class="pr-3">
                    <span
                      class="block size-4"
                      :class="
                        check.matches === true
                          ? 'lucide-circle-check text-ink-green-7'
                          : check.matches === false
                            ? 'lucide-triangle-alert text-ink-amber-3'
                            : 'lucide-minus text-ink-gray-4'
                      "
                      :aria-label="check.matches === true ? 'Matches' : check.matches === false ? 'Differs' : 'Nothing to check'"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
            <p
              v-if="firstDifference"
              class="border-t border-outline-gray-1 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8"
            >
              {{ firstDifference }}
            </p>
            <div
              v-if="totals && currencyDiffers"
              class="border-t border-outline-gray-1 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8"
            >
              The scan looks like it is in {{ scanned.currency }}, and this invoice will be in {{ totals.currency }}.
              A supplier billed in another currency needs that currency on its record in the desk.
            </div>
          </div>
        </section>

        <ErrorMessage v-if="create.error" :message="create.error.message" />
      </div>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch, watchEffect } from 'vue'
import { Button, Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import { useDebounceFn } from '@vueuse/core'
import BikramDatePicker from './BikramDatePicker.vue'
import LinkControl from './LinkControl.vue'
import {
  PURCHASE_INVOICE,
  attachScan,
  captureCan,
  deskUrl,
  useCreate,
  usePreview,
  useSuggest,
  type Suggestions,
} from '@/data/capture'
import {
  blankLine,
  draftFrom,
  draftProblems,
  invoicePayload,
  isoDate,
  isTaxed,
  checks,
  lineAmount,
  lineFixes,
  lineProblem,
  printedDate,
  rowsMatchSubtotal,
  rowTotal,
  type Draft,
  type DraftLine,
  type Reading,
  type ScannedInvoice,
  type Totals,
} from '@/data/captureRules'
import { formatExact } from '@/data/format'

const props = defineProps<{
  /** What `read_invoice` answered. A new one starts a new draft; the same one
   *  again reopens the draft as it was left. */
  reading: Reading | null
  /** The scan itself, shown beside the draft and attached once it exists. */
  file: File | null
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ created: [name: string] }>()

const warningBox =
  'rounded-4 border border-outline-amber-3 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8'

function localToday() {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const EMPTY: ScannedInvoice = {
  is_invoice: true,
  supplier: { name: null, tax_id: null },
  buyer: { name: null, tax_id: null },
  invoice_number: null,
  invoice_date: null,
  due_date: null,
  currency: null,
  lines: [],
  discount: null,
  subtotal: null,
  taxes: [],
  total: null,
  notes: [],
}

const scanned = computed<ScannedInvoice>(() => props.reading?.extracted ?? EMPTY)

const draft = reactive<Draft>({
  company: '',
  supplier: '',
  newSupplier: null,
  bill_no: '',
  bill_date: '',
  posting_date: '',
  due_date: '',
  discount_amount: null,
  taxes: 'none',
  lines: [],
})

/** Lines whose account the reader chose, which a later suggestion leaves
 *  alone. By `key`, which survives lines being removed around it. */
const chosen = reactive(new Set<number>())
const taxesChosen = ref(false)
const submitAttempted = ref(false)

const suggest = useSuggest()
const preview = usePreview()
const create = useCreate()
const suggestions = ref<Suggestions | null>(null)
const totals = ref<Totals | null>(null)
const previewProblem = ref('')

watch(
  () => props.reading,
  (reading) => {
    if (!reading) return
    Object.assign(draft, draftFrom(reading, localToday()))
    chosen.clear()
    taxesChosen.value = false
    submitAttempted.value = false
    suggestions.value = null
    totals.value = null
    previewProblem.value = ''
    lastAsked = ''
    runSuggest()
  },
  { immediate: true },
)

/* ------------------------------------------------------------------------ */
/* The scan                                                                  */
/* ------------------------------------------------------------------------ */

const scanUrl = ref('')
watchEffect((onCleanup) => {
  if (!props.file) {
    scanUrl.value = ''
    return
  }
  const url = URL.createObjectURL(props.file)
  scanUrl.value = url
  onCleanup(() => URL.revokeObjectURL(url))
})

const isPdf = computed(() => props.file?.type === 'application/pdf' || props.file?.name.toLowerCase().endsWith('.pdf'))

/* ------------------------------------------------------------------------ */
/* Company and supplier                                                      */
/* ------------------------------------------------------------------------ */

const companyOptions = computed(() => [
  { label: 'Choose a company', value: '' },
  ...(props.reading?.companies ?? []).map((company) => ({ label: company.name, value: company.name })),
])

/** Said only while the company is still the one the reading suggested. */
const companyReason = computed(() =>
  props.reading && draft.company && draft.company === props.reading.company.name
    ? props.reading.company.reason
    : null,
)

/** `LinkControl` sets null when cleared; the draft keeps a string. */
const supplier = computed({
  get: () => draft.supplier || null,
  set: (value: string | null) => {
    draft.supplier = value ?? ''
  },
})

const candidates = computed(() => props.reading?.suppliers ?? [])
const chosenCandidate = computed(() => candidates.value.find((candidate) => candidate.name === draft.supplier) ?? null)
const otherCandidates = computed(() => candidates.value.filter((candidate) => candidate.name !== draft.supplier))

function startNewSupplier() {
  draft.newSupplier = {
    supplier_name: scanned.value.supplier.name ?? '',
    tax_id: scanned.value.supplier.tax_id ?? '',
  }
}

/* ------------------------------------------------------------------------ */
/* Suggestions                                                               */
/* ------------------------------------------------------------------------ */

let suggestRun = 0
/** The last question asked, so that a change arriving through two watchers
 *  at once (a new reading moves the company, the supplier and the lines
 *  together) is asked about once. */
let lastAsked = ''

async function runSuggest() {
  if (!draft.company) return
  const params = {
    company: draft.company,
    descriptions: draft.lines.map((line) => line.description),
    taxed: isTaxed(scanned.value),
    supplier: draft.newSupplier ? null : draft.supplier || null,
    bill_no: draft.bill_no || null,
  }
  const asked = JSON.stringify(params)
  if (asked === lastAsked) return
  lastAsked = asked
  const run = ++suggestRun
  const answer = await suggest.submit(params)
  // A later run has started since; its answer is the one that counts.
  if (run !== suggestRun) return
  if (!answer) {
    lastAsked = ''
    return
  }
  suggestions.value = answer
  answer.lines.forEach((suggestion, index) => {
    const line = draft.lines[index]
    if (!line || chosen.has(line.key)) return
    line.expense_account = suggestion.account ?? ''
    line.reason = suggestion.reason
    line.review = suggestion.review
  })
  if (!taxesChosen.value) draft.taxes = answer.taxes.suggested
}

const suggestSoon = useDebounceFn(runSuggest, 600)

// A company's accounts are its own, so switching company starts every line
// again. Not on the way in from no company, where there is nothing to undo.
watch(
  () => draft.company,
  (company, previous) => {
    if (!previous || company === previous) {
      runSuggest()
      return
    }
    chosen.clear()
    taxesChosen.value = false
    for (const line of draft.lines) {
      line.expense_account = ''
      line.reason = ''
      line.review = false
    }
    runSuggest()
  },
)

watch(() => [draft.supplier, Boolean(draft.newSupplier)], () => runSuggest())
watch(() => [draft.bill_no, draft.lines.map((line) => line.description).join('\n')], () => suggestSoon())

function chooseAccount(line: DraftLine, value: string | null | undefined) {
  line.expense_account = value ?? ''
  line.reason = ''
  line.review = false
  chosen.add(line.key)
}

const taxOptions = computed(() =>
  (suggestions.value?.taxes.options ?? [{ key: 'none', label: 'No taxes', summary: '' }]).map((option) => ({
    label: option.summary ? `${option.label} — ${option.summary}` : option.label,
    value: option.key,
  })),
)

/** Said only while the taxes are still the suggested ones. */
const taxReason = computed(() =>
  suggestions.value && !taxesChosen.value ? suggestions.value.taxes.reason : null,
)

function chooseTaxes(value: string) {
  draft.taxes = value
  taxesChosen.value = true
}

const duplicates = computed(() => suggestions.value?.duplicates ?? [])

function addLine() {
  draft.lines.push(blankLine())
}

function removeLine(index: number) {
  const [removed] = draft.lines.splice(index, 1)
  if (removed) chosen.delete(removed.key)
}

/* ------------------------------------------------------------------------ */
/* Totals                                                                    */
/* ------------------------------------------------------------------------ */

const currency = computed(() => totals.value?.currency ?? suggestions.value?.currency ?? null)

const readyToPrice = computed(
  () =>
    Boolean(draft.company) &&
    Boolean(draft.newSupplier ? draft.newSupplier.supplier_name.trim() : draft.supplier) &&
    draft.lines.length > 0 &&
    draft.lines.every((line) => line.expense_account && (line.qty ?? 0) > 0 && line.rate !== null),
)

let previewRun = 0

async function runPreview() {
  if (!readyToPrice.value) {
    totals.value = null
    previewProblem.value = ''
    return
  }
  const run = ++previewRun
  const answer = await preview.submit({ invoice: invoicePayload(draft), new_supplier: Boolean(draft.newSupplier) })
  if (run !== previewRun) return
  if (answer) {
    totals.value = answer
    previewProblem.value = ''
  } else {
    totals.value = null
    previewProblem.value = preview.error?.message ?? 'The totals could not be worked out.'
  }
}

const previewSoon = useDebounceFn(runPreview, 400)

watch(
  () => JSON.stringify([invoicePayload(draft), Boolean(draft.newSupplier)]),
  () => previewSoon(),
)

const rowsTotal = computed(() => draft.lines.reduce((sum, line) => sum + rowTotal(line), 0))
const subtotalMatches = computed(() => rowsMatchSubtotal(draft, scanned.value))

const stageChecks = computed(() => (totals.value ? checks(draft, scanned.value, totals.value) : []))

/** Where to look, said once: the first stage that differs, since a
 *  difference there carries through to every stage after it. */
const firstDifference = computed(() => {
  const first = stageChecks.value.find((check) => check.matches === false)
  if (!first) return null
  if (first.key === 'lines') {
    return draft.lines.some(lineProblem)
      ? 'The lines do not match the scan. Start with the rows flagged above.'
      : 'The lines do not match the scan. Check each quantity and rate, and the discount, against the paper.'
  }
  if (first.key === 'tax') return 'The lines match, but the tax does not. Check which taxes apply.'
  return 'The lines and tax match, but the total does not. Check for a charge, rounding or discount the draft leaves out.'
})

const currencyDiffers = computed(
  () => Boolean(scanned.value.currency && totals.value && scanned.value.currency !== totals.value.currency),
)

/* ------------------------------------------------------------------------ */
/* Creating it                                                               */
/* ------------------------------------------------------------------------ */

const problems = computed(() => draftProblems(draft))
const errors = computed(() => (submitAttempted.value ? problems.value : {}))
const busy = ref(false)

async function save(close: () => void) {
  submitAttempted.value = true
  if (Object.keys(problems.value).length) return
  busy.value = true
  try {
    const created = await create.submit({
      invoice: invoicePayload(draft),
      new_supplier: draft.newSupplier
        ? { supplier_name: draft.newSupplier.supplier_name.trim(), tax_id: draft.newSupplier.tax_id.trim() }
        : null,
    })
    // `submit` resolves null on failure; the reason renders inline.
    if (!created) return

    const failed = props.file ? await attachScan(created.name, props.file) : null
    if (failed) {
      toast.error(`${created.name} is saved as a draft, but the scan did not attach (${failed}). Attach it in the desk.`)
    } else {
      toast.success(`${created.name} is saved as a draft, with the scan attached`)
    }
    emit('created', created.name)
    close()
  } finally {
    busy.value = false
  }
}

const actions = computed<DialogAction[]>(() => [
  {
    label: 'Create draft invoice',
    variant: 'solid',
    loading: busy.value,
    onClick: ({ close }) => save(close),
  },
])
</script>
