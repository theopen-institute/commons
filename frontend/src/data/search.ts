import { computed, ref, watch } from 'vue'
import { call } from 'frappe-ui'
import { fuzzy_match } from '@fuzzy-match'
import router from '@/router'
import { availableWorkspaces, visibleEntries, type NavEntry } from '@/data/shell'
import { requestSections, type RequestSection } from '@/data/requests/sections'
import { hasDeskAccess, user } from '@/data/session'

/**
 * The Awesome Bar, ported.
 *
 * The desk's search box is two dialogs: a bar you summon with Ctrl+K that
 * answers out of what the browser already knows -- pages, things you can
 * create, where you have just been -- and a Global Search panel on Ctrl+G that
 * asks the server for documents. This module is the first one's sources and the
 * second one's fetching, and the two components in `components/AppSearch*.vue`
 * are the dialogs.
 *
 * It is a port rather than an import, and the reason is worth stating because
 * the rest of this app leans the other way wherever it can. `AwesomeBar` and
 * `SearchDialog` are not modules: they are classes assigned onto the `frappe`
 * global inside the desk bundle, built on jQuery, a Bootstrap modal and
 * Awesomplete, and they read every one of their result lists out of
 * `frappe.boot` -- `can_read`, `can_create`, `all_reports`, `page_info`,
 * `desktop_icons`. None of that exists on a page outside `/app`, and loading
 * the desk bundle to get it would bring jQuery, Bootstrap, socket.io and a
 * stylesheet that fights this app's. So the behaviour is reproduced and the
 * pieces that are genuinely portable are borrowed: the scorer is frappe's own
 * file (see `vite.config.js`), and the document search is frappe's own
 * endpoint.
 *
 * What is reproduced, function for function, is the *shape* of an answer:
 * `frappe/public/js/frappe/ui/toolbar/search_utils.js` builds a list of rows
 * carrying a label with the matched letters marked, a plain value, a score, and
 * somewhere to go; `awesome_bar.js` concatenates its sources, deduplicates on
 * route, sorts by score, and shows recents when the box is empty. All of that
 * is below, under the names it has there.
 *
 * The bar searches the desk as well as this app, and that is the point of it.
 * Somebody raising an expense claim in here should be able to type a supplier's
 * name and land on the supplier, without first working out that the answer is
 * in a different application. So the rows are three kinds:
 *
 * - this app's pages, built from the sidebar;
 * - the desk's doctypes -- "Employee List", "New ToDo" -- built the way
 *   `get_doctypes` builds them, from the four permission lists the desk gets in
 *   its boot and this app asks `commons.better_navigation.search.desk_doctypes` for;
 * - documents, from the same Global Search the desk's own dialog uses.
 *
 * All three sort against each other on one scale, which is what stops the bar
 * from feeling like two searches stapled together.
 *
 * Three deliberate differences from the desk's version:
 *
 * - No reports, workspaces, dashboards or desktop icons. Those are the desk's
 *   own furniture rather than a way to reach a record, and the bar is already
 *   the longest list in this app.
 * - No calculator and no random password. Both are `eval` on whatever you
 *   typed, and a string from the address bar reaching `eval` in this app is not
 *   a trade this feature is worth making.
 * - Recents are this browser's. The desk keeps them per user in `Route History`
 *   and boots them in; those are desk routes, and writing SPA paths into the
 *   same table would put rows in the desk's bar that its router cannot open.
 *
 * And one the other way: no `awesomebar_search` hook call. The hook exists to
 * let apps add rows to the *desk's* bar, and the only app answering it on this
 * site is this one -- so calling it here would fetch, over the network, the
 * pages the sidebar is already holding.
 */

/** Where a row goes when you pick it. */
export type Destination =
  /** A route in this app. Pushed, so the SPA never reloads to reach itself. */
  | { kind: 'page'; to: string }
  /** Anywhere else -- a desk form, a URL. A full page load. */
  | { kind: 'away'; href: string }

/** One row of the bar, in the shape `search_utils.js` builds them. */
export interface SearchResult {
  /** What the row reads, as HTML: the matched letters wrapped in `<mark>`.
   *  Everything that goes in is escaped on the way -- see `fuzzySearch`. */
  label: string
  /** The same text, plain. What the row is identified and announced by. */
  value: string
  /** A second line under the label, plain text. */
  description?: string
  /** The score this row sorted on. Higher is better; see `fuzzySearch`. */
  index: number
  /** The bar's own word for the kind of row this is -- 'Page', 'New', 'List'.
   *
   *  Never drawn, here or in the desk: a row says what it is in its label. It
   *  is what a trailing word filters on; see `setSpecifics`. */
  type?: string
  /** A word shown on the row's right, muted.
   *
   *  Only documents set it, and they set it to their doctype -- which is what
   *  the desk's own results table puts beside a hit, and the one thing a bare
   *  document title does not say. Everything else says what it is in its label
   *  ("Employee List", "New Supplier"), the way the desk writes them. */
  hint?: string
  destination?: Destination
  /** For a row that does something instead of going somewhere. */
  onSelect?: () => void
  /** Whether this row came from somewhere you have already been, which changes
   *  how it survives deduplication. */
  recent?: boolean
}

