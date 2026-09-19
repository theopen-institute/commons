<template>
	<!-- The Awesome Bar.

       `bare` strips frappe-ui's card chrome, because what goes inside is the
       desk's own modal body: an input row over a divider, a list, and a row of
       key hints. `xl` is 576px against the desk's 575 (`$modal-md`), and
       `padding-top="0px"` puts the panel 32px from the top of the window
       against the desk's 28 (`.modal-dialog`'s `margin: 1.75rem auto`) --
       frappe-ui's own `position="top"` is 20vh down the page, which is
       somewhere else entirely.

       The measurements the rows and the footer are drawn to are in index.css,
       with the desk files they came from. -->
	<Dialog v-model:open="searchOpen" size="xl" padding-top="0px" bare>
		<Dialog.Title as-child>
			<h2 class="sr-only">Search</h2>
		</Dialog.Title>

		<div class="app-search__row">
			<span class="app-search__icon">
				<span class="lucide-search size-4" aria-hidden="true" />
			</span>
			<input
				ref="input"
				v-model="query"
				type="text"
				class="app-search__input"
				placeholder="Search or type a command"
				autofocus
				autocomplete="off"
				spellcheck="false"
				aria-label="Search"
				@keydown.down.prevent="move(1)"
				@keydown.up.prevent="move(-1)"
				@keydown.enter.prevent="choose($event)"
				@keydown="onKeydown"
			/>
			<!-- Only the document search can keep anybody waiting; the rest of the
           list is already in memory. A spinner over the whole panel would say
           the bar was busy when it is not. -->
			<LoadingIndicator v-if="loadingDocuments" class="size-4 shrink-0 text-ink-gray-5" />
			<div class="app-search__divider" />
		</div>

		<ul ref="list" class="app-search__list">
			<li v-if="!options.length" class="px-2 py-6 text-center text-p-sm text-ink-gray-5">
				{{ query.trim() ? 'No results' : 'Nothing here yet' }}
			</li>

			<li
				v-for="(option, position) in options"
				:key="position"
				:data-active="position === active ? '' : undefined"
				class="app-search__item flex items-center gap-2"
				@mouseenter="active = position"
				@click="select(option, $event)"
			>
				<span class="min-w-0 flex-1">
					<!-- The marked-up label and snippet. Safe as HTML because every
               piece of both was escaped where it was built: the only tags in
               here are the `<mark>`, `<b>` and `<span>` this app put around
               what matched. See `fuzzySearch`, `highlightTerms` and
               `escapeHtml`. -->
					<span class="app-search__label block truncate" v-html="option.label" />
					<span
						v-if="option.description"
						class="app-search__description block truncate"
						v-html="option.description"
					/>
				</span>
				<span v-if="option.hint" class="app-search__hint">{{ option.hint }}</span>
			</li>
		</ul>

		<!-- The desk's footer, hint for hint and glyph for glyph: two arrows, the
         return key, and the two shortcuts that move between this dialog and
         Global Search written out as they are typed. -->
		<div class="app-search__footer">
			<span class="app-search__help">
				<kbd class="app-search__key">
					<span class="lucide-arrow-up size-3" aria-hidden="true" />
				</kbd>
				<kbd class="app-search__key">
					<span class="lucide-arrow-down size-3" aria-hidden="true" />
				</kbd>
				to navigate
			</span>
			<span class="app-search__help">
				<kbd class="app-search__key">
					<span class="lucide-corner-down-left size-3" aria-hidden="true" />
				</kbd>
				to select
			</span>
			<span class="app-search__help">
				<kbd class="app-search__key app-search__key--text">{{ modKey }}K</kbd>
				to close
			</span>
			<span v-if="canSearchDesk" class="app-search__help">
				<kbd class="app-search__key app-search__key--text">{{ modKey }}G</kbd>
				to open Global Search
			</span>
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Dialog, LoadingIndicator } from 'frappe-ui'
import {
	canSearchDesk,
	deduplicate,
	ensureDeskDoctypes,
	getDeskDocuments,
	goTo,
	modKey,
	openGlobalSearch,
	searchKeywords,
	searchOpen,
	searchOptions,
	type SearchResult,
} from '@/data/search'

/** The desk's own debounce on the bar's input handler. Everything it answers is
 *  already in memory; this is only there to stop a rebuild per keystroke. */
const LOCAL_DELAY = 50

/** And the desk's debounce on a search that reaches the database, from its
 *  Global Search dialog. */
const DOCUMENT_DELAY = 300

const input = ref<HTMLInputElement | null>(null)
const list = ref<HTMLElement | null>(null)

const query = ref('')
const active = ref(0)

/** The rows this browser can build on its own: this app's pages, the desk's
 *  doctypes, what you created before, where you have been. */
const local = ref<SearchResult[]>([])

