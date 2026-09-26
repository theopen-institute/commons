<template>
	<Dialog
		v-model:open="open"
		:title="props.request ? 'Edit Procurement Request' : 'New Procurement Request'"
		:actions="actions"
		size="3xl"
	>
		<div class="space-y-4">
			<div class="grid gap-4 sm:grid-cols-2">
				<BikramDatePicker v-model="form.schedule_date" label="Needed by" required />
				<LinkControl
					v-model="form.department"
					doctype="Department"
					label="Department"
					required
				/>
			</div>

			<section>
				<div>
					<h3 class="text-base-medium text-ink-gray-8">What you need</h3>
				</div>

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

						<FormControl
							v-model="line.item_name"
							class="mt-2"
							type="text"
							label="What is it"
							placeholder="e.g. Brass fittings, 12mm"
							required
						/>

						<!-- `withScheme` adds the scheme to a bare host on the way out,
                 so a link pasted from the address bar is accepted as typed. -->
						<FormControl
							v-model="line.reference_url"
							class="mt-3"
							type="text"
							label="Link to Item"
							placeholder="Optional — a product page, quote or spec"
						/>

						<div class="mt-3 grid gap-3 sm:grid-cols-3">
							<FormControl
								v-model.number="line.qty"
								type="number"
								label="Quantity"
								min="0"
							/>
							<LinkControl v-model="line.uom" doctype="UOM" label="Unit" />
							<FormControl
								v-model.number="line.estimated_rate"
								type="number"
								:label="priceLabel"
								min="0"
							/>
						</div>
					</li>
				</ul>

				<div class="mt-3 flex justify-end">
					<Button
						variant="subtle"
						icon-left="lucide-plus"
						label="Add line"
						@click="addLine"
					/>
				</div>
			</section>

			<FormControl
				v-model="form.justification"
				type="textarea"
				label="Why it's needed"
				:rows="3"
				placeholder="Optional context for the people reviewing this request."
			/>

			<LinkControl
				v-model="form.approver"
				doctype="User"
				label="Approver"
				title-first
				:query="procurementCan.approver_query"
				required
			/>

			<ErrorMessage v-if="saveRequest.error" :message="saveRequest.error.message" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { Button, Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import BikramDatePicker from './BikramDatePicker.vue'
import LinkControl from './LinkControl.vue'
import {
	procurementCan,
	procurementWorkflow,
	useProcurementRequestDefaults,
	useSaveProcurementRequest,
	workflowActionButtons,
	type AvailableWorkflowAction,
	type ProcurementRequestItemRow,
	type ProcurementRequestRow,
} from '@/data/requests/procurement'
import { withScheme } from '@/data/format'

const props = defineProps<{
	request?: ProcurementRequestRow | null
	lines?: ProcurementRequestItemRow[]
	workflowActions?: AvailableWorkflowAction[]
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ created: [name: string] }>()

interface LineForm {
	/** Local only, for `v-for` — rows have no name until the server makes one. */
	key: number
	name?: string
	item_code?: string | null
	item_name: string
	reference_url: string
	description?: string | null
	qty: number
	uom: string
	estimated_rate: number
	verified_rate?: number
}

interface RequestForm {
	/** Only ever filled by the insert's response — never posted. */
	name?: string
	company?: string
	schedule_date: string
	department: string
	approver: string
	justification?: string | null
	items: LineForm[]
}

// Fetched when the form opens rather than with the section's permissions: they
// are four queries for a blank request, and most visits never draw one.
const defaults = useProcurementRequestDefaults()

let nextKey = 0

function blankLine(fill = defaults.data): LineForm {
	return {
		key: nextKey++,
		item_name: '',
		reference_url: '',
		qty: 1,
		uom: fill?.uom ?? '',
		estimated_rate: 0,
	}
}

function lineForms(lines: ProcurementRequestItemRow[]): LineForm[] {
	return lines.map((line) => ({
		key: nextKey++,
		name: line.name,
		item_code: line.item_code,
		item_name: line.item_name ?? '',
		reference_url: line.reference_url ?? '',
		description: line.description,
		qty: line.qty,
		uom: line.uom,
		estimated_rate: line.estimated_rate,
		verified_rate: line.verified_rate,
	}))
}

function blankForm(fill = defaults.data): RequestForm {
	if (props.request) {
		return {
			name: props.request.name,
			company: props.request.company,
			schedule_date: props.request.schedule_date ?? '',
			department: props.request.department ?? '',
			approver: props.request.approver ?? '',
			justification: props.request.justification,
			items: lineForms(props.lines ?? []),
		}
	}
	return {
		// Cleared explicitly: the form is refilled with `Object.assign`, which
		// would otherwise carry the last edited request's name and reason into a
		// new one, and the save would then update that request instead.
		name: undefined,
		justification: null,
		// Omitted rather than guessed when the server had no answer: Frappe then
		// applies the user's own default, and says so if there isn't one.
		company: fill?.company ?? undefined,
		schedule_date: '',
		department: fill?.department ?? '',
		// Workflow state is deliberately absent. Frappe applies the doctype or
		// active Workflow's initial value.
		approver: fill?.approver ?? '',
		items: [blankLine(fill)],
	}
}

const form = reactive<RequestForm>(blankForm())
const saveRequest = useSaveProcurementRequest()

const currency = computed(() => defaults.data?.currency ?? null)

// The code, not a symbol: the company currency can be one the viewer's locale
// has no symbol for, and a bare number is the thing an approver misreads.
const priceLabel = computed(() =>
	currency.value ? `Estimated price each (${currency.value})` : 'Estimated price each',
)

function addLine() {
	form.items.push(blankLine())
}

// Built once per open, and never rebuilt while it stays open. Rebuilding on
// every change to the props wiped what the user had typed: the parent hands
// over a fresh `lines` array on each render, and `request` is a row in a list
// that reloads under the open dialog.
//
// The defaults are the one thing worth taking late, and they only ever fill a
// field that is still blank — someone who has already picked a department
// while they loaded keeps it.
let awaitingDefaults = false
/** An edit opened before its lines were in — see the watch on `lines`. */
let awaitingLines = false

// Fresh on every open: a user's default company or department approver can have
// changed since the section was loaded, and this is the moment it matters.
watch(open, (isOpen) => {
	awaitingDefaults = isOpen && !props.request
	awaitingLines = isOpen && !!props.request && !props.lines?.length
	if (!isOpen) return
	// Without the last open's defaults: they are about to be replaced, and a
	// field filled from them would then look typed and keep the stale value.
	Object.assign(form, blankForm(null))
	defaults.reload()
})

watch(
	() => defaults.data,
	(fill) => {
		if (!open.value || !awaitingDefaults || !fill) return
		awaitingDefaults = false
		form.company ??= fill.company ?? undefined
		form.department ||= fill.department ?? ''
		form.approver ||= fill.approver ?? ''
		for (const line of form.items) line.uom ||= fill.uom ?? ''
	},
)

// The other late arrival: an edited request's lines, when the list's line
// query was still out as it opened. Taken once, and only into an empty table,
// so it can never replace a line someone has typed — or bring back one they
// removed.
watch(
	() => props.lines,
	(lines) => {
		if (!open.value || !awaitingLines || !lines?.length) return
		awaitingLines = false
		if (!form.items.length) form.items = lineForms(lines)
	},
)

function requestDocument() {
	return {
		doctype: 'Procurement Request',
		...form,
		items: form.items.map(({ key: _key, ...line }) => ({
			...line,
			// On the way out rather than as it is typed: rewriting the field under
			// the cursor fights whoever is still halfway through pasting into it.
			reference_url: withScheme(line.reference_url),
		})),
	}
}

async function save(close: () => void, action?: string) {
	try {
		const saved = await saveRequest.submit({
			doc: JSON.stringify(requestDocument()),
			...(action ? { action } : {}),
		})
		if (!saved) return
		toast.success(
			action ? `${action} applied` : props.request ? 'Changes saved' : 'Draft saved',
		)
		emit('created', saved.name!)
		close()
	} catch {
		// `saveRequest.error` renders the server's reason inline — a missing
		// company or an unknown unit is worth reading in full.
	}
}

const actions = computed<DialogAction[]>(() => {
	const saveDraft: DialogAction = {
		label: props.request ? 'Save changes' : 'Save draft',
		variant: 'subtle',
		onClick: ({ close }) => save(close),
	}
	const available = props.request
		? (props.workflowActions ?? [])
		: (procurementWorkflow.value?.initial_actions ?? [])
	const workflowActions = workflowActionButtons(
		available,
		procurementWorkflow.value,
	).map((button): DialogAction => ({
		label: button.label,
		variant: button.variant,
		theme: button.theme,
		// The action's own name, not the button's label. They are the same string
		// today; the label is what a site could rename, and `apply_workflow` would
		// then be asked for a transition the workflow has never heard of.
		onClick: ({ close }) => save(close, button.action.action),
	}))
	return [saveDraft, ...workflowActions]
})
</script>
