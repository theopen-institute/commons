<template>
	<!-- Wider than the other pages' max-w-3xl, because the register is a grid
       with one 40px column per student and a group of twenty needs about
       1,100px. Wider groups scroll sideways inside the grid, as they already
       did. Capped so the pickers and a small group's columns don't spread
       across a wide monitor. -->
	<div class="mx-auto max-w-6xl px-5 py-4">
		<!-- Refused rather than arrived. The sidebar already hides this row from
         anybody who cannot mark attendance, so almost nobody reaches this —
         somebody following a link they were sent does, and a blank page would
         leave them guessing. -->
		<div v-if="attendancePermissionsLoaded && !attendanceCan.mark" class="mt-16 text-center">
			<span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
			<p class="mt-2 text-base-medium text-ink-gray-7">This register isn't yours to keep</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				Attendance registers are open to the people who mark them. Ask whoever administers
				permissions if that should include you.
			</p>
		</div>

		<template v-else>
			<!-- Two pickers and the shortcuts. The pickers are the whole filter; the
           chips exist because a teacher opens this page for the same two or
           three courses every week, and choosing them from a menu twice a week
           is a keystroke tax. For an instructor they are their own courses, a
           row per term from the one before the current term onwards, and each
           chip picks its term as well as its course. For anybody else they are
           every course, in whatever term is picked. -->
			<div class="grid gap-3 sm:grid-cols-2">
				<FormControl
					v-model="term"
					type="select"
					label="Academic term"
					:options="termOptions"
					:disabled="!pickers.loaded.value"
				/>
				<FormControl
					v-model="course"
					type="select"
					label="Course"
					:options="courseOptions"
					:disabled="!pickers.loaded.value"
				/>
			</div>

			<div v-if="shortcuts.state.value === 'mine'" class="mt-3 space-y-1">
				<div
					v-for="row in shortcuts.rows.value"
					:key="row.term"
					class="flex flex-wrap items-center gap-x-2 gap-y-1"
				>
					<span class="w-32 shrink-0 text-p-sm text-ink-gray-5">{{ row.term }}</span>
					<Button
						v-for="option in row.courses"
						:key="option.name"
						size="sm"
						:variant="option.name === course && row.term === term ? 'subtle' : 'ghost'"
						:label="courseChip(option)"
						:title="`${option.course_name ?? option.name} · ${row.term}`"
						@click="pickShortcut(row.term, option.name)"
					/>
				</div>
			</div>

			<div
				v-else-if="shortcuts.state.value === 'none' && pickers.courses.value.length"
				class="mt-3 flex flex-wrap items-center gap-2"
			>
				<Button
					v-for="option in pickers.courses.value"
					:key="option.name"
					size="sm"
					:variant="option.name === course ? 'subtle' : 'ghost'"
					:label="courseChip(option)"
					:title="option.course_name ?? option.name"
					@click="course = option.name"
				/>
			</div>

			<ErrorMessage
				v-if="pickers.error.value"
				:message="pickers.error.value.message"
				class="mt-4"
			/>

			<!-- Every list is read to its end; this is the safety ceiling, which no
           school's register should meet. Said rather than hidden, because a
           list cut short looks exactly like one that had nothing more in it. -->
			<div
				v-if="incomplete.length"
				class="mt-4 flex items-start gap-2 rounded-4 bg-surface-amber-1 px-3 py-2 text-p-sm text-ink-amber-3"
			>
				<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0" />
				<span>
					Not everything could be read: the {{ incomplete.join(', ') }}
					{{ incomplete.length === 1 ? 'list stops' : 'lists stop' }} at
					{{ MAX_ROWS.toLocaleString() }} rows, so totals here may be short.
				</span>
			</div>

			<div v-if="!term || !course" class="mt-16 text-center">
				<span class="lucide-calendar-search mx-auto size-8 text-ink-gray-4" />
				<p class="mt-2 text-base-medium text-ink-gray-7">Pick a term and a course</p>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					The register opens on whichever groups are taught that course that term.
				</p>
			</div>

			<template v-else>
				<ErrorMessage
					v-if="registerData.error.value"
					:message="registerData.error.value.message"
					class="mt-4"
				/>

				<div v-else-if="!registerData.loaded.value" class="mt-4 space-y-3">
					<Skeleton class="h-8 w-64 rounded-4" />
					<Skeleton class="h-64 w-full rounded-4" />
				</div>

				<div v-else-if="!register.groups.length" class="mt-16 text-center">
					<span class="lucide-users mx-auto size-8 text-ink-gray-4" />
					<p class="mt-2 text-base-medium text-ink-gray-7">
						No groups take this course this term
					</p>
					<p class="mt-1 text-p-sm text-ink-gray-5">
						A student group is what a register is kept for. Whoever sets up the term
						creates them.
					</p>
				</div>

				<section v-for="group in register.groups" v-else :key="group.name" class="mt-6">
					<div
						class="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1"
					>
						<div class="min-w-0">
							<h2 class="text-base-medium text-ink-gray-8">{{ group.title }}</h2>
							<p class="text-p-sm text-ink-gray-5">
								{{ pluralise(group.students.length, 'student') }} ·
								{{ formatHours(group.scheduled) }}
								{{
									group.planned === null
										? 'scheduled hours'
										: `of ${formatHours(
												group.planned
										  )} planned hours scheduled`
								}}
							</p>
						</div>
						<Button
							v-if="attendanceCan.schedule"
							size="sm"
							variant="subtle"
							icon-left="lucide-plus"
							label="New session"
							@click="openDialog(group, null)"
						/>
					</div>

					<div
						v-if="!group.students.length"
						class="rounded-4 border border-dashed border-outline-gray-2 px-4 py-8 text-center"
					>
						<p class="text-base-medium text-ink-gray-7">Nobody is in this group</p>
						<p class="mt-1 text-p-sm text-ink-gray-5">
							There is nothing to mark until students are added to it.
						</p>
					</div>

					<AttendanceGrid v-else :group="group" @open="openMarks" />
				</section>
			</template>
		</template>

		<AttendanceMarksDialog
			v-if="marksGroup"
			v-model:open="marksOpen"
			:group="marksGroup"
			:course="course"
			:session="marksSession"
			:focus="marksFocus"
			:can-mark="attendanceCan.mark"
			:can-schedule="attendanceCan.schedule"
			@saved="reloadRegister"
			@edit-session="editFromMarks"
		/>

		<AttendanceSessionDialog
			v-if="dialogGroup"
			v-model:open="dialogOpen"
			:group="dialogGroup"
			:course="course"
			:session="dialogSession"
			:session-types="pickers.sessionTypes.value"
			:term-start="bounds.start.value"
			:term-end="bounds.end.value"
			@saved="reloadRegister"
		/>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, ErrorMessage, FormControl, Skeleton } from 'frappe-ui'
