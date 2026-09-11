<template>
  <div class="mx-auto mt-16 max-w-md text-center">
    <span class="lucide-lock size-8 text-ink-gray-4" />
    <p class="mt-2 text-base-medium text-ink-gray-7">
      You don't have permission to {{ action }} employees
    </p>
    <p class="mt-1 text-p-sm text-ink-gray-5">
      Ask an HR Manager or a System Manager to give your account the role that
      grants it.
    </p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** Filled into "permission to ___ employees", e.g. "see", "edit". */
  action: string
}>()
</script>
