<!--
  A date field whose calendar can be read in Bikram Sambat.

  The value never changes shape: `modelValue` is `YYYY-MM-DD` Gregorian going in
  and coming out, the input shows a Gregorian date, and what reaches the server
  is what reached it before. The only thing the toggle changes is which calendar
  the grid is drawn in — so nothing downstream, on the wire or in the database,
  has to know this component exists.

  ## Why this is not frappe-ui's DatePicker

  `FormControl type="date"` dispatches to `frappe-ui`'s `DatePicker`, and that is
  what these dialogs used before. Its grid is `CalendarPanel`, which renders a
  cell as `cell.date.date()`, its header as `months[currentMonth]`, and moves the
  keyboard cursor with `cell.date.add(7, 'day')` — Gregorian at every level, from
  a `Dayjs` it derives itself. There is no prop or slot that changes any of that:
  the component's public slots are `trigger`, `prefix`, `suffix` and `actions`,
  and the calendar body is its own internal default slot.

  Reaching past that — importing `CalendarPanel` or `PickerShell` directly — was
  the alternative, and it is a worse bet than it looks: `frappe-ui`'s export map
  publishes only `"."`, so those paths are internal, and the dependency is pinned
  to a beta (`1.0.0-beta.63`) where internals are expected to move. A silent
  break on upgrade in a date field is an expensive thing to debug.

  So this composes the two primitives that *are* exported — `Popover` and
  `TextInput` — and owns the grid. `TextInput` carries the label, error, required
  marker and sizing, so the field is chrome-identical to the `FormControl`s
  beside it in the same dialog; the calendar's own buttons are plain elements
  wearing frappe-ui's design tokens, since they are 28px grid cells rather than
  anything `Button` is shaped for.
-->

<template>
	<Popover v-model:open="open" side="bottom" align="start" :offset="6" @close="onClose">
		<template #trigger>
			<div>
				<TextInput
					type="text"
					:model-value="draft"
					:label="label"
					:description="description"
					:error="error"
					:required="required"
					:disabled="disabled"
					:placeholder="placeholder"
					:size="size"
					:variant="variant"
					class="w-full"
					@update:model-value="draft = $event"
					@blur="commitTyped"
					@keydown.enter.prevent="commitTyped"
				/>
			</div>
		</template>

		<div class="w-60 p-2" @keydown.esc.stop.prevent="open = false">
			<!-- Calendar switch. Disabled rather than hidden when the visible date
           falls outside the Bikram Sambat table's span, so the control does not
           appear and disappear as someone pages through years. -->
			<div class="mb-2 flex items-center gap-1">
				<button
					v-for="option in MODES"
					:key="option.value"
					type="button"
					class="flex-1 rounded px-2 py-1 text-xs-medium transition-colors duration-100"
					:class="
						mode === option.value
							? 'bg-surface-gray-9 text-ink-base'
							: 'text-ink-gray-6 hover:bg-surface-gray-2'
					"
					:disabled="option.value === 'BS' && !bsAvailable"
					:aria-pressed="mode === option.value"
					@click="setMode(option.value)"
				>
					{{ option.label }}
				</button>
			</div>

			<!-- Month navigation -->
			<div class="mb-1 flex items-center justify-between">
				<button
					type="button"
					class="flex size-6 items-center justify-center rounded text-ink-gray-7 hover:bg-surface-gray-2"
					aria-label="Previous month"
					@click="step(-1)"
				>
					&lsaquo;
				</button>
				<span class="text-sm-medium text-ink-gray-8">{{ grid.header }}</span>
				<button
					type="button"
					class="flex size-6 items-center justify-center rounded text-ink-gray-7 hover:bg-surface-gray-2"
					aria-label="Next month"
					@click="step(1)"
				>
					&rsaquo;
				</button>
			</div>

			<div class="mb-1 flex items-center gap-0.5 text-xs-medium uppercase text-ink-gray-4">
				<div
					v-for="(name, index) in grid.weekdays"
					:key="index"
					class="flex size-7 items-center justify-center"
				>
					{{ name }}
				</div>
			</div>

			<div
				ref="gridRef"
				role="grid"
				aria-label="Calendar dates"
				class="flex flex-col gap-0.5"
			>
				<div v-for="(week, wi) in grid.weeks" :key="wi" role="row" class="flex gap-0.5">
					<template v-for="cell in week" :key="cell.key">
						<div v-if="!cell.iso" class="size-7" aria-hidden="true" />
						<button
							v-else
							type="button"
							role="gridcell"
							class="flex size-7 items-center justify-center rounded-4 text-sm transition-colors duration-100"
							:class="cellClass(cell)"
							:disabled="cell.disabled"
							:aria-selected="cell.isSelected"
							:aria-label="cell.title"
							:title="cell.title"
							:tabindex="cell.iso === tabStopIso ? 0 : -1"
							@click="choose(cell)"
							@keydown.left.prevent="moveFocus(-1)"
							@keydown.right.prevent="moveFocus(1)"
							@keydown.up.prevent="moveFocus(-7)"
							@keydown.down.prevent="moveFocus(7)"
							@keydown.enter.prevent="choose(cell)"
							@keydown.space.prevent="choose(cell)"
						>
							{{ cell.label }}
						</button>
					</template>
				</div>
			</div>

			<div
				class="mt-2 flex items-center justify-between border-t border-outline-gray-1 pt-2"
			>
				<button
					type="button"
					class="rounded px-2 py-1 text-xs text-ink-gray-7 hover:bg-surface-gray-2"
					@click="chooseIso(todayIso)"
				>
					{{ mode === 'BS' ? 'आज' : 'Today' }}
				</button>
				<!-- The same date in the calendar that is not on screen. The toggle is
             only useful if you can see the correspondence while you use it. -->
				<span class="text-xs tabular-nums text-ink-gray-5">{{ counterpart }}</span>
			</div>
		</div>
	</Popover>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Popover, TextInput } from 'frappe-ui'
