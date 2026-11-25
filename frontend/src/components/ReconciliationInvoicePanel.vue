<!--
  Book a deposit as payments of Sales Invoices, and reconcile them, in one Save.

  The loan tab's way, for invoices. The desk way is to note the amount and
  date, find whose payment it was, open the invoice, Create > Payment, fix the
  date, the bank and the amount, submit, come back to the reconciliation tool,
  find the line again and match it. Here the panel says whose payment it
  probably is and why, and books exactly the Payment Entry the invoice's own
  Create > Payment makes (`commons.banking.invoice_payments.create_invoice_payments`).

  Everything here is a draft until the button at the bottom is pressed.
-->

<template>
	<div class="space-y-4">
		<!-- A payment already on the books is a better answer than a new one. -->
		<div
			v-if="existing.length"
			class="flex items-start gap-2 rounded-4 border border-outline-amber-3 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8"
		>
			<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0 text-ink-amber-7" />
			<div class="min-w-0 flex-1">
				{{ existing.length === 1 ? 'A payment' : `${existing.length} payments` }} of
				exactly this amount {{ existing.length === 1 ? 'is' : 'are' }} already booked and
				not yet matched to a statement line ({{
					existing
						.map((row) => `${row.name}, ${row.party_name || row.party}`)
						.join('; ')
				}}). Match {{ existing.length === 1 ? 'it' : 'one' }} instead of booking another.
			</div>
			<Button size="sm" variant="subtle" label="Match" @click="emit('switch', 'match')" />
		</div>

		<section v-if="suggestions.length">
			<h3 class="mb-1.5 text-p-sm font-medium text-ink-gray-7">Likely invoices</h3>
			<ul class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2">
				<li
					v-for="suggestion in suggestions.slice(0, 4)"
					:key="suggestion.invoice"
					class="flex items-center gap-3 px-3 py-2"
				>
					<div class="min-w-0 flex-1">
						<div class="truncate text-p-base text-ink-gray-8">
							{{ customerOf(suggestion.invoice) }}
							<span class="text-p-sm text-ink-gray-5"
								>· <InvoiceLink :name="suggestion.invoice" /><template
									v-if="invoiceByName.get(suggestion.invoice)?.due_date"
								>
									· due
									{{
										formatDate(
											invoiceByName.get(suggestion.invoice)!.due_date!
										)
									}}</template
								></span
							>
						</div>
						<div class="mt-0.5 flex flex-wrap gap-1">
							<Badge
								v-for="reason in suggestion.reasons"
								:key="reason"
								:label="reason"
								theme="blue"
								size="sm"
							/>
						</div>
					</div>
					<div class="shrink-0 text-right text-p-sm tabular-nums text-ink-gray-6">
						{{ formatExact(outstanding[suggestion.invoice], transaction.currency) }}
						<div class="text-p-xs text-ink-gray-5">outstanding</div>
					</div>
					<Button
						size="sm"
						:variant="isChosen(suggestion.invoice) ? 'ghost' : 'subtle'"
						:label="isChosen(suggestion.invoice) ? 'Added' : 'Add'"
						:disabled="isChosen(suggestion.invoice) || busy"
						@click="addLine(suggestion.invoice)"
					/>
				</li>
			</ul>
		</section>

		<section>
			<h3 class="mb-1.5 text-p-sm font-medium text-ink-gray-7">
				{{ suggestions.length ? 'Or find an invoice' : 'Find the invoice' }}
			</h3>
			<TextInput
				v-model="query"
				placeholder="Customer's name or invoice number"
				:disabled="busy"
			>
				<template #prefix><span class="lucide-search size-4 text-ink-gray-5" /></template>
			</TextInput>
			<ul
				v-if="query.trim()"
				class="mt-1.5 max-h-56 divide-y divide-outline-gray-1 overflow-y-auto rounded-4 border border-outline-gray-2"
			>
				<li
					v-for="invoice in searchResults"
					:key="invoice.name"
					class="flex items-center gap-3 px-3 py-1.5"
				>
					<div class="min-w-0 flex-1 truncate text-p-sm text-ink-gray-8">
						{{ invoice.customer_name || invoice.customer }}
						<span class="text-ink-gray-5"
							>· <InvoiceLink :name="invoice.name" /><template
								v-if="invoice.due_date"
							>
								· due {{ formatDate(invoice.due_date) }}</template
							></span
						>
					</div>
					<span class="shrink-0 text-p-sm tabular-nums text-ink-gray-6">
						{{ formatExact(invoice.outstanding_amount, transaction.currency) }}
					</span>
					<Button
						size="sm"
						variant="ghost"
						:label="isChosen(invoice.name) ? 'Added' : 'Add'"
						:disabled="isChosen(invoice.name) || busy"
						@click="addLine(invoice.name)"
					/>
				</li>
				<li v-if="!searchResults.length" class="px-3 py-2 text-p-sm text-ink-gray-5">
					No open invoice matches “{{ query.trim() }}”
				</li>
			</ul>
			<p v-else-if="!book.invoices.length" class="mt-1.5 text-p-sm text-ink-gray-5">
				There are no open sales invoices for this bank account's company.
			</p>
		</section>

		<section v-if="lines.length">
			<h3 class="mb-1.5 text-p-sm font-medium text-ink-gray-7">Payments to book</h3>
			<ul class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2">
				<li
					v-for="(line, index) in lines"
					:key="line.invoice"
					class="flex items-center gap-3 px-3 py-2"
				>
					<div class="min-w-0 flex-1">
						<div class="truncate text-p-base text-ink-gray-8">
							{{ customerOf(line.invoice) }}
						</div>
						<div class="text-p-xs text-ink-gray-5">
							<InvoiceLink :name="line.invoice" /> ·
							{{ formatExact(outstanding[line.invoice], transaction.currency) }}
							outstanding
						</div>
					</div>
					<div class="w-36 shrink-0">
						<TextInput
							v-model.number="line.amount"
							type="number"
							min="0"
							step="0.01"
							:disabled="busy"
							:aria-label="`Amount paid on ${line.invoice}`"
						/>
					</div>
					<Button
						size="sm"
						variant="ghost"
						icon="lucide-x"
						:aria-label="`Remove ${line.invoice}`"
						:disabled="busy"
						@click="lines.splice(index, 1)"
					/>
				</li>
			</ul>

			<div class="mt-3 grid gap-3 sm:grid-cols-2">
				<FormControl
					v-model="reference"
					label="Reference"
					:disabled="busy"
					description="Kept on each payment entry. The statement's own, or its description."
				/>
				<div class="text-p-sm text-ink-gray-6 sm:pt-6">
					<div class="flex justify-between tabular-nums">
						<span>Deposit left to account for</span>
						<span>{{
							formatExact(transaction.unallocated_amount, transaction.currency)
						}}</span>
					</div>
					<div class="flex justify-between tabular-nums">
						<span>These payments</span>
						<span>{{ formatExact(check.total, transaction.currency) }}</span>
					</div>
					<div
						class="flex justify-between font-medium tabular-nums"
						:class="check.remaining < 0 ? 'text-ink-red-7' : 'text-ink-gray-8'"
					>
						<span>Left after booking</span>
						<span>{{ formatExact(check.remaining, transaction.currency) }}</span>
					</div>
				</div>
			</div>

			<p v-if="customers > 1" class="mt-2 text-p-sm text-ink-gray-6">
				One payment entry per customer: {{ customers }} in all.
			</p>
		</section>

		<ErrorMessage v-if="problem" :message="problem" />

		<div
			class="flex flex-wrap items-center justify-between gap-2 border-t border-outline-gray-1 pt-3"
		>
			<p class="text-p-xs text-ink-gray-5">
				Posted to the ledger on {{ formatDate(transaction.date) }}, the day the money
				arrived.
			</p>
			<div class="flex gap-2">
				<Button
					v-if="lines.length"
					variant="ghost"
					label="Clear"
					:disabled="busy"
					@click="reset"
				/>
				<Button
					variant="subtle"
					:label="customers > 1 ? `Make ${customers} drafts` : 'Make draft'"
					:loading="busy && drafting"
					:disabled="!lines.length || check.errors.length > 0 || (busy && !drafting)"
					title="Create the payment entries as drafts, without posting them or matching them to this line"
					@click="save(true)"
				/>
				<Button
					variant="solid"
					:label="
						customers > 1
							? `Book ${customers} payments and reconcile`
							: 'Book payment and reconcile'
					"
					:loading="busy && !drafting"
					:disabled="!lines.length || check.errors.length > 0 || (busy && drafting)"
					:title="check.errors.join(' · ')"
					@click="save(false)"
				/>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, reactive, ref, watch } from 'vue'
