<template>
	<AppPageHeader>
		<div class="flex min-w-0 items-center gap-2">
			<span class="truncate text-lg font-semibold text-ink-gray-8">
				{{ can.label || nav?.label || 'Records' }}
			</span>
			<Badge v-if="pendingCount" theme="amber" variant="subtle">
				{{ pluralise(pendingCount, 'request') }} pending
			</Badge>
		</div>
		<template #actions>
			<div class="flex items-center gap-2">
				<Button
					v-if="can.allow_new && can.request"
					variant="solid"
					icon-left="lucide-plus"
					:label="`Propose new`"
					@click="showNew = true"
				/>
				<Button
					variant="ghost"
					icon-left="lucide-refresh-cw"
					label="Refresh"
					:loading="!recordsLoaded"
					@click="refresh"
				/>
			</div>
		</template>
	</AppPageHeader>

	<div class="px-5 py-4">
		<div v-if="loadError" class="mx-auto max-w-3xl">
			<ErrorMessage :message="loadError.message" class="mb-3" />
			<Button label="Try again" variant="subtle" @click="refresh" />
		</div>

		<div v-else-if="!recordsLoaded" class="mx-auto max-w-3xl space-y-4">
			<Skeleton v-for="n in 4" :key="n" class="h-20 w-full rounded-4" />
		</div>

		<!-- Nothing to show, and which nothing it is decides who to ask. The
		     wording is the record type's own -- see `Self Service Record` -- so a
		     page can send somebody to payroll rather than to HR. -->
		<div v-else-if="!records.length" class="mx-auto mt-16 max-w-md text-center">
			<span
				class="mx-auto size-8 text-ink-gray-4"
				:class="
					can.record_access === 'forbidden' ? 'lucide-lock' : nav?.icon || 'lucide-inbox'
				"
			/>
			<p class="mt-2 text-base-medium text-ink-gray-7">
				{{
					can.record_access === 'forbidden'
						? "You don't have access to these records"
						: `Nothing here yet`
				}}
			</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				{{
					can.record_access === 'forbidden'
						? "Your account isn't permitted to open them. If you should be able to see yours, ask a System Manager to review the permissions."
						: can.empty_notice || 'There is nothing of this kind against your name.'
				}}
			</p>
			<Button
				v-if="can.allow_new && can.request"
				class="mt-4"
				variant="subtle"
				icon-left="lucide-plus"
				label="Propose new"
				@click="showNew = true"
			/>
		</div>

		<div v-else class="mx-auto max-w-3xl">
			<Alert
				theme="gray"
				title="This page is read only"
				:description="
					can.read_only_notice ||
					'These details are held for you. Use the pencils to propose a correction — someone reviews it before anything changes.'
				"
			/>

			<!-- One record, or several. The shape is the record type's, not this
			     page's: `singular` says whether an owner has one of these. A page that
			     can hold several gives each its own card: the run of sections inside one
			     record looks exactly like the run inside the next, so without an edge
			     around each there is nothing to say where one bank account stops and the
			     one below it starts. A page with a single record needs no such edge --
			     boxing the only thing on the page just adds a line to look at. -->
			<div class="mt-6 space-y-4">
				<div
					v-for="record in records"
					:key="record.name"
					:class="
						can.singular ? '' : 'overflow-hidden rounded-4 border border-outline-gray-1'
					"
				>
					<!-- The card's own header, on a band rather than under a rule: it names
					     which record everything below it belongs to, and a band reads as the
					     top of a box in a way another underline would not, with the section
					     headings inside already carrying rules of their own. -->
					<div
						v-if="!can.singular"
						class="flex flex-wrap items-center justify-between gap-2 border-b border-outline-gray-1 bg-surface-gray-1 px-4 py-2.5"
					>
						<div class="flex min-w-0 items-center gap-2">
							<h2 class="truncate text-lg font-semibold text-ink-gray-9">
								{{ titleOf(record) }}
							</h2>
							<!-- A record somebody has asked to have removed still shows its
							     details, because nothing has happened to it yet -- but reading it
							     as ordinary would be wrong, and the pencils beside its fields
							     would invite corrections to something on its way out. -->
							<Badge v-if="removalPending(record)" theme="red" variant="subtle">
								Removal pending
							</Badge>
						</div>
						<Button
							v-if="can.allow_delete && can.request"
							variant="ghost"
							theme="red"
							size="sm"
							:icon-left="removalPending(record) ? 'lucide-clock' : 'lucide-trash-2'"
							:label="removalPending(record) ? 'Removal requested' : 'Propose removal'"
							:disabled="removalPending(record)"
							:loading="deleting === record.name"
							@click="proposeRemoval(record)"
						/>
					</div>

					<div
						class="space-y-8"
						:class="[
							can.singular ? '' : 'p-4 sm:p-5',
							removalPending(record) ? 'opacity-60' : '',
						]"
					>
						<ProfileSection
							v-for="section in can.sections"
							:key="section.title"
							:section="section"
							:doc="record"
							:pending="pendingFor(record)"
							:can-propose="can.request && !removalPending(record)"
							@propose="(field) => startEdit(record, field)"
						/>
					</div>
				</div>
			</div>

			<!-- What the records say, and what somebody has asked to change about
			     them, are two different kinds of thing, and the second was reading as
			     one more section of the first: same heading weight, same bordered
			     cards, only a gap between them. The rule and the space are the seam,
			     and the panel behind the requests keeps them on their own ground. -->
			<div
				v-if="can.proposable.length || can.allow_new || can.allow_delete"
				class="mt-10 border-t border-outline-gray-2 pt-10"
			>
				<ChangeRequestList
					v-model:tab="changesTab"
					:requests="changes.data ?? []"
					:loading="changes.loading && !changes.data"
					:decisions="can.decisions"
					@refresh="refresh"
				/>
			</div>
		</div>

		<ProposeFieldDialog
			v-if="editing"
			:record="editing.record"
			:field="editing.field"
			:pending="pendingFor(editing.record)"
			:doctype="doctype"
			:reference-name="editing.record.name"
			@close="editing = null"
			@created="refresh"
		/>

		<ProposeRecordDialog
			v-if="can.allow_new"
			v-model:open="showNew"
			:doctype="doctype"
			:label="can.label || nav?.label || 'record'"
			:fields="proposableFields"
			@created="refresh"
		/>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Alert, Badge, Button, ErrorMessage, Skeleton, dialog, toast } from 'frappe-ui'
