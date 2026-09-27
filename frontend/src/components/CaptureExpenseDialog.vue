<!--
  Receipts, scanned, beside the expense claim they become.

  The scan on the left and the claim on the right, laid out like
  `CaptureInvoiceDialog`, and nothing is written until "Send claim". Each
  expense starts from one receipt: its date, what it was for, and the total
  paid as printed. An amount the scan does not show is left blank for the
  claimant, never worked out.

  The claim is the claimant's own, raised by `expense_claim.create` through the
  same `request_expense_claim` the expenses page uses, so the company, currency,
  cost centre and accounts are settled there and not here. The receipt is
  attached to the claim in the same call.

  Outside clicks and Escape do not close it. The close button does, and the
  reading stays on its capture, to be reopened from the page's list.
-->

<template>
	<Dialog v-model:open="open" :dismissible="false" size="7xl" bare>
		<template #default="{ close }">
			<div class="flex h-[calc(100dvh-6rem)] flex-col">
				<header
					class="flex shrink-0 items-start justify-between gap-4 border-b border-outline-gray-1 px-5 py-4"
				>
					<div class="min-w-0">
						<h2 class="text-lg font-semibold text-ink-gray-8">Claim these expenses</h2>
						<p class="mt-0.5 text-p-sm text-ink-gray-5">
							Read from the receipt by {{ reading?.model }}. Check each expense
							against it. Your approver is notified once you send the claim.
						</p>
					</div>
					<Button variant="ghost" icon="lucide-x" aria-label="Close" @click="close" />
				</header>

				<div
					v-if="reading"
					class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,2fr)_minmax(0,3fr)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:grid-rows-1"
				>
					<figure
						class="flex min-h-0 flex-col border-b border-outline-gray-1 bg-surface-gray-1 p-4 lg:border-b-0 lg:border-r"
					>
						<div
							class="min-h-0 flex-1 overflow-auto rounded-4 border border-outline-gray-2 bg-surface-white"
						>
							<iframe
								v-if="isPdf"
								:src="scanUrl"
								class="size-full"
								title="The scanned receipt"
							/>
							<a
								v-else
								:href="scanUrl"
								target="_blank"
								rel="noopener"
								title="Open the scan full size"
							>
								<img
									:src="scanUrl"
									alt="The scanned receipt"
									class="block w-full"
								/>
							</a>
						</div>
						<figcaption class="mt-1 shrink-0 truncate text-p-xs text-ink-gray-5">
							{{ reading.capture.file_name }} · {{ reading.capture.name }} · attached
							to the claim when it is sent
						</figcaption>
					</figure>

					<div class="min-h-0 min-w-0 space-y-6 overflow-y-auto px-5 py-4">
						<div v-if="!reading.extracted.is_receipt" :class="warningBox">
							<p class="text-base-medium text-ink-gray-8">
								This may not be a receipt
							</p>
							<p class="mt-0.5">
								Claude did not read it as one. Check the scan before going on.
							</p>
						</div>
						<div v-if="notMine" :class="warningBox">
							<p class="text-base-medium text-ink-gray-8">
								This receipt is {{ reading.capture.owner }}'s
							</p>
							<p class="mt-0.5">Only they can claim it, as their own expense.</p>
						</div>
						<div v-if="!reading.defaults.employee" :class="warningBox">
							<p class="text-base-medium text-ink-gray-8">
								You have no employee record
							</p>
							<p class="mt-0.5">
								A claim is raised for an employee. Ask HR to link one to your user.
							</p>
						</div>
						<div v-else-if="!expenseTypes.length" :class="warningBox">
							<p class="text-base-medium text-ink-gray-8">
								Nothing to claim against yet
							</p>
							<p class="mt-0.5">
								No expense type has an account set up for your company. Ask
								Accounts to configure one.
							</p>
						</div>
						<div v-if="reading.extracted.notes.length" :class="warningBox">
							<p class="text-base-medium text-ink-gray-8">
								Worth checking against the paper
							</p>
							<!-- Rendered as text. These are the model's words about the scan. -->
							<ul class="mt-1 list-disc space-y-0.5 pl-4">
								<li v-for="(note, index) in reading.extracted.notes" :key="index">
									{{ note }}
								</li>
							</ul>
						</div>

						<section>
							<h3 class="text-base-medium text-ink-gray-8">What you spent</h3>
							<ErrorMessage
								v-if="errors.lines"
								:message="errors.lines"
								class="mt-2"
							/>
							<p
								v-if="
									reading.extracted.currency &&
									reading.defaults.currency &&
									reading.extracted.currency !== reading.defaults.currency
								"
								class="mt-1 text-p-sm text-ink-amber-3"
							>
								The receipt is in {{ reading.extracted.currency }}, and your claims
								are in {{ reading.defaults.currency }}. Enter each amount in
								{{ reading.defaults.currency }}.
							</p>

							<ul class="mt-3 space-y-3">
								<li
									v-for="(line, index) in lines"
									:key="line.key"
									class="rounded-4 border border-outline-gray-1 p-3"
								>
									<div class="flex items-center justify-between">
										<span class="text-p-sm text-ink-gray-5"
											>Expense {{ index + 1 }}</span
										>
										<Button
											variant="ghost"
											theme="red"
											icon="lucide-trash-2"
											:aria-label="`Remove expense ${index + 1}`"
											:disabled="lines.length === 1"
											@click="lines.splice(index, 1)"
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
										<div>
											<BikramDatePicker
												v-model="line.expense_date"
												label="When"
												:max="today"
												:error="errors[`date-${index}`]"
											/>
											<p
												v-if="line.printed"
												class="mt-1 text-p-xs text-ink-gray-5"
											>
												Printed {{ line.printed }}, which is not a date.
												Enter it by hand.
											</p>
										</div>
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
									/>
								</li>
							</ul>

							<div class="mt-3 flex items-center justify-between">
								<span v-if="claimedTotal" class="text-p-sm text-ink-gray-6">
									Claiming
									{{ formatCurrency(claimedTotal, reading.defaults.currency) }}
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
							v-model="remark"
							type="textarea"
							label="Anything else"
							:rows="2"
							placeholder="Optional context for the person settling this."
						/>

						<LinkControl
							v-if="reading.defaults.employee"
							v-model="approver"
							doctype="User"
							label="Approver"
							title-first
							:query="expenseCan.approver_query"
							:filters="{
								employee: reading.defaults.employee,
								doctype: 'Expense Claim',
							}"
							:error="errors.expense_approver"
							description="Set from your employee record. Ask HR if the right person isn't listed."
							:required="expenseCan.approver_mandatory"
						/>
					</div>
				</div>

				<footer
					class="flex shrink-0 items-center justify-end gap-3 border-t border-outline-gray-1 px-5 py-3"
				>
					<ErrorMessage
						v-if="create.error"
						:message="create.error.message"
						class="mr-auto min-w-0"
					/>
					<Button
						variant="solid"
						label="Send claim"
						:loading="busy"
						:disabled="!canSend"
						@click="send(close)"
					/>
				</footer>
			</div>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, Dialog, ErrorMessage, FormControl, toast } from 'frappe-ui'
