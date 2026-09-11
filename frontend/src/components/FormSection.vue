<template>
  <section>
    <h2 class="text-base-medium text-ink-gray-8">{{ section.title }}</h2>
    <p v-if="section.description" class="mt-0.5 text-p-sm text-ink-gray-5">
      {{ section.description }}
    </p>
    <div class="mt-3 grid gap-4 sm:grid-cols-2">
      <EmployeeField
        v-for="field in section.fields"
        :key="field.fieldname"
        v-model="doc[field.fieldname]"
        :field="field"
        :disabled="disabled"
        :error="errors?.[field.fieldname]"
        :class="field.type === 'textarea' ? 'sm:col-span-2' : ''"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import EmployeeField from './EmployeeField.vue'
import type { EmployeeSection } from '@/data/employeeFields'

const props = defineProps<{
  section: EmployeeSection
  /** The reactive document the fields write into. */
  doc: Record<string, any>
  disabled?: boolean
  errors?: Record<string, string>
}>()

// A computed rather than `props.doc` captured once, so replacing the whole
// document (loading a different employee) re-points the fields.
const doc = computed(() => props.doc)
</script>