/** A row's score, and its text with the matched letters marked. */
export interface FuzzyResult {
  score: number
  markedString: string
}

const HTML_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

/** Text as it can safely be handed to `v-html`. */
export function escapeHtml(text: string): string {
  return String(text ?? '').replace(/[&<>"']/g, (char) => HTML_ESCAPES[char])
}

/**
 * How well `item` matches `keywords`, and `item` with the matches marked.
 *
 * `frappe.search.utils.fuzzy_search`, less the translation retry: the desk
 * scores the translated string and falls back to the untranslated one on a
 * miss, and this app has no translator in the browser to produce the first of
 * those.
 *
 * The marking is the reason this returns a string rather than a number. The
 * scorer already knows which letters matched, so highlighting them costs
 * nothing extra and does not risk a second, differently-behaved matcher
 * disagreeing with the first about what was found. Unlike the desk's, this
 * escapes as it goes: these labels are configuration -- a workspace row's
 * label is typed by a System Manager -- and they end up inside `v-html`.
 */
export function fuzzySearch(keywords = '', item = ''): FuzzyResult {
  const [, score, matches] = fuzzy_match(keywords, item)
  if (!score) return { score: 0, markedString: escapeHtml(item) }

  const matched = new Set(matches)
  let marked = ''
  let run = ''
  const flush = () => {
    if (!run) return ''
    const wrapped = `<mark>${escapeHtml(run)}</mark>`
    run = ''
    return wrapped
  }
  for (let index = 0; index < item.length; index++) {
    if (matched.has(index)) {
      run += item[index]
    } else {
      marked += flush()
      marked += escapeHtml(item[index])
    }
  }
  marked += flush()
  return { score, markedString: marked }
}

/*
 * Where you have been, and how often.
 *
 * The desk boots both lists in -- `boot.user.recent` and
 * `boot.frequently_visited_links`, the second one counted from the
 * `Route History` doctype -- and this app keeps its own in `localStorage` for
 * the reason given at the top of the file. One record serves both questions:
 * a count answers "frequent" and a timestamp answers "recent", and keeping two
 * would mean two things to keep in step.
 *
 * Paths, not labels. A row is resolved back to a nav entry when it is read, so
 * a renamed page comes back under its new name and one that has been taken out
 * of the workspace -- or that this user has lost the permission for -- stops
 * being offered at all, without anything having to clean up after it.
 */

/**
 * Per user, not per browser. `localStorage` belongs to the machine, and on a
 * shared one the next person to sign in was offered the last one's recent and
 * frequent pages — which, for somebody in HR or accounts, is a list of whose
 * records they had open.
 */
const VISITS_KEY = 'commons-search-visits'

function visitsKey(): string {
  return `${VISITS_KEY}:${user.value.name}`
}

// The unkeyed table from before, which could be anybody's. Dropped rather than
// migrated: there is no telling whose history it is.
try {
  localStorage.removeItem(VISITS_KEY)
} catch {
  // Private mode or blocked storage: there is nothing stored to leak either.
}

/** How many paths are remembered. The desk's own recents cap is 20; this holds
 *  more because it is also the frequency table, and a count is only useful
 *  once it has had time to add up. */
const VISITS_LIMIT = 50

interface Visit {
  count: number
  /** Epoch milliseconds of the last visit. */
  at: number
}

type Visits = Record<string, Visit>

function readVisits(): Visits {
  try {
    const raw = localStorage.getItem(visitsKey())
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? (parsed as Visits) : {}
  } catch {
    // Private mode, cleared storage, or something else's key under this name.
    return {}
  }
}

function writeVisits(visits: Visits) {
  try {
    localStorage.setItem(visitsKey(), JSON.stringify(visits))
  } catch {
    // Quota or private mode. Losing the history is not worth an error.
  }
}

/** The visit table, as the dialog reads it. A ref so the list under an open
 *  dialog is not stale the moment you navigate from it. */
const visits = ref<Visits>(readVisits())

// Read again once the user is known: in development the session arrives by a
// call rather than with the page, and until it has this would be Guest's table.
watch(
  () => user.value.name,
  () => {
    visits.value = readVisits()
  },
)

/**
 * Remember that this path was opened.
 *
 * Called from the router, after each navigation -- see `App.vue`. Trimmed to
 * `VISITS_LIMIT` by dropping the least recently seen, not the least frequent:
 * a page you used heavily a year ago is exactly the row that should stop being
 * offered first.
 */
export function recordVisit(path: string) {
  const previous = visits.value[path]
  const next: Visits = {
    ...visits.value,
    [path]: { count: (previous?.count ?? 0) + 1, at: Date.now() },
  }

  const paths = Object.keys(next)
  if (paths.length > VISITS_LIMIT) {
    paths
      .sort((left, right) => next[right].at - next[left].at)
      .slice(VISITS_LIMIT)
      .forEach((stale) => delete next[stale])
  }

  visits.value = next
  writeVisits(next)
}

/** Every sidebar row this user actually has, across every workspace. */
function navEntries(): NavEntry[] {
  return availableWorkspaces.value.flatMap(visibleEntries)
}

/** A nav entry's address as a path, which is what a visit is keyed by. */
function pathOf(entry: NavEntry): string {
  return router.resolve(entry.to).path
}

/** The nav entries this user has, keyed by path. */
const entriesByPath = computed(() => {
  const found = new Map<string, NavEntry>()
  for (const entry of navEntries()) found.set(pathOf(entry), entry)
  return found
})

/*
 * The sources. One function per list the desk builds, under the desk's name for
 * it, returning the desk's shape.
 */

/** The score a page row carries over its match, from `get_doctypes`'s `option`
 *  ordering: a list sits just above the "new one of these" row beside it. */
const PAGE_ORDER = 0.05
const CREATE_ORDER = 0.015

/**
 * This app's pages. `frappe.search.utils.get_pages`, over the sidebar.
 *
 * Only the rows this user has: `availableWorkspaces` has already dropped the
 * workspaces they cannot open and `visibleEntries` the rows within one they
 * cannot, which is the same permission answer the sidebar draws itself from.
 * A search result that opens a page saying you may not be here is worse than
 * no result.
 */
export function getPages(keywords: string): SearchResult[] {
  const out: SearchResult[] = []
  for (const entry of navEntries()) {
    const { score, markedString } = fuzzySearch(keywords, entry.label)
    if (!score) continue

    out.push({
      type: 'Page',
      label: `Open ${markedString}`,
      value: `Open ${entry.label}`,
      index: score + PAGE_ORDER,
      destination: { kind: 'page', to: pathOf(entry) },
    })

    // The desk offers "New X" beside the list of X whenever you may create one,
    // without being asked -- the single most-used thing the bar does. The
    // sections are the only pages here that create anything.
    if (entry.section?.canCreate.value) {
      out.push(newRequestRow(entry.section, markedString, entry.label, score + CREATE_ORDER))
    }
  }
  return out
}

/**
 * "New leave request", when the box starts with the word new.
 *
 * `frappe.search.utils.get_creatables`, scoring what follows the word rather
 * than the whole of it -- so "new lea" ranks against "Leave Request" and is not
 * dragged down by three letters that were never meant to match.
 */
export function getCreatables(keywords: string): SearchResult[] {
  const [first] = keywords.split(' ')
  if (first.toLowerCase() !== 'new') return []

  const rest = keywords.slice(4)
  const out: SearchResult[] = []
  for (const section of requestSections) {
    if (!section.canCreate.value) continue
    const { score, markedString } = fuzzySearch(rest, section.label)
    if (!score) continue
    out.push(newRequestRow(section, markedString, section.label, 1 + score))
  }
  return out
}

/**
 * One "New X" row.
 *
 * The page opens the dialog, not this module: the form belongs to the page it
 * is on, and a search bar that mounted its own copy would be a second one to
 * keep in step. So the row asks for the page with `?new=1` and the page does
 * the rest -- see `MyLeave.vue` and the two beside it.
 */
function newRequestRow(
  section: RequestSection,
  markedLabel: string,
  plainLabel: string,
  index: number,
): SearchResult {
  return {
    type: 'New',
    label: `New ${markedLabel}`,
    value: `New ${plainLabel}`,
    index,
    destination: {
      kind: 'page',
      to: `${router.resolve({ name: section.mineRoute }).path}?new=1`,
    },
  }
}

/*
 * The desk's doctypes.
 *
 * `frappe.search.utils.get_doctypes`, over the four permission lists the desk
 * receives in its boot and this app has to ask for -- see
 * `commons.better_navigation.search.desk_doctypes`. Fetched once, lazily, the first time the bar
 * is opened: it is a few tens of kilobytes on a site with ERPNext and HRMS
 * installed, which is not worth paying for on a page load that may never
 * search anything.
 */

interface DeskDoctypes {
  /** Everything with a list view this user may read. The master list. */
  search: string[]
  /** Everything they may create. */
  create: string[]
  /** Singles -- a document rather than a list. */
  singles: string[]
  /** Doctypes whose default view is a tree. */
  trees: string[]
}

const NO_DESK_DOCTYPES: DeskDoctypes = { search: [], create: [], singles: [], trees: [] }

const deskDoctypes = ref<DeskDoctypes>(NO_DESK_DOCTYPES)
let deskDoctypesPromise: Promise<DeskDoctypes> | null = null

export function ensureDeskDoctypes(): Promise<DeskDoctypes> {
  // The endpoint refuses anyone who cannot open the desk, and would be a
  // pointless round trip on every open of the bar for exactly those users.
  if (!canSearchDesk.value) return Promise.resolve(NO_DESK_DOCTYPES)
  if (!deskDoctypesPromise) {
    deskDoctypesPromise = call<DeskDoctypes>('commons.better_navigation.search.desk_doctypes')
      .then((found) => {
        deskDoctypes.value = found ?? NO_DESK_DOCTYPES
        return deskDoctypes.value
      })
      .catch(() => {
        // The endpoint refuses anyone who cannot open the desk, and the bar is
        // perfectly useful without these rows. Not an error worth showing.
        deskDoctypes.value = NO_DESK_DOCTYPES
        return deskDoctypes.value
      })
  }
  return deskDoctypesPromise
}

/** `frappe.router.slug`: how a doctype reads in a desk URL. */
function slug(name: string): string {
  return name.toLowerCase().replace(/ /g, '-')
}

/**
 * How much a desk row is marked down against a page of this app's.
 *
 * Only enough to break a tie. "Leave Request" and "Leave Application" score
 * within a few points of each other on the word "leave", and in this app the
 * page you are standing in should win that -- but a strong desk match still
 * beats a weak page one, which is the whole reason the two are on one scale.
 * The desk marks its own foreign rows down the same way: `get_marketplace_apps`
 * scores at `score * 0.8`.
 */
const DESK_DAMPENING = 0.9

/**
 * The desk's doctypes, as rows. `frappe.search.utils.get_doctypes`.
 *
 * Empty until `ensureDeskDoctypes` has answered, and empty for good for anyone
 * who cannot open the desk -- there is no point offering a route that will
 * refuse them.
 */
export function getDoctypes(keywords: string): SearchResult[] {
  const { search, create, singles, trees } = deskDoctypes.value
  const creatable = new Set(create)
  const isTree = new Set(trees)
  const out: SearchResult[] = []

  // A Single is one document, so it is offered as itself rather than as a list.
  // Its name is its doctype's, which is what makes the route look doubled.
  for (const doctype of singles) {
    const { score, markedString } = fuzzySearch(keywords, doctype)
    if (!score) continue
    out.push({
      label: markedString,
      value: doctype,
      index: (score + PAGE_ORDER) * DESK_DAMPENING,
      destination: {
        kind: 'away',
        href: `/app/${slug(doctype)}/${encodeURIComponent(doctype)}`,
      },
    })
  }

  for (const doctype of search) {
    const { score, markedString } = fuzzySearch(keywords, doctype)
    if (!score) continue

    // "New X" sits just under the list of X, the way the desk offers it --
    // without being asked, and only where the server would accept one.
    if (creatable.has(doctype)) {
      out.push({
        type: 'New',
        label: `New ${markedString}`,
        value: `New ${doctype}`,
        index: (score + CREATE_ORDER) * DESK_DAMPENING,
        destination: { kind: 'away', href: `/app/${slug(doctype)}/new` },
      })
    }

    const tree = isTree.has(doctype)
    const kind = tree ? 'Tree' : 'List'
    // "Price List List" is nobody's idea of a row. The desk drops the second
    // word when the doctype already ends in it.
    const suffix = kind === 'List' && doctype.endsWith('List') ? '' : ` ${kind}`
    out.push({
      type: kind,
      label: `${markedString}${suffix}`,
      value: `${doctype}${suffix}`,
      index: (score + PAGE_ORDER) * DESK_DAMPENING,
      destination: {
        kind: 'away',
        href: tree ? `/app/${slug(doctype)}/view/tree` : `/app/${slug(doctype)}`,
      },
    })
  }

  return out
}

/**
 * Where you have just been. `frappe.search.utils.get_recent_pages`.
 *
 * Matched by substring rather than fuzzily, which is the desk's choice too:
 * a recent row is one you already know the name of, and fuzzy matching a short
 * list you have seen before mostly produces rows you did not mean.
 */
export function getRecentPages(keywords: string): SearchResult[] {
  const needle = (keywords ?? '').toLowerCase().replace(/-/g, ' ')
  const out: SearchResult[] = []
  const seen = Object.entries(visits.value).sort(([, left], [, right]) => right.at - left.at)

  for (const [path] of seen) {
    const entry = entriesByPath.value.get(path)
    // A path that no longer resolves to a row this user has: renamed away,
    // taken out of the workspace, or a permission withdrawn. Not offered, and
    // left in storage -- it costs nothing there and comes back if the row does.
    if (!entry) continue
    if (needle && !entry.label.toLowerCase().replace(/-/g, ' ').includes(needle)) continue

    out.push({
      type: 'Recent',
      label: `<b>${escapeHtml(entry.label)}</b>`,
      value: entry.label,
      // The desk's flat 80 for every recent row: within the list the order is
      // recency, and against the other lists a recent row should sit below a
      // strong name match and above a weak one.
      index: 80,
      recent: true,
      destination: { kind: 'page', to: path },
    })
  }
  return out
}

/**
 * Where you go most. `frappe.search.utils.get_frequent_links`.
 *
 * What an empty box shows, and it falls back to plain recents when nothing has
 * been counted yet -- the desk's own fallback, and what a first visit gets.
 */
export function getFrequentLinks(): SearchResult[] {
  const out: SearchResult[] = []
  for (const [path, visit] of Object.entries(visits.value)) {
    const entry = entriesByPath.value.get(path)
    if (!entry) continue
    out.push({
      type: 'Frequent',
      label: escapeHtml(entry.label),
      value: entry.label,
      // The visit count, as the desk uses it: these rows only ever sort against
      // each other, because this list is shown on its own.
      index: visit.count,
      destination: { kind: 'page', to: path },
    })
  }
  if (!out.length) return getRecentPages('')
  return out.sort((left, right) => right.index - left.index)
}

/**
 * The row that opens Global Search. `AwesomeBar.make_global_search`.
 *
 * Index 100, above any fuzzy match, because it is the answer to "none of these
 * is what I meant" and pressing Enter on a box you have just typed into should
 * do something predictable.
 */
function globalSearchRow(keywords: string): SearchResult {
  return {
    label: `Search for <b>${escapeHtml(keywords)}</b>`,
    value: `Search for ${keywords}`,
    index: 100,
    type: 'Search',
    onSelect: () => openGlobalSearch(keywords),
  }
}

/** A destination as one comparable string, or null for a row that goes
 *  nowhere. The desk joins its route array for the same purpose. */
function destinationKey(destination: Destination | undefined): string | null {
  if (!destination) return null
  return destination.kind === 'page' ? destination.to : destination.href
}

/**
 * `AwesomeBar.deduplicate`: one row per destination, keeping the best.
 *
 * Rows that go nowhere are always kept -- two of them are two different
 * actions, whatever they are called. A recent row never displaces the row it
 * duplicates, which is the desk's rule and the right one: the ranked row says
 * what the page is for, the recent one only says you were there.
 */
export function deduplicate(options: SearchResult[]): SearchResult[] {
  const out: SearchResult[] = []
  const at = new Map<string, number>()

  for (const option of options) {
    const key = destinationKey(option.destination)
    if (key === null) {
      out.push(option)
      continue
    }
    const already = at.get(key)
    if (already === undefined) {
      at.set(key, out.length)
      out.push(option)
    } else if (out[already].index < option.index && !option.recent) {
      out[already] = option
    }
  }
  return out
}

/** Every local source, concatenated, deduplicated and ranked.
 *  `AwesomeBar.build_options`. */
export function buildOptions(keywords: string): SearchResult[] {
  const options = [
    ...getCreatables(keywords),
    ...getPages(keywords),
    ...getDoctypes(keywords),
    ...getRecentPages(keywords),
  ]
  return deduplicate(options).sort((left, right) => right.index - left.index)
}

/**
 * `AwesomeBar.set_specifics`: a trailing word that names a kind of row.
 *
 * Typing "leave new" searches for "leave" and keeps only the rows whose type
 * starts with "new". It is undiscoverable and it is in the desk, and anybody
 * who has the habit would notice it missing.
 */
function setSpecifics(keywords: string, suffix: string): SearchResult[] {
  return buildOptions(keywords).filter(
    (option) => option.type && option.type.toLowerCase().indexOf(suffix.toLowerCase()) === 0,
  )
}

/**
 * How many local rows the bar will show.
 *
 * Awesomplete caps the desk's bar at 99 and this is the same idea with one
 * difference that matters. Two letters can match several hundred of the
 * doctypes on a site running ERPNext and HRMS, and the documents are merged in
 * *after* this list -- so a cap on the merged list would let a vague query
 * crowd out the records, which are the reason anybody typed a vague query. The
 * cap therefore lands on the local rows alone, and the documents are always
 * offered underneath them.
 */
const BAR_RESULT_LIMIT = 50

/**
 * What the bar shows for what has been typed. `AwesomeBar`'s input handler.
 *
 * The local half only -- this app's pages, the desk's doctypes, recents. The
 * documents are fetched separately and merged by the dialog, because they are a
 * round trip and these are not.
 *
 * Under two characters it is the empty state -- recents and frequents -- which
 * is also what an untouched box shows, because that is the same answer to the
 * same question.
 */
export function searchOptions(text: string): SearchResult[] {
  const keywords = (text ?? '').trim().replace(/\s\s+/g, ' ')

  if (keywords.length <= 1) {
    return deduplicate([...getRecentPages(keywords), ...getFrequentLinks()]).slice(
      0,
      BAR_RESULT_LIMIT,
    )
  }

  // Offered only where it leads somewhere: for a user who cannot open the desk
  // there is no document view to send them to, and a top row that silently
  // does nothing when you press Enter is worse than one row fewer.
  const options: SearchResult[] = canSearchDesk.value ? [globalSearchRow(keywords)] : []
  const lastSpace = keywords.lastIndexOf(' ')
  if (lastSpace !== -1) {
    options.push(...setSpecifics(keywords.slice(0, lastSpace), keywords.slice(lastSpace + 1)))
  }
  options.push(...buildOptions(keywords))

  return deduplicate(options)
    .sort((left, right) => right.index - left.index)
    .slice(0, BAR_RESULT_LIMIT)
}

/*
 * Global Search: the documents half.
 *
 * `frappe.utils.global_search.search` is called directly rather than wrapped in
 * an endpoint of this app's, because there is nothing for a wrapper to add: it
 * already narrows to the doctypes a site has put in Global Search Settings,
 * intersects that with what this user may read, and then checks
 * `has_permission` on every document before returning it.
 */

/** One hit, in the shape `get_global_results` builds. */
export interface GlobalResult {
  /** The document's title, or its name where it has no title field. */
  label: string
  /** The document's name. */
  value: string
  /** The matching fields, as HTML with the search terms marked. */
  description: string
  /** The raw `__global_search` content, which the table view parses into
   *  columns -- see `parseGlobalSearchFields`. */
  content: string
  doctype: string
  image?: string | null
  /** The desk form this opens. */
  destination: Destination
}

/** Hits of one doctype, which is how the panel groups them. */
export interface GlobalResultSet {
  title: string
  results: GlobalResult[]
}

/** What `frappe.utils.global_search.search` returns per row. */
interface GlobalSearchRow {
  doctype: string
  name: string
  content: string
  title?: string
  image?: string | null
}

/** How long a snippet may run, and how much of one field it may spend --
 *  `make_description`'s own numbers. */
const DESCRIPTION_MAX_LENGTH = 300
const DESCRIPTION_FIELD_LENGTH = 120

/**
 * The matching fields of one hit, as a snippet. `make_description`.
 *
 * `__global_search` content is one string: `label : value` segments joined by
 * `|||`. Only the segments containing what you searched for are shown, each one
 * trimmed around the match if it is long, and the whole thing stops at
 * `DESCRIPTION_MAX_LENGTH`.
 */
function makeDescription(content: string, docName: string, keywords: string): string {
  const parts = (content ?? '').split(' ||| ')
  const fields: string[] = []
  let used = 0

  for (const part of parts) {
    if (part.toLowerCase().indexOf(keywords.toLowerCase()) === -1) continue

    let separatorAt = part.indexOf(' &&& ')
    let valueFrom = separatorAt + 5
    if (separatorAt === -1) {
      separatorAt = part.indexOf(' : ')
      valueFrom = separatorAt + 3
    }
    if (separatorAt === -1) continue

    const fieldName = part.slice(0, separatorAt)
    let fieldValue = part.slice(valueFrom)

    if (fieldValue.length > DESCRIPTION_FIELD_LENGTH) {
      // Keep the half-field either side of the match rather than the first
      // 120 characters, which is often nowhere near what was found.
      const half = DESCRIPTION_FIELD_LENGTH / 2
      // Case-insensitively, as the filter above matched: a case-sensitive
      // search missed "Kathmandu" for "kathmandu" and cut around position -1.
      // Nought when the match was in the field's name rather than its value.
      const at = Math.max(fieldValue.toLowerCase().indexOf(keywords.toLowerCase()), 0)
      const head = at < half ? fieldValue.slice(0, at) : `...${fieldValue.slice(at - half, at)}`
      const tail = at + half < fieldValue.length ? '...' : ''
      fieldValue = `${head}${fieldValue.slice(at, at + half)}${tail}`
    }

    let remaining = DESCRIPTION_MAX_LENGTH - used
    used += fieldName.length + fieldValue.length + 2

    if (used < DESCRIPTION_MAX_LENGTH) {
      const text = `<span class="text-ink-gray-5">${escapeHtml(fieldName)}: </span>${highlightTerms(
        fieldValue,
        keywords,
      )}`
      if (!fields.includes(text) && docName !== fieldValue) fields.push(text)
      continue
    }

    // Out of room. Enough for the field name means a trimmed value after it;
    // otherwise say only that there was more.
    if (fieldName.length < remaining) {
      remaining -= fieldName.length
      const clipped = fieldValue.slice(0, remaining)
      fields.push(
        `<span class="text-ink-gray-5">${escapeHtml(fieldName)}: </span>${highlightTerms(
          `${clipped.slice(0, clipped.lastIndexOf(' '))} ...`,
          keywords,
        )}`,
      )
    } else {
      fields.push('...')
    }
    break
  }

  return fields.join(', ')
}

/**
 * `__global_search` content as { field label: values }.
 * `frappe.search.utils.parse_global_search_fields`.
 *
 * What the results table's columns are built from. The synthetic `name` segment
 * is skipped: the document's name has a column of its own.
 */
export function parseGlobalSearchFields(content: string): Record<string, string[]> {
  const fields: Record<string, string[]> = {}
  if (!content) return fields

  for (const raw of content.split('|||')) {
    const part = (raw ?? '').trim()
    if (!part.length) continue

    let separator = ' : '
    let at = part.indexOf(separator)
    if (at === -1) {
      separator = ' &&& '
      at = part.indexOf(separator)
    }
    if (at === -1) continue

    const label = part.slice(0, at).trim()
    const value = part.slice(at + separator.length).trim()
    if (!label.length || /^name$/i.test(label)) continue
    if (!fields[label]) fields[label] = []
    fields[label].push(value)
  }
  return fields
}

/**
 * The columns a set of hits needs, in the order they were first seen.
 * `frappe.search.utils.global_search_field_columns_for_results`.
 */
export function globalSearchFieldColumns(results: GlobalResult[]): string[] {
  const columns: string[] = []
  const seen = new Set<string>()
  for (const result of results ?? []) {
    for (const column of Object.keys(parseGlobalSearchFields(result.content))) {
      if (seen.has(column)) continue
      seen.add(column)
      columns.push(column)
    }
  }
  return columns
}

/**
 * `text` with every search term wrapped in `<mark>`.
 * `frappe.search.utils.highlight_global_search_terms`.
 *
 * Terms are split on `&`, which is Global Search's own way of asking for two
 * words at once (`Marie&John`).
 */
export function highlightTerms(text: string, keywords: string): string {
  const source = text == null ? '' : String(text)
  const terms = keywords
    .split('&')
    .map((part) => part.trim())
    .filter(Boolean)
  if (!terms.length) return escapeHtml(source)

  const pattern = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  try {
    const expression = new RegExp(`(${pattern.join('|')})`, 'gi')
    return source
      .split(expression)
      .map((part) => {
        const isMatch = part && terms.some((term) => part.toLowerCase() === term.toLowerCase())
        return isMatch ? `<mark>${escapeHtml(part)}</mark>` : escapeHtml(part)
      })
      .join('')
  } catch {
    return escapeHtml(source)
  }
}

/**
 * Documents matching `keywords`, grouped by doctype.
 * `frappe.search.utils.get_global_results`.
 *
 * `start` and `limit` are only sent past the first page, the way the desk sends
 * them, so the endpoint keeps its own default page size for the first ask.
 */
export async function getGlobalResults(
  keywords: string,
  start = 0,
  limit: number | null = null,
  doctype = '',
): Promise<GlobalResultSet[]> {
  const args: Record<string, unknown> = { text: keywords }
  if (doctype) args.doctype = doctype
  if (start > 0) {
    args.start = start
    args.limit = limit && limit > 0 ? limit : 20
  }

  const rows = await call<GlobalSearchRow[]>('frappe.utils.global_search.search', args)
  if (!rows?.length) return []

  const sets: GlobalResultSet[] = []
  const byDoctype = new Map<string, GlobalResultSet>()

  for (const row of rows) {
    const result: GlobalResult = {
      label: row.title || row.name,
      value: row.name,
      description: makeDescription(row.content, row.name, keywords),
      content: row.content,
      doctype: row.doctype,
      image: row.image,
      destination: {
        kind: 'away',
        href: `/app/${slug(row.doctype)}/${encodeURIComponent(row.name)}`,
      },
    }

    const existing = byDoctype.get(row.doctype)
    if (existing) {
      existing.results.push(result)
    } else {
      const set = { title: row.doctype, results: [result] }
      byDoctype.set(row.doctype, set)
      sets.push(set)
    }
  }
  return sets
}

/**
 * How high the best document sits.
 *
 * Below "Search for …" at 100, and below a page or a doctype whose *name* is
 * what you typed -- typing "leave" means the leave page far more often than it
 * means a document with the word in it. Above a weak name match, so that typing
 * somebody's name, which matches no name at all, still fills the bar with them.
 */
const DOCUMENT_INDEX_BASE = 90

/** How many documents the bar shows before deferring to the dialog. The desk's
 *  bar shows none at all and its dialog shows everything; this is the middle,
 *  and it is a bar rather than a results page. */
const DOCUMENT_LIMIT = 10

/**
 * Documents, as bar rows. The inline half of Global Search.
 *
 * Server order is kept rather than re-scored. `global_search.search` ranks by
 * full-text relevance and walks the site's configured doctype priority, and a
 * fuzzy score over the title would throw that away -- the match is often in a
 * field the title never mentions, which would score zero and sink the row that
 * was the reason the search matched.
 */
export async function getDeskDocuments(keywords: string): Promise<SearchResult[]> {
  if (!canSearchDesk.value) return []

  const sets = await getGlobalResults(keywords)
  const out: SearchResult[] = []

  for (const set of sets) {
    for (const result of set.results) {
      if (out.length >= DOCUMENT_LIMIT) return out
      out.push({
        label: highlightTerms(result.label, keywords),
        // The doctype is part of the value because a name on its own is not
        // unique across doctypes, and this is what the row is announced by.
        value: `${result.doctype} ${result.value}`,
        // The fields that matched, or -- where the hit was on the title alone
        // -- the document's own name, which a title field otherwise hides.
        description:
          result.description ||
          (result.value === result.label ? '' : escapeHtml(result.value)),
        index: DOCUMENT_INDEX_BASE - out.length,
        hint: result.doctype,
        destination: result.destination,
      })
    }
  }
  return out
}

/*
 * Which doctypes the filter bar offers, and which of them are pinned.
 *
 * `SearchDialog.ensure_global_search_allowed_doctypes` and the pin functions
 * beside it, carried over including their failure mode: `Global Search
 * Settings` is a System Manager's document, so for most users the read is
 * refused and the bar is left with "All" alone. The desk does the same, and the
 * alternative -- inferring the list from whatever the last search returned --
 * would offer a different set of filters after every query.
 */

const PINS_KEY = 'global-search-pinned-doctypes'

/** How many of the settings' rows are pinned for somebody who has never said
 *  otherwise. `GLOBAL_SEARCH_VISIBLE_DT_LIMIT` in `search.js`. */
const DEFAULT_PIN_COUNT = 5

/** The doctypes Global Search Settings allows, in its own order. Empty until
 *  asked for, and empty for good if the read is refused. */
const allowedDoctypes = ref<string[]>([])
let allowedDoctypesPromise: Promise<string[]> | null = null

interface GlobalSearchSettings {
  allowed_in_global_search?: { document_type: string; idx: number }[]
}

export function ensureAllowedDoctypes(): Promise<string[]> {
  if (!allowedDoctypesPromise) {
    allowedDoctypesPromise = call<GlobalSearchSettings>('frappe.client.get', {
      doctype: 'Global Search Settings',
      name: 'Global Search Settings',
    })
      .then((settings) => {
        const rows = [...(settings?.allowed_in_global_search ?? [])]
        rows.sort((left, right) => (left.idx || 0) - (right.idx || 0))
        allowedDoctypes.value = rows.map((row) => row.document_type).filter(Boolean)
        return allowedDoctypes.value
      })
      .catch(() => {
        // Almost always "you may not read this Single", which is not an error
        // worth showing: it means this user gets the unfiltered bar.
        allowedDoctypes.value = []
        return allowedDoctypes.value
      })
  }
  return allowedDoctypesPromise
}

/** The stored pins, and whether this browser has ever set any. The difference
 *  matters: never-set means "the first few of whatever the site allows", and
 *  an empty array means somebody unpinned them all. */
function readPinState(): { explicit: boolean; pins: string[] } {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(PINS_KEY)
  } catch {
    raw = null
  }
  if (raw === null) return { explicit: false, pins: [] }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return { explicit: true, pins: [] }
    return { explicit: true, pins: parsed.filter(Boolean) }
  } catch {
    return { explicit: true, pins: [] }
  }
}

