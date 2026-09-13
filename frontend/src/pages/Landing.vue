<template>
  <!-- Deliberately bare: this is a redirect with a heartbeat, not a page. -->
  <div class="flex h-full items-center justify-center">
    <div v-if="!appsResolved" class="flex items-center gap-2 text-ink-gray-5">
      <Spinner class="size-4" />
      <span class="text-p-base">Loading…</span>
    </div>
    <div v-else class="max-w-md px-5 text-center">
      <span class="lucide-lock size-8 text-ink-gray-4" />
      <p class="mt-2 text-base-medium text-ink-gray-7">Nothing to show you</p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        Your account can't open any of these apps. Ask an HR Manager or a
        System Manager for access.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { Spinner } from 'frappe-ui'
import { appsResolved, availableApps } from '@/data/apps'

const router = useRouter()

// Someone landing on bare /tbs_commons gets the first app they can actually use.
// Normal entry is via an apps-screen tile, which lands on a real route, so
// this only catches a hand-typed URL or an old bookmark.
watch(
  [appsResolved, availableApps],
  () => {
    if (!appsResolved.value) return
    const first = availableApps.value[0]
    if (first) router.replace(first.home)
  },
  { immediate: true },
)
</script>
