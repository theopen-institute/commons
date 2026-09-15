<template>
  <PageHeader>
    <div class="flex min-w-0 items-center gap-2">
      <Button
        variant="ghost"
        icon="lucide-arrow-left"
        aria-label="Back to employees"
        @click="router.push({ name: 'EmployeeList' })"
      />
      <Avatar
        v-if="employee.doc"
        :image="employee.doc.image"
        :label="title"
        size="md"
      />
      <span class="truncate text-lg font-semibold text-ink-gray-8">
        {{ title }}
      </span>
      <Badge
        v-if="employee.doc"
        :theme="statusTheme(employee.doc.status)"
        variant="subtle"
      >
        {{ employee.doc.status }}
      </Badge>
      <Badge v-if="isDirty" theme="amber" variant="subtle">
        Unsaved changes
      </Badge>
    </div>

    <div class="flex shrink-0 items-center gap-2">
      <Dropdown
        v-if="employee.doc"
        :options="moreOptions"
        side="bottom"
        align="end"
      >
        <template #trigger="{ open }">
          <Button
            variant="ghost"
            icon="lucide-ellipsis"
            aria-label="More actions"
            :active="open"
          />
        </template>
      </Dropdown>
      <Button
        v-if="isDirty"
        label="Discard"
        variant="subtle"
        @click="resetDraft"
      />
      <Button
        v-if="canEdit"
        label="Save"
        variant="solid"
        :loading="employee.setValue.loading"
        :disabled="!isDirty"
        @click="save"
      />
    </div>
  </PageHeader>

  <div class="px-5 py-4">
    <!-- A refused permission answer is not a refusal of permission: say which
         it was, rather than telling someone they lack a right nobody checked. -->
    <div v-if="permissionsError" class="mx-auto max-w-md text-center">
      <ErrorMessage :message="permissionsError.message" class="mb-3" />
      <Button label="Try again" variant="subtle" @click="reloadPermissions()" />
    </div>
    <PermissionNotice v-else-if="permissionsLoaded && !can.read" what="see employees" />

    <div v-else-if="employee.loading && !employee.doc" class="mx-auto max-w-2xl space-y-4">
      <Skeleton v-for="n in 5" :key="n" class="h-16 w-full rounded-4" />
    </div>

    <ErrorMessage
      v-else-if="employee.error && !employee.doc"
      :message="employee.error.message"
      class="mx-auto max-w-2xl"
    />

    <form v-else-if="employee.doc" class="mx-auto max-w-2xl" @submit.prevent="save">
      <Alert
        v-if="!canEdit"
        theme="gray"
        title="Read only"
        description="You can see this employee but not change them."
      />

      <div class="space-y-8" :class="canEdit ? '' : 'mt-4'">
        <FormSection
          v-for="section in visibleSections"
          :key="section.title"
          :section="section"
          :doc="draft"
          :disabled="!canEdit"
          :errors="fieldErrors"
          :class="section === visibleSections[0] ? 'mt-4' : ''"
        />
      </div>

      <ErrorMessage
        v-if="employee.setValue.error"
        :message="employee.setValue.error.message"
        class="mt-4"
      />

      <dl
        class="mt-8 grid grid-cols-2 gap-2 border-t border-outline-gray-1 pt-4 text-p-sm text-ink-gray-5"
      >
        <div>
          <dt class="text-ink-gray-6">Employee ID</dt>
          <dd>{{ employee.doc.name }}</dd>
        </div>
        <div>
          <dt class="text-ink-gray-6">Last modified</dt>
          <dd>{{ formatDate(employee.doc.modified?.slice(0, 10)) }}</dd>
        </div>
      </dl>

      <button type="submit" class="sr-only">Save employee</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Dropdown,
  ErrorMessage,
  PageHeader,
  Skeleton,
  dialog,
  toast,
} from 'frappe-ui'
import { can, permissionsError, permissionsLoaded, reloadPermissions } from '@/data/session'
import { useEmployee } from '@/data/employees'
import {
  allEmployeeFields,
  employeeSections,
  isFieldFilled,
  missingRequiredFields,
} from '@/data/employeeFields'
import { formatDate, statusTheme } from '@/data/format'
import FormSection from '@/components/FormSection.vue'
import PermissionNotice from '@/components/PermissionNotice.vue'

