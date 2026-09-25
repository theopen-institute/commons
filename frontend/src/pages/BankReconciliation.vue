<template>
  <AppPageHeader>
    <div class="flex min-w-0 items-center gap-3">
      <span class="text-lg font-semibold text-ink-gray-8">Bank Reconciliation</span>
    </div>
    <template #actions>
      <Button
        v-if="importAvailable && bankAccount"
        variant="subtle"
        icon-left="lucide-file-up"
        label="Import statement"
        @click="importOpen = true"
      />
      <Button
        v-if="reconciliationCan.reconcile && bankAccount"
        variant="subtle"
        icon-left="lucide-wand-sparkles"
        label="Auto-match"
        @click="autoOpen = true"
      />
      <Button
        variant="ghost"
        icon-left="lucide-refresh-cw"
        label="Refresh"
        :loading="transactions.loading.value"
        @click="reload()"
      />
    </template>
  </AppPageHeader>

  <div class="px-5 py-4">
    <!-- The sidebar hides this page from anybody who cannot write a Bank
         Transaction, so only somebody following a link lands here. -->
    <div v-if="canReconcileResolved && !reconciliationCan.reconcile" class="mt-16 text-center">
      <span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
      <p class="mt-2 text-base-medium text-ink-gray-7">Reconciling the bank isn't yours to do</p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        This page is for whoever keeps the bank accounts' books. Ask whoever administers permissions if
        that should include you.
      </p>
    </div>

    <template v-else>
      <div class="grid gap-3 sm:grid-cols-[minmax(0,2fr)_1fr_1fr]">
        <FormControl
          v-model="bankAccount"
          type="select"
          label="Bank account"
          :options="accountOptions"
          :disabled="!accounts.loaded.value"
          :description="importedTo"
        />
        <FormControl v-model="from" type="date" label="From" />
        <FormControl v-model="to" type="date" label="To" />
      </div>

      <ErrorMessage v-if="accounts.error.value" :message="accounts.error.value.message" class="mt-4" />

      <div
        v-if="accounts.loaded.value && !accounts.accounts.value.length"
        class="mt-16 text-center"
      >
        <span class="lucide-landmark mx-auto size-8 text-ink-gray-4" />
        <p class="mt-2 text-base-medium text-ink-gray-7">No company bank accounts</p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          A Bank Account marked as the company's own is what statements are kept for.
        </p>
      </div>

      <template v-else-if="bankAccount">
        <ReconciliationBalances
          class="mt-5"
          :balances="periodBalances.balances.value"
          :bank-account="bankAccount"
          :currency="currency"
          :to="to"
          @saved="loadProgress"
        />

        <div class="mt-5 flex flex-wrap items-center justify-between gap-3">
          <TabButtons v-model="view" :options="viewOptions" />
          <div class="w-full sm:w-64">
            <TextInput v-model="search" placeholder="Filter by description, reference, amount" size="sm">
              <template #prefix><span class="lucide-search size-4 text-ink-gray-5" /></template>
            </TextInput>
          </div>
        </div>

        <!-- What the period leaves out, and the drafts. Both are added to the
             board on request rather than by moving the dates, so the figures
             above stay the period's. -->
        <div
          v-if="outsideCount || (view === 'unreconciled' && draftData.drafts.value.length)"
          class="mt-3 flex flex-wrap items-center gap-2"
        >
          <div
            v-if="outsideCount"
            class="flex items-center gap-2 rounded-4 bg-surface-amber-2 px-3 py-1 text-p-sm text-ink-gray-8"
          >
            <span class="lucide-calendar-x size-4 text-ink-amber-7" />
            <span v-if="!outside">{{ outsideLabel }} outside these dates</span>
            <span v-else>Including {{ outsideLabel }} from outside these dates</span>
            <Button size="sm" variant="ghost" :label="outside ? 'Hide them' : 'Show them'" @click="outside = !outside" />
          </div>
          <Button
            v-if="view === 'unreconciled' && draftData.drafts.value.length"
            size="sm"
            variant="subtle"
            icon-left="lucide-file-pen"
            :label="withDrafts ? 'Hide drafts' : `Include ${pluralise(draftData.drafts.value.length, 'draft')}`"
            title="Unsubmitted vouchers that will post to this account when submitted"
            @click="withDrafts = !withDrafts"
          />
        </div>

        <ErrorMessage
          v-if="progressData.error.value"
          :message="progressData.error.value.message"
          class="mt-4"
        />
        <ErrorMessage
          v-if="transactions.error.value"
          :message="transactions.error.value.message"
          class="mt-4"
        />
        <ErrorMessage
          v-if="draftData.error.value"
          :message="`Drafts could not be read: ${draftData.error.value.message}`"
          class="mt-4"
        />
        <ErrorMessage
          v-if="unmatched.error.value"
          :message="`The entries not yet on the statement could not be read: ${unmatched.error.value.message}`"
          class="mt-4"
        />
        <ErrorMessage
          v-if="loanBook.error.value"
          :message="`Loans could not be read, so there are no suggestions: ${loanBook.error.value.message}`"
          class="mt-4"
        />

        <div v-if="!transactions.loaded.value" class="mt-3 space-y-2">
          <Skeleton v-for="n in 6" :key="n" class="h-11 w-full rounded-4" />
        </div>

        <!-- What is left to reconcile, both halves of it: the lines and the
             entries the two open rows of the check above are made of. -->
        <template v-else-if="view === 'unreconciled'">
          <ReconciliationBoard
            class="mt-3"
            :lines="visible"
            :entries="boardEntries"
            :names="loanBook.book.value.names"
            :currency="currency"
            @open="openLine"
            @pair="openPair"
          />
          <p class="mt-2 text-p-xs text-ink-gray-5">
            Drag a line onto its entry, or an entry onto its line, to match them. Click a statement line for
            everything else: a loan repayment, a new payment or journal entry.
          </p>
        </template>

        <div v-else-if="!visible.length" class="mt-12 text-center">
          <span class="lucide-circle-check mx-auto size-8 text-ink-gray-4" />
          <p class="mt-2 text-base-medium text-ink-gray-7">
            {{
              search.trim()
                ? 'No line matches that filter'
                : !transactions.rows.value.length
                  ? 'No statement lines between these dates'
                  : 'No reconciled lines between these dates'
            }}
          </p>
        </div>

        <template v-else>
          <ReconciliationList
            ref="list"
            class="mt-3"
            :rows="visible"
            :hints="hints"
            :names="loanBook.book.value.names"
            @open="openLine"
          />
          <p class="mt-2 text-p-xs text-ink-gray-5">
            ↑ ↓ to move, Enter to open. After each line is reconciled, the next open one comes up.
          </p>
        </template>
      </template>
    </template>

    <ReconciliationImportDialog v-model:open="importOpen" :account="account" @imported="reload" />

    <ReconciliationPairDialog
      v-model:open="pairOpen"
      :line="pairLine"
      :entry="pairEntry"
      :currency="currency"
      @done="onPaired"
    />

    <ReconciliationDialog
      v-model:open="dialogOpen"
      :transaction="current"
      :book="loanBook.book.value"
      :suggestions="currentSuggestions"
      :lending="reconciliationCan.repayLoans"
      :names="loanBook.book.value.names"
      :position="position"
      :has-previous="stepTarget(-1) !== null"
      :has-next="stepTarget(1) !== null"
      @done="onDone"
      @updated="onUpdated"
      @step="step"
    />

    <Dialog
      v-model:open="autoOpen"
      title="Auto-match"
      :message="autoMessage"
      :actions="autoActions"
      :dismissible="!autoBusy"
    >
      <ErrorMessage v-if="autoProblem" :message="autoProblem" />
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button,
  Dialog,
  ErrorMessage,
  FormControl,
  Skeleton,
  TabButtons,
  TextInput,
  toast,
  type DialogAction,
} from 'frappe-ui'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ReconciliationDialog from '@/components/ReconciliationDialog.vue'
import ReconciliationList, { type RowHint } from '@/components/ReconciliationList.vue'
import ReconciliationBoard from '@/components/ReconciliationBoard.vue'
import ReconciliationImportDialog from '@/components/ReconciliationImportDialog.vue'
import ReconciliationPairDialog from '@/components/ReconciliationPairDialog.vue'
import ReconciliationBalances from '@/components/ReconciliationBalances.vue'
import { formatDate, pluralise } from '@/data/format'
import {
  importAvailable,
  inView,
  reconciliationCan,
  reconciliationGate,
  useAutoReconcile,
  useBankAccounts,
  useLoanBook,
  usePeriodBalances,
  useProgress,
  useDraftEntries,
  useUnmatchedEntries,
  useTransactions,
  write,
  type TransactionView,
} from '@/data/reconciliation'
import {
  amountOf,
  daysBetween,
  money,
  suggestLoans,
  type BookEntry,
  type Suggestion,
  type TransactionRow,
} from '@/data/reconciliationRules'

