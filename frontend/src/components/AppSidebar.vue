<template>
	<!-- Built to the desk's sidebar, down to the numbers: a user crosses between
       the two all day, and the two panels sit in the same place on the screen.
       Widths, paddings and colors come from the desk's own tokens (see
       index.css); the rows are frappe-ui's, which already match its 28px
       height, 13px label and 8px selection radius. -->
	<Sidebar class="app-sidebar gap-3.5 border-r p-2 pb-2.5" width="var(--sidebar-width)">
		<!-- The desk's header: a 32px mark, the section over the app it belongs to,
         and one menu built like the desk's own -- same sections in the same
         order, icons from the same family (see `menuItems`). -->
		<Dropdown class="shrink-0" :options="menuItems" match-trigger-width>
			<!-- The desk prints an item's shortcut in a right-aligned span after the
           label (`menu-item-shortcut`); frappe-ui's suffix slot is that
           position, driven by an optional `shortcut` on the option. -->
			<template #item-suffix="{ item }">
				<span v-if="item.shortcut" class="text-sm text-ink-gray-5">
					{{ item.shortcut }}
				</span>
			</template>
			<button
				class="app-sidebar__hover flex h-12 w-full items-center rounded-4 p-2"
				aria-label="App menu"
			>
				<!-- Bound, not a literal `src`: a literal absolute path is treated as
             an import to bundle, and this asset is served by Frappe from the
             app's public folder. -->
				<img :src="currentApp.logo" alt="" class="size-8 shrink-0 rounded-4" />
				<span class="ml-2 flex min-w-0 flex-1 flex-col text-left">
					<span class="truncate text-base-medium leading-[1.2] text-ink-gray-8">
						{{ currentApp.title }}
					</span>
					<span class="mt-[3px] truncate text-sm leading-[1.2] text-ink-gray-6">
						{{ SUITE_TITLE }}
					</span>
				</span>
				<span class="lucide-chevron-down ml-2 size-4 shrink-0 text-ink-gray-6" />
			</button>
		</Dropdown>

		<!-- One app's navigation only; the switcher in the header dropdown is the
         only way across. Employees is a flat list under its header, exactly as
         the desk lists a workspace's items straight under its name. Requests
         holds two jobs that are read separately -- leave and procurement -- so
         each gets a label, which is the desk's own pattern for a sidebar that
         carries more than one group. A section whose permission this user does
         not have is absent rather than empty. -->
		<div class="flex-1 overflow-y-auto">
			<!-- Rows a pixel apart, like the desk's own list of workspace items. -->
			<div v-if="currentApp.key === 'employees'" class="space-y-px">
				<SidebarItem
					label="Employees"
					icon="lucide-users"
					:to="{ name: 'EmployeeList' }"
					:active="route.name === 'EmployeeList' || route.name === 'Employee'"
				/>
				<SidebarItem
					v-if="can.create"
					label="New employee"
					icon="lucide-user-plus"
					:to="{ name: 'NewEmployee' }"
				/>
			</div>

			<!-- `gap-2` on top of the 8px each SidebarSection already carries: the
           two sections are separate jobs, and the label alone does not read as
           a break at the library's default spacing. No `space-y-*` on this
           container -- its specificity beats the sections' own `mt-2` and
           collapses them back together. -->
			<div v-else class="flex flex-col gap-2">
				<!-- A bare row, not a section: one page with nothing under it, and
             ungated, so it sits above the two jobs rather than beside them. -->
				<SidebarItem
					label="Announcements"
					icon="lucide-megaphone"
					:to="{ name: 'Announcements' }"
				/>

				<SidebarSection v-if="leaveCan.read" label="Leave" collapsible>
					<SidebarItem label="My leave" icon="lucide-palmtree" :to="{ name: 'MyLeave' }" />
					<SidebarItem
						v-if="leaveCan.approve"
						label="Approvals"
						icon="lucide-check-check"
						:to="{ name: 'LeaveApprovals' }"
					>
						<template v-if="leaveCan.pending_approvals" #suffix>
							<Badge theme="amber" variant="subtle">
								{{ leaveCan.pending_approvals }}
							</Badge>
						</template>
					</SidebarItem>
				</SidebarSection>

				<SidebarSection v-if="procurementCan.read" label="Procurement" collapsible>
					<SidebarItem
						label="My requests"
						icon="lucide-shopping-cart"
						:to="{ name: 'MyProcurement' }"
					/>
					<SidebarItem
						v-if="procurementCan.workflow_access"
						label="Approvals"
						icon="lucide-check-check"
						:to="{ name: 'ProcurementApprovals' }"
					>
						<template v-if="procurementCan.pending_workflow_actions" #suffix>
							<Badge theme="amber" variant="subtle">
								{{ procurementCan.pending_workflow_actions }}
							</Badge>
						</template>
					</SidebarItem>
				</SidebarSection>
			</div>
		</div>

		<!-- Who you are, and a way to your own User record -- the one thing the
         desk's own footer badge does when you click it. No menu: everything
         else is in the header's, which is the only menu in the sidebar. -->
		<a :href="userDeskUrl" class="app-sidebar__hover mt-3 block shrink-0 rounded-4 px-2 py-1">
			<!-- 40px of content inside 4px of padding, like the desk's row: the
           minimum is the content's, not the padded box's, or the whole thing
           comes up 2px short. -->
			<div class="flex min-h-10 items-center">
				<!-- The desk's avatar, not a generic one: two initials on the colour
             it gives this person everywhere else (see `get_avatar_color`). -->
				<span
					class="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full text-base leading-none"
					:style="avatarStyle"
					:title="user.full_name"
				>
					<img
						v-if="user.user_image"
						:src="user.user_image"
						alt=""
						class="size-full object-cover"
					/>
					<template v-else>{{ initials }}</template>
				</span>
				<div class="ml-2 flex min-w-0 flex-col">
					<span class="truncate text-sm leading-[1.5] text-ink-gray-8">
						{{ user.full_name }}
					</span>
					<!-- The -1px is the desk's, from its own sidebar template: the two
               lines are a pixel tighter than their line boxes stack to. -->
					<span class="-mt-px truncate text-sm leading-[1.5] text-ink-gray-5">
						{{ user.email ?? user.name }}
					</span>
				</div>
			</div>
		</a>
	</Sidebar>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
	Badge,
	Dropdown,
	Sidebar,
	SidebarItem,
	SidebarSection,
	useCall,
	useColorScheme,
} from 'frappe-ui'
import { can, logout, user } from '@/data/session'
import { leaveCan } from '@/data/leave'
import { procurementCan } from '@/data/procurement'
import { apps, availableApps, SUITE_TITLE, type AppDefinition, type AppKey } from '@/data/apps'

