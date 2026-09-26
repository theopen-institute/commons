<!--
  Import a bank statement: a spreadsheet, a PDF or a photo of the pages.

  Three steps in one dialog. Choose the file; it is read on the server
  (`commons.banking.statement_import`), by Claude where it has to be; then the
  rows are shown with what the dialog proposes for each:

  * **New** rows are ticked, ready to import.
  * **Already imported** rows, the same date, direction and amount as a line
    already on the account, are unticked, with the line they match. See
    `proposeRows` in `data/statementImport.ts`.
  * Rows whose **running balance does not follow** from the row before are
    flagged, ticked or not: on a copied PDF that is where a figure was misread.

  Nothing is written until "Import", which inserts and submits the ticked rows
  as Bank Transactions through `frappe.client.insert_many`. Once a file has
  been read, an outside click does not close the dialog: the reading was a paid
  call, and throwing it away by accident would mean paying for it again.
-->

<template>
  <Dialog
    v-model:open="open"
    :title="reading ? 'Review the statement' : 'Import a bank statement'"
    :message="account ? account.name : undefined"
    :dismissible="!busy && !reading"
    size="5xl"
  >
    <!-- Choosing the file -->
    <!-- A file dropped anywhere else in the dialog is swallowed: left to
         the browser, a missed drop opens the file in place of the page. -->
    <div v-if="!reading" class="space-y-3" @dragover.prevent @drop.prevent>
      <p class="text-p-sm text-ink-gray-6">
        An export from the bank's website (XLSX, XLS or CSV), the statement as a PDF, or photos of its
        pages. Rows already on this account are recognised and left out.
      </p>
      <!-- Click to choose, or drop a file on it. The children ignore the
           pointer, so moving across them does not fire dragleave and make
           the highlight flicker. -->
      <label
        class="flex cursor-pointer flex-col items-center gap-2 rounded-4 border-2 border-dashed px-4 py-8 text-center transition-colors"
        :class="dragging ? 'border-outline-gray-4 bg-surface-gray-2' : 'border-outline-gray-3 hover:bg-surface-gray-1'"
        @dragover.prevent="dragging = !busy"
        @dragleave.prevent="dragging = false"
        @drop.prevent="drop"
      >
        <span class="lucide-file-up pointer-events-none size-6 text-ink-gray-5" />
        <span class="pointer-events-none text-p-sm text-ink-gray-7">
          {{ file ? file.name : dragging ? 'Drop it here' : 'Choose a statement, or drop it here' }}
        </span>
        <span v-if="file && !dragging" class="pointer-events-none text-p-xs text-ink-gray-5">
          Click or drop to choose a different file
        </span>
        <input type="file" class="hidden" :accept="ACCEPTED_STATEMENTS" :disabled="busy" @change="pick" />
      </label>
      <!-- What the background job is doing, asked every two seconds. -->
      <div v-if="busy" class="rounded-4 bg-surface-gray-1 px-3 py-2">
        <div class="flex items-center gap-2 text-p-sm text-ink-gray-8">
          <Spinner class="size-4 shrink-0" />
          <span>{{ progressText }}</span>
          <span class="ml-auto shrink-0 tabular-nums text-ink-gray-5">{{ elapsedText }}</span>
        </div>
        <p class="mt-1 text-p-xs text-ink-gray-5">
          <template v-if="stuckInQueue">
            Nothing has picked the reading up yet. If this goes on, the site's background worker may not be
            running.
          </template>
          <template v-else>A long PDF can take a few minutes. The statement is read in the background.</template>
        </p>
      </div>
      <ErrorMessage v-if="problem" :message="problem" />
      <div class="flex justify-end">
        <Button variant="solid" label="Read statement" :disabled="!file" :loading="busy" @click="read" />
      </div>
    </div>

    <!-- Reviewing the rows -->
    <div v-else class="space-y-3">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-p-sm text-ink-gray-7">
        <span>{{ pluralise(rows.length, 'row') }} read</span>
        <span class="text-ink-green-7">{{ counts.new }} new</span>
        <span>{{ counts.duplicate }} already imported</span>
        <span v-if="counts.breaks" class="text-ink-amber-7">
          {{ pluralise(counts.breaks, 'balance') }} to check
        </span>
        <span v-if="counts.badDate" class="text-ink-red-7">{{ pluralise(counts.badDate, 'unreadable date') }}</span>
      </div>

      <!-- What the statement as a whole says, where it disagrees with itself
           or with this account. -->
      <ul v-if="warnings.length" class="space-y-1 rounded-4 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8">
        <li v-for="warning in warnings" :key="warning" class="flex gap-2">
          <span class="lucide-triangle-alert mt-0.5 size-4 shrink-0 text-ink-amber-7" /> {{ warning }}
        </li>
      </ul>

      <div class="max-h-[26rem] overflow-auto rounded-4 border border-outline-gray-2">
        <table class="w-full border-separate border-spacing-0 text-p-sm">
          <thead class="sticky top-0 bg-surface-white">
            <tr class="text-left text-ink-gray-5">
              <th class="w-8 border-b border-outline-gray-2 px-3 py-2">
                <Checkbox
                  :model-value="allNewSelected"
                  aria-label="Tick every new row"
                  @update:model-value="(on) => selectAllNew(Boolean(on))"
                />
              </th>
              <th class="border-b border-outline-gray-2 px-2 py-2 font-medium">Date</th>
              <th class="w-full border-b border-outline-gray-2 px-2 py-2 font-medium">Description</th>
              <th class="border-b border-outline-gray-2 px-2 py-2 text-right font-medium">Amount</th>
              <th class="border-b border-outline-gray-2 px-2 py-2 text-right font-medium">Balance</th>
              <th class="border-b border-outline-gray-2 px-3 py-2 font-medium">Proposed</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key" :class="row.status === 'duplicate' ? 'text-ink-gray-5' : 'text-ink-gray-8'">
              <td class="border-b border-outline-gray-1 px-3 py-1.5">
                <Checkbox
                  :model-value="selected.has(row.key)"
                  :disabled="row.status === 'bad-date' || busy"
                  :aria-label="`Import the row of ${row.date.printed}`"
                  @update:model-value="(on) => toggle(row.key, Boolean(on))"
                />
              </td>
              <td class="whitespace-nowrap border-b border-outline-gray-1 px-2 py-1.5 tabular-nums">
                {{ row.iso ? formatDate(row.iso) : row.date.printed }}
                <div v-if="row.date.calendar === 'BS'" class="text-p-xs text-ink-gray-5">{{ row.date.printed }} B.S.</div>
              </td>
              <td class="max-w-0 border-b border-outline-gray-1 px-2 py-1.5">
                <div class="truncate" :title="row.description">{{ row.description || '—' }}</div>
                <div v-if="row.reference" class="text-p-xs text-ink-gray-5">Ref {{ row.reference }}</div>
              </td>
              <td
                class="whitespace-nowrap border-b border-outline-gray-1 px-2 py-1.5 text-right tabular-nums"
                :class="row.deposit > 0 && row.status !== 'duplicate' ? 'text-ink-green-7' : ''"
              >
                {{ signed(row.deposit - row.withdrawal) }}
              </td>
              <td class="whitespace-nowrap border-b border-outline-gray-1 px-2 py-1.5 text-right tabular-nums">
                <span v-if="row.balance !== null" :class="row.balanceBreak ? 'text-ink-amber-7' : ''">
                  <span v-if="row.balanceBreak" class="lucide-triangle-alert mr-1 inline-block size-3.5 align-[-2px]" />
                  {{ formatExact(row.balance, currency) }}
                </span>
              </td>
              <td class="whitespace-nowrap border-b border-outline-gray-1 px-3 py-1.5">
                <Badge v-if="row.status === 'new'" label="New" theme="green" size="sm" />
                <a
                  v-else-if="row.status === 'duplicate'"
                  :href="deskUrl('Bank Transaction', row.existing!)"
                  target="_blank"
                  class="inline-flex items-center gap-1 text-p-xs hover:text-ink-gray-7"
                >
                  Already imported · {{ row.existing }} <span class="lucide-external-link size-3" />
                </a>
                <Badge v-else label="Date unreadable" theme="red" size="sm" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <ErrorMessage v-if="problem" :message="problem" />

      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-p-sm tabular-nums text-ink-gray-6">
          {{ pluralise(selected.size, 'row') }} ticked · {{ signed(selectedTotal) }}
        </p>
        <div class="flex gap-2">
          <Button variant="ghost" label="Close" :disabled="busy" @click="open = false" />
          <Button variant="subtle" label="Read another file" :disabled="busy" @click="reset" />
          <Button
            variant="solid"
            :label="selected.size ? `Import ${pluralise(selected.size, 'transaction')}` : 'Import'"
            :disabled="!selected.size"
            :loading="busy"
            @click="importSelected"
          />
        </div>
      </div>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Badge, Button, Checkbox, Dialog, ErrorMessage, Spinner, toast } from 'frappe-ui'
