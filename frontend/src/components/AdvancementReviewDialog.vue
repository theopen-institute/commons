<!--
  Everything Apply will write, before it writes it: the groups the new term
  needs, named here; the draft enrolments by program; and each student's
  change. One request, so it lands whole or not at all.
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
			<section v-if="plan.newGroups.length">
				<h3 class="mb-1 text-base-medium text-ink-gray-8">New student groups</h3>
				<p class="mb-2 text-p-sm text-ink-gray-5">
					{{ targetTerm }} has no group for
					{{ plan.newGroups.length === 1 ? 'this program' : 'these programs' }} yet. Each
					is set up like the program's last group, without students: they join when their
					enrolment is submitted.
				</p>
				<div class="space-y-2">
					<FormControl
						v-for="program in plan.newGroups"
						:key="program"
						v-model="names[program]"
						type="text"
						:label="program"
					/>
				</div>
			</section>

			<section>
				<h3 class="mb-1 text-base-medium text-ink-gray-8">Draft enrolments</h3>
				<p v-if="!plan.enrolments.length" class="text-p-sm text-ink-gray-5">None.</p>
				<ul v-else class="text-p-sm text-ink-gray-7">
					<li v-for="row in plan.enrolments" :key="row.program">
						{{ pluralise(row.count, 'student') }} into {{ row.program }}
						<span class="text-ink-gray-5">
							· {{ row.group ? `group ${row.group}` : 'new group' }}
						</span>
					</li>
				</ul>
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

			<ErrorMessage v-if="problem" :message="problem" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Dialog, ErrorMessage, FormControl, toast, type DialogAction } from 'frappe-ui'
import { useApply, type Applied } from '@/data/advancement'
import type { Plan } from '@/data/advancementPlan'
import { pluralise } from '@/data/format'

const props = defineProps<{
	plan: Plan
	/** The name a new group for a program is offered under. */
	nameGroup: (program: string) => string
	sourceTerm: string
	targetTerm: string
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
	applied: [result: Applied]
}>()

const apply = useApply()
const busy = ref(false)
const problem = ref('')

/** The new groups' names, suggested afresh each time the dialog opens. */
const names = reactive<Record<string, string>>({})

watch(open, (isOpen) => {
	if (!isOpen) return
	problem.value = ''
	for (const key of Object.keys(names)) delete names[key]
	for (const program of props.plan.newGroups) {
		names[program] = props.nameGroup(program)
	}
})

const missingName = computed(() => props.plan.newGroups.some((program) => !names[program]?.trim()))

async function submit(close: () => void) {
	busy.value = true
	problem.value = ''
	try {
		const result = await apply.submit({
			source_term: props.sourceTerm,
			target_term: props.targetTerm,
			decisions: props.plan.rows.map((row) => ({
				enrollment: row.candidate.enrollment,
				program: row.decision.program,
				status: row.decision.status,
			})),
			group_names: Object.fromEntries(
				props.plan.newGroups.map((program) => [program, names[program].trim()])
			),
		})
		if (!result || apply.error) {
			problem.value =
				apply.error?.message || 'Nothing was written: the changes could not be applied.'
			return
		}
		toast.success(`${pluralise(result.enrollments.length, 'draft enrolment')} made`)
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
		disabled: !props.plan.rows.length || missingName.value,
		loading: busy.value,
		onClick: ({ close }) => submit(close),
	},
])
</script>
