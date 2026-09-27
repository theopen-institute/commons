<template>
	<div class="px-5 py-4">
		<!-- The sidebar hides this page from anybody who can draft neither kind,
         so only somebody following a link lands here. -->
		<div v-if="captureGate.resolved.value && !captureCan.capture" class="mt-16 text-center">
			<span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
			<p class="mt-2 text-base-medium text-ink-gray-7">
				There is nothing here for you to draft
			</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				This page drafts purchase invoices and expense claims from scans. Ask whoever
				administers permissions if that should include you.
			</p>
		</div>

		<div v-else class="mx-auto max-w-3xl">
			<!-- What the scan should become, when this person may make both. -->
			<div
				v-if="captureCan.kinds.length > 1"
				class="mb-3 grid gap-2 sm:grid-cols-2"
				role="radiogroup"
				aria-label="What the scan is"
			>
				<button
					v-for="kind in captureCan.kinds"
					:key="kind"
					type="button"
					role="radio"
					:aria-checked="uploadKind === kind"
					class="rounded-4 border px-4 py-3 text-left transition-colors"
					:class="
						uploadKind === kind
							? 'border-outline-gray-4 bg-surface-gray-2'
							: 'border-outline-gray-2 hover:bg-surface-gray-1'
					"
					:disabled="reading.busy"
					@click="uploadKind = kind"
				>
					<p class="text-base-medium text-ink-gray-8">{{ KIND_LABELS[kind].noun }}</p>
					<p class="mt-0.5 text-p-sm text-ink-gray-5">{{ KIND_LABELS[kind].hint }}</p>
				</button>
			</div>

			<!-- Choosing a file stores it as a capture and reads it; the draft is
           only made in the dialog that opens. -->
			<section
				class="rounded-4 border-2 border-dashed px-6 py-8 text-center transition-colors"
				:class="
					dragging ? 'border-outline-gray-4 bg-surface-gray-2' : 'border-outline-gray-2'
				"
				@dragover.prevent="dragging = true"
				@dragleave.prevent="dragging = false"
				@drop.prevent="onDrop"
			>
				<template v-if="reading.busy">
					<LoadingIndicator class="mx-auto size-6 text-ink-gray-6" />
					<p class="mt-3 text-base-medium text-ink-gray-8">
						{{ reading.uploading ? 'Keeping' : 'Reading' }} {{ reading.pending }}
					</p>
					<p v-if="!reading.uploading" class="mt-1 text-p-sm text-ink-gray-5">
						{{
							readingProgressText(reading.progress) ??
							'This usually takes ten to thirty seconds.'
						}}
					</p>
				</template>
				<template v-else>
					<span class="lucide-scan-text mx-auto size-8 text-ink-gray-5" />
					<p class="mt-2 text-base-medium text-ink-gray-8">
						Scan
						{{ uploadKind === EXPENSE_CLAIM ? 'a receipt' : "a supplier's invoice" }}
					</p>
					<p class="mx-auto mt-1 max-w-md text-p-sm text-ink-gray-5">
						<template v-if="uploadKind === EXPENSE_CLAIM">
							A photo or a PDF of what you paid for. It is kept for you to read with
							Claude, which drafts your expense claim for you to check, with the
							receipt attached.
						</template>
						<template v-else>
							A photo or a PDF of one invoice. It is kept for you to read with
							Claude, which drafts a purchase invoice for you to check against the
							scan, with the scan attached.
						</template>
					</p>
					<Button
						class="mt-4"
						variant="solid"
						icon-left="lucide-upload"
						label="Choose a scan"
						@click="pick"
					/>
					<p class="mt-2 text-p-xs text-ink-gray-5">Or drop the file here.</p>
				</template>

				<!-- `hidden` rather than styled: the button above is the control. On
             a phone the picker offers the camera. -->
				<input
					ref="fileInput"
					type="file"
					class="hidden"
					:accept="ACCEPTED_SCANS"
					@change="onPicked"
				/>
			</section>

			<ErrorMessage v-if="reading.error" :message="reading.error" class="mt-3" />

			<!-- Every scan is kept as a capture until it is drafted or discarded,
           so a closed dialog, a failed read or an emailed scan waits here. A
           click only opens a dialog; reading and discarding are its buttons. -->
			<section class="mt-8">
				<div class="flex items-center justify-between">
					<h2 class="text-base-medium text-ink-gray-8">Waiting to be checked</h2>
					<Button
						variant="ghost"
						icon-left="lucide-refresh-cw"
						label="Refresh"
						:loading="waiting.loading.value"
						@click="waiting.load()"
					/>
				</div>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					Scans uploaded here or emailed in that are not drafts yet. Open one to check it
					and make the draft, or to read it again.
				</p>

				<ErrorMessage
					v-if="waiting.error.value"
					:message="waiting.error.value.message"
					class="mt-3"
				/>

				<div v-if="!waiting.loaded.value" class="mt-3 space-y-2">
					<Skeleton v-for="n in 2" :key="n" class="h-14 w-full rounded-4" />
				</div>

				<p
					v-else-if="!waiting.rows.value.length"
					class="mt-6 text-center text-p-sm text-ink-gray-5"
				>
					Nothing waiting.
				</p>

				<ul
					v-else
					class="mt-3 divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1"
				>
					<li v-for="row in waiting.rows.value" :key="row.name">
						<button
							type="button"
							class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-gray-1 disabled:cursor-default disabled:hover:bg-transparent"
							:disabled="
								row.state === 'queued' ||
								row.state === 'reading' ||
								row.state === 'received'
							"
							@click="openRow(row)"
						>
							<div class="min-w-0">
								<p class="truncate text-base text-ink-gray-8">
									{{ row.subject || row.name }}
								</p>
								<p class="truncate text-p-sm text-ink-gray-5">
									{{ KIND_LABELS[row.document_type]?.noun ?? row.document_type }}
									·
									<template v-if="row.source === 'Email'">
										from {{ row.sender_name || row.sender }}
									</template>
									<template v-else>uploaded</template>
									{{ formatDate(row.creation) }}
								</p>
							</div>
							<Badge
								:label="STATE_LABELS[row.state].label"
								:theme="STATE_LABELS[row.state].theme"
								variant="subtle"
								class="shrink-0"
							/>
						</button>
					</li>
				</ul>
			</section>

			<section v-if="captureCan.invoices" class="mt-8">
				<div class="flex items-center justify-between">
					<h2 class="text-base-medium text-ink-gray-8">Your draft invoices</h2>
					<Button
						variant="ghost"
						icon-left="lucide-refresh-cw"
						label="Refresh"
						:loading="drafts.loading.value"
						@click="drafts.load()"
					/>
				</div>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					Purchase invoices you have made and not yet submitted, however they were made.
					Open one in the desk to submit it.
				</p>

				<ErrorMessage
					v-if="drafts.error.value"
					:message="drafts.error.value.message"
					class="mt-3"
				/>

				<div v-if="!drafts.loaded.value" class="mt-3 space-y-2">
					<Skeleton v-for="n in 3" :key="n" class="h-14 w-full rounded-4" />
				</div>

				<p
					v-else-if="!drafts.rows.value.length"
					class="mt-6 text-center text-p-sm text-ink-gray-5"
				>
					Nothing waiting to be submitted.
				</p>

				<ul
					v-else
					class="mt-3 divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1"
				>
					<li v-for="row in drafts.rows.value" :key="row.name">
						<a
							:href="deskUrl(PURCHASE_INVOICE, row.name)"
							target="_blank"
							rel="noopener"
							class="flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-gray-1"
							:class="row.name === justCreated ? 'bg-surface-gray-1' : ''"
						>
							<div class="min-w-0">
								<p class="truncate text-base text-ink-gray-8">
									{{ row.supplier_name || row.supplier }}
								</p>
								<p class="truncate text-p-sm text-ink-gray-5">
									{{ row.name
									}}<template v-if="row.bill_no">
										· bill {{ row.bill_no }}</template
									>
									· {{ formatDate(row.posting_date) }} · {{ row.company }}
								</p>
							</div>
							<span class="shrink-0 text-base tabular-nums text-ink-gray-7">
								{{ formatExact(row.grand_total, row.currency) }}
							</span>
						</a>
					</li>
				</ul>
			</section>
		</div>

		<CaptureInvoiceDialog
			v-model:open="invoiceOpen"
			:reading="invoiceReading"
			@created="onCreated"
		/>
		<CaptureExpenseDialog
			v-model:open="expenseOpen"
			:reading="expenseReading"
			@created="onCreated"
		/>
		<CaptureDetailsDialog
			v-model:open="detailsOpen"
			:capture="detailsRow"
			@queued="onQueued"
			@discarded="waiting.load()"
		/>
	</div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, LoadingIndicator, Skeleton, toast } from 'frappe-ui'