import {
	navBySlug,
	useMyChanges,
	useRaiseRequest,
	useSelfServiceRecords,
	type RecordField,
} from '@/data/selfService'
import { pluralise } from '@/data/format'
import AppPageHeader from '@/components/AppPageHeader.vue'
import ChangeRequestList from '@/components/ChangeRequestList.vue'
import ProfileSection from '@/components/ProfileSection.vue'
import ProposeFieldDialog from '@/components/ProposeFieldDialog.vue'
import ProposeRecordDialog from '@/components/ProposeRecordDialog.vue'

/**
 * One self-service page, for whichever record type the address names.
 *
 * There is nothing about employees or bank accounts here. Which fields to show,
 * how they are grouped, what the page is called, what it says when there is
 * nothing, and whether an owner may add or remove records are all the server's
 * answers -- see `Self Service Record`. Adding a third record type is a desk
 * entry and no code at all.
 */
const props = defineProps<{ slug: string }>()

const nav = computed(() => navBySlug(props.slug))
const doctype = computed(() => nav.value?.doctype ?? '')

// Created once, with getters. The record type arrives with the navigation and
// changes again when the address does; a composable called inside a computed
// would build a fresh set of calls on every read and none of them would settle.
const source = useSelfServiceRecords<Record<string, any>>(() => doctype.value)
const changesTab = ref<'pending' | 'history'>('pending')

// Two lists, not one switched between. The open requests are what marks a field
// as already having a proposal against it and what the header badge counts, and
// neither of those should empty out because somebody looked at their history.
const pendingChanges = useMyChanges(() => doctype.value)
const historyChanges = useMyChanges(
	() => doctype.value,
	true,
	// Dormant until asked for: nobody opens a profile to read history.
	() => changesTab.value === 'history',
)
const changes = computed(() =>
	changesTab.value === 'history' ? historyChanges : pendingChanges,
)

const can = source.can
const records = source.records
const recordsLoaded = computed(() => Boolean(doctype.value) && source.recordsLoaded.value)
const loadError = computed(
	() => source.permissionsError.value ?? source.recordsError.value
)
const request = useRaiseRequest()

const showNew = ref(false)
const editing = ref<{ record: Record<string, any>; field: RecordField } | null>(null)
const deleting = ref('')

const proposableFields = computed(() =>
	can.value.sections.flatMap((section) => section.fields.filter((f) => f.proposable))
)

function titleOf(record: Record<string, any>) {
	const [first] = can.value.sections.flatMap((s) => s.fields)
	return record[first?.fieldname ?? 'name'] || record.name
}

function startEdit(record: Record<string, any>, field: RecordField) {
	editing.value = { record, field }
}

/**
 * Proposals still awaiting a decision, by fieldname, for one record.
 *
 * `open` is the server's answer rather than `docstatus`: a declined or withdrawn
 * request stays at 0 so it can be amended, so reading the docstatus would mark
 * fields as pending long after they were settled.
 */
function pendingFor(record: Record<string, any>) {
	const pending: Record<string, string | null> = {}
	for (const row of pendingChanges.data ?? []) {
		if (!row.open || row.reference_name !== record.name) continue
		for (const change of row.changes) pending[change.fieldname] = change.proposed_value
	}
	return pending
}

/**
 * Whether somebody has asked for this record to be removed and nobody has
 * decided yet.
 *
 * `open` is the server's answer rather than `docstatus`: a declined or withdrawn
 * request stays at 0 so it can be amended, so reading the docstatus would leave
 * a record marked for removal long after the request was turned down.
 */
function removalPending(record: Record<string, any>): boolean {
	return (pendingChanges.data ?? []).some(
		(row) =>
			row.open && row.request_type === 'Delete' && row.reference_name === record.name,
	)
}

const pendingCount = computed(
	() => (pendingChanges.data ?? []).filter((row) => row.open).length,
)

function proposeRemoval(record: Record<string, any>) {
	const label = titleOf(record)
	dialog.danger({
		title: 'Propose removal',
		message: `Ask for ${label} to be removed? Nothing is deleted until someone approves it.`,
		confirmLabel: 'Send for review',
		onConfirm: async () => {
			deleting.value = record.name
			try {
				const created = await request.submit({
					doctype: doctype.value,
					doc: JSON.stringify({
						request_type: 'Delete',
						reference_name: record.name,
					}),
				})
				// Throwing keeps the dialog open and renders the reason inline.
				if (!created) throw request.error ?? new Error('Could not send the request')
				toast.success('Sent for review')
				refresh()
			} finally {
				deleting.value = ''
			}
		},
	})
}

function refresh() {
	source.reload()
	// The open list always: it feeds the field markers and the badge whichever
	// tab is showing. The history only when it is the one on screen.
	pendingChanges.reload()
	if (changesTab.value === 'history') historyChanges.reload()
}

// A different record type is a different page; nothing from the last one should
// survive the navigation.
watch(
	() => props.slug,
	() => {
		editing.value = null
		showNew.value = false
	}
)
</script>
