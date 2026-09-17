<template>
  <!-- No `message` prop: it only renders as the default slot's fallback, so a
       dialog with content of its own has to place that line itself. -->
  <Dialog v-model:open="open" title="Claim expenses" :actions="actions" size="2xl">
    <div class="space-y-4">
      <p class="text-p-base text-ink-gray-6">
        Your approver is notified once you send this. They can allow less than
        you claimed, so say what each expense was for.
      </p>

      <!-- An expense type with no account configured for this company cannot be
           saved against, so the server leaves it out — and an empty list is the
           site saying nothing has been set up to claim against yet. Said here
           rather than left to a failed save, which sends the reader to the same
           people one wasted form later. -->
      <Alert
        v-if="defaults.isFinished && !expenseTypes.length"
        theme="amber"
        title="Nothing to claim against yet"
        description="No expense type has an account set up for your company. Ask Accounts to configure one before claiming."
      />

      <section>
        <h3 class="text-base-medium text-ink-gray-8">What you spent</h3>

        <ul class="mt-3 space-y-3">
          <li
            v-for="(line, index) in form.expenses"
            :key="line.key"
            class="rounded-4 border border-outline-gray-1 p-3"
          >
            <div class="flex items-center justify-between">
              <span class="text-p-sm text-ink-gray-5">Expense {{ index + 1 }}</span>
              <Button
                variant="ghost"
                theme="red"
                icon="lucide-trash-2"
                :aria-label="`Remove expense ${index + 1}`"
                :disabled="form.expenses.length === 1"
                @click="form.expenses.splice(index, 1)"
              />
            </div>

            <div class="mt-2 grid gap-3 sm:grid-cols-3">
              <FormControl
                v-model="line.expense_type"
                type="select"
                label="Type"
                :options="typeOptions"
                :error="errors[`type-${index}`]"
                required
              />
              <FormControl
                v-model="line.expense_date"
                type="date"
                label="When"
                :max="today"
                :error="errors[`date-${index}`]"
              />
              <FormControl
                v-model.number="line.amount"
                type="number"
                :label="amountLabel"
                min="0"
                step="0.01"
                :error="errors[`amount-${index}`]"
                required
              />
            </div>

            <FormControl
              v-model="line.description"
              class="mt-3"
              type="textarea"
              label="What it was for"
              :rows="2"
              placeholder="Optional, but it is what your approver reads."
            />
          </li>
        </ul>

        <div class="mt-3 flex items-center justify-between">
          <span v-if="claimedTotal" class="text-p-sm text-ink-gray-6">
            Claiming {{ formatCurrency(claimedTotal, defaults.data?.currency) }}
          </span>
          <Button
            class="ml-auto"
            variant="subtle"
            icon-left="lucide-plus"
            label="Add expense"
            @click="addLine"
          />
        </div>
      </section>

      <FormControl
        v-model="form.remark"
        type="textarea"
        label="Anything else"
        :rows="2"
        placeholder="Optional context for the person settling this."
      />

      <!-- Receipts. Held here and uploaded once the claim exists, because an
           attachment needs a document to hang on and there is none until the
           claim is raised. -->
      <section>
        <div class="flex items-center justify-between">
          <span class="text-xs text-ink-gray-5">Receipts</span>
          <Button
            variant="subtle"
            icon-left="lucide-paperclip"
            label="Attach files"
            @click="pickFiles"
          />
        </div>

        <!-- `hidden` rather than a styled input: the button above is the
             control, and a file input cannot be restyled into one. -->
        <input
          ref="fileInput"
          type="file"
          multiple
          class="hidden"
          :accept="ACCEPTED_FILE_TYPES"
          @change="onFilesPicked"
        />

        <ul v-if="attachments.length" class="mt-2 space-y-1">
          <li
            v-for="(file, index) in attachments"
            :key="`${file.name}:${file.lastModified}:${index}`"
            class="flex items-center gap-2 rounded-4 border border-outline-gray-1 px-3 py-2"
          >
            <span class="lucide-paperclip size-4 shrink-0 text-ink-gray-5" />
            <span class="min-w-0 flex-1 truncate text-base text-ink-gray-8">
              {{ file.name }}
            </span>
            <span class="shrink-0 text-p-sm text-ink-gray-5">
              {{ formatFileSize(file.size) }}
            </span>
            <Button
              variant="ghost"
              icon="lucide-x"
              :label="`Remove ${file.name}`"
              @click="removeAttachment(index)"
            />
          </li>
        </ul>

        <p v-else class="mt-1.5 text-p-sm text-ink-gray-5">
          Optional. Photos or PDFs of what you are claiming for, attached to the
          claim where your approver and Accounts can read them.
        </p>
      </section>

      <LinkControl
        v-model="form.expense_approver"
        doctype="User"
        label="Approver"
        title-first
        :query="expenseCan.approver_query"
        :filters="{ employee: employee, doctype: 'Expense Claim' }"
        :error="errors.expense_approver"
        description="Set from your employee record. Ask HR if the right person isn't listed."
        :required="expenseCan.approver_mandatory"
      />

      <ErrorMessage v-if="request.error" :message="request.error.message" />
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
  toast,
  type DialogAction,
} from 'frappe-ui'
import LinkControl from './LinkControl.vue'
import {
  attachToExpenseClaim,
  expenseCan,
  useExpenseClaimDefaults,
  useRequestExpenseClaim,
} from '@/data/expense'
import { formatCurrency, formatFileSize, pluralise } from '@/data/format'

