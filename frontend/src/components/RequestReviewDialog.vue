<!--
  One request, opened from an approvals list, with its decision buttons.

  The shell the leave, expense and procurement review dialogs share: the
  request's details go in the default slot, and the buttons along the footer
  are the only place on those pages where a decision is written. The lists
  used to carry the buttons themselves, and an outcome that needed no
  confirming was written on the first click, from a row read at a glance.

  The footer is drawn here rather than handed to Dialog as `actions`: Dialog
  rebuilds its actions whenever the list changes and forgets which one was
  spinning, and while one decision is being written the others must stay
  pressed down.
-->

<template>
  <Dialog
    v-model:open="open"
    :title="title"
    :dismissible="dismissible && !running"
    size="2xl"
  >
    <div class="space-y-4">
      <p v-if="message" class="text-p-sm text-ink-gray-5">{{ message }}</p>

      <slot />

      <!-- The list refreshed under the dialog and this request left it:
           settled by someone else, or moved on by the decision just refused. -->
      <Alert
        v-if="gone"
        theme="amber"
        title="This request has moved on"
        description="It is no longer in this list, so there is nothing to decide here. Someone may have settled it since it was opened."
      />

      <ErrorMessage v-if="error" :message="error" />
    </div>

    <template v-if="(buttons.length && !gone) || $slots.footer" #actions="{ close }">
      <div class="flex flex-wrap items-center gap-2">
        <slot name="footer" />
        <div v-if="!gone" class="ml-auto flex flex-wrap items-center gap-2">
          <Button
            v-for="button in buttons"
            :key="button.key"
            :variant="button.variant"
            :theme="button.theme"
            :label="button.label"
            :icon-left="button.icon"
            :loading="running === button.key"
            :disabled="Boolean(running)"
            @click="emit('choose', button.key, close)"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { Alert, Button, Dialog, ErrorMessage } from 'frappe-ui'
import type { ButtonTheme } from '@/data/workflowStyle'

/** One decision along the footer. `key` is what `choose` hands back. */
export interface ReviewButton {
  key: string
  label: string
  theme: ButtonTheme
  variant: 'solid' | 'subtle'
  icon?: string
}

withDefaults(
  defineProps<{
    title: string
    /** One line under the title: who asked, and when. */
    message?: string
    buttons: ReviewButton[]
    /** The key of the decision being written, while one is. */
    running?: string
    error?: string | null
    /** False while the dialog holds a draft that closing it would throw away. */
    dismissible?: boolean
    gone?: boolean
  }>(),
  { message: '', running: '', error: null, dismissible: true, gone: false },
)

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ choose: [key: string, close: () => void] }>()
</script>
