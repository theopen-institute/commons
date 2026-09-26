<template>
	<!-- The desk's own two shapes for the column, and the widget that swaps
       between them: a full sidebar, or the 50px rail that keeps the icons and
       drops everything else. The button straddles the column's right edge, so
       it belongs to this wrapper rather than to the panel -- `Sidebar` clips
       its own overflow to animate its width, and would cut the circle in half. -->
	<div class="app-sidebar-shell relative flex shrink-0">
		<!-- Built to the desk's sidebar, down to the numbers: a user crosses between
         the two all day, and the two panels sit in the same place on the screen.
         Widths, paddings and colors come from the desk's own tokens (see
         index.css); the rows are frappe-ui's, which already match its 28px
         height, 13px label and 8px selection radius.

         Below the desk's own mobile width it is a drawer rather than a narrower
         column, again like the desk: see `shellClass`. -->
		<Sidebar
			v-model:collapsed="collapsed"
			class="app-sidebar gap-3.5"
			:class="shellClass"
			:width="shellWidth"
			collapsed-width="var(--sidebar-collapsed-width)"
		>
			<!-- The desk's header: a 32px mark, the workspace over the name of the app
           it is part of, and one menu built like the desk's own -- same sections
           in the same order, icons from the same family (see `menuItems`).

           Both lines are the site's to choose now: the workspace is a
           `Commons Workspace` document and the name under it is
           `Commons Settings`. See `data/shell.ts`. -->
			<!-- The menu is as wide as the button it hangs off, which is how the
           desk's own sits under its header -- until the button is 34px of
           logo, at which point that rule has nothing to do with the menu and
           it falls back to sizing itself. -->
			<Dropdown class="shrink-0" :options="menuItems" :match-trigger-width="!collapsed">
				<!-- The desk prints an item's shortcut in a right-aligned span after the
             label (`menu-item-shortcut`); frappe-ui's suffix slot is that
             position, driven by an optional `shortcut` on the option. -->
				<template #item-suffix="{ item }">
					<span v-if="item.shortcut" class="text-sm text-ink-gray-5">
						{{ item.shortcut }}
					</span>
				</template>
				<!-- Collapsed, the 32px mark is wider than what is left inside the
             row's own padding, so the padding goes rather than the mark --
             which is the desk's answer too (`SidebarHeader.toggle_width`
             zeroes exactly these two). -->
				<button
					class="app-sidebar__hover flex h-12 w-full items-center rounded-4 py-2"
					:class="collapsed ? 'justify-center px-0' : 'px-2'"
					aria-label="App menu"
				>
					<!-- Bound, not a literal `src`: a literal absolute path is treated as
               an import to bundle, and this asset is served by Frappe from the
               app's public folder. -->
					<img :src="workspace.logo" alt="" class="size-8 shrink-0 rounded-4" />
					<span v-if="!collapsed" class="ml-2 flex min-w-0 flex-1 flex-col text-left">
						<span class="truncate text-base-medium leading-[1.2] text-ink-gray-8">
							{{ workspace.title }}
						</span>
						<span class="mt-[3px] truncate text-sm leading-[1.2] text-ink-gray-6">
							{{ title }}
						</span>
					</span>
					<span
						v-if="!collapsed"
						class="lucide-chevron-down ml-2 size-4 shrink-0 text-ink-gray-6"
					/>
				</button>
			</Dropdown>

			<!-- The rows that belong to the person rather than to the workspace, in
           the desk's own order: Search, Notifications, To Do. They sit above the
           workspace's own rows because each reaches all of them and none of them
           is it, and flush against each other in one stack -- the sidebar's own
           `gap-3.5` is the space between jobs, and these three are one job.

           The search bar is the way in for anyone who has not met Ctrl+K: the
           desk keeps its Awesome Bar in the navbar, and this app has no navbar.
           The other two are absent for a signed-out visitor -- both lists are
           "yours", and the server has nothing to answer for somebody who is
           nobody -- and each hides its own row while it has nothing in it, so a
           person with a clear plate is left with Search alone. -->
			<div class="flex shrink-0 flex-col">
				<SidebarItem label="Search" icon="lucide-search" @click="openSearch()">
					<!-- Written out rather than drawn as key caps, which is what the desk
               does everywhere a shortcut sits beside the thing it opens -- the
               same `get_shortcut_label` spelling as Reload in the menu above. -->
					<template #suffix>
						<span class="mr-2 text-sm text-ink-gray-5">{{ modKey }}K</span>
					</template>
				</SidebarItem>

				<template v-if="user.name !== 'Guest'">
					<AppNotifications />
					<!-- Desk access as well as a session: every to-do opens a desk form,
               and "See all" is a desk list, so for somebody whose roles do not
               open the desk the whole widget is a list of dead ends. -->
					<AppTodoList v-if="hasDeskAccess" />
				</template>
			</div>

			<!-- One workspace's navigation, laid out the way its document lays it out:
           rows in order, and consecutive rows sharing a heading drawn as a
           group. Which rows exist is the site's (`Commons Workspace`); which of
           them this user has is not (`data/shell.ts`). A group whose every row
           belongs to somebody else is absent rather than empty. -->
			<div class="flex-1 overflow-y-auto">
				<!-- `gap-2` on top of the 8px each SidebarSection already carries: the
             sections are separate jobs, and the label alone does not read as
             a break at the library's default spacing. No `space-y-*` on this
             container -- its specificity beats the sections' own `mt-2` and
             collapses them back together. -->
				<div class="flex flex-col gap-2">
					<template v-for="(group, index) in navGroups(workspace)" :key="index">
						<SidebarSection v-if="group.label" :label="group.label" collapsible>
							<AppSidebarRow
								v-for="entry in group.entries"
								:key="entry.id"
								:entry="entry"
							/>
						</SidebarSection>
						<!-- Bare rows, not a section: nothing groups them, so they sit above
                 the groups rather than beside them. -->
						<template v-else>
							<AppSidebarRow
								v-for="entry in group.entries"
								:key="entry.id"
								:entry="entry"
							/>
						</template>
					</template>
				</div>
			</div>

			<!-- Who you are, and the menu of everything that is yours rather than the
           workspace's: your User record, display, session defaults, help,
           reload, logout. The desk's badge opens the same menu, built by
           `commons/public/js/user_menu.js`; before that both badges went
           straight to the User record, which is now the menu's first entry.

           It opens upward -- the badge is at the foot of the column -- and as
           wide as the badge while there is a badge's width to match, like the
           header's. -->
			<Dropdown
				class="mt-3 shrink-0"
				side="top"
				:options="userMenuItems"
				:match-trigger-width="!collapsed"
			>
				<template #item-suffix="{ item }">
					<span v-if="item.shortcut" class="text-sm text-ink-gray-5">
						{{ item.shortcut }}
					</span>
				</template>
				<button
					class="app-sidebar__hover block w-full rounded-4 py-1 text-left"
					:class="collapsed ? 'px-0' : 'px-2'"
					aria-label="User menu"
				>
					<!-- 40px of content inside 4px of padding, like the desk's row: the
               minimum is the content's, not the padded box's, or the whole thing
               comes up 2px short. -->
					<div class="flex min-h-10 items-center" :class="{ 'justify-center': collapsed }">
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
						<div v-if="!collapsed" class="ml-2 flex min-w-0 flex-col">
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
				</button>
			</Dropdown>
		</Sidebar>

		<SessionDefaultsDialog v-model:open="sessionDefaultsOpen" @saved="clearCacheAndReload" />

		<!-- The desk's collapse widget, to the numbers
         (frappe/public/scss/desk/sidebar.scss, `.sidebar-toggle-btn`): a 24px
         circle centred on the border 80px off the floor, drawn only while the
         pointer is over the column. Kept for the keyboard too, which the desk
         does not do -- a control that only exists under a pointer cannot be
         reached by anyone tabbing to it.

         Absent below `md`, where there is no narrow column to go to: the panel
         is a drawer there, and the way out of it is the overlay. -->
		<button
			v-if="!isMobile"
			type="button"
			class="app-sidebar__collapse"
			:aria-label="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
			:aria-expanded="!collapsed"
			@click="collapsed = !collapsed"
		>
			<span
				class="size-3"
				:class="collapsed ? 'lucide-chevron-right' : 'lucide-chevron-left'"
			/>
		</button>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dropdown, Sidebar, SidebarItem, SidebarSection, useCall, useColorScheme } from 'frappe-ui'