import AttendanceGrid from '@/components/AttendanceGrid.vue'
import AttendanceMarksDialog from '@/components/AttendanceMarksDialog.vue'
import AttendanceSessionDialog from '@/components/AttendanceSessionDialog.vue'
import { pluralise } from '@/data/format'
import {
	attendanceCan,
	attendancePermissionsLoaded,
	courseChip,
	formatHours,
	MAX_ROWS,
	termBounds,
	useAttendancePickers,
	useCourseShortcuts,
	useAttendanceRegister,
	type GroupRegister,
	type Session,
} from '@/data/attendance'
import type { PageAction, ScreenQuery } from '@/islands/contract'

/**
 * The attendance register: one term of one course, for every group taught it.
 *
 * Which term and which course live in the query string, not in component state
 * alone. That is what the register this replaces did too, and it was the best
 * thing about it: "the seminar register for last autumn" is a link somebody can
 * send a colleague, and a refresh comes back where it was rather than at the
 * top of a picker. The screen does not read the URL itself: it takes `query`
 * and reports `replaceQuery`, so it runs the same under the SPA's router
 * (`pages/AttendanceRegister.vue`) and as the `commons.attendance` desk island
 * (`islands/attendance.ts`).
 *
 * It draws no header either. It reports its `title` and `actions`, and each
 * host puts them in its own chrome. See `islands/contract.ts`.
 *
 * Every read and every write below goes through an API Frappe already ships —
 * see `data/attendance.ts` for why that matters more than the round trips it
 * costs.
 */

const props = withDefaults(
	defineProps<{
		/** The register to open on: `term` and `course`. */
		query?: ScreenQuery
		/** The path below the page, from a desk host. This screen has no sub-pages. */
		route?: string[]
	}>(),
	{ query: () => ({}), route: () => [] }
)

const emit = defineEmits<{
	title: [title: string | null]
	actions: [actions: PageAction[]]
	/** The view's query keys, to write back to the URL in place. */
	replaceQuery: [query: Record<string, string | undefined>]
}>()

emit('title', 'Attendance')

const term = ref('')
const course = ref('')

const pickers = useAttendancePickers()
const shortcuts = useCourseShortcuts()
const registerData = useAttendanceRegister()
const register = registerData.register

/** The lists, picker or register, that stopped at the safety ceiling. */
const incomplete = computed(() => [
	...pickers.incomplete.value,
	...(term.value && course.value ? registerData.incomplete.value : []),
])