import CaptureDetailsDialog from '@/components/CaptureDetailsDialog.vue'
import CaptureExpenseDialog from '@/components/CaptureExpenseDialog.vue'
import CaptureInvoiceDialog from '@/components/CaptureInvoiceDialog.vue'
import {
	ACCEPTED_SCANS,
	EXPENSE_CLAIM,
	KIND_LABELS,
	PURCHASE_INVOICE,
	ReadingCancelled,
	captureCan,
	captureGate,
	deskUrl,
	readingProgressText,
	uploadScan,
	useMyDrafts,
	useOpenCapture,
	useWaitingCaptures,
	waitForReading,
	type CaptureKind,
	type CaptureReadingState,
	type CaptureRow,
	type CaptureState,
} from '@/data/capture'
import type { ExpenseReading, Reading } from '@/data/captureRules'
import type { PageAction } from '@/islands/contract'
import { formatDate, formatExact } from '@/data/format'

/**
 * Document capture: a scan in, a draft Purchase Invoice or Expense Claim out.
 *
 * Every scan is kept as a `Captured Document` from the moment it is chosen
 * here or emailed in, and read in the background once somebody presses Read
 * in its dialog; nothing is read on arrival, because a reading is billed. The page lists the ones
 * that are not drafts yet; a click opens a dialog, and only the dialogs'
 * buttons write anything (reading, discarding, making the draft). See
 * `commons.document_capture` for the order of the calls.
 *
 * It draws no header. It reports its `title` and its `actions` (none), and
 * each host puts them in its own chrome: the SPA's page
 * (`pages/DocumentCapture.vue`) and the `commons.capture` desk island
 * (`islands/capture.ts`). See `islands/contract.ts`.
 */