import { Badge, Button, ErrorMessage, FormControl, TextInput } from 'frappe-ui'
import { formatDate, formatExact, pluralise } from '@/data/format'
import { deskUrl, useCreateInvoicePayments, write, type InvoiceBook } from '@/data/reconciliation'
import {
	checkInvoiceSplit,
	type InvoiceLine,
	type InvoiceSuggestion,
} from '@/data/invoiceMatching'
import {
	money,
	proposeAmount,
	proposedReference,
	type TransactionRow,
} from '@/data/reconciliationRules'
import { toastWithLinks } from '@/data/toastLinks'

const props = defineProps<{
	transaction: TransactionRow
	book: InvoiceBook
	suggestions: InvoiceSuggestion[]
}>()

const emit = defineEmits<{
	/** Something was written; carries the line's new unallocated amount. */
	done: [unallocated: number]
	dirty: [dirty: boolean]
	switch: [tab: 'match']
	/** Drafts were created; nothing was posted or matched. */
	drafted: []
}>()

/** An invoice's number, opening it in the desk in a new tab. */
const InvoiceLink = defineComponent({
	props: { name: { type: String, required: true } },
	setup: (linkProps) => () =>
		h(
			'a',
			{
				href: deskUrl('Sales Invoice', linkProps.name),
				target: '_blank',
				class: 'inline-flex items-center gap-0.5 hover:text-ink-gray-8 hover:underline',
				title: `Open ${linkProps.name} in a new tab`,
				onClick: (event: Event) => event.stopPropagation(),
			},
			[linkProps.name, h('span', { class: 'lucide-external-link size-3' })]
		),
})

