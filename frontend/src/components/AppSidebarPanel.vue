<template>
	<!-- One sidebar row and the panel it opens. Both personal widgets --
       Notifications and To Do -- are this same thing with different contents,
       so the row, the panel, and the three ways out of it are written once. -->
	<SidebarItem ref="trigger" :label="label" :icon="icon" :active="open" @click="toggle">
		<template v-if="count" #suffix>
			<Badge :theme="badgeTheme" variant="subtle">{{ badgeLabel(count) }}</Badge>
		</template>
	</SidebarItem>

	<!-- Teleported because the panel belongs to the viewport, not to the column
       it is opened from: it runs the full height of the screen regardless of
       how far down the sidebar its row happens to sit.

       Two shapes, and a media query rather than a JS breakpoint decides which
       -- so the panel is laid out by the same stylesheet that lays out the
       sidebar it sits beside, and cannot disagree with it. From `md` up it is
       the desk's bar: 360px, flush against the sidebar's right edge -- which
       moves when the sidebar is collapsed, so the edge is read off the same
       state the column is drawn from, and moves over the same 300ms. Below
       `md` there is no column to sit beside, so it takes the screen. -->
	<Teleport to="body">
		<div
			v-if="open"
			ref="panel"
			class="fixed inset-0 z-[1040] flex flex-col bg-surface-elevation-2 shadow-[8px_0_8px_rgba(0,0,0,0.1)] transition-[left] duration-300 ease-in-out md:inset-y-0 md:left-[var(--sidebar-current-width)] md:right-auto md:w-[360px]"
			:style="{ '--sidebar-current-width': sidebarWidth }"
			role="dialog"
			:aria-label="label"
		>
			<div class="flex shrink-0 items-center gap-2 border-b border-outline-gray-1 px-3 py-2">
				<h2 class="flex min-w-0 items-center gap-1.5 text-base-medium text-ink-gray-8">
					{{ label }}
					<span v-if="count" class="text-sm text-ink-gray-5">{{ count }}</span>
				</h2>
				<div class="ml-auto flex items-center gap-1">
					<slot name="actions" />
					<Button variant="ghost" icon="lucide-x" aria-label="Close" @click="close" />
				</div>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto p-1.5">
				<slot />
			</div>

			<slot name="footer" />
		</div>
	</Teleport>
</template>

<script setup lang="ts">
import { useTemplateRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { onClickOutside, onKeyStroke } from '@vueuse/core'
import { Badge, Button, SidebarItem } from 'frappe-ui'
import { badgeLabel } from '@/data/sidebarFeeds'
import { closeSidebar, sidebarWidth } from '@/data/sidebar'

withDefaults(
	defineProps<{
		/** Said by the row and by the panel's heading alike. */
		label: string
		icon: string
		/** How many are waiting. 0 draws no badge and no count. */
		count?: number
		badgeTheme?: 'gray' | 'blue' | 'green' | 'amber' | 'red' | 'violet'
	}>(),
	{ count: 0, badgeTheme: 'gray' },
)

const open = defineModel<boolean>('open', { required: true })

const trigger = useTemplateRef('trigger')
const panel = useTemplateRef('panel')
const route = useRoute()

function close() {
	open.value = false
}

function toggle() {
	open.value = !open.value
	// The drawer is over the page below `md`, and the row that was just pressed
	// is in it -- the desk closes its own drawer on the same press. Unconditional
	// rather than asked of a breakpoint: above `md` the sidebar is a column in
	// the layout and this flag does not reach it, so there is nothing to guard.
	if (open.value) closeSidebar()
}

// The three ways out, matching what the popover this replaced gave for free.
//
// Two things are ignored. The trigger, or its own press would close the panel
// it just opened -- a press on the *other* widget's row is not ignored, which
// is what keeps the two from ever being open at once. And anything reka has
// portalled to the body: a menu opened from inside the panel (the sort control)
// renders outside it in the DOM, so picking an option would otherwise read as a
// click away.
onClickOutside(panel, close, {
	ignore: [trigger, '[data-reka-popper-content-wrapper]'],
})
onKeyStroke('Escape', () => close())
watch(() => route.fullPath, close)
</script>
