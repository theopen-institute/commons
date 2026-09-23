<!--
  One session of a course: when it ran, what kind it was, and what it was about.

  Deliberately not where attendance is taken. The register this replaces put a
  dropdown per student in this dialog, so marking a class of twenty meant twenty
  selects in a scrolling modal. Marks are changed in the session's details
  (`AttendanceMarksDialog`), which is opened from the grid.

  What is left here is the session itself, plus the one thing that genuinely
  belongs at the moment a session is created: saying that everybody was there.
  That is how a register is actually kept — the class happened, two people were
  missing — and it turns taking attendance into a tick and two clicks rather
  than a form.

  Every write goes through `frappe.client`, so `Course Schedule`'s own
  validation, the site's Server Scripts and the permission check all run. This
  dialog states no rule of its own about what a session may be; whatever
  refuses, its message is what is shown.
-->

<template>
  <Dialog v-model:open="open" :title="session ? 'Edit session' : 'New session'" :actions="actions">
    <div class="space-y-4">
      <p class="text-p-base text-ink-gray-6">{{ group.title }} · {{ course }}</p>

      <div class="grid gap-4 sm:grid-cols-2">
        <!-- A text input over a list rather than a Select, because the field is
             free text on purpose: the vocabulary is the school's, and a Select
             would make its fifth kind of session a deploy. The list offers what
             is already in use, so typing a new one is possible and never
             accidental. -->
        <div>
          <FormControl
            v-model="form.session_type"
            type="text"
            label="Session type"
            list="attendance-session-types"
            placeholder="e.g. Seminar"
            :description="isNewType ? 'A new kind of session' : undefined"
          />
          <datalist id="attendance-session-types">
            <option v-for="name in sessionTypes" :key="name" :value="name" />
          </datalist>
        </div>
        <FormControl
          v-model="form.session_details"
          type="text"
          label="What it covered"
          placeholder="Optional"
        />
      </div>

      <BikramDatePicker
        v-model="form.schedule_date"
        label="Date"
        :min="termStart ?? undefined"
        :max="termEnd ?? undefined"
        :error="errors.schedule_date"
        description="Must fall inside the academic term."
        required
      />

      <!-- `TextInput` rather than `FormControl` for these two, which is the same
           swap `BikramDatePicker` makes and for a related reason.
           `FormControl type="time"` dispatches to frappe-ui's time *picker*: a
           96-item dropdown of quarter hours that does not filter as you type and
           commits only when an option is clicked. A register takes two new
           sessions a week and a class does not always start on the quarter hour.
           `TextInput` renders the browser's own time input — typed, keyboard
           navigable, minute by minute — and carries the label, error and
           required marker, so the field is chrome-identical to the controls
           above it. -->
      <div class="grid gap-4 sm:grid-cols-2">
        <TextInput
          v-model="form.from_time"
          type="time"
          label="Starts"
          :error="errors.from_time"
          required
          class="w-full"
        />
        <TextInput
          v-model="form.to_time"
          type="time"
          label="Ends"
          :error="errors.to_time"
          required
          class="w-full"
        />
      </div>

      <p v-if="length" class="text-p-sm text-ink-gray-6">{{ length }}</p>

      <!-- New sessions only. An existing session's marks are changed in its
           details, where the changes can be seen before they are saved. A
           checkbox here that overwrote them without showing them would be the
           one destructive control on the page. -->
      <FormControl
        v-if="!session"
        v-model="form.mark_all"
        type="checkbox"
        :label="`Mark all ${group.students.length} students present`"
        :disabled="!group.students.length"
      />

      <ErrorMessage v-if="problem" :message="problem" />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  Dialog,
  ErrorMessage,
  FormControl,
  TextInput,
  toast,
  type DialogAction,
} from 'frappe-ui'
import BikramDatePicker from './BikramDatePicker.vue'
import {
  COURSE_SCHEDULE,
  formatHours,
  fromTimeInput,
  newMark,
  STUDENT_ATTENDANCE,
  toTimeInput,
  useDeleteDocument,
  useInsertDocument,
  useInsertDocuments,
  useSetValue,
  write,
  type GroupRegister,
  type Session,
} from '@/data/attendance'