// Two initials, like the desk's `get_abbr`: the first letter of each of the
// first two words, left in the case they were written in -- the desk does not
// uppercase them either, so "José da Silva" is "Jd" in both places.
const initials = computed(() =>
	user.value.full_name
		.split(' ')
		.filter(Boolean)
		.slice(0, 2)
		.map((word) => word[0])
		.join(''),
)

// The palette entry is the server's answer; these two variables are the desk's,
// copied into index.css with the rest of its sidebar tokens.
const avatarStyle = computed(() => {
	const color = user.value.avatar_color ?? 'gray'
	return {
		backgroundColor: `var(--${color}-avatar-bg)`,
		color: `var(--${color}-avatar-color)`,
	}
})

const route = useRoute()
const router = useRouter()
const { colorScheme, setColorScheme } = useColorScheme()

// The route says which app we are in. Employees is the fallback for the
// landing route, which redirects away before this matters.
const currentApp = computed<AppDefinition>(() => apps[route.meta.app ?? 'employees'])

// Keyed by route prefix, not by app: Requests spans two doctypes, and "Open in
// desk" should land on the one whose section is on screen.
const DESK_ROUTES: [prefix: string, deskPath: string][] = [
	['/employees', '/app/employee'],
	['/leave', '/app/leave-application'],
	['/procurement', '/app/procurement-request'],
]

// A full page load, not a router push: the desk is a different app served off
// the same site.
function openDesk() {
	const match = DESK_ROUTES.find(([prefix]) => route.path.startsWith(prefix))
	window.location.href = match ? match[1] : '/app'
}

// The marks each app carries in the switcher -- the same ones its navigation
// rows use, so a submenu entry reads as the section it opens.
const APP_ICONS: Record<AppKey, string> = {
	employees: 'lucide-users',
	requests: 'lucide-inbox',
}

// The desk's Reload (`frappe.ui.toolbar.clear_cache`): clear the server's
// session cache, then reload the page. The desk wipes its asset keys from
// localStorage first; this app keeps none (see session.ts), so there is
// nothing local to clear.
const clearCacheCall = useCall({
	url: '/api/v2/method/frappe.sessions.clear',
	method: 'POST',
	immediate: false,
})

