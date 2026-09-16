<template>
  <!-- The app's page header, which is frappe-ui's with the desk's mobile
       hamburger in front of the title.

       The desk puts that button in the page's own title area, not in the
       sidebar (frappe/public/js/frappe/ui/page.html -> `.page-title >
       .sidebar-toggle-btn`), so it sits on the same line as the title and
       scrolls with nothing. This wrapper is where that happens here, because
       PageHeader's row is `justify-between` and the button has to travel with
       the title rather than become a third thing spread across the row.

       Hence the two slots: whatever a page used to put first goes in the
       default slot, and its right-hand actions in `#actions`. -->
  <PageHeader>
    <div class="flex min-w-0 items-center">
      <!-- 20px glyph, 10px of air, the desk's `--gray-700`: `icon-md` and
           `--margin-sm` from its own stylesheet. Rendered only below the
           breakpoint -- above it the sidebar is on screen and there is
           nothing to toggle. -->
      <button
        v-if="isMobile"
        class="mr-2.5 flex shrink-0"
        aria-label="Toggle sidebar"
        :aria-expanded="sidebarOpen"
        @click="toggleSidebar"
      >
        <span class="lucide-menu size-5 text-ink-gray-7" />
      </button>
      <slot />
    </div>
    <slot name="actions" />
  </PageHeader>
</template>

<script setup lang="ts">
import { PageHeader } from 'frappe-ui'
import { isMobile, sidebarOpen, toggleSidebar } from '@/data/sidebar'

defineSlots<{
  /** The title area — what sits at the left of the header, after the toggle. */
  default?: () => any
  /** The right-hand actions, kept apart from the title by the header's own row. */
  actions?: () => any
}>()
</script>
