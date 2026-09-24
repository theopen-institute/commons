<template>
  <AppPageHeader>
    <div class="flex min-w-0 items-center gap-3">
      <span class="text-lg font-semibold text-ink-gray-8">Document Capture</span>
    </div>
  </AppPageHeader>

  <div class="px-5 py-4">
    <!-- The sidebar hides this page from anybody who cannot create a Purchase
         Invoice, so only somebody following a link lands here. -->
    <div v-if="captureGate.resolved.value && !captureCan.capture" class="mt-16 text-center">
      <span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
      <p class="mt-2 text-base-medium text-ink-gray-7">Booking purchase invoices isn't yours to do</p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        This page drafts purchase invoices from scans. Ask whoever administers permissions if that should
        include you.
      </p>
    </div>

    <div v-else class="mx-auto max-w-3xl">
      <!-- The one thing the page does. Choosing a file reads it; nothing is
           written to the site until the draft is created in the dialog. -->
      <section
        class="rounded-4 border-2 border-dashed px-6 py-8 text-center transition-colors"
        :class="dragging ? 'border-outline-gray-4 bg-surface-gray-2' : 'border-outline-gray-2'"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
      >
        <template v-if="reading.busy">
          <LoadingIndicator class="mx-auto size-6 text-ink-gray-6" />
          <p class="mt-3 text-base-medium text-ink-gray-8">Reading {{ reading.pending }}</p>
          <p class="mt-1 text-p-sm text-ink-gray-5">This usually takes ten to thirty seconds.</p>
        </template>
        <template v-else>
          <span class="lucide-scan-text mx-auto size-8 text-ink-gray-5" />
          <p class="mt-2 text-base-medium text-ink-gray-8">Scan a supplier's invoice</p>
          <p class="mx-auto mt-1 max-w-md text-p-sm text-ink-gray-5">
            A photo or a PDF of one invoice. Claude reads it and drafts a purchase invoice for you to check
            against the scan, and the scan is attached to the draft.
          </p>
          <Button class="mt-4" variant="solid" icon-left="lucide-upload" label="Choose a scan" @click="pick" />
          <p class="mt-2 text-p-xs text-ink-gray-5">Or drop the file here.</p>
        </template>

        <!-- `hidden` rather than styled: the button above is the control. On
             a phone the picker offers the camera. -->
        <input ref="fileInput" type="file" class="hidden" :accept="ACCEPTED_SCANS" @change="onPicked" />
      </section>

      <ErrorMessage v-if="reading.error" :message="reading.error" class="mt-3" />

      <!-- A reading is paid for, so closing the dialog does not throw it away. -->
      <section
        v-if="reading.result && !dialogOpen && !reading.busy"
        class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-4 border border-outline-gray-2 px-4 py-3"
      >
        <div class="min-w-0">
          <p class="truncate text-base-medium text-ink-gray-8">
            {{ reading.result.extracted.supplier.name || reading.file?.name }}
          </p>
          <p class="text-p-sm text-ink-gray-5">
            Read, not yet saved<template v-if="reading.result.extracted.total !== null">
              · {{ formatExact(reading.result.extracted.total, reading.result.extracted.currency) }}</template
            >
          </p>
        </div>
        <div class="flex shrink-0 gap-2">
          <Button variant="ghost" label="Discard" @click="discard" />
          <Button variant="subtle" label="Continue checking" @click="dialogOpen = true" />
        </div>
      </section>

      <section class="mt-8">
        <div class="flex items-center justify-between">
          <h2 class="text-base-medium text-ink-gray-8">Your drafts</h2>
          <Button
            variant="ghost"
            icon-left="lucide-refresh-cw"
            label="Refresh"
            :loading="drafts.loading.value"
            @click="drafts.load()"
          />
        </div>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Purchase invoices you have made and not yet submitted, however they were made. Open one in the
          desk to submit it.
        </p>

        <ErrorMessage v-if="drafts.error.value" :message="drafts.error.value.message" class="mt-3" />

        <div v-if="!drafts.loaded.value" class="mt-3 space-y-2">
          <Skeleton v-for="n in 3" :key="n" class="h-14 w-full rounded-4" />
        </div>

        <p v-else-if="!drafts.rows.value.length" class="mt-6 text-center text-p-sm text-ink-gray-5">
          Nothing waiting to be submitted.
        </p>

        <ul v-else class="mt-3 divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-1">
          <li v-for="row in drafts.rows.value" :key="row.name">
            <a
              :href="deskUrl(PURCHASE_INVOICE, row.name)"
              target="_blank"
              rel="noopener"
              class="flex items-center justify-between gap-3 px-4 py-3 hover:bg-surface-gray-1"
              :class="row.name === justCreated ? 'bg-surface-gray-1' : ''"
            >
              <div class="min-w-0">
                <p class="truncate text-base text-ink-gray-8">{{ row.supplier_name || row.supplier }}</p>
                <p class="truncate text-p-sm text-ink-gray-5">
                  {{ row.name }}<template v-if="row.bill_no"> · bill {{ row.bill_no }}</template> ·
                  {{ formatDate(row.posting_date) }} · {{ row.company }}
                </p>
              </div>
              <span class="shrink-0 text-base tabular-nums text-ink-gray-7">
                {{ formatExact(row.grand_total, row.currency) }}
              </span>
            </a>
          </li>
        </ul>
      </section>
    </div>

    <CaptureInvoiceDialog
      v-model:open="dialogOpen"
      :reading="reading.result"
      :file="reading.file"
      @created="onCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { Button, ErrorMessage, LoadingIndicator, Skeleton } from 'frappe-ui'