const pinState = ref(readPinState())

function writePins(pins: string[]) {
  const unique = Array.from(new Set(pins.filter(Boolean)))
  try {
    localStorage.setItem(PINS_KEY, JSON.stringify(unique))
  } catch {
    // Quota or private mode.
  }
  pinState.value = { explicit: true, pins: unique }
}

/** Every doctype the site allows in Global Search. */
export const searchableDoctypes = computed(() => allowedDoctypes.value)

/** The pinned doctypes, less any the site no longer allows.
 *  `current_effective_pins_list`. */
export const pinnedDoctypes = computed(() => {
  const allowed = new Set(allowedDoctypes.value)
  const base = pinState.value.explicit
    ? pinState.value.pins
    : allowedDoctypes.value.slice(0, DEFAULT_PIN_COUNT)
  return base.filter((doctype) => allowed.has(doctype))
})

/** The rest of them, for the overflow menu. */
export const unpinnedDoctypes = computed(() =>
  allowedDoctypes.value.filter((doctype) => !pinnedDoctypes.value.includes(doctype)),
)

export function pinDoctype(doctype: string) {
  if (!doctype || !allowedDoctypes.value.includes(doctype)) return
  writePins([...pinnedDoctypes.value, doctype])
}

export function unpinDoctype(doctype: string) {
  writePins(pinnedDoctypes.value.filter((pinned) => pinned !== doctype))
}

