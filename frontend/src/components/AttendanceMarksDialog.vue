<!--
  One session's marks, and the only place on the register where a mark is
  changed.

  The grid used to be the place: a cell was a button, and each click moved it
  one step round Present → Late → Absent → blank and wrote it straight away.
  That was quick to use, and it also meant a stray tap while scrolling a
  register on a tablet quietly changed somebody's record with nothing on screen
  to say it had happened. Over a term those changes built up, and nobody
  could tell which marks were meant.

  So the grid is now read-only, and this dialog works on a draft. Nothing is
  written until Save, the footer says how many marks Save will change, and
  while there are unsaved changes an outside click or Escape does not close the
  dialog and throw them away. Every write still goes through `frappe.client`,
  so `Student Attendance`'s own validation, the site's Server Scripts and the
  permission check all run.
-->

<template>
  <Dialog
    v-model:open="open"
    :title="session ? sessionTitle : 'Session'"
    :message="`${group.title} · ${course}`"
    :actions="actions"
    :dismissible="!changeCount && !busy"
    size="xl"
  >
    <div v-if="session" class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-p-sm text-ink-gray-6">
          {{ sessionTypeLabel(session.session_type) }} ·
          {{ formatHours(session.hours) }} scheduled hours
          <template v-if="session.session_details"> · {{ session.session_details }}</template>
        </p>
        <div class="flex items-center gap-1">
          <Button
            v-if="canSchedule"
            size="sm"
            variant="ghost"
            icon-left="lucide-pencil"
            label="Edit session"
            :disabled="busy"
            @click="emit('editSession', session)"
          />
          <Button
            v-if="canMark && group.students.length"
            size="sm"
            variant="subtle"
            icon-left="lucide-check-check"
            label="All present"
            :disabled="busy"
            @click="markAll('Present')"
          />
        </div>
      </div>

      <ul class="divide-y divide-outline-gray-1 rounded-4 border border-outline-gray-2">
        <li
          v-for="student in group.students"
          :key="student.student"
          :ref="(el) => student.student === focus && (focusRow = el as HTMLElement | null)"
          class="flex items-center gap-3 px-3 py-1.5"
          :class="[
            isChanged(student.student) ? 'bg-surface-amber-1' : '',
            student.student === focus ? 'ring-2 ring-inset ring-outline-gray-3' : '',
          ]"
        >
          <div class="min-w-0 flex-1">
            <div class="truncate text-p-base text-ink-gray-8">{{ student.student_name }}</div>
            <div v-if="isChanged(student.student)" class="text-p-xs text-ink-gray-5">
              Was {{ MARK_LABELS[storedMark(student.student)].toLowerCase() }}
            </div>
          </div>

          <div
            role="radiogroup"
            :aria-label="`${student.student_name}'s mark`"
            class="flex shrink-0 overflow-hidden rounded border border-outline-gray-2"
          >
            <button
              v-for="option in MARKS"
              :key="option || 'unmarked'"
              type="button"
              role="radio"
              :aria-checked="draftMark(student.student) === option"
              :title="MARK_LABELS[option]"
              :aria-label="MARK_LABELS[option]"
              :disabled="!canMark || busy"
              class="flex h-8 w-10 items-center justify-center border-l border-outline-gray-2 first:border-l-0 disabled:cursor-not-allowed"
              :class="
                draftMark(student.student) === option
                  ? `${MARK_COLOURS[option]} font-medium`
                  : 'bg-surface-white text-ink-gray-4 hover:bg-surface-gray-2'
              "
              @click="draft[student.student] = option"
            >
              <span v-if="option" :class="MARK_GLYPHS[option]" class="size-4" />
              <span v-else class="lucide-circle-dashed size-4" />
            </button>
          </div>
        </li>
      </ul>

      <ErrorMessage v-if="problem" :message="problem" />
    </div>

    <p v-else class="text-p-base text-ink-gray-6">
      This session is no longer in the register. It may have been removed.
    </p>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { Button, Dialog, ErrorMessage, toast, type DialogAction } from 'frappe-ui'
import { formatDate, pluralise } from '@/data/format'
import {
  formatHours,
  formatTime,
  MARK_COLOURS,
  MARK_GLYPHS,
  MARK_LABELS,
  markChanges,
  markValues,
  MARKS,
  newMark,
  sessionTypeLabel,
  STUDENT_ATTENDANCE,
  useDeleteDocument,
  useInsertDocuments,
  useSetValue,
  write,
  type GroupRegister,
  type Mark,
  type Session,
} from '@/data/attendance'

