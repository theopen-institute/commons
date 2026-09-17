<template>
  <div class="mx-auto mt-16 max-w-md text-center">
    <span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
    <p class="mt-2 text-base-medium text-ink-gray-7">
      You don't have permission to {{ what }}
    </p>
    <p class="mt-1 text-p-sm text-ink-gray-5">
      Ask {{ who }} to give your account the role that grants it.
    </p>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /**
     * Completes "You don't have permission to ___" — so it carries the object
     * too ("see employees", "approve leave"), not just the verb. An earlier
     * version appended a fixed "employees", which had nothing sensible to say
     * once leave got its own pages.
     */
    what: string
    /**
     * Who to ask. The default suits the people side of the app; procurement
     * is not HR's to grant, so its pages name their own.
     */
    who?: string
  }>(),
  { who: 'an HR Manager or a System Manager' },
)
</script>
