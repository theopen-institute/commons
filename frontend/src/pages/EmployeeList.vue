<template>
  <PageHeader>
    <div class="flex items-center gap-2">
      <span class="text-lg font-semibold text-ink-gray-8">Employees</span>
      <Badge v-if="employees.data" theme="gray" variant="subtle">
        {{ employees.data.length }}{{ employees.hasNextPage ? '+' : '' }}
      </Badge>
    </div>
    <Button
      v-if="can.create"
      variant="solid"
      icon-left="lucide-plus"
      label="New employee"
      @click="router.push({ name: 'NewEmployee' })"
    />
  </PageHeader>

  <div class="px-5 py-4">
    <!-- A refused permission answer is not a refusal of permission: say which
         it was, rather than telling someone they lack a right nobody checked. -->
    <div v-if="permissionsError" class="mx-auto max-w-md text-center">
      <ErrorMessage :message="permissionsError.message" class="mb-3" />
      <Button label="Try again" variant="subtle" @click="reloadPermissions()" />
    </div>
    <PermissionNotice v-else-if="permissionsLoaded && !can.read" what="see employees" />

    <template v-else>
      <div class="flex flex-wrap items-center gap-2">
        <TextInput
          v-model="searchTerm"
          type="search"
          placeholder="Search by name"
          class="w-64"
        >
          <template #prefix>
            <span class="lucide-search size-4 text-ink-gray-5" />
          </template>
        </TextInput>
        <Select
          v-model="statusFilter"
          :options="statusFilterOptions"
          class="w-40"
        />
        <div class="flex-1" />
        <Button
          variant="ghost"
          icon-left="lucide-refresh-cw"
          label="Refresh"
          :loading="employees.loading"
          @click="employees.reload()"
        />
      </div>

      <ErrorMessage v-if="employees.error" :message="employees.error.message" class="mt-3" />

      <div
        v-if="employees.loading && !employees.data"
        class="mt-4 space-y-2"
        role="status"
        aria-label="Loading employees"
      >
        <Skeleton v-for="n in 6" :key="n" class="h-14 w-full rounded-4" />
      </div>

      <div
        v-else-if="employees.data && employees.data.length === 0"
        class="mt-16 flex flex-col items-center gap-2 text-center"
      >
        <span class="lucide-users size-8 text-ink-gray-4" />
        <p class="text-base-medium text-ink-gray-7">
          {{ hasFilters ? 'No employees match this search' : 'No employees yet' }}
        </p>
        <p class="text-p-sm text-ink-gray-5">
          {{
            hasFilters
              ? 'Try a different name or status.'
              : 'Add the first one to get started.'
          }}
        </p>
        <Button
          v-if="can.create && !hasFilters"
          class="mt-2"
          variant="subtle"
          icon-left="lucide-plus"
          label="New employee"
          @click="router.push({ name: 'NewEmployee' })"
        />
      </div>

      <List
        v-else-if="employees.data"
        class="mt-4 list-row-px-3"
        :columns="{
          base: ['minmax(0,1fr)', '7rem'],
          md: ['minmax(0,2fr)', 'minmax(0,1fr)', '8rem', '7rem'],
        }"
        :row-height="56"
      >
        <ListHeader>
          <ListHeaderCell>Employee</ListHeaderCell>
          <ListHeaderCell class="hidden md:flex">Department</ListHeaderCell>
          <ListHeaderCell class="hidden md:flex">Joined</ListHeaderCell>
          <ListHeaderCell class="justify-end">Status</ListHeaderCell>
        </ListHeader>
        <ListRows :items="employees.data" v-slot="{ item: employee, value }">
          <ListRow :value="value" :to="{ name: 'Employee', params: { name: employee.name } }">
            <ListCell>
              <Avatar
                :image="employee.image ?? undefined"
                :label="employee.employee_name || employee.name"
                size="xl"
              />
              <div class="ml-3 min-w-0">
                <div class="truncate text-base text-ink-gray-8">
                  {{ employee.employee_name || employee.name }}
                </div>
                <div class="mt-0.5 truncate text-sm text-ink-gray-5">
                  {{ employee.designation || employee.name }}
                </div>
              </div>
            </ListCell>
            <ListCell class="hidden md:flex">
              <span class="truncate text-base text-ink-gray-7">
                {{ employee.department || '—' }}
              </span>
            </ListCell>
            <ListCell class="hidden md:flex">
              <span class="text-base text-ink-gray-6">
                {{ formatDate(employee.date_of_joining) }}
              </span>
            </ListCell>
            <ListCell class="justify-end">
              <Badge :theme="statusTheme(employee.status)" variant="subtle">
                {{ employee.status }}
              </Badge>
            </ListCell>
          </ListRow>
        </ListRows>
      </List>

      <div
        v-if="employees.data?.length && (employees.hasNextPage || employees.hasPreviousPage)"
        class="mt-4 flex items-center justify-center gap-2"
      >
        <Button
          label="Previous"
          variant="subtle"
          icon-left="lucide-chevron-left"
          :disabled="!employees.hasPreviousPage"
          @click="employees.previous()"
        />
        <Button
          label="Next"
          variant="subtle"
          icon-right="lucide-chevron-right"
          :disabled="!employees.hasNextPage"
          @click="employees.next()"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { refDebounced } from '@vueuse/core'
import {
  Avatar,
  Badge,
  Button,
  ErrorMessage,
  PageHeader,
  Select,
  Skeleton,
  TextInput,
} from 'frappe-ui'
import {
  List,
  ListCell,
  ListHeader,
  ListHeaderCell,
  ListRow,
  ListRows,
} from 'frappe-ui/list'
import { can, permissionsError, permissionsLoaded, reloadPermissions } from '@/data/session'
import { useEmployeeList } from '@/data/employees'
import PermissionNotice from '@/components/PermissionNotice.vue'
import { formatDate, statusTheme } from '@/data/format'

const router = useRouter()

const searchTerm = ref('')
// Debounced so typing a name is one request at the end, not one per keystroke.
const debouncedSearch = refDebounced(searchTerm, 300)
const statusFilter = ref('')

const statusFilterOptions = [
  { label: 'All statuses', value: '' },
  { label: 'Active', value: 'Active' },
  { label: 'Inactive', value: 'Inactive' },
  { label: 'Suspended', value: 'Suspended' },
  { label: 'Left', value: 'Left' },
]

const employees = useEmployeeList({
  search: debouncedSearch,
  status: statusFilter,
})

const hasFilters = computed(
  () => Boolean(searchTerm.value) || Boolean(statusFilter.value),
)
</script>