const props = defineProps<{
  group: GroupRegister
  course: string
  /** The session being changed, or null to timetable a new one. */
  session: Session | null
  /** What this school already calls its sessions. Offered, never enforced. */
  sessionTypes: string[]
  termStart: string | null
  termEnd: string | null
}>()

const open = defineModel<boolean>('open', { required: true })

/** Something was written. The page re-reads rather than being handed a
 *  register: a new session changes which rows exist, not just what one of them
 *  says, and re-reading is the only answer that cannot drift. */
const emit = defineEmits<{ saved: [] }>()

interface SessionForm {
  session_type: string
  session_details: string
  schedule_date: string
  from_time: string
  to_time: string
  mark_all: boolean
}

const insertSession = useInsertDocument()
const insertMarks = useInsertDocuments()
const changeSession = useSetValue()
const removeDocument = useDeleteDocument()

const busy = ref(false)
const problem = ref('')

/**
 * What date a new session opens on.
 *
 * Today, unless today is not in the term being looked at — in which case the
 * nearest day of it. Somebody adding a session to a term that finished last
 * year is back-filling a register, and `Course Schedule` refuses a date outside
 * the term: defaulting to today would mean every one of those sessions opened
 * pre-filled with a value the server was going to reject.
 */
function defaultDate(): string {
  const today = new Date().toISOString().slice(0, 10)
  if (props.termStart && today < props.termStart) return props.termStart
  if (props.termEnd && today > props.termEnd) return props.termEnd
  return today
}

function blankForm(): SessionForm {
  const session = props.session
  return {
    session_type: session?.session_type ?? '',
    session_details: session?.session_details ?? '',
    schedule_date: session?.schedule_date ?? defaultDate(),
    from_time: toTimeInput(session?.from_time ?? null),
    to_time: toTimeInput(session?.to_time ?? null),
    // New sessions open with everybody present, because that is what a class
    // usually is. The exceptions are changed in the session's details afterwards.
    mark_all: !props.session,
  }
}

const form = reactive<SessionForm>(blankForm())
const submitAttempted = ref(false)

const isNewType = computed(
  () => Boolean(form.session_type) && !props.sessionTypes.includes(form.session_type),
)