import { hasDeskAccess, logout, user } from '@/data/session'
import { websiteUrl } from '@/data/website'
import { isMobile, sidebarCollapsed, sidebarOpen } from '@/data/sidebar'
import { modKey, openSearch } from '@/data/search'
import AppSidebarRow from '@/components/AppSidebarRow.vue'
import AppNotifications from '@/components/AppNotifications.vue'
import AppTodoList from '@/components/AppTodoList.vue'
import SessionDefaultsDialog from '@/components/SessionDefaultsDialog.vue'
import { userMenu, type NavbarLink } from '@/data/userMenu'
import {
	availableWorkspaces,
	homeOf,
	navGroups,
	title,
	workspaceFor,
	type Workspace,
} from '@/data/shell'

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

// Two shapes, the desk's both: a column in the layout, and -- below 768px --
// a drawer over it. The desk does not narrow its sidebar on a phone, it takes
// it out of the layout entirely (`width: 0`) and lays the same full-width
// panel over the page when the hamburger is pressed
// (frappe/public/scss/desk/sidebar.scss, `media-breakpoint-down(sm)`), so
// frappe-ui's own collapse-to-a-rail is turned off.
const shellClass = computed(() => {
	if (!isMobile.value) return 'border-r p-2 pb-2.5'
	return sidebarOpen.value
		? 'app-sidebar--drawer fixed inset-y-0 left-0 z-[1020] border-r p-2 pb-2.5'
		: 'app-sidebar--drawer overflow-hidden'
})