const props = defineProps<{ name: string }>()

const router = useRouter()
const employee = useEmployee(() => props.name)

const canEdit = computed(() => can.value.write)

// The form edits a draft, not the cached document: `useDoc` hands back a
// read-through store copy, and a PUT of every field on every keystroke is not
// a save model. Save diffs the draft and sends only what changed.
const draft = reactive<Record<string, any>>({})

// Nothing is flagged until a save is attempted; after that the messages are
// derived from the draft, so filling a field clears its error immediately.
const saveAttempted = ref(false)

function resetDraft() {
  const doc = employee.doc as Record<string, any> | null
  if (!doc) return
  for (const field of allEmployeeFields) {
    draft[field.fieldname] = doc[field.fieldname] ?? ''
  }
  saveAttempted.value = false
}

// Reseeds on load, on switching to another employee, and after a save (the
// server's copy is the one that counts — it may have recomputed fields).
watch(
  () => [props.name, employee.doc?.modified],
  () => resetDraft(),
  { immediate: true },
)

const changes = computed(() => {
  const doc = employee.doc as Record<string, any> | null
  if (!doc) return {}
  const diff: Record<string, any> = {}
  for (const field of allEmployeeFields) {
    const next = draft[field.fieldname]
    const current = doc[field.fieldname]
    // Frappe stores an empty field as '' or null and the form only ever
    // produces '', so treat the two as equal rather than as a change.
    if (!isFieldFilled(next) && !isFieldFilled(current)) continue
    if (next !== current) diff[field.fieldname] = next
  }
  return diff
})

const isDirty = computed(() => Object.keys(changes.value).length > 0)

const title = computed(
  () => employee.doc?.employee_name || employee.doc?.name || props.name,
)

// Exit details are noise on an active employee, so the section follows the
// status in the draft — it appears as soon as the user picks "Left".
const visibleSections = computed(() =>
  employeeSections.filter(
    (section) => !section.visibleWhen || section.visibleWhen(draft),
  ),
)

const editableFields = computed(() =>
  visibleSections.value.flatMap((section) => section.fields),
)

const missing = computed(() => missingRequiredFields(draft, editableFields.value))

const fieldErrors = computed(() =>
  saveAttempted.value
    ? Object.fromEntries(
        missing.value.map((field) => [
          field.fieldname,
          `${field.label} is required`,
        ]),
      )
    : {},
)

async function save() {
  if (!canEdit.value || !isDirty.value) return

  saveAttempted.value = true
  if (missing.value.length) return

  const saved = await employee.setValue.submit(changes.value)
  if (saved) toast.success('Changes saved')
}

const moreOptions = computed(() => [
  {
    label: 'Open in desk',
    icon: 'lucide-external-link',
    onClick: () => {
      window.open(`/app/employee/${props.name}`, '_blank')
    },
  },
  ...(can.value.delete
    ? [
        {
          label: 'Delete employee',
          icon: 'lucide-trash-2',
          onClick: confirmDelete,
        },
      ]
    : []),
])

function confirmDelete() {
  const name = title.value
  dialog.danger({
    title: 'Delete employee',
    message: `Delete ${name}? This cannot be undone, and it fails if other records already reference them — marking the employee as Left is usually what you want instead.`,
    onConfirm: async () => {
      // Rejecting keeps the dialog open and renders the reason inline, which
      // is what should happen when a link elsewhere blocks the delete.
      await employee.delete.submit()
      if (employee.delete.error) throw employee.delete.error
      toast.success(`${name} deleted`)
      router.push({ name: 'EmployeeList' })
    },
  })
}
</script>
