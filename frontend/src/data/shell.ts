import { computed, type ComputedRef } from 'vue'
import { useCall } from 'frappe-ui'
import { attendanceGate } from './attendance'
import type { RouteLocationNormalizedLoaded, RouteLocationRaw } from 'vue-router'
import { requestSection, type RequestSection, type RequestSectionKey } from './requests/sections'

/**
 * The shell: what this app is called, and which workspace's navigation you are in.
 *
 * Both used to be constants. The name over the sidebar was `SUITE_TITLE` and the
 * one workspace was an entry in an app registry, so a site that called its staff
 * area something else, or wanted two of them, was asking for a deploy. Both are
 * documents now -- `Commons Settings` and `Commons Workspace` -- and this module
 * is the browser's half of reading them.
 *
 * The split with the server is deliberate and worth stating, because it decides
 * where a question gets answered.
 *
 * The server says *which rows, in what order, under which heading, and what they
 * are called*. That is configuration, and it is the same for everyone on the
 * site.
 *
 * This module says *what a row opens, whether this user may open it, and what
 * the badge on it reads*. That is either code -- a route only the bundle knows
 * -- or a permission answer that is about the person rather than the site. A
 * server that filtered rows by permission would also have to answer four
 * permission questions before the page could paint, and the sidebar has never
 * needed it: a row this user cannot use is either hidden here or opens a page
 * that explains itself.
 *
 * The keys in `PAGES` are the contract. `commons/shell/pages.py` holds the same
 * set, and the two halves have to agree on them.
 */

/** One of the pages this app ships, as a workspace row may name it. */
export type PageKey = 'announcements' | 'statement' | 'attendance' | RequestSectionKey

/**
 * A permission answer a row waits on, for a page that is not a request section.
 *
 * The same two questions a section answers -- may this reader have the row, and
 * is that answer in yet -- without the rest of what a section is. Account
 * Balance needs neither and says so with nulls; the attendance register needs
 * both, because `Student Attendance` is readable by every student on the site
 * and the page is a whole cohort's marks on one screen. See
 * `commons.education_extensions.attendance.can_mark`, which is the server's
 * half of the same rule.
 */
interface PageGate {
  visible: ComputedRef<boolean>
  resolved: ComputedRef<boolean>
}

interface PageChrome {
  label: string
  icon: string
  to: RouteLocationRaw
  /** The route this page is lit on. Two for a request section -- see `section`. */
  routeName: string
  /** The request section behind the row, for the ones that have one: its
   *  permission, its approvals tab, and the badge an approver reads. */
  section: RequestSection | null
  /** A permission answer the row waits on where a section is not what decides
   *  it. Null for a row offered to everybody. */
  gate: PageGate | null
}

function fromSection(key: RequestSectionKey): PageChrome {
  const section = requestSection(key)
  return {
    label: section.label,
    icon: section.icon,
    to: { name: section.mineRoute },
    routeName: section.mineRoute,
    section,
    gate: null,
  }
}

/**
 * What each shipped page is called and drawn with, and where it goes.
 *
 * Here rather than on the server for a build reason as much as a routing one:
 * Tailwind compiles an icon class only where it can read the literal name in
 * scanned source (see `commons/self_service/icons.py`). A workspace row may
 * still override either, and an override is held to that same palette.
 */
const PAGES: Record<PageKey, PageChrome> = {
  announcements: {
    label: 'Announcements',
    icon: 'lucide-megaphone',
    to: { name: 'Announcements' },
    routeName: 'Announcements',
    section: null,
    gate: null,
  },
  // No section, and so always visible. That is the same answer a self-service
  // row gets and it is the same argument: a page that says "you have no account
  // here" explains an empty balance far better than a missing row does, and
  // deciding otherwise would mean asking the server who this reader is before
  // the sidebar could draw itself.
  statement: {
    label: 'Account Balance',
    icon: 'lucide-wallet',
    to: { name: 'AccountBalance' },
    routeName: 'AccountBalance',
    section: null,
    gate: null,
  },
  // Gated, unlike the two above, and for the opposite reason to each of them.
  // Announcements and Account Balance are offered to everybody because the page
  // explains itself better than a missing row would; this one is a whole
  // cohort's attendance, and a student who may not mark it should not be
  // offered it. See `PageGate`.
  attendance: {
    label: 'Attendance',
    icon: 'lucide-clipboard-check',
    to: { name: 'AttendanceRegister' },
    routeName: 'AttendanceRegister',
    section: null,
    gate: attendanceGate,
  },
  leave: fromSection('leave'),
  expense: fromSection('expense'),
  procurement: fromSection('procurement'),
}