/**
 * Bank reconciliation: one bank account's statement for a period, and a
 * dialog per line.
 *
 * The account, the dates and the view live in the query string, as the
 * attendance register's term and course do, so "OI Checking for July" is a
 * link and a refresh comes back where it was.
 *
 * The page itself writes nothing. A line opens its dialog, the dialog's tabs
 * hold drafts, and each tab has one button that writes. See
 * `data/reconciliation.ts` for what those writes are. All but one are
 * ERPNext's.
 */

const route = useRoute()
const router = useRouter()

const accounts = useBankAccounts()
const transactions = useTransactions()
const progressData = useProgress()
const periodBalances = usePeriodBalances()
const unmatched = useUnmatchedEntries()
const draftData = useDraftEntries()
const loanBook = useLoanBook()
const auto = useAutoReconcile()

const canReconcileResolved = reconciliationGate.resolved

const bankAccount = ref('')
const from = ref('')
const to = ref('')
const view = ref<TransactionView>('unreconciled')
const search = ref('')
/** Whether the list also shows the open lines dated outside the period. */
const outside = ref(false)
/** Whether the board lists drafts that will post to this account. */
const withDrafts = ref(false)

function isoDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

/** The desk tool's default period: the last month, to today. */
function defaultPeriod() {
  const today = new Date()
  const monthAgo = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate())
  return { from: isoDate(monthAgo), to: isoDate(today) }
}