const dialogOpen = ref(false)
const dialogGroup = ref<GroupRegister | null>(null)
const dialogSession = ref<Session | null>(null)

/**
 * The session whose details are open, held by name rather than as the object
 * the grid handed over. A save re-reads the register, which builds new
 * objects, and the dialog has to show the new ones: after a partial save it
 * works out what is still unwritten against what the server now holds.
 */
const marksOpen = ref(false)
const marksGroupName = ref('')
const marksSessionName = ref('')
const marksFocus = ref<string | null>(null)
const marksGroup = computed(
	() => register.value.groups.find((row) => row.name === marksGroupName.value) ?? null
)
const marksSession = computed(
	() =>
		marksGroup.value?.blocks
			.flatMap((block) => block.sessions)
			.find((row) => row.name === marksSessionName.value) ?? null
)

const bounds = termBounds(pickers.terms, term)

// Nothing is asked for until the permission answer is in, so a reader who has
// no register never sends a round of reads that would only be refused.
watch(
	() => attendanceCan.value.mark,
	(mark) => {
		if (mark) pickers.load()
	},
	{ immediate: true }
)

// The address first, then the school's current term. An address that names a
// term wins, including one that names a term the picker has retired — an old
// link still resolves to the register it was written for.
function applyQuery() {
	term.value = queryValue('term') || pickers.currentTerm.value || ''
	course.value = queryValue('course') || ''
}

watch(pickers.loaded, (ready) => {
	if (ready) applyQuery()
})

// The shortcuts are worked out from the pickers' lists, so again whenever
// those are read again (Refresh).
watch(
	() => [pickers.loaded.value, pickers.terms.value, pickers.courses.value] as const,
	([ready, terms, courses]) => {
		if (ready) shortcuts.load(terms, pickers.currentTerm.value, courses)
	}
)

function pickShortcut(nextTerm: string, nextCourse: string) {
	term.value = nextTerm
	course.value = nextCourse
}

// And again whenever the address changes under the screen — a link to another
// register followed from here, back and forward, the sidebar row clicked while
// already on it. Neither host remounts the screen for a new query, so reading
// it once on arrival left the pickers on the old register. An address that
// already says what the pickers say is this screen's own `replaceQuery` below
// coming back round, and is left alone.
watch(
	() => [queryValue('term'), queryValue('course')],
	([nextTerm, nextCourse]) => {
		if (!pickers.loaded.value) return
		if (nextTerm === term.value && nextCourse === course.value) return
		applyQuery()
	}
)

function queryValue(key: string): string {
	const value = props.query[key]
	return typeof value === 'string' ? value : ''
}

// Replace rather than push: changing a filter is not somewhere you went, and a
// back button that walked through six courses would never reach the page you
// arrived from. The host does the replacing; an `undefined` drops the key.
watch([term, course], ([nextTerm, nextCourse]) => {
	emit('replaceQuery', { term: nextTerm || undefined, course: nextCourse || undefined })
	registerData.load(nextTerm, nextCourse)
})

function reloadRegister() {
	registerData.load(term.value, course.value)
}

function reload() {
	pickers.load()
	reloadRegister()
}

/** The header's one action. Offered only to somebody the register is for: to
 *  anybody else the screen is a refusal, and there is nothing to refresh. */
const actions = computed<PageAction[]>(() =>
	attendanceCan.value.mark
		? [
				{
					label: 'Refresh',
					icon: 'lucide-refresh-cw',
					onClick: () => reload(),
					primary: true,
					loading: registerData.loading.value,
				},
		  ]
		: []
)

watch(actions, (next) => emit('actions', next), { immediate: true })

const termOptions = computed(() => [
	{ label: 'Select a term', value: '' },
	...pickers.terms.value.map((row) => ({ label: row.name, value: row.name })),
])

const courseOptions = computed(() => [
	{ label: 'Select a course', value: '' },
	...pickers.courses.value.map((row) => ({
		label: row.course_name ?? row.name,
		value: row.name,
	})),
])

function openDialog(group: GroupRegister, session: Session | null) {
	dialogGroup.value = group
	dialogSession.value = session
	dialogOpen.value = true
}

function openMarks(session: Session, student: string | null) {
	marksGroupName.value = session.group
	marksSessionName.value = session.name
	marksFocus.value = student
	marksOpen.value = true
}

/** From a session's details to changing the session itself. One dialog at a
 *  time: stacked, a Save in the one underneath would be out of sight. */
function editFromMarks(session: Session) {
	const group = marksGroup.value
	if (!group) return
	marksOpen.value = false
	openDialog(group, session)
}
</script>
