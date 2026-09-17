<template>
	<LinkControl
		v-if="field.type === 'link'"
		v-model="model"
		:doctype="field.doctype!"
		:label="field.label"
		:description="field.description ?? undefined"
		:error="error"
		:required="field.required"
		:disabled="disabled"
	/>
	<FormControl
		v-else
		v-model="model"
		:type="controlType"
		:label="field.label"
		:description="field.description ?? undefined"
		:error="error"
		:required="field.required"
		:disabled="disabled"
		:options="field.type === 'select' ? selectOptions : undefined"
		:rows="field.type === 'textarea' ? 3 : undefined"
	/>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import LinkControl from './LinkControl.vue'
import type { RecordField } from '@/data/selfService'

/**
 * One editable control, drawn from the field definition the server sent.
 *
 * It takes `RecordField` directly rather than a shape of this app's own: the
 * label, the control, a select's options and the link's target are all resolved
 * from the doctype's meta on the way out (see `registry.field_definitions`), so
 * there is nothing here to translate and nothing to keep in step.
 */
const props = defineProps<{
	field: RecordField
	disabled?: boolean
	error?: string
}>()

const value = defineModel<unknown>('modelValue')

// Frappe hands back `null` for an empty field, which every text control would
// render as the string "null". Reads normalize to '', writes pass through.
const model = computed({
	get: () => (value.value ?? '') as string,
	set: (next: string) => {
		value.value = next
	},
})

// The server's vocabulary is already the control's, bar the two it has no
// opinion about. Anything unrecognised falls back to a plain text box rather
// than rendering nothing.
type ControlType = NonNullable<InstanceType<typeof FormControl>['$props']['type']>

const CONTROLS: Record<string, ControlType> = {
	select: 'select',
	date: 'date',
	textarea: 'textarea',
	email: 'email',
	tel: 'tel',
	url: 'text',
	number: 'number',
	check: 'checkbox',
}

const controlType = computed<ControlType>(() => CONTROLS[props.field.type] ?? 'text')

const selectOptions = computed(() => {
	const options = props.field.options.map((option) => ({
		label: option,
		value: option,
	}))
	// A required select has no valid empty value, so it gets no way back to
	// one; an optional select needs a row that clears it.
	if (props.field.required) return options
	return [{ label: 'Not set', value: '' }, ...options]
})
</script>
