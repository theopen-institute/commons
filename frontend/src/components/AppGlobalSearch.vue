<template>
	<!-- Global Search: the documents half of the desk's search, on Ctrl+G.

       The desk opens this one at `size: "extra-large"`, which is Bootstrap's
       `.modal-xl` at 1140px; `6xl` is 1152. Same 32px from the top as the bar,
       and `bare` for the same reason -- what goes inside is the desk's own
       body, and it wears the same input row (see index.css). -->
	<Dialog v-model:open="globalSearchOpen" size="6xl" padding-top="0px" bare>
		<Dialog.Title as-child>
			<h2 class="sr-only">Global Search</h2>
		</Dialog.Title>

		<div class="flex max-h-[80vh] flex-col">
			<div class="app-search__row">
				<span class="app-search__icon">
					<span class="lucide-search size-4" aria-hidden="true" />
				</span>
				<input
					ref="input"
					v-model="query"
					type="text"
					class="app-search__input"
					placeholder="Search"
					autofocus
					autocomplete="off"
					spellcheck="false"
					aria-label="Global search"
					@keydown="onKeydown"
				/>
				<LoadingIndicator v-if="loading" class="size-4 shrink-0 text-ink-gray-5" />
				<div class="app-search__divider" />
			</div>

			<!-- The DocType filter bar. Present only for somebody who can read
           Global Search Settings, which is where the list of doctypes comes
           from -- the desk's bar disappears the same way, and inferring the
           filters from whatever the last query returned would change them
           under the reader after every search. -->
			<div
				v-if="searchableDoctypes.length"
				class="flex flex-wrap items-center gap-1.5 border-b border-outline-gray-1 px-3 py-2 mt-1"
			>
				<button
					v-for="pill in pills"
					:key="pill.doctype || 'all'"
					type="button"
					class="rounded-md px-2 py-1 text-p-sm"
					:class="
						filter === pill.doctype
							? 'bg-surface-gray-3 text-ink-gray-9'
							: 'text-ink-gray-6 hover:bg-surface-gray-2'
					"
					@click="applyFilter(pill.doctype)"
				>
					{{ pill.label }}
				</button>

				<Dropdown :options="doctypeMenu" align="start">
					<template #item-suffix="{ item }">
						<button
							v-if="item.doctype"
							type="button"
							class="text-ink-gray-5 hover:text-ink-gray-8"
							:aria-label="item.pinned ? `Unpin ${item.doctype}` : `Pin ${item.doctype}`"
							@click.stop="togglePin(item)"
						>
							<span
								:class="[item.pinned ? 'lucide-pin-off' : 'lucide-pin', 'size-3.5']"
								aria-hidden="true"
							/>
						</button>
					</template>
					<button
						type="button"
						class="flex items-center gap-1 rounded-md px-2 py-1 text-p-sm text-ink-gray-6 hover:bg-surface-gray-2"
					>
						<span class="lucide-menu size-3.5" aria-hidden="true" />
						More
					</button>
				</Dropdown>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
				<!-- The desk's empty state, with the two things it tells you there:
             that `&` joins terms, and how to get back to the bar. -->
				<div
					v-if="!query.trim() || query.trim().length < 2"
					class="py-12 text-center text-ink-gray-5"
				>
					<p class="text-base">Search for anything</p>
					<p class="mt-2 text-p-sm">Use ampersand to match multiple terms (e.g. Marie&amp;John)</p>
					<p class="mt-1 flex items-center justify-center gap-1.5 text-p-sm">
						<kbd class="app-search__key app-search__key--text">{{ modKey }}K</kbd>
						to open the search bar
					</p>
				</div>

				<div v-else-if="loading && !sets.length" class="py-12 text-center text-p-sm text-ink-gray-5">
					Searching…
				</div>

				<!-- Before "No results": a search that failed found nothing because it
				     never ran, and saying otherwise sends somebody off to create a
				     record that already exists. -->
				<div v-else-if="searchError" class="py-12 text-center text-p-sm">
					<p class="text-ink-red-3">The search could not be run.</p>
					<p class="mt-1 text-ink-gray-5">{{ searchError }}</p>
				</div>

				<div v-else-if="!sets.length" class="py-12 text-center text-p-sm text-ink-gray-5">
					No results found
				</div>

				<section v-for="set in sets" :key="set.title" class="mb-6 last:mb-0">
					<h3 class="mb-2 text-base-medium text-ink-gray-8">
						{{ set.title }} ({{ set.results.length }}
						{{ set.results.length === 1 ? 'result' : 'results' }})
					</h3>

					<!-- The one thing allowed to scroll sideways: a hit can carry any
               number of matched fields, and the panel behind it must not. -->
					<div class="overflow-x-auto rounded-lg border border-outline-gray-1">
						<table class="w-full text-left text-p-sm">
							<thead class="bg-surface-gray-1 text-ink-gray-5">
								<tr>
									<th class="px-3 py-2 font-normal">Name</th>
									<th
										v-for="column in columnsFor(set)"
										:key="column"
										class="px-3 py-2 font-normal"
									>
										{{ column }}
									</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="result in set.results"
									:key="result.value"
									class="border-t border-outline-gray-1 align-top"
								>
									<td class="px-3 py-2">
										<a
											:href="hrefOf(result)"
											class="flex items-center gap-2 text-ink-gray-8 hover:underline"
											:title="result.label"
										>
											<img
												v-if="result.image"
												:src="result.image"
												alt=""
												class="size-5 shrink-0 rounded-full object-cover"
											/>
											<!-- Escaped in `highlightTerms`; the only tags are its
                           own `<mark>`s. -->
											<span v-html="highlightTerms(result.label, keywords)" />
										</a>
									</td>
									<td
										v-for="column in columnsFor(set)"
										:key="column"
										class="px-3 py-2 text-ink-gray-7"
										v-html="cell(result, column)"
									/>
								</tr>
							</tbody>
						</table>
					</div>

					<Button
						v-if="!exhausted.has(set.title)"
						class="mt-2"
						size="sm"
						:loading="loadingMore === set.title"
						@click="showMore(set)"
					>
						Show more
					</Button>
				</section>
			</div>
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Button, Dialog, Dropdown, LoadingIndicator, toast } from 'frappe-ui'
import {
	ensureAllowedDoctypes,
	getGlobalResults,
	globalSearchFieldColumns,
	globalSearchKeywords,
	globalSearchOpen,
	highlightTerms,
	modKey,
	openSearch,
	parseGlobalSearchFields,
	pinDoctype,
	pinnedDoctypes,
	searchableDoctypes,
	unpinDoctype,
	unpinnedDoctypes,
	type GlobalResult,
	type GlobalResultSet,
} from '@/data/search'