defineProps<{
  /** The employee this claim is for. Only the approver query reads it — the
   *  server resolves the claim's own employee from the session. */
  employee: string
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ created: [name: string] }>()

/**
 * What this form collects.
 *
 * Not an Expense Claim document. `request_expense_claim` takes the fields a
 * claim may set and settles the rest — the employee from the session, the
 * company and currency from that employee, the exchange rate from ERPNext, the
 * cost centre from the company, the expense account from the type, and the
 * posting date and naming series from the doctype. A form that posted a
 * document would be deciding all of that here instead, which is what the desk's
 * own Expense Claim form does in about two hundred lines of JavaScript.
 */
interface ExpenseLineForm {
  /** Local only, for `v-for` — rows have no name until the server makes one. */
  key: number
  expense_type: string
  expense_date: string
  description: string
  amount: number | null
}

interface ClaimForm {
  expense_approver: string
  remark: string
  expenses: ExpenseLineForm[]
}

// Fetched when the form opens rather than with the section's permissions: they
// are queries for a blank claim, and most visits never draw one.
const defaults = useExpenseClaimDefaults()
const request = useRequestExpenseClaim()

const today = new Date().toISOString().slice(0, 10)

// Declared before `blankLine`, which reads it -- and `blankLine` runs during
// setup, through the `blankForm()` the form is built from. A `const` below its
// own first use is a dead zone rather than an undefined: the dialog threw
// before it could render, taking the button that opens it with it.
const expenseTypes = computed(() => defaults.data?.expense_types ?? [])

let nextKey = 0

function blankLine(): ExpenseLineForm {
  return {
    key: nextKey++,
    // Offered only when there is one choice: picking for the claimant where
    // there are several would be guessing what they spent it on.
    expense_type: expenseTypes.value.length === 1 ? expenseTypes.value[0].name : '',
    expense_date: today,
    description: '',
    amount: null,
  }
}

function blankForm(): ClaimForm {
  return {
    // Omitted rather than guessed when the server had no answer: the field then
    // opens blank and the claimant picks.
    expense_approver: defaults.data?.approver ?? '',
    remark: '',
    expenses: [blankLine()],
  }
}

const form = reactive<ClaimForm>(blankForm())

const submitAttempted = ref(false)

// What the file picker offers by default. Frappe refuses anything outside its
// own list for a user without desk access, and receipts are photos and PDFs
// anyway -- this steers rather than enforces, and the server is the authority.
const ACCEPTED_FILE_TYPES = 'image/*,application/pdf'

// Chosen now, uploaded after the claim is inserted. `File` objects, not
// uploads: nothing is written to the site until there is a claim to attach it
// to, so a dialog that is closed again leaves nothing behind.
const attachments = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

function pickFiles() {
  fileInput.value?.click()
}