const props = defineProps<{
  group: GroupRegister
  course: string
  /** Looked up afresh from the register by the page, so a re-read after a
   *  partial save shows what the server now holds. Null if it has gone. */
  session: Session | null
  /** The student whose cell was clicked to get here, picked out in the list. */
  focus: string | null
  canMark: boolean
  canSchedule: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  /** Something was written; the page re-reads. */
  saved: []
  editSession: [session: Session]
}>()

const insertMarks = useInsertDocuments()
const changeMark = useSetValue()
const removeMark = useDeleteDocument()

const busy = ref(false)
const problem = ref('')
const focusRow = ref<HTMLElement | null>(null)

/** What the dialog would save, keyed by student. Starts as what is stored. */
const draft = reactive<Record<string, Mark>>({})

function storedMark(student: string): Mark {
  return props.session?.marks[student]?.mark ?? ''
}

function draftMark(student: string): Mark {
  return draft[student] ?? storedMark(student)
}

function isChanged(student: string): boolean {
  return draftMark(student) !== storedMark(student)
}

function resetDraft() {
  for (const key of Object.keys(draft)) delete draft[key]
  for (const row of props.group.students) draft[row.student] = storedMark(row.student)
}

// A dialog that kept the last session's choices would be a trap: it would open
// on somebody else's class with marks already moved.
watch(open, async (isOpen) => {
  if (!isOpen) return
  resetDraft()
  problem.value = ''
  await nextTick()
  focusRow.value?.scrollIntoView({ block: 'nearest' })
})

const changes = computed(() => markChanges(props.session?.marks ?? {}, draft))
const changeCount = computed(
  () => changes.value.insert.length + changes.value.update.length + changes.value.remove.length,
)

const sessionTitle = computed(() => {
  const session = props.session
  if (!session) return ''
  return `${formatDate(session.schedule_date)}, ${formatTime(session.from_time)}–${formatTime(session.to_time)}`
})

function markAll(mark: Mark) {
  for (const row of props.group.students) draft[row.student] = mark
}

/**
 * Write the draft.
 *
 * New rows go in one `insert_many`, and so one transaction, because that is
 * nearly all of a fresh session's marks. Changes and clearings are one request
 * each. If any is refused the dialog stays open with the server's reason, and
 * the page re-reads: by then some rows may have been written, and the diff is
 * worked out again against what the server actually holds, so pressing Save a
 * second time writes only what is still outstanding.
 */
async function save(close: () => void) {
  const session = props.session
  if (!session || !changeCount.value) return
  const { insert, update, remove } = changes.value

  busy.value = true
  problem.value = ''
  try {
    if (insert.length) {
      const done = await write(insertMarks, {
        docs: JSON.stringify(insert.map((row) => newMark(session.name, row.student, row.mark))),
      })
      if (!done.ok) return fail(insertMarks.error)
    }
    for (const row of update) {
      const done = await write(changeMark, {
        doctype: STUDENT_ATTENDANCE,
        name: row.name,
        fieldname: JSON.stringify(markValues(row.mark)),
      })
      if (!done.ok) return fail(changeMark.error)
    }
    for (const name of remove) {
      const done = await write(removeMark, { doctype: STUDENT_ATTENDANCE, name })
      if (!done.ok) return fail(removeMark.error)
    }
    toast.success(`${pluralise(changeCount.value, 'mark')} saved`)
    emit('saved')
    close()
  } finally {
    busy.value = false
  }
}

function fail(error: Error | null | undefined) {
  problem.value = error?.message || 'Those marks could not be saved'
  emit('saved')
}

const actions = computed<DialogAction[]>(() => [
  ...(changeCount.value
    ? [
        {
          label: 'Undo changes',
          variant: 'ghost' as const,
          disabled: busy.value,
          onClick: () => resetDraft(),
        },
      ]
    : []),
  {
    label: changeCount.value ? `Save ${pluralise(changeCount.value, 'change')}` : 'No changes',
    variant: 'solid',
    disabled: !props.canMark || !changeCount.value,
    loading: busy.value,
    onClick: ({ close }) => save(close),
  },
])
</script>