/** And the documents, which only the server knows. Held separately so a slow
 *  query never delays the rows that were ready immediately -- the list is
 *  usable the moment you stop typing, and fills in underneath. */
const documents = ref<SearchResult[]>([])

const loadingDocuments = ref(false)

/** The two lists as one, on one scale. Merged rather than concatenated: a
 *  document and a page can be the same destination, and the higher-scoring row
 *  should be the one that survives. */
const options = computed(() =>
	deduplicate([...local.value, ...documents.value]).sort((left, right) => right.index - left.index),
)

let localPending: ReturnType<typeof setTimeout> | null = null
let documentPending: ReturnType<typeof setTimeout> | null = null

/** Which search the documents on screen belong to; only the newest may write
 *  its results. The ordinary fix for a search box -- a slow query for "ram"
 *  must not land on top of a fast one for "ramesh" typed after it. */
let documentTicket = 0

/** What the document search was last started for, so that text handed over
 *  from Global Search is not searched for twice: writing it into the box looks
 *  exactly like typing it. `SearchDialog.current_keyword` does the same job. */
let documentsFor: string | null = null

function refreshLocal(immediate = false) {
	if (localPending) clearTimeout(localPending)
	const run = () => {
		local.value = searchOptions(query.value)
		active.value = 0
	}
	if (immediate) run()
	else localPending = setTimeout(run, LOCAL_DELAY)
}

function searchDocuments(immediate = false) {
	const keywords = query.value.trim().replace(/\s\s+/g, ' ')
	if (keywords === documentsFor) return

	if (documentPending) clearTimeout(documentPending)
	documentsFor = keywords

	// Cleared now rather than when the next answer arrives: documents for what
	// was typed three keystrokes ago are worse than none.
	documents.value = []
	documentTicket++

	if (!canSearchDesk.value || keywords.length <= 1) {
		loadingDocuments.value = false
		return
	}

	const ticket = documentTicket
	loadingDocuments.value = true
	const run = async () => {
		try {
			const found = await getDeskDocuments(keywords)
			if (ticket === documentTicket) documents.value = found
		} catch {
			// A failed document search leaves the rest of the bar working, which
			// is the whole reason the two lists are fetched apart.
			if (ticket === documentTicket) documents.value = []
		} finally {
			if (ticket === documentTicket) loadingDocuments.value = false
		}
	}

	if (immediate) void run()
	else documentPending = setTimeout(run, DOCUMENT_DELAY)
}

watch(query, () => {
	refreshLocal()
	searchDocuments()
})

// Opening is the one time the list has to be right before the frame is drawn,
// so it is built synchronously rather than 50ms later.
watch(searchOpen, (open) => {
	if (!open) {
		if (localPending) clearTimeout(localPending)
		if (documentPending) clearTimeout(documentPending)
		documentTicket++
		documentsFor = null
		loadingDocuments.value = false
		return
	}

	query.value = searchKeywords.value
	refreshLocal(true)
	searchDocuments(true)

	// The desk's doctypes are fetched once and answer instantly after that. The
	// first open is the one that has to wait for them, and it rebuilds when
	// they land rather than showing a bar that is quietly missing half of what
	// it can offer.
	void ensureDeskDoctypes().then(() => {
		if (searchOpen.value) refreshLocal(true)
	})

	nextTick(() => {
		const field = input.value
		if (!field) return
		field.focus({ preventScroll: true })
		// Text handed over from Global Search arrives selected, so the next
		// keystroke replaces it instead of appending to it -- the desk's
		// `focus_global_search_input` does the same.
		if (field.value.length) field.select()
	})
})

function move(delta: number) {
	if (!options.value.length) return
	active.value = (active.value + delta + options.value.length) % options.value.length
	nextTick(scrollActiveIntoView)
}

function scrollActiveIntoView() {
	list.value?.querySelector('[data-active]')?.scrollIntoView({ block: 'nearest' })
}

function choose(event: KeyboardEvent) {
	const option = options.value[active.value]
	if (option) select(option, event)
}

function select(option: SearchResult, event: MouseEvent | KeyboardEvent) {
	// Closed first: a row that navigates within the app would otherwise leave
	// the dialog standing over the page it just asked for.
	searchOpen.value = false
	if (option.onSelect) {
		option.onSelect()
		return
	}
	if (option.destination) goTo(option.destination, event)
}

// Ctrl/Cmd+G hands what has been typed to Global Search, which is the desk's
// `open_global_search_from_navbar_shortcut`. Bound here rather than globally
// because it only means this while the bar has the keyboard.
function onKeydown(event: KeyboardEvent) {
	if (event.key.toLowerCase() !== 'g' || !(event.ctrlKey || event.metaKey)) return
	event.preventDefault()
	// Stopped here, so the app-wide binding in `App.vue` does not also fire and
	// reopen this dialog with an empty box a moment after it handed its text on.
	event.stopPropagation()
	openGlobalSearch(query.value.trim())
}
</script>