/** The mark a self-service row wears when its record names none -- the server's
 *  fallback too, and it has to survive a record saved before that field
 *  existed. */
const DEFAULT_RECORD_ICON = 'lucide-file-text'

/** The 32px mark at the top of the sidebar, for a workspace with no logo of its
 *  own: this app's, the same one the desk icon and the favicon wear. */
const DEFAULT_LOGO = '/assets/commons/images/commons-logo.svg'

/** The switcher mark for a workspace that names no icon. */
const DEFAULT_WORKSPACE_ICON = 'lucide-inbox'

/** What the sidebar says when the site has not named itself. The server's
 *  default as well; this one answers while the dev server is still asking. */
const DEFAULT_TITLE = 'Commons'

/** One sidebar row as the server sends it. */
interface ShellItem {
  kind: 'page' | 'record'
  /** A `PageKey`, or the doctype a self-service row opens. */
  key: string
  /** The self-service page's address. Null on a shipped page. */
  slug: string | null
  /** The heading this row is grouped under, or null for a row on its own. */
  group: string | null
  /** Null on a shipped page nobody overrode: this module's default wins. */
  label: string | null
  icon: string | null
}

interface ShellWorkspace {
  /** The document's name, or null for the workspace the app falls back to. */
  name: string | null
  title: string
  icon: string | null
  logo: string | null
  items: ShellItem[]
}

interface ShellData {
  title: string
  workspaces: ShellWorkspace[]
}

declare global {
  interface Window {
    shell?: ShellData
  }
}

// Same split as `session.ts` and `website.ts`: a production build has the www
// page's boot data on `window`, and the Vite dev server serves index.html
// without the Jinja pass, so there we ask.
const bootShell = window.shell

const shellCall = useCall<ShellData>({
  url: '/api/v2/method/commons.shell.api.get_shell',
  immediate: bootShell === undefined,
})

const shell = computed<ShellData>(() => bootShell ?? shellCall.data ?? { title: '', workspaces: [] })

/** Whether the shell is the site's answer rather than this module's placeholder. */
export const shellLoaded = computed(() => bootShell !== undefined || shellCall.isFinished)

/** What this app is called on this site. Read by the sidebar and the browser tab. */
export const title = computed(() => shell.value.title?.trim() || DEFAULT_TITLE)

/** One sidebar row, resolved: what it says, where it goes, and who may see it. */
export interface NavEntry {
  /** Unique within a workspace, and stable across reloads -- a list key. */
  id: string
  label: string
  icon: string
  group: string | null
  to: RouteLocationRaw
  /** The self-service slug this row opens, or null. */
  slug: string | null
  /** The request section behind the row, or null. Carries the approvals tab and
   *  the pending badge. */
  section: RequestSection | null
  /** The route name the row is lit on. A section adds its approvals tab. */
  routeName: string | null
  /** Whether this user has the row at all. */
  visible: () => boolean
  /** Whether that answer is in, so nothing flashes on the way to it. */
  resolved: () => boolean
}

export interface NavGroup {
  /** The heading, or null for rows that stand on their own. */
  label: string | null
  entries: NavEntry[]
}

export interface Workspace {
  name: string | null
  title: string
  icon: string
  logo: string
  entries: NavEntry[]
}

/** Stands in for a workspace while the dev server is still answering. Never
 *  rendered as a row -- it holds none -- but it keeps the header from having to
 *  null-check its way through the first paint. */
const EMPTY_WORKSPACE: Workspace = {
  name: null,
  title: '',
  icon: DEFAULT_WORKSPACE_ICON,
  logo: DEFAULT_LOGO,
  entries: [],
}

function entryFor(item: ShellItem): NavEntry | null {
  if (item.kind === 'record') {
    // A record row is always offered, permission or not: the page explains an
    // account with no record of its own far better than an absent row does.
    return {
      id: `record:${item.key}`,
      label: item.label ?? item.key,
      icon: item.icon ?? DEFAULT_RECORD_ICON,
      group: item.group,
      to: `/profile/${item.slug}`,
      slug: item.slug,
      section: null,
      routeName: null,
      visible: () => true,
      resolved: () => true,
    }
  }

  const page = PAGES[item.key as PageKey]
  // A key this bundle does not know is a server that has a page this build does
  // not. Dropped rather than drawn as a row that goes nowhere.
  if (!page) return null
  return {
    id: `page:${item.key}`,
    label: item.label ?? page.label,
    icon: item.icon ?? page.icon,
    group: item.group,
    to: page.to,
    slug: null,
    section: page.section,
    routeName: page.routeName,
    visible: () =>
      (!page.section || page.section.visible.value) && (!page.gate || page.gate.visible.value),
    resolved: () =>
      (!page.section || page.section.resolved.value) && (!page.gate || page.gate.resolved.value),
  }
}