function queryValue(key: string) {
  const value = route.query[key]
  return typeof value === 'string' ? value : ''
}

watch(
  () => reconciliationCan.value.reconcile,
  (can) => {
    if (can) accounts.load()
  },
  { immediate: true },
)

watch(accounts.loaded, (ready) => {
  if (!ready) return
  // The desk tool's period, the last month. Open lines before it are not
  // lost: the page says how many there are and adds them on request.
  const period = defaultPeriod()
  from.value = queryValue('from') || period.from
  to.value = queryValue('to') || period.to
  const views: TransactionView[] = ['unreconciled', 'reconciled', 'all']
  view.value = views.find((value) => value === queryValue('view')) ?? 'unreconciled'
  outside.value = queryValue('outside') === '1'
  withDrafts.value = queryValue('drafts') === '1'
  bankAccount.value = queryValue('account') || accounts.accounts.value[0]?.name || ''
})

const account = computed(
  () => accounts.accounts.value.find((row) => row.name === bankAccount.value) ?? null,
)

/** The statement's currency, read off its lines, since a Bank Account names
 *  none of its own. */
const currency = computed(
  () => transactions.rows.value[0]?.currency ?? progressData.progress.value?.currency ?? null,
)

const accountOptions = computed(() =>
  accounts.accounts.value.map((row) => ({
    label: row.company ? `${row.name} · ${row.company}` : row.name,
    value: row.name,
  })),
)