// A start time on its own is nearly always a two-hour session here, and typing
// the end time is the sort of keystroke a register should not ask for twice a
// week. Only ever fills a blank — it never moves an end time somebody set.
watch(
  () => form.from_time,
  (from) => {
    if (!from || form.to_time) return
    const [hours, minutes] = from.split(':').map(Number)
    form.to_time = `${String(Math.min(hours + 2, 23)).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
  },
)

const problems = computed(() => {
  const found: Record<string, string> = {}
  if (!form.schedule_date) found.schedule_date = 'Pick a date'
  if (!form.from_time) found.from_time = 'Pick a start time'
  if (!form.to_time) found.to_time = 'Pick an end time'
  if (form.from_time && form.to_time && form.to_time <= form.from_time) {
    found.to_time = 'The session ends before it starts'
  }
  return found
})

const errors = computed(() => (submitAttempted.value ? problems.value : {}))

/** How long the session runs, said in the dialog rather than left to be
 *  discovered in the grid — it is the figure every total on the page is built
 *  from. */
const length = computed(() => {
  if (problems.value.from_time || problems.value.to_time) return ''
  const minutes =
    Number(form.to_time.slice(0, 2)) * 60 +
    Number(form.to_time.slice(3, 5)) -
    Number(form.from_time.slice(0, 2)) * 60 -
    Number(form.from_time.slice(3, 5))
  return `${formatHours(minutes / 60)} scheduled hours.`
})

// A dialog that keeps the last session's values is a trap: the next one opens
// half-filled with a date that has passed.
watch(open, (isOpen) => {
  if (!isOpen) return
  Object.assign(form, blankForm())
  submitAttempted.value = false
  problem.value = ''
})

/** The fields a session carries, whether it is being made or changed. */
function sessionValues() {
  return {
    schedule_date: form.schedule_date,
    from_time: fromTimeInput(form.from_time),
    to_time: fromTimeInput(form.to_time),
    custom_session_type: form.session_type || null,
    custom_session_details: form.session_details || null,
  }
}

async function send(close: () => void) {
  submitAttempted.value = true
  if (Object.keys(problems.value).length) return

  busy.value = true
  problem.value = ''
  try {
    if (props.session) {
      const saved = await write(changeSession, {
        doctype: COURSE_SCHEDULE,
        name: props.session.name,
        fieldname: JSON.stringify(sessionValues()),
      })
      if (!saved.ok) return fail(changeSession.error, 'That session could not be saved')
    } else {
      const created = await write(insertSession, {
        doc: JSON.stringify({
          doctype: COURSE_SCHEDULE,
          // Not the instructor and not the room, both of which `Course Schedule`
          // requires and both of which the site fetches from the course. Filling
          // them in from here would override a school's answer with a guess.
          student_group: props.group.name,
          course: props.course,
          ...sessionValues(),
        }),
      })
      if (!created.ok || !created.data) {
        return fail(insertSession.error, 'That session could not be added')
      }

      if (form.mark_all && props.group.students.length) {
        // One request, and so one transaction: twenty students are marked or
        // none of them are, rather than the class being left half marked with
        // no way to tell from the page which half.
        const marked = await write(insertMarks, {
          docs: JSON.stringify(
            props.group.students.map((row) =>
              newMark(created.data!.name, row.student, 'Present'),
            ),
          ),
        })
        if (!marked.ok) {
          return fail(
            insertMarks.error,
            'The session was added, but the marks were not. Open it from the grid to mark it.',
          )
        }
      }
    }
    toast.success(props.session ? 'Session updated' : 'Session added')
    emit('saved')
    close()
  } finally {
    busy.value = false
  }
}

/**
 * Remove a session and everything recorded against it.
 *
 * The marks first, because they link to it: `Student Attendance` names a
 * `Course Schedule`, and Frappe refuses to delete a document another one still
 * points at. Each goes through the document API, so a reader who may remove a
 * session but not its marks is stopped at the first one rather than halfway
 * through — and if one does fail, the page re-reads and shows exactly what is
 * left.
 */
async function destroy(close: () => void) {
  const session = props.session
  if (!session) return
  busy.value = true
  problem.value = ''
  try {
    for (const mark of Object.values(session.marks)) {
      if (!mark.name) continue
      const gone = await write(removeDocument, { doctype: STUDENT_ATTENDANCE, name: mark.name })
      if (!gone.ok) return fail(removeDocument.error, 'Those marks could not be removed')
    }
    const gone = await write(removeDocument, { doctype: COURSE_SCHEDULE, name: session.name })
    if (!gone.ok) return fail(removeDocument.error, 'That session could not be removed')
    toast.success('Session removed')
    emit('saved')
    close()
  } finally {
    busy.value = false
  }
}

/** Show the server's own reason inline. An overlapping class, a date outside
 *  the term or a holiday is worth reading in full, and it is Education's
 *  refusal rather than this page's. */
function fail(error: Error | null | undefined, fallback: string) {
  problem.value = error?.message || fallback
  // The register may have changed even so — a session written and its marks
  // refused, for instance — so the page re-reads either way.
  emit('saved')
}

const actions = computed<DialogAction[]>(() => [
  ...(props.session
    ? [
        {
          label: 'Delete',
          theme: 'red' as const,
          variant: 'subtle' as const,
          loading: busy.value,
          onClick: ({ close }: { close: () => void }) => destroy(close),
        },
      ]
    : []),
  {
    label: props.session ? 'Save' : 'Add session',
    variant: 'solid',
    loading: busy.value,
    onClick: ({ close }) => send(close),
  },
])
</script>
