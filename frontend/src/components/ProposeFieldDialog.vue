<template>
	<!-- No `message` prop: it only renders as the default slot's fallback, so a
       dialog with content of its own has to place that line itself. -->
	<Dialog v-model:open="open" :title="field ? `Change ${field.label}` : ''" :actions="actions">
		<div v-if="field" class="space-y-4">
			<p class="text-p-base text-ink-gray-6">
				This goes to HR as a proposal. Nothing on your record changes until someone
				approves it.
			</p>

			<!-- What it says now, beside what it would say. One field is small enough
           to show the whole before-and-after without a diff block, and seeing
           the current value is half of deciding whether it is wrong. -->
			<div class="rounded-4 bg-surface-gray-2 px-3 py-2">
				<div class="text-p-sm text-ink-gray-5">Currently</div>
				<div
					class="mt-0.5 text-p-base"
					:class="[
						field.type === 'textarea' ? 'whitespace-pre-line' : '',
						isFieldFilled(current) ? 'text-ink-gray-8' : 'text-ink-gray-4',
					]"
				>
					{{ currentLabel }}
				</div>
			</div>

			<EmployeeField v-model="draft" :field="field" :error="error" />

			<FormControl
				v-model="reason"
				type="textarea"
				label="Reason"
				:rows="2"
				placeholder="Optional, but it helps HR decide — a move, a new number, a spelling to fix."
			/>

			<!-- Raising a second request for a field already in the queue is not
           refused -- HR may well want the newer answer -- but it is worth
           knowing you are about to do it. -->
			<Alert
				v-if="alreadyPending !== undefined"
				theme="amber"
				title="Already waiting on review"
				:description="`You've asked for this to become ${displayValue(
					alreadyPending
				)}. HR hasn't decided that yet, and sending this adds a second request.`"
			/>

			<ErrorMessage v-if="request.error" :message="request.error.message" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Alert, Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import EmployeeField from './EmployeeField.vue'
import { displayValue, recordType, useRequestProfileChange, type MyProfile } from '@/data/profile'
import { isFieldFilled, type EmployeeField as Field } from '@/data/employeeFields'
import { formatDate } from '@/data/format'

const props = defineProps<{
	profile: MyProfile
	/** The field being proposed against, or null when nothing is. Held as one
	 *  nullable prop rather than a field plus a flag, so the dialog cannot render
	 *  half a question. */
	field: Field | null
	/** Proposed values from open requests, by fieldname — see `MyProfile.vue`. */
	pending: Record<string, string | null>
}>()

const emit = defineEmits<{ close: []; created: [name: string] }>()

const request = useRequestProfileChange()

const open = computed({
	get: () => props.field !== null,
	set: (isOpen: boolean) => {
		if (!isOpen) emit('close')
	},
})

const current = computed(() =>
	props.field ? (props.profile as Record<string, any>)[props.field.fieldname] : null
)

const currentLabel = computed(() => {
	if (!props.field) return ''
	if (!isFieldFilled(current.value)) return 'Not set'
	return props.field.type === 'date'
		? formatDate(current.value as string)
		: displayValue(current.value)
})

// The form edits a draft seeded from the record, never the record: this dialog
// must not be able to write to the employee at all, and a draft makes that
// structural rather than a rule someone has to remember.
// Declared before the watch below, and that order is load-bearing: the watch is
// `immediate`, so it runs while setup is still executing and writes to both of
// these. Below that point they are consts in their temporal dead zone, and the
// component throws on open rather than misbehaving later.
const reason = ref('')
const submitAttempted = ref(false)

const draft = ref<unknown>('')

// Seeded on open rather than on mount -- the dialog outlives any one field, so
// the next field opened has to start from its own value, not the last one's.
watch(
	() => props.field?.fieldname,
	() => {
		draft.value = current.value ?? ''
		reason.value = ''
		submitAttempted.value = false
		request.reset()
	},
	{ immediate: true }
)

// Frappe stores an empty field as '' or null and the form only ever produces
// '', so treat the two as equal rather than as a change.
const changed = computed(() => {
	if (!props.field) return false
	if (!isFieldFilled(current.value) && !isFieldFilled(draft.value)) return false
	return String(current.value ?? '') !== String(draft.value ?? '')
})

// Only after a press: telling someone they have changed nothing before they
// have touched anything is noise.
const error = computed(() =>
	submitAttempted.value && !changed.value ? 'This is the same as the current value' : undefined
)

const alreadyPending = computed(() =>
	props.field ? props.pending[props.field.fieldname] : undefined
)

async function send() {
	submitAttempted.value = true
	if (!props.field || !changed.value) return

	const created = await request.submit({
		doctype: recordType,
		doc: JSON.stringify({
			reason: reason.value,
			// `current_value` is deliberately not sent. The server captures it from
			// the employee record, so a request cannot state a "before" that was
			// never true.
			changes: [
				{
					fieldname: props.field.fieldname,
					proposed_value: draft.value,
				},
			],
		}),
	})
	// `submit` resolves null on failure; the reason renders inline.
	if (!created) return
	toast.success('Sent to HR for review')
	emit('created', created.name)
	emit('close')
}

const actions = computed<DialogAction[]>(() => [
	{
		label: 'Send to HR',
		variant: 'solid',
		loading: request.loading,
		onClick: () => send(),
	},
])
</script>
