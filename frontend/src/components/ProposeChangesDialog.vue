<template>
	<!-- No `message` prop: it only renders as the default slot's fallback, so a
       dialog with content of its own has to place that line itself. -->
	<Dialog
		v-model:open="open"
		title="Propose changes"
		:actions="actions"
		:options="{ size: '2xl' }"
	>
		<div class="space-y-5">
			<p class="text-p-base text-ink-gray-6">
				Edit what's wrong and send it to HR. Nothing changes on your record until someone
				approves it.
			</p>

			<!-- Only the fields the server said it would accept. The rest of the
           profile is HR's to change -- a department or a joining date is a
           decision somebody made, not a detail anyone can correct. -->
			<div class="space-y-6">
				<FormSection
					v-for="section in sections"
					:key="section.title"
					:section="section"
					:doc="draft"
				/>
			</div>

			<FormControl
				v-model="reason"
				type="textarea"
				label="Reason"
				:rows="2"
				placeholder="Optional, but it helps HR decide — a move, a new number, a spelling to fix."
			/>

			<!-- What is actually being asked for, in the same before-and-after the
           reviewer will see. A form of filled boxes does not show that; the
           whole content of the request is the diff. -->
			<div v-if="changed.length" class="rounded-4 bg-surface-gray-2 px-3 py-2.5">
				<div class="text-p-sm text-ink-gray-6">
					{{ pluralise(changed.length, 'change') }} to propose
				</div>
				<ChangeDiff :changes="changed" class="mt-1.5" />
			</div>

			<!-- Raising a second request for a field already in the queue is not
           refused -- HR may well want the newer answer -- but it is worth
           knowing you are about to do it. -->
			<Alert
				v-if="alreadyPending.length"
				theme="amber"
				title="Already waiting on review"
				:description="`${alreadyPending.join(', ')} ${
					alreadyPending.length === 1 ? 'is' : 'are'
				} in an earlier request that HR hasn't decided yet. Sending this adds a second one.`"
			/>

			<ErrorMessage v-if="request.error" :message="request.error.message" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Alert, Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import ChangeDiff from './ChangeDiff.vue'
import FormSection from './FormSection.vue'
import {
	profileCan,
	recordType,
	useRequestProfileChange,
	type MyProfile,
	type ProfileChangeRow,
} from '@/data/profile'
import { allEmployeeFields, employeeSections, isFieldFilled } from '@/data/employeeFields'
import { pluralise } from '@/data/format'

const props = defineProps<{
	profile: MyProfile
	/** Proposed values from open requests, by fieldname — see `MyProfile.vue`. */
	pending: Record<string, string | null>
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ created: [name: string] }>()

const request = useRequestProfileChange()

/**
 * The fields this form offers: the ones the server will accept a proposal for,
 * intersected with the ones `employeeFields.ts` knows how to draw.
 *
 * The intersection rather than either list alone. Taking the server's list on
 * its own would mean drawing a control for a field this app has no definition
 * of; taking the frontend's would mean collecting values the save then refuses.
 */
const sections = computed(() =>
	employeeSections
		.map((section) => ({
			...section,
			fields: section.fields.filter((field) =>
				profileCan.value.proposable.includes(field.fieldname)
			),
		}))
		.filter((section) => section.fields.length > 0)
)

const offeredFields = computed(() => sections.value.flatMap((section) => section.fields))

// The form edits a draft seeded from the record, not the record itself: this
// dialog must not be able to write to the employee at all, and a draft makes
// that structural rather than a rule someone has to remember.
const draft = reactive<Record<string, any>>({})
const reason = ref('')

function resetDraft() {
	for (const field of allEmployeeFields) {
		draft[field.fieldname] = (props.profile as Record<string, any>)[field.fieldname] ?? ''
	}
	reason.value = ''
}

/** Only the fields that actually differ. An unchanged field is not a proposal,
 *  and the server refuses a request that asks for nothing. */
const changed = computed<ProfileChangeRow[]>(() =>
	offeredFields.value
		.map((field) => ({
			fieldname: field.fieldname,
			label: field.label,
			current_value: (props.profile as Record<string, any>)[field.fieldname] ?? null,
			proposed_value: String(draft[field.fieldname] ?? ''),
		}))
		.filter((row) => {
			// Frappe stores an empty field as '' or null and the form only ever
			// produces '', so treat the two as equal rather than as a change.
			if (!isFieldFilled(row.current_value) && !isFieldFilled(row.proposed_value)) {
				return false
			}
			return String(row.current_value ?? '') !== String(row.proposed_value ?? '')
		})
)

const alreadyPending = computed(() =>
	changed.value
		.filter((row) => props.pending[row.fieldname] !== undefined)
		.map((row) => row.label)
)

// A dialog that keeps the last attempt's edits is a trap: the next one opens
// half-filled with answers the employee has already sent.
watch(open, (isOpen) => {
	if (isOpen) resetDraft()
})

// Re-seed when the record itself changes underneath -- an approval elsewhere,
// or this employee's own request being applied.
watch(() => props.profile.modified, resetDraft, { immediate: true })

async function send(close: () => void) {
	if (!changed.value.length) return
	const created = await request.submit({
		doctype: recordType,
		doc: JSON.stringify({
			reason: reason.value,
			// `current_value` is deliberately not sent. The server captures it from
			// the employee record, so a request cannot state a "before" that was
			// never true.
			changes: changed.value.map((row) => ({
				fieldname: row.fieldname,
				proposed_value: row.proposed_value,
			})),
		}),
	})
	// `submit` resolves null on failure; the reason renders inline.
	if (!created) return
	toast.success('Sent to HR for review')
	emit('created', created.name)
	close()
}

const actions = computed<DialogAction[]>(() => [
	{
		label: changed.value.length ? `Send ${pluralise(changed.value.length, 'change')}` : 'Send',
		variant: 'solid',
		// Nothing to send is a disabled button rather than an error on press: the
		// diff above it already says why.
		disabled: !changed.value.length,
		loading: request.loading,
		onClick: ({ close }) => send(close),
	},
])
</script>