import type { InputSize, InputVariant } from 'frappe-ui'
import {
	add_months,
	days_in_month,
	format as formatBs,
	from_gregorian,
	month_name,
	to_devanagari_digits,
	to_gregorian,
	weekday_name,
} from '@bikram/bikram_sambat.js'

type Mode = 'AD' | 'BS'

interface Cell {
	key: string
	/** Empty for the leading blanks that pad the first week. */
	iso: string
	label: string
	title: string
	isToday: boolean
	isSelected: boolean
	disabled: boolean
}

const MODES: Array<{ value: Mode; label: string }> = [
	{ value: 'AD', label: 'AD' },
	{ value: 'BS', label: 'वि.सं.' },
]

const AD_MONTHS = [
	'January',
	'February',
	'March',
	'April',
	'May',
	'June',
	'July',
	'August',
	'September',
	'October',
	'November',
	'December',
]
const AD_WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']

/** Remembered per browser: whoever prefers one calendar sets it once. */
const STORAGE_KEY = 'commons:date-picker-calendar'

const props = withDefaults(
	defineProps<{
		modelValue?: string
		label?: string
		description?: string
		error?: string
		required?: boolean
		disabled?: boolean
		placeholder?: string
		/** Bounds, as `YYYY-MM-DD`. Honoured in both calendars. */
		min?: string
		max?: string
		size?: InputSize
		variant?: InputVariant
	}>(),
	{
		modelValue: '',
		placeholder: 'YYYY-MM-DD',
		size: 'sm',
		variant: 'subtle',
	},
)

const emit = defineEmits<{
	'update:modelValue': [value: string]
	change: [value: string]
}>()

// ── Dates as calendar days ───────────────────────────────────────────────────
// `toIso` rather than `Date.prototype.toISOString`, which converts to UTC first
// and so reports the previous day for anyone east of Greenwich — Nepal
// included, every time before 05:45 local.

const pad = (value: number) => String(value).padStart(2, '0')
const toIso = (date: Date) =>
	`${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`

