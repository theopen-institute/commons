<template>
  <AppPageHeader>
    <div class="flex items-center gap-2">
      <Button
        variant="ghost"
        icon="lucide-arrow-left"
        aria-label="Back to employees"
        @click="router.push({ name: 'EmployeeList' })"
      />
      <span class="text-lg font-semibold text-ink-gray-8">New employee</span>
    </div>
    <template #actions>
      <div class="flex items-center gap-2">
        <Button
          label="Cancel"
          variant="subtle"
          @click="router.push({ name: 'EmployeeList' })"
        />
        <Button
          label="Create"
          variant="solid"
          :loading="newEmployee.loading"
          :disabled="!can.create"
          @click="create"
        />
      </div>
    </template>
  </AppPageHeader>

  <div class="px-5 py-4">
    <!-- A refused permission answer is not a refusal of permission: say which
         it was, rather than telling someone they lack a right nobody checked. -->
    <div v-if="permissionsError" class="mx-auto max-w-md text-center">
      <ErrorMessage :message="permissionsError.message" class="mb-3" />
      <Button label="Try again" variant="subtle" @click="reloadPermissions()" />
    </div>
    <PermissionNotice v-else-if="permissionsLoaded && !can.create" what="add employees" />

    <form v-else class="mx-auto max-w-2xl" @submit.prevent="create">
      <p class="text-p-base text-ink-gray-6">
        The essentials only — everything else can be filled in on the employee
        once they exist.
      </p>

      <FormSection
        v-for="section in createSections"
        :key="section.title"
        :section="section"
        :doc="newEmployee.doc"
        :errors="fieldErrors"
        class="mt-6"
      />

      <ErrorMessage
        v-if="newEmployee.error"
        :message="newEmployee.error.message"
        class="mt-4"
      />

      <!-- A submit button so Enter submits the form; the header's Create
           button is the visible one. -->
      <button type="submit" class="sr-only">Create employee</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, ErrorMessage, toast } from 'frappe-ui'
import { can, permissionsError, permissionsLoaded, reloadPermissions } from '@/data/session'
import { useNewEmployee } from '@/data/employees'
import { createSections, missingRequiredFields } from '@/data/employeeFields'
import AppPageHeader from '@/components/AppPageHeader.vue'
import FormSection from '@/components/FormSection.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

const router = useRouter()
const newEmployee = useNewEmployee()

const createFields = createSections.flatMap((section) => section.fields)

// Nothing is flagged until the first submit — a form that scolds you before
// you have typed anything is hostile. After that the errors are derived, so
// filling a field clears its message on the spot rather than at the next
// submit.
const submitAttempted = ref(false)

const missing = computed(() =>
  missingRequiredFields(newEmployee.doc as Record<string, unknown>, createFields),
)

const fieldErrors = computed(() =>
  submitAttempted.value
    ? Object.fromEntries(
        missing.value.map((field) => [
          field.fieldname,
          `${field.label} is required`,
        ]),
      )
    : {},
)

async function create() {
  submitAttempted.value = true
  if (missing.value.length) return

  try {
    const employee = await newEmployee.submit()
    toast.success(`${employee.employee_name || employee.name} added`)
    router.push({ name: 'Employee', params: { name: employee.name } })
  } catch {
    // `newEmployee.error` renders the reason inline; nothing to add here.
  }
}
</script>