// Replace rather than push: changing a filter is not somewhere you went.
watch([bankAccount, from, to, view, outside, withDrafts], () => {
  router.replace({
    query: {
      ...route.query,
      account: bankAccount.value || undefined,
      from: from.value || undefined,
      to: to.value || undefined,
      view: view.value === 'unreconciled' ? undefined : view.value,
      outside: outside.value ? '1' : undefined,
      drafts: withDrafts.value ? '1' : undefined,
    },
  })
})

watch([bankAccount, from, to, outside], () => {
  if (!bankAccount.value || !from.value || !to.value) return
  loadLines()
})

watch([account, from, to], () => periodBalances.load(account.value, from.value, to.value))

watch(account, () => {
  progressData.load(account.value)
  unmatched.load(account.value)
})

// Lending decides whether loan drafts are read, and its answer can arrive
// after the account does.
watch(
  () => [account.value?.name, reconciliationCan.value.repayLoans],
  () => draftData.load(account.value, reconciliationCan.value.repayLoans),
)

function inPeriod(date: string) {
  return date >= from.value && date <= to.value
}

function loadLines() {
  return transactions.load(bankAccount.value, from.value, to.value, outside.value)
}

/** Open lines dated before or after the period, from the account's progress,
 *  which reads every open line whatever the dates. */
const outsideLines = computed(
  () => (progressData.progress.value?.openDates ?? []).filter((date) => !inPeriod(date)).length,
)
const outsideEntries = computed(() => unmatched.entries.value.filter((entry) => !inPeriod(entry.date)).length)
const outsideCount = computed(() => outsideLines.value + outsideEntries.value)
/** "3 open lines and one entry", whichever of the two there are. */
const outsideLabel = computed(() =>
  [
    outsideLines.value && pluralise(outsideLines.value, 'open line'),
    outsideEntries.value && pluralise(outsideEntries.value, 'open entry', 'open entries'),
  ]
    .filter(Boolean)
    .join(' and '),
)

/** The entries the board shows: the period's, or all of them with the
 *  outside toggle on, then the drafts (whatever their dates, see
 *  `useDraftEntries`) if asked for, narrowed by the same filter as the lines. */
const boardEntries = computed(() => {
  const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const drafts = withDrafts.value ? draftData.drafts.value : []
  return [...unmatched.entries.value, ...drafts].filter((entry) => {
    if (!entry.draft && !outside.value && !inPeriod(entry.date)) return false
    if (!words.length) return true
    const haystack = [entry.name, entry.doctype, entry.against, entry.reference, String(entry.debit || entry.credit)]
      .join(' ')
      .toLowerCase()
    return words.every((word) => haystack.includes(word))
  })
})

/** "Statement imported to Jul 18, 2026 · 68 days ago", under the account
 *  picker: how far the bank's side is known, before any dates are chosen. */