import { formatDate, formatExact, pluralise } from '@/data/format'
import {
  ACCEPTED_STATEMENTS,
  deskUrl,
  startReading,
  useAccountIdentity,
  useExistingLines,
  useImportTransactions,
  useReadingStatus,
  type BankAccountRow,
  type ReadingState,
} from '@/data/reconciliation'
import { money } from '@/data/reconciliationRules'
import { pollReading } from '@/data/backgroundReading'
import {
  STATEMENT_READING_DEADLINE_MS,
  accountMatches,
  balanceSummary,
  proposeRows,
  transactionFor,
  type ProposedRow,
  type StatementReading,
} from '@/data/statementImport'

const props = defineProps<{ account: BankAccountRow | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ imported: [count: number] }>()

const existingLines = useExistingLines()
const identity = useAccountIdentity()
const importer = useImportTransactions()

const file = ref<File | null>(null)
const reading = ref<StatementReading | null>(null)
const rows = ref<ProposedRow[]>([])
const selected = reactive(new Set<number>())
const ownNumbers = ref<(string | null)[]>([])
const currency = ref<string | null>(null)
const busy = ref(false)
const problem = ref('')

function reset() {
  file.value = null
  reading.value = null
  rows.value = []
  selected.clear()
  problem.value = ''
}

