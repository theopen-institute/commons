<template>
	<section>
		<h2 class="text-base-medium text-ink-gray-8">{{ section.title }}</h2>
		<p v-if="section.description" class="mt-0.5 text-p-sm text-ink-gray-5">
			{{ section.description }}
		</p>
		<!-- A description list, not a form of disabled inputs. The page is read
         only by design rather than by a flag, and a row of greyed-out boxes
         reads as "you may edit this later" -- which is exactly the wrong
         promise when the way to change any of it is to propose it. -->
		<dl class="mt-3 grid gap-x-6 gap-y-4 sm:grid-cols-2">
			<div
				v-for="field in section.fields"
				:key="field.fieldname"
				:class="field.type === 'textarea' ? 'sm:col-span-2' : ''"
			>
				<dt class="flex items-center gap-1.5 text-p-sm text-ink-gray-5">
					{{ field.label }}
					<!-- An open proposal against this field, so nobody raises the same
               correction twice while the first one is still in the queue. -->
					<Tooltip
						v-if="pending?.[field.fieldname] !== undefined"
						:text="`Waiting on review: ${displayValue(pending[field.fieldname])}`"
					>
						<Badge theme="amber" variant="subtle">Change pending</Badge>
					</Tooltip>
				</dt>
				<dd
					class="mt-0.5 text-p-base text-ink-gray-8"
					:class="[
						field.type === 'textarea' ? 'whitespace-pre-line' : 'truncate',
						isFieldFilled(doc[field.fieldname]) ? '' : 'text-ink-gray-4',
					]"
				>
					{{ render(field) }}
				</dd>
			</div>
		</dl>
	</section>
</template>

<script setup lang="ts">
import { Badge, Tooltip } from 'frappe-ui'
import { displayValue } from '@/data/profile'
import { isFieldFilled, type EmployeeField, type EmployeeSection } from '@/data/employeeFields'
import { formatDate } from '@/data/format'

const props = defineProps<{
	section: EmployeeSection
	/** The employee record being shown. Read, never written. */
	doc: Record<string, any>
	/** Proposed values from this employee's open requests, by fieldname. */
	pending?: Record<string, string | null>
}>()

// Dates are stored as YYYY-MM-DD and would otherwise read as the raw string;
// everything else this section shows is already text.
function render(field: EmployeeField): string {
	const value = props.doc[field.fieldname]
	if (!isFieldFilled(value)) return 'Not set'
	return field.type === 'date' ? formatDate(value as string) : displayValue(value)
}
</script>
