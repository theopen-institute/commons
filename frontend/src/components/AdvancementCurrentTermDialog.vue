<!--
  Make a term the current one in Education Settings, on its own -- for a term
  advanced into without ticking it on Apply, or whose students were enrolled
  some other way.
-->

<template>
	<Dialog v-model:open="open" title="Change the current term" :actions="actions" size="md">
		<div class="space-y-2 text-p-base text-ink-gray-7">
			<p>
				Make <b>{{ term }}</b> the current term, in place of
				{{ currentTerm || 'no term' }}?
			</p>
			<p class="text-p-sm text-ink-gray-5">
				Education Settings changes for the whole site. The attendance register and
				Education's own pages open on the current term.
			</p>
			<ErrorMessage v-if="problem" :message="problem" />
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, ErrorMessage, toast, type DialogAction } from 'frappe-ui'
import { useMakeCurrent } from '@/data/advancement'

const props = defineProps<{
	term: string
	currentTerm: string | null
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ changed: [term: string] }>()

const call = useMakeCurrent()
const busy = ref(false)
const problem = ref('')

watch(open, (isOpen) => {
	if (isOpen) problem.value = ''
})

async function submit(close: () => void) {
	busy.value = true
	problem.value = ''
	try {
		const result = await call.submit({ term: props.term })
		if (!result || call.error) {
			problem.value = call.error?.message || 'The current term could not be changed.'
			return
		}
		toast.success(`${result} is now the current term`)
		emit('changed', result)
		close()
	} finally {
		busy.value = false
	}
}

const actions = computed<DialogAction[]>(() => [
	{
		label: `Make ${props.term} current`,
		variant: 'solid',
		loading: busy.value,
		onClick: ({ close }) => submit(close),
	},
])
</script>
