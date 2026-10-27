<!--
  Everything Apply will write, before it writes it: the draft enrolments by
  program, and each student's change. One request, so it lands whole or not at
  all. Groups, fees and invoices are not made here: they follow when each
  enrolment is submitted.
-->

<template>
	<Dialog
		v-model:open="open"
		title="Review and apply"
		:actions="actions"
		:dismissible="!busy"
		size="2xl"
	>
		<div class="space-y-5">
			<p class="text-p-sm text-ink-gray-7">{{ sourceTerm }} → {{ targetTerm }}</p>
			<section
				v-if="plan.unresolved.length"
				class="rounded-4 bg-surface-red-1 px-3 py-2 text-p-sm text-ink-red-4"
			>
				<p class="font-medium">Nothing can be applied yet</p>
				<p class="mt-1">
					{{ plan.unresolved.length === 1 ? 'This student is' : 'These students are' }}
					not enrolled in {{ targetTerm }} and need a status that says they left ({{
						leaving.join(' or ')
					}}): {{ plan.unresolved.map((row) => row.studentName).join(', ') }}.
				</p>
			</section>

			<section>
				<h3 class="mb-1 text-base-medium text-ink-gray-8">Draft enrolments</h3>
				<p v-if="!plan.enrolments.length" class="text-p-sm text-ink-gray-5">None.</p>
				<template v-else>
					<ul class="text-p-sm text-ink-gray-7">
						<li v-for="row in plan.enrolments" :key="row.program">
							{{ pluralise(row.count, 'student') }} into {{ row.program }}
						</li>
					</ul>
					<p class="mt-1 text-p-sm text-ink-gray-5">
						Submitting each one puts the student in the term's group and bills them.
					</p>
				</template>
			</section>

			<section>
				<h3 class="mb-2 text-base-medium text-ink-gray-8">Students</h3>
				<ul
					class="max-h-72 divide-y divide-outline-gray-1 overflow-y-auto rounded-4 border border-outline-gray-2"
				>
					<li
						v-for="row in plan.rows"
						:key="row.candidate.enrollment"
						class="flex items-center justify-between gap-3 px-3 py-1.5 text-p-sm"
					>
						<span class="min-w-0 truncate text-ink-gray-8">{{
							row.candidate.studentName
						}}</span>
						<span class="shrink-0 text-right text-ink-gray-6">
							<template v-if="row.decision.program"
								>→ {{ row.decision.program }}</template
							>
							<template v-if="row.decision.program && row.decision.status">
								·
							</template>
							<template v-if="row.decision.status">
								{{ row.candidate.status || 'No status' }} →
								{{ row.decision.status }}
							</template>
						</span>
					</li>
				</ul>
			</section>

			<!-- Offered when the new term is not current yet and this reader may
			     change Education Settings. On by default: advancing into a term is
			     normally the moment it becomes the current one. -->
			<section v-if="offerCurrent" class="rounded-4 bg-surface-gray-2 px-3 py-2">
				<FormControl
					v-model="makeCurrent"
					type="checkbox"
					:label="`Also make ${targetTerm} the current term`"
				/>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					Education Settings now says {{ currentTerm || 'no term' }}. The attendance
					register and Education's own pages open on the current term.
				</p>
			</section>

			<ErrorMessage v-if="problem" :message="problem" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import { useApply, type Applied } from '@/data/advancement'
import { leavingStatuses, type AdvancementSettings, type Plan } from '@/data/advancementPlan'
import { pluralise } from '@/data/format'

const props = defineProps<{
	plan: Plan
	sourceTerm: string
	targetTerm: string
	/** Education Settings' current term, or null. */
	currentTerm: string | null
	/** Whether this reader may change it. */
	canSetCurrent: boolean
	settings: AdvancementSettings
}>()

const leaving = computed(() => leavingStatuses(props.settings))

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
	applied: [result: Applied]
}>()

const apply = useApply()
const busy = ref(false)
const problem = ref('')

watch(open, (isOpen) => {
	if (!isOpen) return
	problem.value = ''
	makeCurrent.value = true
})

const offerCurrent = computed(() => props.canSetCurrent && props.currentTerm !== props.targetTerm)
const makeCurrent = ref(true)

async function submit(close: () => void) {
	busy.value = true
	problem.value = ''
	try {
		const result = await apply.submit({
			source_term: props.sourceTerm,
			target_term: props.targetTerm,
			// A stray has no enrolment to name: it is sent by student, and only
			// its status can change.
			decisions: props.plan.rows.map((row) =>
				row.candidate.stray
					? {
							student: row.candidate.student,
							program: null,
							status: row.decision.status,
					  }
					: {
							enrollment: row.candidate.enrollment,
							program: row.decision.program,
							status: row.decision.status,
					  }
			),
			make_current: offerCurrent.value && makeCurrent.value,
		})
		if (!result || apply.error) {
			problem.value =
				apply.error?.message || 'Nothing was written: the changes could not be applied.'
			return
		}
		toast.success(
			`${pluralise(result.enrollments.length, 'draft enrolment')} made` +
				(result.current_term ? `; ${result.current_term} is now the current term` : '')
		)
		emit('applied', result)
		close()
	} finally {
		busy.value = false
	}
}

const actions = computed<DialogAction[]>(() => [
	{
		label: `Apply ${pluralise(props.plan.rows.length, 'change')}`,
		variant: 'solid',
		disabled: !props.plan.rows.length || props.plan.unresolved.length > 0,
		loading: busy.value,
		onClick: ({ close }) => submit(close),
	},
])
</script>