// Inline, because that is where Sidebar puts its own width and nothing in a
// class would beat it. 0 rather than hidden: the panel keeps its place in the
// layout, so the page beside it is laid out against a column of no width.
//
// The expanded width only: `collapsed-width` is the other half, and Sidebar
// picks between the two.
const shellWidth = computed(() =>
	isMobile.value && !sidebarOpen.value ? '0px' : 'var(--sidebar-width)',
)

// Never collapsed below `md`, whatever the stored preference says: down there
// the panel is a drawer at full width, and a rail laid over the page would be
// a third shape the desk does not have. Writable so the widget can set it --
// it is only drawn above `md`, so the getter's floor is never in its way.
const collapsed = computed({
	get: () => !isMobile.value && sidebarCollapsed.value,
	set: (value) => {
		sidebarCollapsed.value = value
	},
})

const route = useRoute()
const router = useRouter()

const { colorScheme, setColorScheme } = useColorScheme()

// The open page says which workspace we are in -- a page belongs to exactly one
// (see `workspaceFor`). The fallback is the first workspace this user has, which
// is what the two landing paths sit on while they decide where to send you.
const workspace = computed<Workspace>(() => workspaceFor(route))

// Keyed by route prefix, not by app: Requests spans two doctypes, and "Open in
// desk" should land on the one whose section is on screen.
const DESK_ROUTES: [prefix: string, deskPath: string][] = [
	// The profile page itself is one employee record, not the list of them.
	['/profile', '/app/employee'],
	['/requests/leave', '/app/leave-application'],
	['/requests/expenses', '/app/expense-claim'],
	['/requests/procurement', '/app/procurement-request'],
]