/** How many more rows a "Show more" asks for. `SearchDialog.more_count`. */
const MORE_COUNT = 20

/** How many values of one field are shown before the rest are summarised.
 *  `GLOBAL_SEARCH_FIELD_INLINE_PREVIEW_LIMIT`. */
const FIELD_PREVIEW_LIMIT = 3

const input = ref<HTMLInputElement | null>(null)

const query = ref('')
/** What the results on screen were fetched for. Kept apart from `query` so the
 *  highlighting does not race ahead of the rows it is marking. */
const keywords = ref('')
const filter = ref('')
const sets = ref<GlobalResultSet[]>([])
const exhausted = ref(new Set<string>())
const loading = ref(false)
const loadingMore = ref('')
/** Why the last search came back with nothing to show, when it failed. */
const searchError = ref('')

/**
 * Which search the rows on screen belong to.
 *
 * Every fetch takes a number and only the latest one is allowed to write its
 * results, which is the ordinary fix for a search box: a slow query for "ram"
 * must not land on top of a fast one for "ramesh" typed after it.
 */
let sequence = 0

// The desk's 300ms, which is a different number from the bar's 50ms for a good
// reason: this one is a database query, and the bar is a list already in memory.
let pending: ReturnType<typeof setTimeout> | null = null

/** What the last fetch was started for. `SearchDialog.current_keyword`, and it
 *  is there for the same reason: opening this dialog writes the text handed
 *  over from the bar into the box, which looks exactly like typing it, and
 *  without this the same search would be run twice -- once now and once when
 *  the debounce catches up. */
let requested = ''

watch(query, () => {
	if (pending) clearTimeout(pending)
	if (query.value.trim() === requested) return
	pending = setTimeout(run, 300)
})

watch(globalSearchOpen, (open) => {
	if (!open) {
		if (pending) clearTimeout(pending)
		sequence++
		return
	}
	query.value = globalSearchKeywords.value
	filter.value = ''
	void ensureAllowedDoctypes()
	run()
	nextTick(() => {
		const field = input.value
		if (!field) return
		field.focus({ preventScroll: true })
		if (field.value.length) field.select()
	})
})

