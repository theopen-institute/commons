<template>
  <!-- The permission answer refused rather than arrived: say so, instead of
       leaving a skeleton up for a reply that is never coming. -->
  <div v-if="error" class="mx-auto max-w-3xl">
    <ErrorMessage :message="error.message" class="mb-3" />
    <Button label="Try again" variant="subtle" @click="$emit('retry')" />
  </div>

  <div v-else-if="!loaded" class="mx-auto max-w-3xl space-y-2">
    <Skeleton v-for="n in 3" :key="n" class="w-full rounded-4" :class="rowClass" />
  </div>

  <PermissionNotice v-else-if="!permitted" :what="what" :who="who" />

  <slot v-else />
</template>

<script setup lang="ts">
import { Button, ErrorMessage, Skeleton } from 'frappe-ui'
import PermissionNotice from './PermissionNotice.vue'

/**
 * What every page in the requests app does before it draws anything.
 *
 * Four pages opened with the same three-step preamble — the permissions call
 * refused, the permissions call outstanding, the permissions call saying no —
 * written out four times with the same comment above it each time. The steps
 * are in a fixed order for a reason worth keeping in one place: a refusal has
 * to beat the skeleton, or a page that will never get an answer sits spinning;
 * and the refusal notice has to wait for the answer, or every page accuses the
 * reader for one frame on the way in.
 */
withDefaults(
  defineProps<{
    /** The permissions call's error, when it refused rather than arrived. */
    error: { message: string } | null
    /** Whether every answer this page gates on is in — settled or refused. */
    loaded: boolean
    /** Whether this user may see what the page is about. */
    permitted: boolean
    /** What they would be doing, in the refusal: "see leave requests". */
    what: string
    /** Who to ask, where the default -- HR -- is not who grants it. */
    who?: string
    /** How tall one placeholder row is, for a page whose rows are not lines. */
    rowClass?: string
  }>(),
  { rowClass: 'h-20', who: undefined },
)

defineEmits<{ retry: [] }>()
</script>