function clearCacheAndReload() {
	clearCacheCall.submit().finally(() => window.location.reload())
}

// The hint the desk prints beside Reload --
// `get_shortcut_label('Shift+Ctrl+R')`, which draws glyphs on a Mac and the
// written keys elsewhere. It names the browser's own hard reload; frappe
// binds no key of its own.
const RELOAD_SHORTCUT = /mac/i.test(navigator.platform) ? '⇧⌘R' : 'Shift+Ctrl+R'

// Where the desk's own footer badge goes: this person's User record. `name` is
// the user id, which is an email for everyone but Administrator, so it has to
// be encoded. `/app` rather than `/desk`, like the routes above -- Frappe
// forwards it, and has kept forwarding it across two renames of the desk.
const userDeskUrl = computed(() => `/app/user/${encodeURIComponent(user.value.name)}`)

// The desk's header menu (`SidebarHeader.dropdown_items`), carried over
// section for section: navigation, a divider, display and maintenance, a
// divider, the account actions. Two of the desk's entries have no counterpart
// here and are left out rather than stubbed -- Session Defaults is a desk
// boot feature with no dialog to open, and Help lists Navbar Settings links
// this app does not have. The desk's `is_divider` markers become groups with
// the label hidden: the menu renderer borders each group, which is that line.
const menuItems = computed(() => [
	// Desktop is the desk's own name for its home. Workspaces is where the desk
	// lists a workspace's siblings -- here that is the rest of the suite, with
	// the two destinations that are not workspaces under a divider: the apps
	// screen, and this app's page in the desk.
	{
		label: 'Desktop',
		icon: 'lucide-home',
		onClick: () => {
			window.location.href = '/app'
		},
	},
	{
		label: 'Workspaces',
		icon: 'lucide-layout-dashboard',
		submenu: [
			// Only the apps this user can actually open, and never the one they
			// are in.
			...availableApps.value
				.filter((app) => app.key !== currentApp.value.key)
				.map((app) => ({
					label: app.title,
					icon: APP_ICONS[app.key],
					onClick: () => router.push(app.home),
				})),
			{
				group: '',
				hideLabel: true,
				options: [
					{
						label: 'All apps',
						icon: 'lucide-layout-grid',
						onClick: () => {
							window.location.href = '/apps'
						},
					},
					{
						label: 'Open in desk',
						icon: 'lucide-external-link',
						onClick: openDesk,
					},
				],
			},
		],
	},
	{
		label: 'Website',
		icon: 'lucide-globe',
		onClick: () => {
			window.open(window.location.origin)
		},
	},
	{
		group: '',
		hideLabel: true,
		options: [
			{
				// The desk tucks its appearance controls behind Display; the scheme
				// is the one choice this app has. `selected` marks the preference,
				// so nothing is checked while the app follows the OS setting.
				label: 'Display',
				icon: 'lucide-palette',
				submenu: [
					{
						label: 'Light mode',
						icon: 'lucide-sun',
						selected: colorScheme.value === 'light',
						onClick: () => setColorScheme('light'),
					},
					{
						label: 'Dark mode',
						icon: 'lucide-moon',
						selected: colorScheme.value === 'dark',
						onClick: () => setColorScheme('dark'),
					},
				],
			},
			{
				label: 'Reload',
				icon: 'lucide-rotate-cw',
				shortcut: RELOAD_SHORTCUT,
				onClick: clearCacheAndReload,
			},
		],
	},
	{
		group: '',
		hideLabel: true,
		options: [
			{
				label: 'Logout',
				icon: 'lucide-log-out',
				onClick: logout,
			},
		],
	},
])
</script>

<style scoped>
/*
  The desk's shades, over frappe-ui's near-misses. The row components are
  selected by the data attributes they document, not by the utility classes
  they happen to carry.
*/
.app-sidebar {
	border-color: var(--sidebar-border-color);
}

.app-sidebar__hover:hover,
.app-sidebar :deep([data-slot='sidebar-item'][data-state='inactive']:hover) {
	background-color: var(--sidebar-hover-color);
}

.app-sidebar :deep([data-slot='sidebar-item'][data-state='active']) {
	background-color: var(--sidebar-active-color);
	box-shadow: var(--shadow-sm);
}
</style>