import AppPageHeader from '@/components/AppPageHeader.vue'
import CaptureInvoiceDialog from '@/components/CaptureInvoiceDialog.vue'
import {
  ACCEPTED_SCANS,
  PURCHASE_INVOICE,
  captureCan,
  captureGate,
  deskUrl,
  readInvoice,
  useMyDrafts,
} from '@/data/capture'
import type { Reading } from '@/data/captureRules'
import { formatDate, formatExact } from '@/data/format'

/**
 * Document capture: a scan in, a draft Purchase Invoice out.
 *
 * The page itself writes nothing. Choosing a scan sends it to be read, which
 * stores nothing either, and the dialog that opens holds the draft and has the
 * one button that saves it. See `commons.document_capture` for the order of
 * the calls, and `CaptureInvoiceDialog.vue` for the draft.
 *
 * Purchase invoices are the only document it takes so far. The page is named
 * for what it does rather than for them, because bank statements are the next
 * thing it should read.
 */

const drafts = useMyDrafts()

watch(
  () => captureCan.value.capture,
  (can) => {
    if (can) drafts.load()
  },
  { immediate: true },
)

/** The scan the dialog shows and the reading of it, which stay together: a
 *  failed read of a second scan leaves the first one's reading as it was. */
const reading = reactive<{
  file: File | null
  result: Reading | null
  pending: string
  busy: boolean
  error: string
}>({ file: null, result: null, pending: '', busy: false, error: '' })

const dialogOpen = ref(false)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const justCreated = ref('')

function pick() {
  fileInput.value?.click()
}

function onPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // Cleared so the same file can be chosen again after a failed read.
  input.value = ''
  if (file) read(file)
}

function onDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file && !reading.busy) read(file)
}

async function read(file: File) {
  reading.busy = true
  reading.pending = file.name
  reading.error = ''
  try {
    const result = await readInvoice(file)
    reading.file = file
    reading.result = result
    dialogOpen.value = true
  } catch (error) {
    reading.error = error instanceof Error ? error.message : 'That scan could not be read.'
  } finally {
    reading.busy = false
  }
}

function discard() {
  reading.file = null
  reading.result = null
}

function onCreated(name: string) {
  justCreated.value = name
  discard()
  drafts.load()
}
</script>