defineProps<{
	/** From a desk host, which passes every page its route and query. This
	 *  screen reads neither. */
	route?: string[]
	query?: Record<string, string>
}>()

const emit = defineEmits<{
	title: [title: string | null]
	actions: [actions: PageAction[]]
}>()

emit('title', 'Document Capture')
emit('actions', [])

const STATE_LABELS: Record<
	CaptureState,
	{ label: string; theme: 'gray' | 'blue' | 'amber' | 'red' }
> = {
	received: { label: 'Arriving', theme: 'gray' },
	unread: { label: 'Not read', theme: 'gray' },
	queued: { label: 'Waiting to be read', theme: 'blue' },
	reading: { label: 'Reading', theme: 'blue' },
	done: { label: 'Ready to check', theme: 'amber' },
	failed: { label: 'Reading failed', theme: 'red' },
}

const drafts = useMyDrafts()
const waiting = useWaitingCaptures()
const opener = useOpenCapture()

const uploadKind = ref<CaptureKind>(PURCHASE_INVOICE)

watch(
	() => captureCan.value.kinds,
	(kinds) => {
		if (kinds.length && !kinds.includes(uploadKind.value)) uploadKind.value = kinds[0]
		if (kinds.length) waiting.load()
		if (kinds.includes(PURCHASE_INVOICE)) drafts.load()
	},
	{ immediate: true }
)

/** The scan being read now, from the upload box or from a row read again. */
const reading = reactive<{
	name: string
	pending: string
	busy: boolean
	/** Sending the file, before there is any reading to report on. */
	uploading: boolean
	error: string
	progress: CaptureReadingState | null
}>({ name: '', pending: '', busy: false, uploading: false, error: '', progress: null })