// A full page load, not a router push: the desk is a different app served off
// the same site.
function openDesk() {
	const match = DESK_ROUTES.find(([prefix]) => route.path.startsWith(prefix))
	window.location.href = match ? match[1] : '/app'
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

// Where the desk's own footer badge goes: this person's User record, for a
// person who can open it. `name` is the user id, which is an email for
// everyone but Administrator, so it has to be encoded. `/app` rather than
// `/desk`, like the routes above -- Frappe forwards it, and has kept
// forwarding it across two renames of the desk.
const userDeskUrl = computed(() => `/app/user/${encodeURIComponent(user.value.name)}`)

// The menu items that leave for the desk, spread in only when they lead
// somewhere: for a user whose roles do not open it every one of them is a
// refusal page. The apps screen is one of them -- `/apps` redirects to `/desk`
// (frappe/hooks.py, `website_redirects`). What is left for such a user is this
// app's own workspaces, which is the whole of what they can reach.
function deskOnly<T>(...items: T[]): T[] {
	return hasDeskAccess.value ? items : []
}

// Workspaces, where the desk lists a workspace's siblings -- here the rest of
// this app's, with the two destinations that are not workspaces under a
// divider: the apps screen, and this app's page in the desk.
//
// The row itself is conditional, which is why this builds the submenu before
// deciding: a menu item that opens onto nothing is a dead end, and somebody
// with one workspace and no desk to leave for has nothing to list under it.
const workspacesItem = computed(() => {
	const submenu = [
		// Only the workspaces this user can actually open, and never the one they
		// are in. Each lands on its own first row, which is a row they have --
		// that is what made the workspace available.
		...availableWorkspaces.value
			.filter((item) => item !== workspace.value)
			.map((item) => ({
				label: item.title,
				icon: item.icon,
				onClick: () => {
					const home = homeOf(item)
					if (home) router.push(home)
				},
			})),
		// The group goes with its contents rather than standing empty: the menu
		// draws a border for it, and a divider under the last workspace with
		// nothing after it is a line across the bottom of the menu.
		...deskOnly({
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
		}),
	]

	if (!submenu.length) return []
	return [{ label: 'Workspaces', icon: 'lucide-layout-dashboard', submenu }]
})

// The desk's header menu (`SidebarHeader.dropdown_items`) as `user_menu.js`
// leaves it: the navigation, and nothing else -- the rest has moved to the
// user badge's menu below.
const menuItems = computed(() => [
	// Desktop is the desk's own name for its home.
	...deskOnly({
		label: 'Desktop',
		icon: 'lucide-home',
		onClick: () => {
			window.location.href = '/app'
		},
	}),
	...workspacesItem.value,
	{
		// Website Settings' Website Button Target, falling back to the site root.
		// Not the home page: that one setting also decides where a login lands.
		label: 'Website',
		icon: 'lucide-globe',
		onClick: () => {
			window.open(websiteUrl.value)
		},
	},
])

const sessionDefaultsOpen = ref(false)

// A Navbar Settings row, followed the way the desk's menu follows one: a path
// on the site in place, anything else in a new tab (the server has already
// said which). A row into the desk is a refusal page for somebody whose roles
// do not open it, so for them it is not offered.
function navbarLinks(links: NavbarLink[]) {
	return links
		.filter((link) => hasDeskAccess.value || !/^\/(app|desk)(\/|$)/.test(link.url))
		.map((link) => ({
			label: link.label,
			onClick: () => {
				if (link.new_tab) window.open(link.url, '_blank')
				else window.location.href = link.url
			},
		}))
}

// The desk badge's menu (`commons/public/js/user_menu.js`), section for
// section: your User record; Display, Session Defaults, Help, the Navbar
// Settings rows, Reload; Logout. What the desk has and this app cannot carry
// is left out rather than stubbed -- Toggle Full Width and Toggle Sidebar
// under Display (the scheme is the one display choice here), the Help rows
// that are desk dialogs (About, Keyboard Shortcuts), and Edit Sidebar. The
// server drops the Help and settings rows that are desk JavaScript; see
// `commons/commons_core/user_menu.py`.
const userMenuItems = computed(() => {
	const help = navbarLinks(userMenu.value.help)

	return [
		// Your own User record, which is what the badge did before it had a menu.
		// "My Settings" is Frappe's own name for that destination.
		...deskOnly({
			group: '',
			hideLabel: true,
			options: [
				{
					label: 'My Settings',
					icon: 'lucide-user',
					onClick: () => {
						window.location.href = userDeskUrl.value
					},
				},
			],
		}),
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
				// The desk's condition too: only while Session Default Settings
				// lists something to default.
				...(userMenu.value.session_defaults.length
					? [
							{
								label: 'Session Defaults',
								icon: 'lucide-sliders-horizontal',
								onClick: () => {
									sessionDefaultsOpen.value = true
								},
							},
						]
					: []),
				...(help.length ? [{ label: 'Help', icon: 'lucide-info', submenu: help }] : []),
				...navbarLinks(userMenu.value.settings),
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
	]
})
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

/*
  The desk's collapse widget, from `.sidebar-toggle-btn` in
  frappe/public/scss/desk/sidebar.scss: a 24px circle centred on the border
  (half of it hanging past the column's edge, hence `-12px`) at the height the
  desk puts it, which is just clear of the user badge in both apps.

  `--surface-sidebar` is transparent in dark mode -- the same thing the drawer
  rule below deals with -- and a circle cut out of the border needs to be
  filled, so in that theme it paints the colour the sidebar is borrowing.
*/
.app-sidebar__collapse {
	position: absolute;
	right: -12px;
	bottom: 80px;
	z-index: 1023;
	display: flex;
	align-items: center;
	justify-content: center;
	width: 24px;
	height: 24px;
	border: 1px solid var(--sidebar-border-color);
	border-radius: 50%;
	background-color: var(--surface-sidebar);
	box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
	color: var(--ink-gray-6);
	opacity: 0;
	visibility: hidden;
	transition: opacity 0.15s ease, visibility 0.15s ease;
}

[data-theme='dark'] .app-sidebar__collapse {
	background-color: var(--surface-base);
}

.app-sidebar__collapse:hover {
	background-color: var(--sidebar-hover-color);
}

/*
  Shown on hover, like the desk's -- and on focus, which the desk's is not: a
  control that appears only under a pointer is one a keyboard cannot reach.
*/
.app-sidebar-shell:hover .app-sidebar__collapse,
.app-sidebar__collapse:focus-visible {
	opacity: 1;
	visibility: visible;
}

/*
  The desk's `transition-property: none` for the same state. A drawer that is
  in the layout one frame and over it the next has nothing to animate between,
  and frappe-ui's 300ms width transition would otherwise play on every open.
*/
.app-sidebar--drawer {
	transition-property: none;
}

/*
  `--surface-sidebar` is fully transparent in dark mode -- the sidebar and the
  base surface are the same colour there, so frappe-ui simply lets the painted
  body show through. A drawer is not on the body, it is over the page, so in
  that one state it has to paint the colour it was borrowing.
*/
[data-theme='dark'] .app-sidebar--drawer {
	background-color: var(--surface-base);
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