function onFilesPicked(event: Event) {
  const input = event.target as HTMLInputElement
  attachments.value = [...attachments.value, ...Array.from(input.files ?? [])]
  // Cleared so the same file can be picked again after being removed --
  // an input holding the value fires no `change` when it is reselected.
  input.value = ''
}

function removeAttachment(index: number) {
  attachments.value.splice(index, 1)
}

const typeOptions = computed(() => [
  { label: 'Select a type', value: '' },
  ...expenseTypes.value.map((type) => ({
    label: type.description ? `${type.name} — ${type.description}` : type.name,
    value: type.name,
  })),
])

// The code, not a symbol: the claim's currency can be one the viewer's locale
// has no symbol for, and a bare number is the thing an approver misreads.
const amountLabel = computed(() =>
  defaults.data?.currency ? `Amount (${defaults.data.currency})` : 'Amount',
)

const claimedTotal = computed(() =>
  form.expenses.reduce((total, line) => total + (Number(line.amount) || 0), 0),
)

const problems = computed(() => {
  const found: Record<string, string> = {}
  form.expenses.forEach((line, index) => {
    if (!line.expense_type) found[`type-${index}`] = 'Pick a type'
    if (!Number(line.amount)) found[`amount-${index}`] = 'Enter what it cost'
    else if (Number(line.amount) < 0) found[`amount-${index}`] = 'Amounts cannot be negative'
    if (line.expense_date && line.expense_date > today) {
      found[`date-${index}`] = "That's in the future"
    }
  })
  // Mandatory is HR Settings' answer, not this form's: a site that made the
  // approver optional is one where a blank field has to be allowed through.
  if (expenseCan.value.approver_mandatory && !form.expense_approver) {
    found.expense_approver = 'Pick an approver'
  }
  return found
})

const errors = computed(() => (submitAttempted.value ? problems.value : {}))

function addLine() {
  form.expenses.push(blankLine())
}

// Fresh on every open: a user's default approver, or the set of expense types
// Accounts has configured, can have changed since the section was loaded.
watch(open, (isOpen) => {
  if (isOpen) defaults.reload()
})

// Rebuild when opening and when the defaults land — both are the same event as
// far as the form is concerned: what it should be showing has arrived. A dialog
// that kept the last claim's values would be a trap, starting the next one
// half-filled with somebody's last taxi fare.
watch([open, () => defaults.data], ([isOpen]) => {
  if (!isOpen) {
    submitAttempted.value = false
    return
  }
  Object.assign(form, blankForm())
  attachments.value = []
  submitAttempted.value = false
})

function claimDocument() {
  return {
    doctype: 'Expense Claim',
    expense_approver: form.expense_approver || undefined,
    remark: form.remark || undefined,
    expenses: form.expenses.map(({ key: _key, ...line }) => ({
      ...line,
      amount: Number(line.amount),
    })),
  }
}

async function send(close: () => void) {
  submitAttempted.value = true
  if (Object.keys(problems.value).length) return

  try {
    const created = await request.submit({ doc: JSON.stringify(claimDocument()) })
    // `submit` resolves null on failure; the reason renders inline.
    if (!created) return

    // After the insert, because the files are attached to the claim it
    // returns. A file that would not upload does not undo a claim that is
    // already raised, so it is reported rather than thrown: the claimant is
    // told which receipts to add, not told to claim again.
    const failed = attachments.value.length
      ? await attachToExpenseClaim(created.name, attachments.value)
      : []
    if (failed.length) {
      toast.error(
        `Expenses claimed, but ${pluralise(failed.length, 'receipt')} did not attach: ` +
          `${failed.map((f) => f.file).join(', ')}. Add them to the claim in the desk.`,
      )
    } else {
      toast.success('Expenses claimed')
    }

    emit('created', created.name)
    close()
  } catch {
    // `request.error` renders the server's reason inline — a missing expense
    // account or an unpriceable currency is worth reading in full.
  }
}

const actions = computed<DialogAction[]>(() => [
  {
    label: 'Send claim',
    variant: 'solid',
    disabled: !expenseTypes.value.length,
    onClick: ({ close }) => send(close),
  },
])
</script>