const importedTo = computed(() => {
  const last = progressData.progress.value?.lastLineDate
  if (!last) return progressData.progress.value ? 'No statement imported yet' : undefined
  const days = daysBetween(last, isoDate(new Date()))
  return `Statement imported to ${formatDate(last)} · ${days <= 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`}`
})

// The loan book belongs to the account's company, not to the period.
watch(
  () => [account.value?.name, reconciliationCan.value.repayLoans],
  () => {
    if (reconciliationCan.value.repayLoans) loanBook.load(account.value)
  },
)

/** The figures every write moves: whether the books match the bank, and the
 *  period's cleared balances. Also what a recorded bank balance moves. */
function loadProgress() {
  progressData.load(account.value)
  periodBalances.load(account.value, from.value, to.value)
  unmatched.load(account.value)
  draftData.load(account.value, reconciliationCan.value.repayLoans)
}


function reload() {
  loadLines()
  loadProgress()
  if (reconciliationCan.value.repayLoans) loanBook.load(account.value)
}

/* -------------------------------------------------------------------------- */
/* What is on screen                                                           */
/* -------------------------------------------------------------------------- */

const counts = computed(() => {
  const rows = transactions.rows.value
  return {
    unreconciled:
      rows.filter((row) => inView(row, 'unreconciled')).length +
      boardEntries.value.filter((entry) => !entry.draft).length,
    reconciled: rows.filter((row) => inView(row, 'reconciled')).length,
    all: rows.length,
  }
})

const viewOptions = computed(() => [
  { value: 'unreconciled', label: `To reconcile · ${counts.value.unreconciled}` },
  { value: 'reconciled', label: `Reconciled · ${counts.value.reconciled}` },
  { value: 'all', label: `All · ${counts.value.all}` },
])

const visible = computed(() => {
  const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
  return transactions.rows.value.filter((row) => {
    if (!inView(row, view.value)) return false
    if (!words.length) return true
    const haystack = [
      row.description,
      row.reference_number,
      row.party,
      row.name,
      String(Math.abs(amountOf(row))),
    ]
      .join(' ')
      .toLowerCase()
    return words.every((word) => haystack.includes(word))
  })
})

/** Every open deposit's suggestions, worked out once per change to the lines
 *  or the loan book. The list shows the first and the dialog all of them. */
const suggestions = computed<Record<string, Suggestion[]>>(() => {
  if (!reconciliationCan.value.repayLoans) return {}
  const { loans, names, history } = loanBook.book.value
  if (!loans.length) return {}
  const out: Record<string, Suggestion[]> = {}
  for (const row of transactions.rows.value) {
    if (row.deposit > 0 && row.unallocated_amount > 0.005) {
      out[row.name] = suggestLoans(row, loans, names, history)
    }
  }
  return out
})

const hints = computed<Record<string, RowHint>>(() => {
  const { loans, names } = loanBook.book.value
  const applicantOf = new Map(loans.map((loan) => [loan.name, loan.applicant]))
  const out: Record<string, RowHint> = {}
  for (const [line, found] of Object.entries(suggestions.value)) {
    const best = found[0]
    if (!best) continue
    const applicant = applicantOf.get(best.loan) ?? ''
    out[line] = {
      label: `${best.strong ? 'Likely' : 'Maybe'} ${names[applicant] ?? applicant}${found.length > 1 ? ` (+${found.length - 1})` : ''}`,
      reasons: best.reasons,
    }
  }
  return out
})

/* -------------------------------------------------------------------------- */
/* The dialog                                                                  */
/* -------------------------------------------------------------------------- */

const list = ref<InstanceType<typeof ReconciliationList> | null>(null)
const dialogOpen = ref(false)
const currentName = ref('')
const current = computed(
  () => transactions.rows.value.find((row) => row.name === currentName.value) ?? null,
)
const currentSuggestions = computed(() => suggestions.value[currentName.value] ?? [])

/**
 * The lines the dialog steps through: the ones on screen, frozen when the
 * dialog opens. Frozen because, in the "to reconcile" view, a line leaves the
 * list the moment it is reconciled, and stepping through a list that keeps
 * shrinking skips the line that moved into the gap.
 */
const sequence = ref<string[]>([])

const position = computed(() => {
  const index = sequence.value.indexOf(currentName.value)
  return index < 0 ? '' : `${index + 1} of ${sequence.value.length}`
})

function openLine(row: TransactionRow) {
  sequence.value = visible.value.map((line) => line.name)
  currentName.value = row.name
  dialogOpen.value = true
}

function stepTarget(direction: 1 | -1): string | null {
  const index = sequence.value.indexOf(currentName.value)
  if (index < 0) return null
  return sequence.value[index + direction] ?? null
}

function step(direction: 1 | -1) {
  const target = stepTarget(direction)
  if (target) currentName.value = target
}

/** The next line after this one that still has something to account for. */
function nextOpen(): string | null {
  const index = sequence.value.indexOf(currentName.value)
  for (const name of sequence.value.slice(index + 1)) {
    const row = transactions.rows.value.find((line) => line.name === name)
    if (row && row.unallocated_amount > 0.005) return name
  }
  return null
}

function onDone(name: string, unallocated: number) {
  patchLine(name, unallocated)
  // How far the account is reconciled, and the loan book (outstanding
  // amounts, uncleared repayments), have moved too. Neither is waited for.
  loadProgress()
  if (reconciliationCan.value.repayLoans) loanBook.load(account.value)

  if (unallocated > 0.005) return
  const next = nextOpen()
  if (next) currentName.value = next
  else {
    toast.success('That was the last line to reconcile here')
    dialogOpen.value = false
  }
}

const importOpen = ref(false)
const pairOpen = ref(false)
const pairLine = ref<TransactionRow | null>(null)
const pairEntry = ref<BookEntry | null>(null)

function openPair(line: TransactionRow, entry: BookEntry) {
  pairLine.value = line
  pairEntry.value = entry
  pairOpen.value = true
}

/** A pair matched from the board: the line's new amounts patched in, and the
 *  figures that moved read again. Nothing advances, unlike the line dialog:
 *  the board is already showing what is left. */
function onPaired(name: string, unallocated: number) {
  patchLine(name, unallocated)
  loadProgress()
}

function patchLine(name: string, unallocated: number) {
  const row = transactions.rows.value.find((line) => line.name === name)
  if (!row) return
  transactions.patch(name, {
    unallocated_amount: unallocated,
    allocated_amount: money(Math.abs(amountOf(row)) - unallocated),
    status: unallocated > 0.005 ? 'Unreconciled' : 'Reconciled',
  })
}

function onUpdated(name: string, values: Partial<TransactionRow>) {
  // An unlink changes amounts the dialog cannot know, so the statement is
  // read again; a new reference or party is only patched in.
  if (!Object.keys(values).length) reload()
  else transactions.patch(name, values)
}

// Back to the list, at the line the dialog ended on, so the keyboard carries
// on from there.
watch(dialogOpen, (isOpen) => {
  if (!isOpen) list.value?.focusRow(currentName.value)
})

/* -------------------------------------------------------------------------- */
/* Auto-match                                                                  */
/* -------------------------------------------------------------------------- */

const autoOpen = ref(false)
const autoBusy = ref(false)
const autoProblem = ref('')

const autoMessage = computed(
  () =>
    `ERPNext's matcher goes through every unreconciled line on ${bankAccount.value}, not only this period's, ` +
    'and reconciles it with any payment, journal entry or sales invoice posted in this period whose reference ' +
    'number is the same as the line’s. It creates nothing. Above ten lines it runs in the background.',
)

const autoActions = computed<DialogAction[]>(() => [
  {
    label: 'Run auto-match',
    variant: 'solid',
    loading: autoBusy.value,
    onClick: async ({ close }) => {
      autoBusy.value = true
      autoProblem.value = ''
      const before = counts.value.unreconciled
      try {
        const done = await write(auto, { bank_account: bankAccount.value, from_date: from.value, to_date: to.value })
        if (!done.ok) {
          autoProblem.value = done.error?.message || 'Auto-match could not run'
          return
        }
        await loadLines()
        loadProgress()
        const matched = before - counts.value.unreconciled
        toast.success(
          matched > 0
            ? `${pluralise(matched, 'line')} reconciled`
            : 'Nothing matched by reference in this period. If it is running in the background, refresh in a minute.',
        )
        close()
      } finally {
        autoBusy.value = false
      }
    },
  },
])
</script>