import BikramDatePicker from './BikramDatePicker.vue'
import LinkControl from './LinkControl.vue'
import { isPdfUrl, useCreateExpenseClaim } from '@/data/capture'
import { expenseLinesFrom, type ExpenseDraftLine, type ExpenseReading } from '@/data/captureRules'
import { expenseCan } from '@/data/requests/expense'
import { formatCurrency } from '@/data/format'
import { user } from '@/data/session'

const props = defineProps<{
	/** The capture's reading. A new one starts a new claim; the same one again
	 *  reopens it as it was left. */
	reading: ExpenseReading | null
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

const today = localToday()

const lines = ref<ExpenseDraftLine[]>([])
const remark = ref('')
const approver = ref<string | null>(null)
const submitAttempted = ref(false)
const busy = ref(false)
const create = useCreateExpenseClaim()

let nextKey = -1

function blankLine(): ExpenseDraftLine {
	const types = expenseTypes.value
	return {
		key: nextKey--,
		expense_date: today,
		expense_type: types.length === 1 ? types[0].name : '',
		description: '',
		amount: null,
		printed: '',
	}
}

watch(
	() => props.reading,
	(reading) => {
		if (!reading) return
		lines.value = expenseLinesFrom(reading, today)
		if (!lines.value.length) lines.value = [blankLine()]
		remark.value = ''
		approver.value = reading.defaults.approver
		submitAttempted.value = false
	},
	{ immediate: true }
)

const scanUrl = computed(() => props.reading?.capture.scan ?? '')
const isPdf = computed(() => isPdfUrl(scanUrl.value))

const expenseTypes = computed(() => props.reading?.defaults.expense_types ?? [])

const typeOptions = computed(() => [
	{ label: 'Select a type', value: '' },
	...expenseTypes.value.map((type) => ({
		label: type.description ? `${type.name} — ${type.description}` : type.name,
		value: type.name,
	})),
])

const amountLabel = computed(() =>
	props.reading?.defaults.currency ? `Amount (${props.reading.defaults.currency})` : 'Amount'
)

const claimedTotal = computed(() =>
	lines.value.reduce((total, line) => total + (Number(line.amount) || 0), 0)
)

/** Receipts are claimed by whoever they belong to, and the server refuses
 *  anybody else. Said here first. */
const notMine = computed(() =>
	Boolean(props.reading && props.reading.capture.owner !== user.value.name)
)

const canSend = computed(
	() =>
		Boolean(props.reading?.defaults.employee) &&
		expenseTypes.value.length > 0 &&
		!notMine.value
)

const problems = computed(() => {
	const found: Record<string, string> = {}
	if (!lines.value.length) found.lines = 'A claim needs at least one expense.'
	lines.value.forEach((line, index) => {
		if (!line.expense_type) found[`type-${index}`] = 'Pick a type'
		if (!Number(line.amount)) found[`amount-${index}`] = 'Enter what it cost'
		else if (Number(line.amount) < 0) found[`amount-${index}`] = 'Amounts cannot be negative'
		if (line.expense_date && line.expense_date > today)
			found[`date-${index}`] = "That's in the future"
	})
	if (expenseCan.value.approver_mandatory && !approver.value)
		found.expense_approver = 'Pick an approver'
	return found
})

const errors = computed(() => (submitAttempted.value ? problems.value : {}))

function addLine() {
	lines.value.push(blankLine())
}

async function send(close: () => void) {
	submitAttempted.value = true
	if (!props.reading || Object.keys(problems.value).length) return
	busy.value = true
	try {
		const created = await create.submit({
			capture: props.reading.capture.name,
			claim: {
				doctype: 'Expense Claim',
				expense_approver: approver.value || undefined,
				remark: remark.value || undefined,
				expenses: lines.value.map((line) => ({
					expense_date: line.expense_date,
					expense_type: line.expense_type,
					description: line.description,
					amount: Number(line.amount),
				})),
			},
		})
		// `submit` resolves null on failure; the reason renders in the footer.
		if (!created) return
		toast.success(`Expenses claimed in ${created.name}, with the receipt attached`)
		emit('created', created.name)
		close()
	} finally {
		busy.value = false
	}
}
</script>