watch(open, (isOpen) => {
  if (isOpen) reset()
  else {
    // Stop asking after a reading nobody is waiting for.
    generation++
    busy.value = false
  }
})

const dragging = ref(false)

/** How long a reading may sit in the queue before the dialog says the
 *  background worker may not be running. */
const QUEUE_PATIENCE_MS = 30_000

const status = useReadingStatus()
const progress = ref<ReadingState | null>(null)
const startedAt = ref(0)
const now = ref(0)
/** Bumped by every new reading and by closing the dialog, so a poll that
 *  outlives its reading stops rather than filling in a dialog it no longer
 *  belongs to. */
let generation = 0

const elapsedMs = computed(() => Math.max(0, now.value - startedAt.value))
const elapsedText = computed(() => {
  const seconds = Math.floor(elapsedMs.value / 1000)
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${seconds % 60} s`
})
const stuckInQueue = computed(
  () => (!progress.value || progress.value.status === 'queued') && elapsedMs.value > QUEUE_PATIENCE_MS,
)
const progressText = computed(() => {
  const state = progress.value
  if (!state || state.status === 'queued') return 'Waiting for the background worker to start the reading'
  if (state.step === 'columns') return "Claude is working out the spreadsheet's columns"
  if (state.step === 'rows') return `Reading the rows${state.rows ? `: ${state.rows} so far` : ''}`
  if (!state.rows) return 'Claude is reading the statement'
  return `Claude has copied ${pluralise(state.rows, 'row')} so far`
})

function pick(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  problem.value = ''
}

/** A dropped file is chosen exactly as a picked one is: the server decides
 *  what it is by its contents, so nothing is checked here beyond there being
 *  one. */
function drop(event: DragEvent) {
  dragging.value = false
  if (busy.value) return
  const dropped = event.dataTransfer?.files?.[0]
  if (!dropped) return
  file.value = dropped
  problem.value = ''
}

/** Read the file, then fetch the account's lines over the statement's dates
 *  and propose. The lines are read after the statement because only then are
 *  its dates known. */
async function read() {
  if (!file.value || !props.account) return
  busy.value = true
  problem.value = ''
  progress.value = null
  startedAt.value = Date.now()
  now.value = Date.now()
  const ticker = window.setInterval(() => (now.value = Date.now()), 1000)
  const run = ++generation
  try {
    const answer = await waitForReading(await startReading(file.value), run)
    if (!answer) return
    const own = await identity.load(props.account)
    ownNumbers.value = own.numbers
    currency.value = own.currency
    await propose(answer)
    reading.value = answer
  } catch (error) {
    if (run === generation) problem.value = (error as Error).message || 'The statement could not be read'
  } finally {
    window.clearInterval(ticker)
    if (run === generation) busy.value = false
  }
}

/** Ask after the reading until it is done, has failed, or has taken longer
 *  than any reading can (`STATEMENT_READING_DEADLINE_MS`). Returns null if the
 *  dialog was closed or restarted meanwhile: the job carries on regardless,
 *  and its answer is simply not collected. */
function waitForReading(token: string, run: number): Promise<StatementReading | null> {
  return pollReading<StatementReading, ReadingState>({
    check: () => status.check(token),
    deadlineMs: STATEMENT_READING_DEADLINE_MS,
    deadlineMessage:
      'The statement is taking far longer than any reading should. The background worker may have stopped; try again.',
    failedMessage: 'The statement could not be read',
    onProgress: (state) => (progress.value = state),
    cancelled: () => run !== generation,
  })
}

/** Compare the statement with the account's lines over its dates, give or
 *  take the slack `proposeRows` allows, and tick what is new. */
async function propose(answer: StatementReading) {
  if (!props.account) return
  const dates = proposeRows(answer, [])
    .map((row) => row.iso)
    .filter(Boolean)
    .sort() as string[]
  const existing = dates.length
    ? await existingLines.load(props.account.name, shift(dates[0], -3), shift(dates[dates.length - 1], 3))
    : []
  rows.value = proposeRows(answer, existing)
  selected.clear()
  for (const row of rows.value) if (row.status === 'new') selected.add(row.key)
}

function shift(date: string, days: number) {
  const [y, m, d] = date.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

const counts = computed(() => ({
  new: rows.value.filter((row) => row.status === 'new').length,
  duplicate: rows.value.filter((row) => row.status === 'duplicate').length,
  badDate: rows.value.filter((row) => row.status === 'bad-date').length,
  breaks: rows.value.filter((row) => row.balanceBreak).length,
}))

/** What the statement says about itself that is worth a second look, one
 *  sentence each. */
const warnings = computed(() => {
  const read = reading.value
  if (!read) return []
  const out: string[] = []
  if (!read.is_statement) out.push('This does not look like a bank statement.')
  const matches = accountMatches(read.account_number, ownNumbers.value)
  if (matches === false) {
    out.push(`The statement is for account ${read.account_number}, which is not this bank account's number.`)
  }
  if (read.currency && currency.value && read.currency !== currency.value) {
    out.push(`The statement is in ${read.currency}; this account is kept in ${currency.value}.`)
  }
  const summary = balanceSummary(read, rows.value)
  if (summary.closingDifference) {
    out.push(
      `The opening balance and the rows come to ${signed(summary.closingDifference)} away from the printed closing balance: a row may be missing or misread.`,
    )
  }
  if (summary.broken) {
    out.push(
      `On ${pluralise(summary.broken, 'row')} the running balance does not follow from the row before. Check ${summary.broken === 1 ? 'it' : 'them'} against the statement.`,
    )
  }
  return [...out, ...read.notes]
})