function fromIso(iso?: string): Date | null {
	const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec((iso ?? '').trim())
	if (!parts) return null
	const date = new Date(+parts[1], +parts[2] - 1, +parts[3])
	return Number.isNaN(date.getTime()) ? null : date
}

const todayIso = toIso(new Date())

// ── State ────────────────────────────────────────────────────────────────────

const open = ref(false)
const gridRef = ref<HTMLElement | null>(null)
const mode = ref<Mode>(loadMode())
/** Any day inside the month on screen. Shared by both calendars, so toggling
 *  keeps you on the same period instead of jumping to today. */
const anchor = ref<Date>(fromIso(props.modelValue) ?? new Date())
const draft = ref(props.modelValue)
const focusedIso = ref(props.modelValue || todayIso)

watch(
	() => props.modelValue,
	(value) => {
		draft.value = value
		const date = fromIso(value)
		if (date) {
			anchor.value = date
			focusedIso.value = value
		}
	},
)

function loadMode(): Mode {
	try {
		return localStorage.getItem(STORAGE_KEY) === 'BS' ? 'BS' : 'AD'
	} catch {
		// Private windows and blocked site data both throw here.
		return 'AD'
	}
}

function setMode(next: Mode) {
	mode.value = next
	try {
		localStorage.setItem(STORAGE_KEY, next)
	} catch {
		// A preference that cannot be remembered still works for this session.
	}
}

/** Whether the month on screen can be expressed in Bikram Sambat at all. */
const bsAvailable = computed(() => from_gregorian(anchor.value) !== null)

// ── The grid ─────────────────────────────────────────────────────────────────
// Both calendars produce the same shape, so the template renders one thing and
// only the generator differs.

const grid = computed(() => (mode.value === 'BS' && bsAvailable.value ? bsGrid() : adGrid()))

function outOfBounds(iso: string) {
	// Plain string comparison is exact for `YYYY-MM-DD`, and avoids a second
	// parse of bounds that arrive as strings anyway.
	return Boolean((props.min && iso < props.min) || (props.max && iso > props.max))
}

function makeCell(iso: string, label: string, title: string): Cell {
	return {
		key: iso,
		iso,
		label,
		title,
		isToday: iso === todayIso,
		isSelected: iso === props.modelValue,
		disabled: outOfBounds(iso),
	}
}

function intoWeeks(leading: number, cells: Cell[]) {
	const blanks: Cell[] = Array.from({ length: leading }, (_, index) => ({
		key: `blank-${index}`,
		iso: '',
		label: '',
		title: '',
		isToday: false,
		isSelected: false,
		disabled: true,
	}))
	const all = [...blanks, ...cells]
	const weeks: Cell[][] = []
	for (let index = 0; index < all.length; index += 7) {
		weeks.push(all.slice(index, index + 7))
	}
	return weeks
}

function adGrid() {
	const year = anchor.value.getFullYear()
	const month = anchor.value.getMonth()
	const leading = new Date(year, month, 1).getDay()
	const length = new Date(year, month + 1, 0).getDate()

	const cells = Array.from({ length }, (_, index) => {
		const date = new Date(year, month, index + 1)
		const iso = toIso(date)
		const bs = from_gregorian(date)
		return makeCell(iso, String(index + 1), bs ? `${iso} — ${formatBs(bs)}` : iso)
	})

	return {
		header: `${AD_MONTHS[month]} ${year}`,
		weekdays: AD_WEEKDAYS,
		weeks: intoWeeks(leading, cells),
	}
}

function bsGrid() {
	const bs = from_gregorian(anchor.value)!
	const length = days_in_month(bs.year, bs.month)!
	const first = to_gregorian({ ...bs, day: 1 })!

	const cells = Array.from({ length }, (_, index) => {
		const day = index + 1
		const date = to_gregorian({ ...bs, day })!
		const iso = toIso(date)
		return makeCell(iso, to_devanagari_digits(day), `${formatBs({ ...bs, day })} — ${iso}`)
	})

	return {
		header: `${month_name(bs.month)} ${to_devanagari_digits(bs.year)}`,
		weekdays: Array.from({ length: 7 }, (_, index) => weekday_name(index)),
		weeks: intoWeeks(first.getDay(), cells),
	}
}

