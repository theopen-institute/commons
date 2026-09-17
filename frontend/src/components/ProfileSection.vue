<template>
	<section>
		<!-- A heading that reads as a break in the page rather than as a slightly
		     bolder row of its own: the sections are what make a long record
		     scannable, so they carry weight and a rule under them. -->
		<h2
			class="border-b border-outline-gray-1 pb-2 text-lg font-semibold text-ink-gray-9"
		>
			{{ section.title }}
		</h2>
		<p v-if="section.description" class="mt-1.5 text-p-sm text-ink-gray-5">
			{{ section.description }}
		</p>
		<!-- A description list, not a form of disabled inputs. The page is read
		     only by design rather than by a flag, and a row of greyed-out boxes
		     reads as "you may edit this later" -- which is exactly the wrong
		     promise when the way to change any of it is to propose it. -->
		<dl class="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2">
			<div
				v-for="field in section.fields"
				:key="field.fieldname"
				:class="field.type === 'textarea' ? 'sm:col-span-2' : ''"
			>
				<dt class="flex items-center gap-1.5 text-p-sm text-ink-gray-5">
					<span class="truncate">{{ field.label }}</span>
					<!-- An open proposal against this field, so nobody raises the same
					     correction twice while the first one is still in the queue. -->
					<Tooltip
						v-if="pending?.[field.fieldname] !== undefined"
						:text="`Waiting on review: ${displayValue(pending[field.fieldname])}`"
					>
						<Badge theme="amber" variant="subtle">Change pending</Badge>
					</Tooltip>
				</dt>
				<!-- The pencil sits with the value, not the label: the value is the
				     thing being corrected, and a control beside the name of a field
				     reads as editing the name. One per field rather than one for the
				     page -- what a person comes here to do is fix the one thing that
				     is wrong, and the fields with no pencil are the visible answer to
				     why a department is not theirs to correct. -->
				<dd class="mt-0.5 flex items-center gap-1.5">
					<span
						class="min-w-0 text-p-base"
						:class="[
							field.type === 'textarea' ? 'whitespace-pre-line' : 'truncate',
							isFieldFilled(doc[field.fieldname]) ? 'text-ink-gray-8' : 'text-ink-gray-4',
						]"
					>
						{{ render(field) }}
					</span>
					<!-- A bare button rather than frappe-ui's: at this size its padding
					     and hover surface are most of what you see, and the mark should
					     be quiet enough to ignore until it is wanted. Kept visible
					     rather than shown on hover -- a control you can only find with a
					     mouse is one a touch user never finds. -->
					<button
						v-if="canPropose(field)"
						type="button"
						class="shrink-0 rounded text-ink-gray-3 transition-colors hover:text-ink-gray-6 focus-visible:text-ink-gray-6"
						:aria-label="`Propose a change to ${field.label}`"
						:title="`Propose a change to ${field.label}`"
						@click="emit('propose', field)"
					>
						<span class="lucide-pencil block size-3.5" />
					</button>
				</dd>
			</div>
		</dl>
	</section>
</template>

<script setup lang="ts">
import { Badge, Button, Tooltip } from 'frappe-ui'
import { displayValue } from '@/data/profile'
import { isFieldFilled, type EmployeeField, type EmployeeSection } from '@/data/employeeFields'
import { formatDate } from '@/data/format'

const props = defineProps<{
	section: EmployeeSection
	/** The employee record being shown. Read, never written. */
	doc: Record<string, any>
	/** Proposed values from this employee's open requests, by fieldname. */
	pending?: Record<string, string | null>
	/** Fieldnames the server will accept a proposal for. Empty when this user
	 *  cannot raise one at all, which is what takes every button off the page. */
	proposable?: string[]
}>()

const emit = defineEmits<{ propose: [field: EmployeeField] }>()

function canPropose(field: EmployeeField): boolean {
	return props.proposable?.includes(field.fieldname) ?? false
}

// Dates are stored as YYYY-MM-DD and would otherwise read as the raw string;
// everything else this section shows is already text. An empty field reads as
// the same dash `displayValue` gives it everywhere else -- a short mark the eye
// skips, rather than "Not set" competing for attention with the values that are
// actually there.
function render(field: EmployeeField): string {
	const value = props.doc[field.fieldname]
	if (!isFieldFilled(value)) return displayValue(null)
	return field.type === 'date' ? formatDate(value as string) : displayValue(value)
}
</script>