const create = useCreateInvoicePayments()
const lines = reactive<InvoiceLine[]>([])
const reference = ref('')
const query = ref('')
const busy = ref(false)
const drafting = ref(false)
const problem = ref('')

const invoiceByName = computed(
	() => new Map(props.book.invoices.map((invoice) => [invoice.name, invoice]))
)

const outstanding = computed<Record<string, number>>(() =>
	Object.fromEntries(
		props.book.invoices.map((invoice) => [invoice.name, money(invoice.outstanding_amount)])
	)
)

function customerOf(name: string) {
	const invoice = invoiceByName.value.get(name)
	return invoice ? invoice.customer_name || invoice.customer : name
}

/** How many payment entries the lines make: one per customer, as the server
 *  groups them (it also splits a customer's invoices by receivable account
 *  and department, which on most sites is the same thing). */
const customers = computed(
	() =>
		new Set(
			lines.map((line) => invoiceByName.value.get(line.invoice)?.customer ?? line.invoice)
		).size
)

const existing = computed(() =>
	props.book.uncleared.filter(
		(row) => money(row.paid_amount) === money(props.transaction.unallocated_amount)
	)
)

function isChosen(invoice: string) {
	return lines.some((line) => line.invoice === invoice)
}

function addLine(invoice: string) {
	if (isChosen(invoice)) return
	const left = money(props.transaction.unallocated_amount - check.value.total)
	lines.push({ invoice, amount: proposeAmount(left, outstanding.value[invoice] ?? 0) })
	query.value = ''
}

const searchResults = computed(() => {
	const words = query.value.trim().toLowerCase().split(/\s+/).filter(Boolean)
	if (!words.length) return []
	return props.book.invoices
		.filter((invoice) => {
			const haystack = `${invoice.name} ${invoice.customer} ${
				invoice.customer_name ?? ''
			}`.toLowerCase()
			return words.every((word) => haystack.includes(word))
		})
		.slice(0, 20)
})

const check = computed(() =>
	checkInvoiceSplit(lines, props.transaction.unallocated_amount, outstanding.value)
)

function reset() {
	lines.splice(0, lines.length)
	reference.value = proposedReference(props.transaction)
	query.value = ''
	problem.value = ''
}

// A strong suggestion that nothing else comes close to is put into the draft,
// as the loan tab does. Still only a draft.
watch(
	() => props.transaction.name,
	() => {
		reset()
		const [best, second] = props.suggestions
		if (best?.strong && (!second || best.score - second.score >= 3)) addLine(best.invoice)
	},
	{ immediate: true }
)

const dirty = computed(() => lines.length > 0)
watch(dirty, (value) => emit('dirty', value), { immediate: true })

/** Book the lines, or with `draft` leave them as drafts: inserted and
 *  checked, but not submitted and not matched. */
async function save(draft: boolean) {
	if (!lines.length || check.value.errors.length) return
	busy.value = true
	drafting.value = draft
	problem.value = ''
	try {
		const done = await write(create, {
			bank_transaction: props.transaction.name,
			payments: lines.map((line) => ({ invoice: line.invoice, amount: money(line.amount) })),
			reference_number: reference.value,
			draft,
		})
		if (!done.ok || !done.data) {
			problem.value = done.error?.message || 'The payments could not be booked'
			return
		}
		const links = done.data.payment_entries.map((name) => ({ doctype: 'Payment Entry', name }))
		lines.splice(0, lines.length)
		if (draft) {
			toastWithLinks(
				`${pluralise(
					links.length,
					'draft payment entry',
					'draft payment entries'
				)} created, not yet posted or matched:`,
				links
			)
			emit('drafted')
			return
		}
		toastWithLinks(
			`${pluralise(
				links.length,
				'payment entry',
				'payment entries'
			)} booked and reconciled:`,
			links
		)
		emit('done', done.data.unallocated_amount)
	} finally {
		busy.value = false
	}
}
</script>
