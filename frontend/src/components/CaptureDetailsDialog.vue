<!--
  One capture that is not ready to draft from: held unread, or failed.

  The scan, where it came from, and why it has not been read, with the two
  things that can be done about it: read it (as whichever kind it is), or put
  it aside. Reading is billed, so it is always this button and never a click
  on the page's list.
-->

<template>
	<Dialog
		v-model:open="open"
		:title="capture?.subject || capture?.name || 'Scan'"
		:actions="actions"
		size="4xl"
	>
		<div v-if="capture" class="grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
			<div
				class="h-[60dvh] overflow-auto rounded-4 border border-outline-gray-2 bg-surface-gray-1"
			>
				<template v-if="capture.scan">
					<iframe
						v-if="isPdfUrl(capture.scan)"
						:src="capture.scan"
						class="size-full"
						title="The scan"
					/>
					<a
						v-else
						:href="capture.scan"
						target="_blank"
						rel="noopener"
						title="Open the scan full size"
					>
						<img :src="capture.scan" alt="The scan" class="block w-full" />
					</a>
				</template>
				<p v-else class="p-6 text-center text-p-sm text-ink-gray-5">
					No scan. Attach one to {{ capture.name }} in the desk, then read it here.
				</p>
			</div>

			<div class="space-y-4">
				<dl class="space-y-2 text-p-sm">
					<div>
						<dt class="text-ink-gray-5">Capture</dt>
						<dd class="text-ink-gray-8">
							<a
								:href="deskUrl('Captured Document', capture.name)"
								target="_blank"
								rel="noopener"
								class="underline"
							>
								{{ capture.name }}
							</a>
							· {{ capture.source === 'Email' ? 'emailed' : 'uploaded' }}
							{{ formatDate(capture.creation) }}
						</dd>
					</div>
					<div v-if="capture.sender">
						<dt class="text-ink-gray-5">From</dt>
						<dd class="text-ink-gray-8">
							{{ capture.sender_name || capture.sender }} &lt;{{
								capture.sender
							}}&gt;
						</dd>
					</div>
				</dl>

				<div
					v-if="capture.error"
					class="rounded-4 border border-outline-amber-3 bg-surface-amber-2 px-3 py-2 text-p-sm text-ink-gray-8"
				>
					<p class="text-base-medium text-ink-gray-8">
						{{ capture.state === 'failed' ? 'The reading failed' : 'Not read yet' }}
					</p>
					<p class="mt-0.5">{{ capture.error }}</p>
				</div>

				<FormControl
					v-if="kindOptions.length > 1"
					v-model="kind"
					type="select"
					label="Read it as"
					:options="kindOptions"
				/>
				<p v-else class="text-p-sm text-ink-gray-6">
					Read as a {{ KIND_LABELS[kind].noun.toLowerCase() }}.
				</p>
				<p class="text-p-xs text-ink-gray-5">
					Claude reads it in the background, which usually takes under a minute. Each
					reading is billed to the site.
				</p>

				<ErrorMessage v-if="failure" :message="failure" />
			</div>
		</div>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog, ErrorMessage, FormControl, type DialogAction } from 'frappe-ui'
import {
	KIND_LABELS,
	captureCan,
	deskUrl,
	isPdfUrl,
	useDiscardCapture,
	useReadCapture,
	type CaptureKind,
	type CaptureRow,
} from '@/data/capture'
import { formatDate } from '@/data/format'

const props = defineProps<{ capture: CaptureRow | null }>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ queued: [name: string]; discarded: [name: string] }>()

const read = useReadCapture()
const discard = useDiscardCapture()
const kind = ref<CaptureKind>('Purchase Invoice')
const failure = ref('')

watch(
	() => props.capture,
	(capture) => {
		if (capture) kind.value = capture.document_type
		failure.value = ''
	},
	{ immediate: true }
)

const kindOptions = computed(() =>
	captureCan.value.kinds.map((value) => ({ label: KIND_LABELS[value].noun, value }))
)

const actions = computed<DialogAction[]>(() => [
	{ label: 'Discard', variant: 'ghost', theme: 'red', onClick: ({ close }) => discardIt(close) },
	{
		label: 'Read it',
		variant: 'solid',
		disabled: !props.capture?.scan,
		onClick: ({ close }) => readIt(close),
	},
])

async function readIt(close: () => void) {
	if (!props.capture) return
	failure.value = ''
	const answer = await read.submit({ name: props.capture.name, document_type: kind.value })
	if (!answer) {
		failure.value = read.error?.message ?? 'It could not be sent to be read.'
		return
	}
	emit('queued', props.capture.name)
	close()
}

async function discardIt(close: () => void) {
	if (!props.capture) return
	failure.value = ''
	await discard.submit({ name: props.capture.name })
	if (discard.error) {
		failure.value = discard.error.message
		return
	}
	emit('discarded', props.capture.name)
	close()
}
</script>
