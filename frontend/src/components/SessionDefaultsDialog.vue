<template>
	<!-- The desk's Session Defaults prompt (`frappe.ui.toolbar.setup_session_defaults`):
	     one Link field per doctype Session Default Settings lists, filled with
	     this user's current value, and a way to that settings page for somebody
	     allowed to change which doctypes those are. -->
	<Dialog v-model:open="open" title="Session Defaults" :actions="actions">
		<div class="space-y-4">
			<LinkControl
				v-for="field in userMenu.session_defaults"
				:key="field.fieldname"
				v-model="draft[field.fieldname]"
				:doctype="field.doctype"
				:label="field.label"
			/>

			<a
				v-if="userMenu.session_defaults_settings && hasDeskAccess"
				href="/app/session-default-settings"
				class="inline-block text-sm text-ink-gray-6 underline"
			>
				Settings
			</a>

			<ErrorMessage v-if="failed" message="An error occurred while setting Session Defaults" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Dialog, ErrorMessage, toast, type DialogAction } from 'frappe-ui'
import LinkControl from './LinkControl.vue'
import { hasDeskAccess } from '@/data/session'
import { saveSessionDefaults, savingSessionDefaults, userMenu } from '@/data/userMenu'

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [] }>()

const draft = reactive<Record<string, string | null>>({})
const failed = ref(false)

// Filled on open from what the page loaded with, rather than kept from the last
// time: a draft left over from a dialog that was dismissed was never saved.
watch(open, (isOpen) => {
	if (!isOpen) return
	for (const field of userMenu.value.session_defaults) draft[field.fieldname] = field.value
	failed.value = false
})

async function save() {
	failed.value = false
	if (!(await saveSessionDefaults(draft))) {
		failed.value = true
		return
	}
	toast.success('Session Defaults Saved')
	// The desk clears the cache and reloads here, so everything on the page is
	// read again under the new defaults; the parent does the same.
	emit('saved')
}

const actions = computed<DialogAction[]>(() => [
	{
		label: 'Save',
		variant: 'solid',
		loading: savingSessionDefaults.value,
		onClick: save,
	},
])
</script>
