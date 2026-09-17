<template>
	<Dialog
		v-model:open="open"
		:title="`New ${(label || '').toLowerCase()}`"
		:actions="actions"
		:options="{ size: '2xl' }"
	>
		<div class="space-y-4">
			<p class="text-p-base text-ink-gray-6">
				This goes for review as a proposal. Nothing is created until someone approves it.
			</p>

			<!-- Only the fields the server would accept. A record proposed here can
			     set exactly what an existing one could have corrected, which is what
			     stops this being a way around the allowlist. -->
			<div class="grid gap-4 sm:grid-cols-2">
				<RecordFieldControl
					v-for="field in fields"
					:key="field.fieldname"
					v-model="draft[field.fieldname]"
					:field="field"
					:class="field.type === 'textarea' ? 'sm:col-span-2' : ''"
				/>
			</div>

			<FormControl
				v-model="reason"
				type="textarea"
				label="Reason"
				:rows="2"
				placeholder="Optional — why this is needed."
			/>

			<ErrorMessage v-if="error" :message="error" />
			<ErrorMessage v-if="request.error" :message="request.error.message" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import RecordFieldControl from './RecordFieldControl.vue'
import { isFilled, useRaiseRequest, type RecordField } from '@/data/selfService'

const props = defineProps<{
	doctype: string
	label: string
	/** The proposable fields, which are the ones a new record may set. */
	fields: RecordField[]
}>()

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ created: [name: string] }>()

const request = useRaiseRequest()
const draft = reactive<Record<string, unknown>>({})
const reason = ref('')
const attempted = ref(false)

// Cleared on open rather than on close: a dialog that keeps the last attempt's
// values offers them again as if they had been saved.
watch(open, (isOpen) => {
	if (!isOpen) return
	for (const field of props.fields) draft[field.fieldname] = ''
	reason.value = ''
	attempted.value = false
	request.reset()
})

const filled = computed(() =>
	props.fields
		.filter((field) => isFilled(draft[field.fieldname]))
		.map((field) => ({
			fieldname: field.fieldname,
			proposed_value: String(draft[field.fieldname] ?? ''),
		}))
)

// The server refuses a request that asks for nothing; saying so here means the
// reader finds out while the form is still in front of them.
const error = computed(() =>
	attempted.value && !filled.value.length
		? 'Fill in at least one field before sending this.'
		: undefined
)

async function send(close: () => void) {
	attempted.value = true
	if (!filled.value.length) return
	const created = await request.submit({
		doctype: props.doctype,
		doc: JSON.stringify({
			request_type: 'New',
			reason: reason.value,
			changes: filled.value,
		}),
	})
	// `submit` resolves null on failure; the reason renders inline.
	if (!created) return
	toast.success('Sent for review')
	emit('created', created.name)
	close()
}

const actions = computed<DialogAction[]>(() => [
	{
		label: 'Send for review',
		variant: 'solid',
		loading: request.loading,
		onClick: ({ close }) => send(close),
	},
])
</script>