const allNewSelected = computed(
  () => counts.value.new > 0 && rows.value.every((row) => row.status !== 'new' || selected.has(row.key)),
)

function selectAllNew(on: boolean) {
  for (const row of rows.value) {
    if (row.status !== 'new') continue
    if (on) selected.add(row.key)
    else selected.delete(row.key)
  }
}

function toggle(key: number, on: boolean) {
  if (on) selected.add(key)
  else selected.delete(key)
}

const selectedTotal = computed(() =>
  money(rows.value.filter((row) => selected.has(row.key)).reduce((sum, row) => sum + row.deposit - row.withdrawal, 0)),
)

function signed(value: number) {
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatExact(Math.abs(value), currency.value)}`
}

async function importSelected() {
  if (!props.account) return
  const chosen = rows.value.filter((row) => selected.has(row.key) && row.iso)
  busy.value = true
  problem.value = ''
  try {
    const done = await importer.run(chosen.map((row) => transactionFor(row, props.account!.name, currency.value)))
    if (done.error) {
      problem.value =
        (done.created.length ? `${pluralise(done.created.length, 'transaction')} imported, then: ` : '') +
        (done.error.message || 'The rows could not be imported')
      // What did go in is now on the account: proposing again turns those
      // rows into "already imported", so a second press cannot book them twice.
      if (done.created.length) {
        emit('imported', done.created.length)
        if (reading.value) await propose(reading.value)
      }
      return
    }
    toast.success(`${pluralise(done.created.length, 'bank transaction')} imported`)
    emit('imported', done.created.length)
    open.value = false
  } finally {
    busy.value = false
  }
}
</script>
