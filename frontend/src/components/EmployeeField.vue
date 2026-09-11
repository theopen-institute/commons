<template>
  <LinkControl
    v-if="field.type === 'link'"
    v-model="model"
    :doctype="field.doctype!"
    :filters="field.filters"
    :label="field.label"
    :description="field.description"
    :error="error"
    :required="field.required"
    :disabled="disabled"
    :placeholder="field.placeholder"
  />
  <FormControl
    v-else
    v-model="model"
    :type="controlType"
    :label="field.label"
    :description="field.description"
    :error="error"
    :required="field.required"
    :disabled="disabled"
    :placeholder="field.placeholder"
    :options="field.type === 'select' ? selectOptions : undefined"
    :rows="field.type === 'textarea' ? 3 : undefined"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FormControl } from 'frappe-ui'
import LinkControl from './LinkControl.vue'
import type { EmployeeField } from '@/data/employeeFields'

const props = defineProps<{
  field: EmployeeField
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

const controlType = computed(() => {
  switch (props.field.type) {
    case 'select':
      return 'select'
    case 'date':
      return 'date'
    case 'textarea':
      return 'textarea'
    case 'email':
      return 'email'
    case 'tel':
      return 'tel'
    default:
      return 'text'
  }
})

const selectOptions = computed(() => {
  const options = (props.field.options ?? []).map((option) => ({
    label: option,
    value: option,
  }))
  // A required select has no valid empty value, so it gets no way back to
  // one; an optional select needs a row that clears it.
  if (props.field.required) return options
  return [{ label: 'Not set', value: '' }, ...options]
})
</script>