/** Every workspace the site offers, in sidebar order. */
export const workspaces = computed<Workspace[]>(() =>
  shell.value.workspaces.map((row) => ({
    name: row.name,
    title: row.title,
    icon: row.icon ?? DEFAULT_WORKSPACE_ICON,
    logo: row.logo ?? DEFAULT_LOGO,
    entries: row.items.map(entryFor).filter((entry): entry is NavEntry => entry !== null),
  })),
)

/** The rows of one workspace this user actually has. */
export function visibleEntries(workspace: Workspace): NavEntry[] {
  return workspace.entries.filter((entry) => entry.visible())
}

/**
 * The visible rows, folded into the groups the sidebar draws.
 *
 * Consecutive rows sharing a heading are one group; a row with no heading
 * stands on its own. Folded after the invisible rows are dropped, so a group
 * whose every row belongs to someone else disappears rather than leaving a
 * labelled gap.
 */
export function navGroups(workspace: Workspace): NavGroup[] {
  const groups: NavGroup[] = []
  for (const entry of visibleEntries(workspace)) {
    const last = groups[groups.length - 1]
    if (last && last.label === entry.group) last.entries.push(entry)
    else groups.push({ label: entry.group, entries: [entry] })
  }
  return groups
}

/** Whether this user can open anything in this workspace -- what the switcher
 *  offers on. */
export function isAvailable(workspace: Workspace): boolean {
  return workspace.entries.some((entry) => entry.visible())
}

/** Whether every permission answer this workspace waits on is in. */
export function isResolved(workspace: Workspace): boolean {
  return shellLoaded.value && workspace.entries.every((entry) => entry.resolved())
}

/** Where the switcher lands: the first row of this workspace the user has. */
export function homeOf(workspace: Workspace): RouteLocationRaw | null {
  return visibleEntries(workspace)[0]?.to ?? null
}

/** The workspaces this user can actually open. */
export const availableWorkspaces = computed(() => workspaces.value.filter(isAvailable))

/** Whether every workspace has its permission answers, so an empty sidebar can
 *  be reported as empty rather than as still loading. */
export const shellResolved = computed(() => shellLoaded.value && workspaces.value.every(isResolved))

/**
 * Where `/requests` and the desk's apps-screen tile land.
 *
 * Null until the answers are in, so nothing redirects early. A page belongs to
 * one workspace, so "the first row of the first workspace this user has" is the
 * whole of the rule.
 */
export const landingRoute = computed<RouteLocationRaw | null>(() => {
  if (!shellResolved.value) return null
  for (const workspace of availableWorkspaces.value) {
    const home = homeOf(workspace)
    if (home) return home
  }
  return null
})

/**
 * Which workspace the open page belongs to.
 *
 * By the row that opens it -- the route's own page key, or the self-service slug
 * in its address -- which is why no page and no record type may sit in two
 * workspaces (`CommonsWorkspace.validate_rows`). A route that is in no
 * workspace at all, such as a landing redirect, falls back to the first one
 * this user has, so the header names somewhere real while it decides.
 */
export function workspaceFor(route: RouteLocationNormalizedLoaded): Workspace {
  const page = route.meta.page
  const slug = typeof route.params.slug === 'string' ? route.params.slug : null
  for (const workspace of workspaces.value) {
    for (const entry of workspace.entries) {
      if (page && entry.id === `page:${page}`) return workspace
      if (slug && entry.slug === slug) return workspace
    }
  }
  return availableWorkspaces.value[0] ?? workspaces.value[0] ?? EMPTY_WORKSPACE
}

/** Whether a row is the one the open page belongs to.
 *
 * Said explicitly rather than left to SidebarItem's own inference, which
 * compares route *names*: a request section is two routes and stays lit on its
 * approvals tab, and every self-service row resolves to one named route, so all
 * of them would light up whenever any one was open. */
export function isCurrentEntry(entry: NavEntry, route: RouteLocationNormalizedLoaded): boolean {
  if (entry.slug) return route.params.slug === entry.slug
  if (entry.section) {
    return route.name === entry.section.mineRoute || route.name === entry.section.approvalsRoute
  }
  return route.name === entry.routeName
}
