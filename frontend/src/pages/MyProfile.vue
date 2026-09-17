<template>
	<AppPageHeader>
		<div class="flex min-w-0 items-center gap-2">
			<Avatar
				v-if="profile"
				:image="profile.image"
				:label="profile.employee_name"
				size="md"
			/>
			<span class="truncate text-lg font-semibold text-ink-gray-8">
				{{ profile?.employee_name ?? 'Employee' }}
			</span>
			<Badge v-if="profile" :theme="statusTheme(profile.status)" variant="subtle">
				{{ profile.status }}
			</Badge>
		</div>
	</AppPageHeader>

	<div class="px-5 py-4">
		<!-- The permission answer refused rather than arrived: say so, instead of
         leaving a skeleton up for a reply that is never coming. -->
		<div v-if="loadError" class="mx-auto max-w-3xl">
			<ErrorMessage :message="loadError.message" class="mb-3" />
			<Button label="Try again" variant="subtle" @click="retry" />
		</div>

		<div v-else-if="!loaded" class="mx-auto max-w-3xl space-y-4">
			<Skeleton v-for="n in 5" :key="n" class="h-20 w-full rounded-4" />
		</div>

		<!-- Nothing to show, and which nothing it is decides who to ask. The
		     server tells the page apart from guessing: a record that exists and is
		     being withheld is a permissions question, and telling that person their
		     record does not exist sends them to HR to fix something HR has already
		     done. -->
		<div v-else-if="!profile" class="mx-auto mt-16 max-w-md text-center">
			<span
				class="mx-auto size-8 text-ink-gray-4"
				:class="profileCan.record_access === 'forbidden' ? 'lucide-lock' : 'lucide-user-x'"
			/>
			<template v-if="profileCan.record_access === 'forbidden'">
				<p class="mt-2 text-base-medium text-ink-gray-7">
					You don't have access to this record
				</p>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					If you should have access, contact a System Manager and ask for the permissions
					to be reviewed.
				</p>
			</template>
			<template v-else>
				<p class="mt-2 text-base-medium text-ink-gray-7">
					No active employee record is linked to your login
				</p>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					There's no profile to show until there is one. Ask HR to set the
					<span class="text-ink-gray-7">User account</span> field on yours to
					{{ user.name }}.
				</p>
			</template>
		</div>

		<div v-else class="mx-auto max-w-3xl">
			<Alert
				theme="gray"
				title="This page is read only"
				:description="
					profileCan.request
						? 'Your details are held by HR. Fields you can correct have a pencil beside them — your change goes to HR as a proposal.'
						: 'Your details are held by HR. Ask them to correct anything that is wrong.'
				"
			/>

			<div class="mt-6 space-y-8">
				<ProfileSection
					v-for="section in visibleSections"
					:key="section.title"
					:section="section"
					:doc="profile"
					:pending="pendingByField"
					:proposable="profileCan.request ? profileCan.proposable : []"
					@propose="editing = $event"
				/>
			</div>

			<dl
				class="mt-8 grid grid-cols-2 gap-2 border-t border-outline-gray-1 pt-4 text-p-sm text-ink-gray-5"
			>
				<div>
					<dt class="text-ink-gray-6">Employee ID</dt>
					<dd>{{ profile.name }}</dd>
				</div>
				<div>
					<dt class="text-ink-gray-6">Last modified</dt>
					<dd>{{ formatDate(profile.modified?.slice(0, 10)) }}</dd>
				</div>
			</dl>

			<section class="mt-10">
				<div class="flex items-center justify-between">
					<h2 class="text-base-medium text-ink-gray-8">Change requests</h2>
					<Button
						variant="ghost"
						icon-left="lucide-refresh-cw"
						label="Refresh"
						:loading="requests.loading"
						@click="refresh"
					/>
				</div>

				<ErrorMessage
					v-if="requests.error"
					:message="requests.error.message"
					class="mt-3"
				/>

				<div v-if="requests.loading && !requests.data" class="mt-3 space-y-2">
					<Skeleton v-for="n in 2" :key="n" class="h-24 w-full rounded-4" />
				</div>

				<div
					v-else-if="requests.data?.length === 0"
					class="mt-3 rounded-4 border border-dashed border-outline-gray-2 px-4 py-10 text-center"
				>
					<p class="text-base-medium text-ink-gray-7">Nothing proposed yet</p>
					<p class="mt-1 text-p-sm text-ink-gray-5">
						Corrections you send to HR, and what they decided, show up here.
					</p>
				</div>

				<ul v-else-if="requests.data" class="mt-3 space-y-3">
					<li
						v-for="row in requests.data"
						:key="row.name"
						class="rounded-4 border border-outline-gray-1 p-4"
					>
						<div class="flex flex-wrap items-start justify-between gap-3">
							<div class="min-w-0">
								<div class="text-base-medium text-ink-gray-8">
									{{ pluralise(row.changes.length, 'change') }}
								</div>
								<div class="mt-0.5 text-p-sm text-ink-gray-5">
									Sent {{ formatDate(row.posting_date) }}
								</div>
							</div>
							<Badge :theme="profileStatus(row).theme" variant="subtle">
								{{ profileStatus(row).label }}
							</Badge>
						</div>

						<ChangeDiff :changes="row.changes" class="mt-3" />

						<p v-if="row.reason" class="mt-3 text-p-sm text-ink-gray-6">
							{{ row.reason }}
						</p>

						<!-- Why it went the way it did. Worth more than the badge when the
                 answer was no. -->
						<p
							v-if="row.review_note"
							class="mt-3 rounded-4 bg-surface-gray-2 px-3 py-2 text-p-sm text-ink-gray-7"
						>
							<span class="text-ink-gray-5">HR:</span> {{ row.review_note }}
						</p>

						<!-- The employee's own way out of a request they've thought better
                 of. Which outcomes they may apply is the server's answer, so a
                 site whose workflow offers none simply gets no buttons. -->
						<div v-if="row.can_decide" class="mt-4 flex items-center gap-2">
							<Button
								v-for="button in decisionButtons(
									row.actions,
									profileCan.decisions,
								)"
								:key="button.decision"
								variant="subtle"
								:theme="button.theme"
								:label="button.label"
								:icon-left="button.icon"
								:loading="deciding === `${row.name}:${button.decision}`"
								:disabled="Boolean(deciding)"
								@click="withdraw(row, button)"
							/>
						</div>
					</li>
				</ul>
			</section>
		</div>

		<ProposeFieldDialog
			v-if="profile"
			:profile="profile"
			:field="editing"
			:pending="pendingByField"
			@close="editing = null"
			@created="refresh"
		/>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Alert, Avatar, Badge, Button, ErrorMessage, Skeleton, dialog, toast } from 'frappe-ui'
