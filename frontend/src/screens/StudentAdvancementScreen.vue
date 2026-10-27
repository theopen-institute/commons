<template>
	<div class="mx-auto max-w-4xl px-5 py-4">
		<!-- Refused rather than arrived: the sidebar hides this row from anybody
         who may not enrol students, so only a followed link lands here. -->
		<div v-if="advancePermissionLoaded && !canAdvance" class="mt-16 text-center">
			<span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
			<p class="mt-2 text-base-medium text-ink-gray-7">
				Advancing students isn't yours to do
			</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				This page is for the people who enrol students. Ask whoever administers permissions
				if that should include you.
			</p>
		</div>

		<template v-else>
			<div class="grid gap-3 sm:grid-cols-2">
				<FormControl
					v-model="from"
					type="select"
					label="From term"
					:options="termOptions"
					:disabled="!data.loaded.value"
				/>
				<FormControl
					v-model="to"
					type="select"
					label="Into term"
					:options="termOptions"
					:disabled="!data.loaded.value"
				/>
			</div>

			<p v-if="data.loaded.value" class="mt-2 text-p-sm text-ink-gray-5">
				Current term in Education Settings: {{ data.currentTerm.value || 'none' }}
			</p>

			<ErrorMessage
				v-if="data.error.value"
				:message="data.error.value.message"
				class="mt-4"
			/>

			<!-- Without next programs the page still works, but suggests nothing:
           every row starts as "no change" and any program may be chosen. -->
			<div
				v-if="data.loaded.value && !data.settings.value.next_programs"
				class="mt-4 flex items-start gap-2 rounded-4 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
			>
				<span class="lucide-info mt-0.5 size-4 shrink-0" />
				<span>
					No next programs are set up, so nothing is suggested and any program can be
					chosen. Name the table on Program that lists them in
					<a :href="settingsUrl" target="_blank" class="underline">Commons Settings</a>.
				</span>
			</div>

			<div
				v-if="data.incomplete.value.length"
				class="mt-4 flex items-start gap-2 rounded-4 bg-surface-amber-1 px-3 py-2 text-p-sm text-ink-amber-3"
			>
				<span class="lucide-triangle-alert mt-0.5 size-4 shrink-0" />
				<span>
					Not everything could be read: the {{ data.incomplete.value.join(', ') }}
					{{ data.incomplete.value.length === 1 ? 'list stops' : 'lists stop' }} at
					{{ MAX_ROWS.toLocaleString() }} rows.
				</span>
			</div>

			<!-- What the last Apply made, until the terms change. Drafts are the
           point: each is submitted in the desk, where fees and group membership
           follow from the site's own rules. -->
			<div
				v-if="applied"
				class="mt-4 rounded-4 border border-outline-gray-2 bg-surface-green-1 px-3 py-2 text-p-sm text-ink-gray-8"
			>
				<div class="flex flex-wrap items-center justify-between gap-2">
					<span>
						{{ appliedSummary }}
					</span>
					<a
						v-if="applied.enrollments.length"
						:href="draftsUrl"
						target="_blank"
						class="font-medium underline"
					>
						Open the draft enrolments
					</a>
				</div>
				<p v-if="applied.skipped.length" class="mt-1 text-ink-gray-6">
					Skipped, already enrolled:
					{{
						applied.skipped
							.map((row) => `${row.student_name} (${row.program})`)
							.join(', ')
					}}
				</p>
			</div>

			<div v-if="!from || !to" class="mt-16 text-center">
				<span class="lucide-calendar-search mx-auto size-8 text-ink-gray-4" />
				<p class="mt-2 text-base-medium text-ink-gray-7">Pick the two terms</p>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					Everyone enrolled in the first is listed, with a suggestion for the second.
				</p>
			</div>

			<div v-else-if="from === to" class="mt-16 text-center">
				<span class="lucide-arrow-right-left mx-auto size-8 text-ink-gray-4" />
				<p class="mt-2 text-base-medium text-ink-gray-7">Pick two different terms</p>
			</div>

			<template v-else>
				<ErrorMessage
					v-if="data.termsError.value"
					:message="data.termsError.value.message"
					class="mt-4"
				/>

				<div v-else-if="!data.termsLoaded.value" class="mt-6 space-y-3">
					<Skeleton class="h-6 w-64 rounded-4" />
					<Skeleton class="h-48 w-full rounded-4" />
				</div>

				<div v-else-if="!everyone.length" class="mt-16 text-center">
					<span class="lucide-users mx-auto size-8 text-ink-gray-4" />
					<p class="mt-2 text-base-medium text-ink-gray-7">
						Nobody is enrolled in {{ from }}
					</p>
					<p class="mt-1 text-p-sm text-ink-gray-5">
						Only submitted enrolments are listed.
					</p>
				</div>

				<template v-else>
					<p class="mt-5 text-p-sm text-ink-gray-6">
						{{ pluralise(data.candidates.value.length, 'student') }} ·
						{{
							pluralise(
								plan.enrolments.reduce((sum, row) => sum + row.count, 0),
								'enrolment'
							)
						}}
						to draft ·
						{{ pluralise(plan.statusChanges, 'status change', 'status changes') }}
						<template v-if="editedCount"> · {{ editedCount }} changed by you</template>
					</p>
					<!-- Said above the list as well as on each row: Apply waits on these,
					     and a long list hides the rows that need them. -->
					<p
						v-if="plan.unresolved.length"
						class="mt-1 flex items-center gap-1.5 text-p-sm text-ink-red-4"
					>
						<span class="lucide-circle-alert size-4 shrink-0" />
						{{ pluralise(plan.unresolved.length, 'student is', 'students are') }}
						not enrolled in {{ to }}, and their status doesn't say they left. Give each
						{{ leaving.join(' or ') }} before applying.
					</p>

					<section v-for="section in sections" :key="section.program" class="mt-5">
						<h2
							class="mb-2 text-base-medium"
							:class="section.stray ? 'text-ink-red-4' : 'text-ink-gray-8'"
						>
							{{ section.program }}
							<span class="text-p-sm font-normal text-ink-gray-5">
								· {{ pluralise(section.rows.length, 'student') }}
							</span>
						</h2>
						<!-- Should never happen, so it is said first and in red. -->
						<p v-if="section.stray" class="-mt-1 mb-2 text-p-sm text-ink-gray-6">
							Marked {{ continuing }}, but enrolled in neither {{ from }} nor
							{{ to }} and active in no {{ from }} group. Enrol them in the desk, or
							give them the status that says they left.
						</p>
						<ul
							class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2"
						>
							<li v-for="row in section.rows" :key="row.enrollment">
								<button
									type="button"
									class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-surface-gray-1"
									@click="openDecision(row)"
								>
									<div class="min-w-0 flex-1">
										<div class="truncate text-p-base text-ink-gray-8">
											{{ row.studentName }}
										</div>
										<div v-if="row.stray" class="text-p-xs text-ink-gray-5">
											{{
												row.lastTerm
													? `Last enrolled in ${row.program}, ${row.lastTerm}`
													: 'Never enrolled'
											}}
										</div>
										<div class="mt-0.5 flex flex-wrap gap-1">
											<Badge
												v-if="
													needsLeavingStatus(
														row,
														decisionOf(row),
														data.settings.value
													)
												"
												size="sm"
												theme="red"
												:label="`Needs ${leaving.join(' or ')}`"
											/>
											<Badge
												v-if="row.status"
												size="sm"
												:theme="
													row.status === continuing ? 'gray' : 'amber'
												"
												:label="row.status"
											/>
											<Badge
												v-if="
													continuingWithoutGroup(
														row,
														data.settings.value
													)
												"
												size="sm"
												theme="red"
												:label="
													row.active === false
														? `${row.status}, but inactive in group`
														: `${row.status}, but in no group`
												"
											/>
											<Badge
												v-else-if="row.active === false"
												size="sm"
												theme="amber"
												label="Inactive in group"
											/>
											<Badge
												v-else-if="row.active === null"
												size="sm"
												theme="gray"
												label="In no group"
											/>
											<Badge
												v-for="other in row.already"
												:key="other.name"
												size="sm"
												theme="blue"
												:label="`${other.draft ? 'Draft' : 'Enrolled'}: ${
													other.program
												}`"
											/>
										</div>
									</div>
									<div class="shrink-0 text-right">
										<div
											class="text-p-sm"
											:class="
												decisionOf(row).program
													? 'text-ink-gray-8'
													: 'text-ink-gray-5'
											"
										>
											{{
												decisionOf(row).program
													? `→ ${decisionOf(row).program}`
													: 'No new enrolment'
											}}
										</div>
										<div
											v-if="
												decisionOf(row).status &&
												decisionOf(row).status !== row.status
											"
											class="text-p-xs text-ink-gray-6"
										>
											Status → {{ decisionOf(row).status }}
										</div>
										<div
											v-if="isEdited(decisionOf(row), suggestionOf(row))"
											class="text-p-xs text-ink-amber-3"
										>
											Changed
										</div>
									</div>
									<span
										class="lucide-chevron-right size-4 shrink-0 text-ink-gray-4"
									/>
								</button>
							</li>
						</ul>
					</section>
				</template>
			</template>
		</template>

		<AdvancementDecisionDialog
			v-if="decisionRow"
			v-model:open="decisionOpen"
			:candidate="decisionRow"
			:decision="decisionOf(decisionRow)"
			:suggestion="suggestionOf(decisionRow)"
			:hold-reason="holdReason(decisionRow, data.settings.value)"
			:settings="data.settings.value"
			:target-term="to"
			@save="saveDecision"
		/>

		<AdvancementReviewDialog
			v-model:open="reviewOpen"
			:plan="plan"
			:source-term="from"
			:target-term="to"
			:current-term="data.currentTerm.value"
			:can-set-current="canSetCurrent"
			:settings="data.settings.value"
			@applied="onApplied"
		/>

		<AdvancementCurrentTermDialog
			v-model:open="currentOpen"
			:term="to"
			:current-term="data.currentTerm.value"
			@changed="data.loadCurrentTerm()"
		/>
	</div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Badge, ErrorMessage, FormControl, Skeleton } from 'frappe-ui'
import AdvancementDecisionDialog from '@/components/AdvancementDecisionDialog.vue'
import AdvancementCurrentTermDialog from '@/components/AdvancementCurrentTermDialog.vue'
import AdvancementReviewDialog from '@/components/AdvancementReviewDialog.vue'
import {
	advancePermissionLoaded,
	canAdvance,
	canSetCurrent,
	useAdvancement,
	type Applied,
	type Candidate,
	type Decision,
} from '@/data/advancement'
import {
	buildPlan,
	continuingWithoutGroup,
	holdReason,
	isEdited,
	leavingStatuses,
	needsLeavingStatus,
	suggest,
} from '@/data/advancementPlan'
import { MAX_ROWS } from '@/data/attendanceRegister'
import { deskFormUrl, deskListUrl } from '@/data/desk'
import { pluralise } from '@/data/format'
import type { PageAction, ScreenQuery } from '@/islands/contract'

/**
 * A term's students, each with what becomes of them in the next.
 *
 * The rows are read-only. A row opens a dialog that changes the decision held
 * here, in the page, and nothing is written until Review and Apply, which shows
 * every enrolment and status it will write before it writes them. The
 * two terms live in the query string (`from`, `to`), so a link reopens the
 * same view; like the attendance register, the screen reports its title,
 * actions and query rather than drawing a header, so it runs the same in the
 * SPA and as the `commons.advancement` desk island.
 */

const props = withDefaults(
	defineProps<{
		query?: ScreenQuery
		route?: string[]
	}>(),
	{ query: () => ({}), route: () => [] }
)

const emit = defineEmits<{
	title: [title: string | null]
	actions: [actions: PageAction[]]
	replaceQuery: [query: Record<string, string | undefined>]
}>()

emit('title', 'Student Advancement')

const data = useAdvancement()
const from = ref('')
const to = ref('')

/** The reader's decisions, by enrolment. A row with none follows the suggestion. */
const decisions = reactive<Record<string, Decision>>({})
const applied = ref<Applied | null>(null)

const continuing = computed(() => data.settings.value.status?.continuing ?? null)

watch(
	canAdvance,
	(may) => {
		if (may) data.load()
	},
	{ immediate: true }
)

function queryValue(key: string): string {
	const value = props.query[key]
	return typeof value === 'string' ? value : ''
}

function applyQuery() {
	from.value = queryValue('from') || data.defaults.value.from
	to.value = queryValue('to') || data.defaults.value.to
}

watch(data.loaded, (ready) => {
	if (ready) applyQuery()
})

watch(
	() => [queryValue('from'), queryValue('to')],
	([nextFrom, nextTo]) => {
		if (!data.loaded.value) return
		if (nextFrom === from.value && nextTo === to.value) return
		if (nextFrom || nextTo) applyQuery()
	}
)

watch([from, to], ([nextFrom, nextTo]) => {
	emit('replaceQuery', { from: nextFrom || undefined, to: nextTo || undefined })
	clearDecisions()
	applied.value = null
	if (nextFrom && nextTo && nextFrom !== nextTo) data.loadTerms(nextFrom, nextTo)
})

function clearDecisions() {
	for (const key of Object.keys(decisions)) delete decisions[key]
}

function suggestionOf(row: Candidate): Decision {
	return suggest(row, data.settings.value)
}

function decisionOf(row: Candidate): Decision {
	return decisions[row.enrollment] ?? suggestionOf(row)
}

/** Every row's decision, suggestions included -- what the plan is made from. */
/** The term's students, then the strays: everyone the page decides about. */
const everyone = computed(() => [...data.strays.value, ...data.candidates.value])

const allDecisions = computed(() =>
	Object.fromEntries(everyone.value.map((row) => [row.enrollment, decisionOf(row)]))
)

const plan = computed(() => buildPlan(everyone.value, allDecisions.value, data.settings.value))

const leaving = computed(() => leavingStatuses(data.settings.value))

const editedCount = computed(
	() => everyone.value.filter((row) => isEdited(decisionOf(row), suggestionOf(row))).length
)

const sections = computed(() => {
	const byProgram = new Map<string, Candidate[]>()
	for (const row of data.candidates.value) {
		const list = byProgram.get(row.program) ?? []
		list.push(row)
		byProgram.set(row.program, list)
	}
	const programs = [...byProgram].map(([program, rows]) => ({ program, rows, stray: false }))
	const strays = data.strays.value
	return strays.length
		? [
				{
					program: `${continuing.value}, but in no group`,
					rows: strays,
					stray: true,
				},
				...programs,
		  ]
		: programs
})

const termOptions = computed(() => [
	{ label: 'Select a term', value: '' },
	...data.terms.value.map((row) => ({ label: row.name, value: row.name })),
])

const decisionOpen = ref(false)
const decisionRow = ref<Candidate | null>(null)

function openDecision(row: Candidate) {
	decisionRow.value = row
	decisionOpen.value = true
}

function saveDecision(decision: Decision) {
	const row = decisionRow.value
	if (!row) return
	if (isEdited(decision, suggestionOf(row))) decisions[row.enrollment] = decision
	else delete decisions[row.enrollment]
}

const reviewOpen = ref(false)
const currentOpen = ref(false)

/** Offered once the new term is picked and is not current yet. */
const offerCurrent = computed(
	() => canSetCurrent.value && Boolean(to.value) && to.value !== data.currentTerm.value
)

function onApplied(result: Applied) {
	applied.value = result
	clearDecisions()
	reload()
}

async function reload() {
	await data.load()
	if (from.value && to.value && from.value !== to.value)
		await data.loadTerms(from.value, to.value)
}

const appliedSummary = computed(() => {
	const result = applied.value
	if (!result) return ''
	const parts = [
		pluralise(result.enrollments.length, 'draft enrolment'),
		pluralise(result.statuses.length, 'status change', 'status changes'),
	]
	return `Made ${parts.join(', ')}.`
})

const draftsUrl = computed(
	() =>
		`${deskListUrl('Program Enrollment')}?academic_term=${encodeURIComponent(
			to.value
		)}&docstatus=0`
)

const settingsUrl = deskFormUrl('Commons Settings', 'Commons Settings')

const changeCount = computed(() => plan.value.rows.length)
/** Open as long as there is something to apply or something holding it back. */
const reviewable = computed(() => Boolean(changeCount.value || plan.value.unresolved.length))

const actions = computed<PageAction[]>(() =>
	canAdvance.value
		? [
				{
					label: 'Review and Apply',
					icon: 'lucide-list-checks',
					primary: true,
					disabled: !reviewable.value,
					onClick: () => {
						if (reviewable.value) reviewOpen.value = true
					},
				},
				...(offerCurrent.value
					? [
							{
								label: `Make ${to.value} the current term`,
								icon: 'lucide-calendar-check',
								onClick: () => {
									currentOpen.value = true
								},
							},
					  ]
					: []),
				{
					label: 'Reset to suggestions',
					icon: 'lucide-rotate-ccw',
					onClick: () => clearDecisions(),
				},
				{
					label: 'Refresh',
					icon: 'lucide-refresh-cw',
					loading: data.termsLoading.value,
					onClick: () => reload(),
				},
		  ]
		: []
)

watch(actions, (next) => emit('actions', next), { immediate: true })
</script>
