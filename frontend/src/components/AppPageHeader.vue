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
			<!-- The desk's first breadcrumb, which is the way back to the desktop
           from any page: `frappe.breadcrumbs.clear()` opens every trail with
           a home icon linking out of the page
           (frappe/public/js/frappe/views/breadcrumbs.js). Its numbers are the
           desk's -- a 16px glyph (`frappe.utils.icon`'s default `icon-sm`)
           and the "/" its breadcrumb stylesheet draws before every crumb but
           the first, 14px with 6px either side.

           `/app` rather than `/desk`, matching the sidebar's Desktop entry --
           the same destination, by the path Frappe has kept forwarding across
           two renames of the desk.

           Not for everybody, and not everywhere:

           - Somebody whose roles do not open the desk would land on a refusal,
             so for them there is no crumb (see `hasDeskAccess`).
           - Not on mobile, because the desk has none there either: its
             stylesheet hides every crumb but the last below 768px
             (frappe/public/scss/desk/mobile.scss), which is the same
             breakpoint at which the hamburger above appears. On a phone that
             button is what sits beside the title. -->
			<template v-if="showHome">
				<a href="/app" class="flex shrink-0 text-ink-gray-8" aria-label="Home">
					<span class="lucide-home size-4" />
				</a>
				<!-- prettier-ignore -->
				<span class="app-page-header__divider shrink-0 text-ink-gray-4" aria-hidden="true">/</span>
			</template>
			<slot />
		</div>
		<slot name="actions" />
	</PageHeader>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { PageHeader } from 'frappe-ui'
import { isMobile, sidebarOpen, toggleSidebar } from '@/data/sidebar'
import { hasDeskAccess } from '@/data/session'

defineSlots<{
	/** The title area — what sits at the left of the header, after the toggle. */
	default?: () => any
	/** The right-hand actions, kept apart from the title by the header's own row. */
	actions?: () => any
}>()

const showHome = computed(() => hasDeskAccess.value && !isMobile.value)
</script>

<style scoped>
/*
  The divider between two crumbs, written out of
  frappe/public/scss/desk/breadcrumb.scss -- it is a `:before` on every crumb
  but the first there, and a span here because the crumb after it is the page's
  own title rather than a link this component renders. Its colour is a token
  (`--ink-gray-4`, applied above); these four are not, and 14px is deliberately
  not the 13px `text-sm` of this app's scale.

  The glyph's own colour is the desk's `--icon-stroke` (`--gray-800`), and it
  does not move on hover: the desk's `a:hover` changes a crumb's *text*, and
  this crumb has none.
*/
.app-page-header__divider {
	margin-left: 6px;
	margin-right: 6px;
	font-size: 14px;
	line-height: 1.15;
	letter-spacing: 0.02em;
	font-weight: 420;
}
</style>
