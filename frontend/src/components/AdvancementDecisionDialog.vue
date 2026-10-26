<!--
  What becomes of one student in the new term, and the only place it is
  changed. Save keeps the choice in the page; nothing is written until the
  page's Review and Apply.
-->

<template>
	<Dialog v-model:open="open" :title="candidate.studentName" :actions="actions" size="lg">
		<div class="space-y-4">
			<p v-if="!candidate.stray" class="text-p-sm text-ink-gray-7">
				{{ candidate.program
				}}<template v-if="candidate.status"> · {{ candidate.status }}</template>
			</p>
			<p v-if="holdReason && !candidate.stray" class="text-p-sm text-ink-gray-6">
				Suggested: no new enrolment ({{ holdReason.toLowerCase() }}).
			</p>
			<p v-else-if="suggestion.program" class="text-p-sm text-ink-gray-6">
				Suggested: {{ suggestion.program }}.
			</p>

			<div v-if="candidate.already.length" class="text-p-sm text-ink-gray-7">
				Already in {{ targetTerm }}:
				{{
					candidate.already
						.map((row) => `${row.program}${row.draft ? ' (draft)' : ''}`)
						.join(', ')
				}}
			</div>

			<!-- A stray has no enrolment this page could carry forward: only its
			     status can be put right here, and enrolling them is the desk's. -->
			<p v-if="candidate.stray" class="text-p-sm text-ink-red-4">
				Marked {{ candidate.status }}, but not enrolled in this term or {{ targetTerm }},
				and active in no group. This should not happen. Enrol them in the desk, or give
				them the status that says they left.
				<template v-if="candidate.lastTerm">
					Last enrolled in {{ candidate.program }}, {{ candidate.lastTerm }}.
				</template>
			</p>

			<fieldset v-else>
				<legend class="mb-1.5 text-p-sm text-ink-gray-6">
					Next program in {{ targetTerm }}
				</legend>
				<div role="radiogroup" class="space-y-1">
					<label
						v-for="option in programOptions"
						:key="option.value"
						class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-surface-gray-2"
						:class="draftProgram === option.value ? 'bg-surface-gray-2' : ''"
					>
						<input
							type="radio"
							:checked="draftProgram === option.value"
							:value="option.value"
							class="text-ink-gray-8 focus:ring-0"
							@change="pickProgram(option.value)"
						/>
						<span class="text-p-base text-ink-gray-8">{{ option.label }}</span>
						<span
							v-if="option.value && option.value === suggestion.program"
							class="text-p-xs text-ink-gray-5"
						>
							suggested
						</span>
					</label>
				</div>
				<p v-if="!candidate.offered.length" class="mt-1 text-p-sm text-ink-gray-5">
					Nothing is listed to follow {{ candidate.program }}. Add next programs to it in
					the desk to offer one here.
				</p>
			</fieldset>

			<FormControl
				v-if="settings.status"
				v-model="draftStatus"
				type="select"
				label="Status"
				:options="statusOptions"
			/>
			<p v-if="unresolved" class="text-p-sm text-ink-red-4">
				Not enrolled in {{ targetTerm }}, so the status has to say how they left:
				{{ leaving.join(' or ') }}.
			</p>
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, FormControl, type DialogAction } from 'frappe-ui'
import {
	leavingStatuses,
	needsLeavingStatus,
	type AdvancementSettings,
	type Candidate,
	type Decision,
} from '@/data/advancementPlan'

const props = defineProps<{
	candidate: Candidate
	/** What the page holds for this student now. */
	decision: Decision
	suggestion: Decision
	holdReason: string | null
	settings: AdvancementSettings
	targetTerm: string
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
	save: [decision: Decision]
}>()

/** '' stands for "no new enrolment" and for "leave the status", which a
 *  radio and a select cannot hold as null. */
const draftProgram = ref('')
const draftStatus = ref('')

function load(decision: Decision) {
	draftProgram.value = decision.program ?? ''
	draftStatus.value = decision.status ?? ''
}

watch(open, (isOpen) => {
	if (isOpen) load(props.decision)
})
load(props.decision)

const programOptions = computed(() => [
	...props.candidate.offered.map((program) => ({ label: program, value: program })),
	{ label: 'No new enrolment', value: '' },
])

const statusOptions = computed(() => [
	{
		label: `Leave as is${props.candidate.status ? ` (${props.candidate.status})` : ''}`,
		value: '',
	},
	...(props.settings.status?.options ?? [])
		.filter((option) => option !== props.candidate.status)
		.map((option) => ({ label: option, value: option })),
])

// Picking a program offers the continuing status, and picking none takes it
// back off -- but only while the status is one the page put there, so a status
// somebody chose is never changed under them. On a pick, not on every change of
// the draft, so reopening a saved choice leaves it as it was saved.
function pickProgram(program: string) {
	const before = draftProgram.value
	draftProgram.value = program
	const continuing = props.settings.status?.continuing
	if (!continuing || continuing === props.candidate.status) return
	if (program && !before && !draftStatus.value) draftStatus.value = continuing
	if (!program && before && draftStatus.value === continuing) draftStatus.value = ''
}

const draft = computed<Decision>(() => ({
	program: draftProgram.value || null,
	status: draftStatus.value || null,
}))

const leaving = computed(() => leavingStatuses(props.settings))

/** Going nowhere with a status that says otherwise; see `needsLeavingStatus`. */
const unresolved = computed(() => needsLeavingStatus(props.candidate, draft.value, props.settings))

const actions = computed<DialogAction[]>(() => [
	{
		label: 'Use suggestion',
		variant: 'ghost',
		onClick: () => load(props.suggestion),
	},
	{
		label: 'Save',
		variant: 'solid',
		disabled: unresolved.value,
		onClick: ({ close }) => {
			emit('save', draft.value)
			close()
		},
	},
])
</script>