async function run() {
	const text = query.value.trim()
	const ticket = ++sequence
	requested = text

	if (text.length < 2) {
		keywords.value = ''
		sets.value = []
		exhausted.value = new Set()
		searchError.value = ''
		loading.value = false
		return
	}

	loading.value = true
	try {
		const found = await getGlobalResults(text, 0, null, filter.value)
		if (ticket !== sequence) return
		keywords.value = text
		sets.value = found
		exhausted.value = new Set()
		searchError.value = ''
	} catch (problem) {
		if (ticket !== sequence) return
		// The last search's rows cleared, not left standing: under a box that now
		// says something else they read as this search's answer.
		keywords.value = text
		sets.value = []
		exhausted.value = new Set()
		searchError.value = (problem as Error)?.message || 'Try again in a moment.'
	} finally {
		if (ticket === sequence) loading.value = false
	}
}

async function showMore(set: GlobalResultSet) {
	loadingMore.value = set.title
	const ticket = sequence
	try {
		const found = await getGlobalResults(
			keywords.value,
			set.results.length,
			MORE_COUNT,
			set.title,
		)
		if (ticket !== sequence) return
		const more = found[0]?.results ?? []
		set.results.push(...more)
		// A short page is the last one. Said by the count rather than by asking
		// again, so the reader is not offered a button that returns nothing.
		if (more.length < MORE_COUNT) exhausted.value = new Set([...exhausted.value, set.title])
	} catch {
		// The rows already shown are still right; only the extra page is missing.
		if (ticket === sequence) toast.error('Could not load more results')
	} finally {
		if (ticket === sequence) loadingMore.value = ''
	}
}

function applyFilter(doctype: string) {
	filter.value = doctype
	run()
}

/** "All", then one chip per pinned doctype -- and the doctype being filtered
 *  on, if it is not among them, so the bar always shows what is in force. */
const pills = computed(() => {
	const rows = [{ doctype: '', label: 'All' }]
	for (const doctype of pinnedDoctypes.value) rows.push({ doctype, label: doctype })
	if (filter.value && !pinnedDoctypes.value.includes(filter.value)) {
		rows.push({ doctype: filter.value, label: filter.value })
	}
	return rows
})

interface DoctypeMenuItem {
	label: string
	doctype: string
	pinned: boolean
	onClick: () => void
}

/** The overflow menu, in the desk's two groups: what is pinned, and the rest. */
const doctypeMenu = computed(() => [
	{
		group: 'Pinned',
		options: pinnedDoctypes.value.map((doctype) => menuItem(doctype, true)),
	},
	{
		group: 'Other',
		options: unpinnedDoctypes.value.map((doctype) => menuItem(doctype, false)),
	},
])

function menuItem(doctype: string, pinned: boolean): DoctypeMenuItem {
	return { label: doctype, doctype, pinned, onClick: () => applyFilter(doctype) }
}

function togglePin(item: DoctypeMenuItem) {
	if (item.pinned) unpinDoctype(item.doctype)
	else pinDoctype(item.doctype)
}

/** The columns one doctype's hits need, cached per render pass by Vue's own
 *  computed on `sets` -- see `globalSearchFieldColumns` for what decides them. */
const columnsBySet = computed(() => {
	const found = new Map<string, string[]>()
	for (const set of sets.value) found.set(set.title, globalSearchFieldColumns(set.results))
	return found
})

function columnsFor(set: GlobalResultSet): string[] {
	return columnsBySet.value.get(set.title) ?? []
}

function hrefOf(result: GlobalResult): string {
	return result.destination.kind === 'away' ? result.destination.href : '#'
}

/**
 * One field's values for one row, marked.
 *
 * Past the preview limit the tail is summarised rather than printed, which is
 * what keeps a document with forty matching child rows from owning the table.
 */
function cell(result: GlobalResult, column: string): string {
	const values = parseGlobalSearchFields(result.content)[column] ?? []
	if (!values.length) return ''

	const shown = values.slice(0, FIELD_PREVIEW_LIMIT).map((value) => highlightTerms(value, keywords.value))
	if (values.length > FIELD_PREVIEW_LIMIT) {
		const rest = values.length - FIELD_PREVIEW_LIMIT
		shown[shown.length - 1] += ` <span class="text-ink-gray-5">and ${rest} more</span>`
	}
	return shown.join('<br>')
}

// Ctrl/Cmd+K goes back to the bar carrying what has been typed --
// `open_awesomebar_from_global_search_shortcut`.
function onKeydown(event: KeyboardEvent) {
	if (event.key.toLowerCase() !== 'k' || !(event.ctrlKey || event.metaKey)) return
	event.preventDefault()
	// Stopped here, so the app-wide binding in `App.vue` does not also fire and
	// reopen this dialog with an empty box a moment after it handed its text on.
	event.stopPropagation()
	openSearch(query.value.trim())
}
</script>