import { user } from '@/data/session'
import {
	decisionButtons,
	myProfile,
	myProfileError,
	myProfileLoaded,
	profileCan,
	profilePermissionsError,
	profilePermissionsLoaded,
	profileStatus,
	reloadMyProfile,
	reloadProfilePermissions,
	reloadProfileWorkflow,
	useMyProfileChanges,
	useProfileDecision,
	type DecisionButton,
	type ProfileChangeRequest,
} from '@/data/profile'
import { employeeSections, type EmployeeField } from '@/data/employeeFields'
import { formatDate, pluralise, statusTheme } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ChangeDiff from '@/components/ChangeDiff.vue'
import ProfileSection from '@/components/ProfileSection.vue'
import ProposeFieldDialog from '@/components/ProposeFieldDialog.vue'

// Which field the propose dialog is open on, or null when it is closed. One
// nullable ref rather than a field plus a visibility flag, so the two cannot
// disagree about what is being asked.
const editing = ref<EmployeeField | null>(null)

const profile = computed(() => myProfile.value)

// Both answers, because the page needs both before it can draw anything: the
// record to show, and whether this user may propose against it.
const loaded = computed(() => myProfileLoaded.value && profilePermissionsLoaded.value)
const loadError = computed(() => myProfileError.value ?? profilePermissionsError.value)

// Both, not just the one that failed: either can be the refusal on screen, and
// a retry that fixes one and leaves the other stale would clear the message
// without clearing what caused it.
function retry() {
	reloadMyProfile()
	reloadProfilePermissions()
}

const requests = useMyProfileChanges()

// Exit details are noise on an active employee, so the section follows the
// record's own status -- the same rule the detail page applies.
const visibleSections = computed(() =>
	employeeSections.filter(
		(section) => !section.visibleWhen || section.visibleWhen(profile.value ?? {}),
	),
)

/**
 * The proposed value for every field sitting in an undecided request.
 *
 * `open` is the server's answer, not `docstatus`: a declined or withdrawn
 * request stays at docstatus 0 so it can be amended, so reading the docstatus
 * here would mark fields as pending long after they were settled.
 */
const pendingByField = computed(() => {
	const pending: Record<string, string | null> = {}
	for (const row of requests.data ?? []) {
		if (!row.open) continue
		for (const change of row.changes) {
			pending[change.fieldname] = change.proposed_value
		}
	}
	return pending
})

const decision = useProfileDecision()

// Keyed by request and outcome so only the button that was pressed spins.
const deciding = ref('')

function withdraw(row: ProfileChangeRequest, button: DecisionButton) {
	dialog.danger({
		title: `${button.label} request`,
		message: `${button.label} this request? HR will no longer see it, and your record keeps the values it has now.`,
		confirmLabel: button.label,
		onConfirm: async () => {
			deciding.value = `${row.name}:${button.decision}`
			try {
				const result = await decision.submit({
					name: row.name,
					decision: button.decision,
				})
				// Throwing keeps the dialog open and renders the reason inline, which
				// is what should happen when the server refuses the transition.
				if (!result) throw decision.error ?? new Error('Could not withdraw the request')
				toast.success('Request withdrawn')
				refresh()
			} finally {
				deciding.value = ''
			}
		},
	})
}

function refresh() {
	requests.reload()
	// The record itself may have moved -- an approval applies to it -- and a
	// workflow's states are where the next row's label and buttons come from.
	reloadMyProfile()
	reloadProfilePermissions()
	reloadProfileWorkflow()
}
</script>