/*
 * The two dialogs' open state.
 *
 * Module state rather than provide/inject, for the reason `data/sidebar.ts`
 * gives about the drawer: the dialogs are mounted by `App.vue` and summoned
 * from a keystroke, a sidebar button, and a row inside the other dialog.
 */

/**
 * How this machine writes the modifier. `frappe.utils.is_mac()`, and the same
 * two spellings the bar's footer uses either side of it: a Mac gets the glyph
 * with nothing between, everything else gets the word and a plus.
 */
export const modKey = /mac/i.test(navigator.platform) ? '⌘' : 'Ctrl+'

export const searchOpen = ref(false)
export const globalSearchOpen = ref(false)

/** What each dialog was opened with, so Ctrl+K and Ctrl+G hand the typed text
 *  to each other the way the desk's two do. */
export const searchKeywords = ref('')
export const globalSearchKeywords = ref('')

/** Whether the desk is worth offering at all -- its doctypes, its documents,
 *  and the Global Search dialog. The bar's own name for `hasDeskAccess`. */
export const canSearchDesk = hasDeskAccess

export function openSearch(keywords = '') {
  searchKeywords.value = keywords
  globalSearchOpen.value = false
  searchOpen.value = true
}

export function openGlobalSearch(keywords = '') {
  if (!canSearchDesk.value) return
  globalSearchKeywords.value = keywords
  searchOpen.value = false
  globalSearchOpen.value = true
  void ensureAllowedDoctypes()
}

/** Follow a row. Pushed inside the app, loaded outside it -- and a modified
 *  click opens a new tab, the way the desk's bar does. */
export function goTo(destination: Destination, event?: MouseEvent | KeyboardEvent) {
  const newTab = Boolean(event && (event.ctrlKey || event.metaKey))
  if (destination.kind === 'page') {
    if (newTab) {
      window.open(router.resolve(destination.to).href, '_blank')
      return
    }
    router.push(destination.to)
    return
  }
  if (newTab) {
    window.open(destination.href, '_blank')
    return
  }
  window.location.href = destination.href
}