/**
 * The one cell reachable by Tab. Normally the focused date, but that date is not
 * always in the month on screen -- after a mode switch, say -- and a grid with no
 * tab stop at all cannot be entered from the keyboard.
 */
const tabStopIso = computed(() => {
	const cells = grid.value.weeks.flat().filter((cell) => cell.iso)
	if (cells.some((cell) => cell.iso === focusedIso.value)) return focusedIso.value
	return cells[0]?.iso ?? ''
})

/** The selected date written in whichever calendar is not on screen. */
const counterpart = computed(() => {
	const date = fromIso(props.modelValue) ?? fromIso(focusedIso.value)
	if (!date) return ''
	if (mode.value === 'BS') return toIso(date)
	const bs = from_gregorian(date)
	return bs ? formatBs(bs) : ''
})

function cellClass(cell: Cell) {
	if (cell.disabled) {
		// Dim the *resting* colour rather than swap in a darker one. `ink-gray-3`
		// is a light grey in the light theme but a dark one (oklch .379) in the
		// dark theme, so using it here painted out-of-range days nearly black on a
		// dark panel. Keeping `ink-gray-8` and lowering the opacity reads as "not
		// available" in both themes, which is what frappe-ui's own panel does.
		return ['text-ink-gray-8', 'opacity-40', 'cursor-not-allowed']
	}
	if (cell.isSelected) {
		return ['bg-surface-gray-9', 'text-ink-base', cell.isToday ? 'font-semibold' : '']
	}
	return [
		cell.isToday ? 'font-semibold text-ink-gray-9' : 'text-ink-gray-8',
		'hover:bg-surface-gray-2',
		'cursor-pointer',
	]
}

// ── Navigation and selection ─────────────────────────────────────────────────

function step(delta: number) {
	if (mode.value === 'BS') {
		const bs = from_gregorian(anchor.value)
		const next = bs && add_months(bs, delta)
		const date = next && to_gregorian(next)
		if (date) anchor.value = date
		return
	}
	const date = new Date(anchor.value)
	date.setDate(1)
	date.setMonth(date.getMonth() + delta)
	anchor.value = date
}

function moveFocus(delta: number) {
	const from = fromIso(focusedIso.value)
	if (!from) return
	const next = new Date(from.getFullYear(), from.getMonth(), from.getDate() + delta)
	focusedIso.value = toIso(next)
	anchor.value = next
	nextTick(() => {
		// Scoped to this grid: the popover is portalled to `body`, so a
		// document-wide query could just as easily land on another picker's cell.
		gridRef.value?.querySelector<HTMLElement>('[role="gridcell"][tabindex="0"]')?.focus()
	})
}

function choose(cell: Cell) {
	if (!cell.iso || cell.disabled) return
	chooseIso(cell.iso)
}

function chooseIso(iso: string) {
	if (outOfBounds(iso)) return
	draft.value = iso
	focusedIso.value = iso
	const date = fromIso(iso)
	if (date) anchor.value = date
	if (iso !== props.modelValue) {
		emit('update:modelValue', iso)
		emit('change', iso)
	}
	open.value = false
}

/**
 * Accept a date typed straight into the field, and put back what was there if it
 * is not one. Typing is how most people fill a date they already know, and
 * `frappe-ui`'s own picker is typeable by default — losing that would be a
 * regression, not a simplification.
 */
function commitTyped() {
	const raw = (draft.value ?? '').trim()
	if (raw === props.modelValue) return
	if (!raw) {
		if (props.modelValue) {
			emit('update:modelValue', '')
			emit('change', '')
		}
		return
	}
	const date = fromIso(raw)
	if (!date || outOfBounds(toIso(date))) {
		draft.value = props.modelValue
		return
	}
	chooseIso(toIso(date))
}

function onClose() {
	// Anything half-typed is committed or reverted when the popover goes, so the
	// field never sits showing text that is not its value.
	commitTyped()
}
</script>