const invoiceOpen = ref(false)
const expenseOpen = ref(false)
const detailsOpen = ref(false)
const invoiceReading = ref<Reading | null>(null)
const expenseReading = ref<ExpenseReading | null>(null)
const detailsRow = ref<CaptureRow | null>(null)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const justCreated = ref('')

function pick() {
	fileInput.value?.click()
}

function onPicked(event: Event) {
	const input = event.target as HTMLInputElement
	const file = input.files?.[0]
	// Cleared so the same file can be chosen again.
	input.value = ''
	if (file) readFile(file)
}

function onDrop(event: DragEvent) {
	dragging.value = false
	const file = event.dataTransfer?.files?.[0]
	if (file && !reading.busy) readFile(file)
}

/** Keep a scan as a capture, then open it: reading is billed, so it waits
 *  for the Read button in that dialog rather than starting here. */
async function readFile(file: File) {
	reading.busy = true
	reading.uploading = true
	reading.pending = file.name
	reading.error = ''
	reading.progress = null
	try {
		const name = await uploadScan(file, uploadKind.value)
		await waiting.load()
		detailsRow.value = waiting.rows.value.find((row) => row.name === name) ?? null
		detailsOpen.value = Boolean(detailsRow.value)
	} catch (error) {
		reading.error = error instanceof Error ? error.message : 'That scan could not be kept.'
	} finally {
		reading.busy = false
		reading.uploading = false
	}
}

/** Wait for a capture's reading, then open its dialog. A failure is shown,
 *  and the capture stays in the list to be read again. */
async function follow(name: string) {
	reading.busy = true
	reading.name = name
	reading.error = ''
	try {
		const result = await waitForReading(name, {
			onProgress: (state) => (reading.progress = state),
			cancelled: () => reading.name !== name,
		})
		showReading(result)
	} catch (error) {
		if (error instanceof ReadingCancelled) return
		reading.error = `${
			error instanceof Error ? error.message : 'That scan could not be read.'
		} The scan is kept in the list below.`
	} finally {
		if (reading.name === name) {
			reading.busy = false
			reading.progress = null
		}
		waiting.load()
	}
}

function showReading(result: Reading | ExpenseReading) {
	if (result.capture.document_type === EXPENSE_CLAIM) {
		expenseReading.value = result as ExpenseReading
		expenseOpen.value = true
	} else {
		invoiceReading.value = result as Reading
		invoiceOpen.value = true
	}
}

async function openRow(row: CaptureRow) {
	if (row.state === 'done') {
		// The same reading again keeps a half-checked draft as it was left.
		const open =
			row.document_type === EXPENSE_CLAIM ? expenseReading.value : invoiceReading.value
		if (open?.capture.name === row.name) {
			showReading(open)
			return
		}
		const result = await opener.submit({ name: row.name })
		if (result) showReading(result)
		else toast.error(opener.error?.message ?? 'That capture could not be opened.')
		return
	}
	detailsRow.value = row
	detailsOpen.value = true
}

function onQueued(name: string) {
	const row = waiting.rows.value.find((one) => one.name === name)
	reading.pending = row?.subject || name
	waiting.load()
	follow(name)
}

function onCreated(name: string) {
	justCreated.value = name
	invoiceReading.value = null
	expenseReading.value = null
	waiting.load()
	if (captureCan.value.invoices) drafts.load()
}

// A closed dialog leaves its capture read and waiting; the list says so.
watch([invoiceOpen, expenseOpen], ([invoice, expense]) => {
	if (!invoice && !expense) waiting.load()
})

// Emailed scans arrive and are read without this page: while any row is
// still arriving or being read, ask again every few seconds.
let timer: ReturnType<typeof setTimeout> | null = null
// Watched by the list itself, which is a new array on every load, so each
// answer that still has one in progress schedules the next.
watch(
	() => waiting.rows.value,
	(rows) => {
		if (timer) clearTimeout(timer)
		const busy = rows.some((row) => ['received', 'queued', 'reading'].includes(row.state))
		timer = busy ? setTimeout(() => waiting.load(), 5000) : null
	}
)
onBeforeUnmount(() => {
	if (timer) clearTimeout(timer)
})
</script>
