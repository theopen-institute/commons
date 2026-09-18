<template>
  <div
    v-if="!employee && access === 'forbidden'"
    class="mx-auto mt-16 max-w-md text-center"
  >
    <span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
    <p class="mt-2 text-base-medium text-ink-gray-7">
      Your employee record isn't available to you
    </p>
    <p class="mt-1 text-p-sm text-ink-gray-5">
      It exists and it's yours, but your account can't read it — {{ forbids }}.
      Ask whoever administers permissions here, not HR.
    </p>
  </div>

  <div v-else-if="!employee" class="mx-auto mt-16 max-w-md text-center">
    <span class="lucide-user-x mx-auto size-8 text-ink-gray-4" />
    <p class="mt-2 text-base-medium text-ink-gray-7">
      Your login isn't linked to an employee record
    </p>
    <p class="mt-1 text-p-sm text-ink-gray-5">
      {{ requires }}, so ask HR to set the
      <span class="text-ink-gray-7">User account</span> field on yours to
      {{ user.name }}.
    </p>
  </div>

  <slot v-else />
</template>

<script setup lang="ts">
import { user } from '@/data/session'
import type { EmployeeAccess } from '@/data/requests/section'

/**
 * A page that needs an Employee record pointing at this login, and what it says
 * when there isn't one.
 *
 * Two empty states, not one, and that is the whole point of the component.
 * "You have no record" and "you may not see your record" send the reader to
 * different people — HR for the first, whoever administers permissions for the
 * second — and a page that cannot tell them apart has to guess. Leave guessed,
 * and sent users whose access had been revoked to HR to have a record created
 * that already existed and already named them. The server distinguishes the two
 * in `session_employee_access`; this is where that answer is finally spent.
 *
 * Both sentences take the section's own words for what a record is needed for,
 * because "leave is requested against an employee" and "expenses are claimed
 * against an employee" are the same fact about two different things.
 */
defineProps<{
  /** The record, or null when there is none to be had. */
  employee: { name: string } | null
  /** Why there is none — the server's answer, not an inference. */
  access: EmployeeAccess
  /** What its absence costs: "so leave can't be requested against it". */
  forbids: string
  /** Why one is needed: "Leave is requested against an employee". */
  requires: string
}>()
</script>
