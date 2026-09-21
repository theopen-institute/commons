<template>
  <AppPageHeader>
    <div class="flex min-w-0 items-center gap-3">
      <span class="text-lg font-semibold text-ink-gray-8">Attendance</span>
    </div>
    <template #actions>
      <Button
        variant="ghost"
        icon-left="lucide-refresh-cw"
        label="Refresh"
        :loading="registerData.loading.value"
        @click="reload()"
      />
    </template>
  </AppPageHeader>

  <div class="px-5 py-4">
    <!-- Refused rather than arrived. The sidebar already hides this row from
         anybody who cannot mark attendance, so almost nobody reaches this —
         somebody following a link they were sent does, and a blank page would
         leave them guessing. -->
    <div
      v-if="attendancePermissionsLoaded && !attendanceCan.mark"
      class="mt-16 text-center"
    >
      <span class="lucide-lock mx-auto size-8 text-ink-gray-4" />
      <p class="mt-2 text-base-medium text-ink-gray-7">This register isn't yours to keep</p>
      <p class="mt-1 text-p-sm text-ink-gray-5">
        Attendance registers are open to the people who mark them. Ask whoever administers
        permissions if that should include you.
      </p>
    </div>

    <template v-else>
      <!-- Two pickers and a row of shortcuts. The pickers are the whole filter;
           the chips exist because a teacher opens this page for the same two or
           three courses every week, and choosing them from a menu twice a week
           is a keystroke tax. -->
      <div class="grid gap-3 sm:grid-cols-2">
        <FormControl
          v-model="term"
          type="select"
          label="Academic term"
          :options="termOptions"
          :disabled="!pickers.loaded.value"
        />
        <FormControl
          v-model="course"
          type="select"
          label="Course"
          :options="courseOptions"
          :disabled="!pickers.loaded.value"
        />
      </div>

      <div v-if="pickers.courses.value.length" class="mt-3 flex flex-wrap items-center gap-2">
        <Button
          v-for="option in pickers.courses.value"
          :key="option.name"
          size="sm"
          :variant="option.name === course ? 'subtle' : 'ghost'"
          :label="courseChip(option)"
          :title="option.course_name ?? option.name"
          @click="course = option.name"
        />
      </div>

      <ErrorMessage
        v-if="pickers.error.value"
        :message="pickers.error.value.message"
        class="mt-4"
      />

      <div v-if="!term || !course" class="mt-16 text-center">
        <span class="lucide-calendar-search mx-auto size-8 text-ink-gray-4" />
        <p class="mt-2 text-base-medium text-ink-gray-7">Pick a term and a course</p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          The register opens on whichever groups are taught that course that term.
        </p>
      </div>

      <template v-else>
        <ErrorMessage
          v-if="registerData.error.value"
          :message="registerData.error.value.message"
          class="mt-4"
        />

        <div v-else-if="!registerData.loaded.value" class="mt-4 space-y-3">
          <Skeleton class="h-8 w-64 rounded-4" />
          <Skeleton class="h-64 w-full rounded-4" />
        </div>

        <div v-else-if="!register.groups.length" class="mt-16 text-center">
          <span class="lucide-users mx-auto size-8 text-ink-gray-4" />
          <p class="mt-2 text-base-medium text-ink-gray-7">No groups take this course this term</p>
          <p class="mt-1 text-p-sm text-ink-gray-5">
            A student group is what a register is kept for. Whoever sets up the term creates them.
          </p>
        </div>

        <section v-for="group in register.groups" v-else :key="group.name" class="mt-6">
          <div class="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <div class="min-w-0">
              <h2 class="text-base-medium text-ink-gray-8">{{ group.title }}</h2>
              <p class="text-p-sm text-ink-gray-5">
                {{ pluralise(group.students.length, 'student') }} ·
                {{ formatHours(group.scheduled) }} scheduled hours
              </p>
            </div>
            <Button
              v-if="attendanceCan.schedule"
              size="sm"
              variant="subtle"
              icon-left="lucide-plus"
              label="New session"
              @click="openDialog(group, null)"
            />
          </div>

          <div
            v-if="!group.students.length"
            class="rounded-4 border border-dashed border-outline-gray-2 px-4 py-8 text-center"
          >
            <p class="text-base-medium text-ink-gray-7">Nobody is in this group</p>
            <p class="mt-1 text-p-sm text-ink-gray-5">
              There is nothing to mark until students are added to it.
            </p>
          </div>

          <AttendanceGrid
            v-else
            :group="group"
            :can-mark="attendanceCan.mark"
            :can-schedule="attendanceCan.schedule"
            :busy="busy"
            @mark="applyMark"
            @mark-all="markAllPresent"
            @edit="(session) => openDialog(group, session)"
          />
        </section>
      </template>
    </template>

    <AttendanceSessionDialog
      v-if="dialogGroup"
      v-model:open="dialogOpen"
      :group="dialogGroup"
      :course="course"
      :session="dialogSession"
      :session-types="pickers.sessionTypes.value"
      :term-start="bounds.start.value"
      :term-end="bounds.end.value"
      @saved="reloadRegister"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, FormControl, Skeleton, toast } from 'frappe-ui'
import AppPageHeader from '@/components/AppPageHeader.vue'
import AttendanceGrid from '@/components/AttendanceGrid.vue'
import AttendanceSessionDialog from '@/components/AttendanceSessionDialog.vue'
import { pluralise } from '@/data/format'
import {
  attendanceCan,
  attendancePermissionsLoaded,
  courseChip,
  formatHours,
  markValues,
  newMark,
  STUDENT_ATTENDANCE,
  termBounds,
  useAttendancePickers,
  useAttendanceRegister,
  useDeleteDocument,
  useInsertDocument,
  useInsertDocuments,
  useSetValue,
  write,
  type GroupRegister,
  type Mark,
  type Session,
} from '@/data/attendance'

/**
 * The attendance register: one term of one course, for every group taught it.
 *
 * Which term and which course live in the query string, not in component state
 * alone. That is what the register this replaces did too, and it was the best
 * thing about it: "the seminar register for last autumn" is a link somebody can
 * send a colleague, and a refresh comes back where it was rather than at the
 * top of a picker.
 *
 * Every read and every write below goes through an API Frappe already ships —
 * see `data/attendance.ts` for why that matters more than the round trips it
 * costs.
 */

const route = useRoute()
const router = useRouter()

const term = ref('')
const course = ref('')

const pickers = useAttendancePickers()
const registerData = useAttendanceRegister()
const register = registerData.register

const insertMark = useInsertDocument()
const insertMarks = useInsertDocuments()
const changeMark = useSetValue()
const removeMark = useDeleteDocument()

/** Sessions with a write in flight. Their rows hold still rather than accepting
 *  a second click that would race the first — which matters more here than
 *  usual, because a new mark has no id until the first write comes back. */
const busy = ref(new Set<string>())

const dialogOpen = ref(false)
const dialogGroup = ref<GroupRegister | null>(null)
const dialogSession = ref<Session | null>(null)

const bounds = termBounds(pickers.terms, term)

// Nothing is asked for until the permission answer is in, so a reader who has
// no register never sends a round of reads that would only be refused.
watch(
  () => attendanceCan.value.mark,
  (mark) => {
    if (mark) pickers.load()
  },
  { immediate: true },
)

// The address first, then the school's current term. An address that names a
// term wins, including one that names a term the picker has retired — an old
// link still resolves to the register it was written for.
watch(pickers.loaded, (ready) => {
  if (!ready) return
  term.value = queryValue('term') || pickers.currentTerm.value || ''
  course.value = queryValue('course') || ''
})

function queryValue(key: string): string {
  const value = route.query[key]
  return typeof value === 'string' ? value : ''
}

// Kept in the address rather than pushed onto the history stack: changing a
// filter is not somewhere you went, and a back button that walked through six
// courses would never reach the page you arrived from.
watch([term, course], ([nextTerm, nextCourse]) => {
  router.replace({
    query: { ...route.query, term: nextTerm || undefined, course: nextCourse || undefined },
  })
  registerData.load(nextTerm, nextCourse)
})

function reloadRegister() {
  registerData.load(term.value, course.value)
}

function reload() {
  pickers.load()
  reloadRegister()
}

const termOptions = computed(() => [
  { label: 'Select a term', value: '' },
  ...pickers.terms.value.map((row) => ({ label: row.name, value: row.name })),
])

const courseOptions = computed(() => [
  { label: 'Select a course', value: '' },
  ...pickers.courses.value.map((row) => ({
    label: row.course_name ?? row.name,
    value: row.name,
  })),
])

function openDialog(group: GroupRegister, session: Session | null) {
  dialogGroup.value = group
  dialogSession.value = session
  dialogOpen.value = true
}

/**
 * One cell, changed.
 *
 * The colour flips first and the server is asked afterwards, because marking a
 * class is twenty of these in a row and a register that waited a round trip for
 * each would be slower to use than paper. The totals underneath follow
 * immediately rather than after a re-read: the arithmetic is in the browser, so
 * patching the one row it depends on is enough. A refusal puts the old mark
 * back and says why.
 */
async function applyMark(session: Session, student: string, mark: Mark) {
  const was = session.marks[student]?.mark ?? ''
  const document = registerData.markDocument(session.name, student)
  registerData.setMark(session.name, student, mark)

  const saved = await hold(session.name, async () => {
    if (!mark) {
      // Nothing to delete: the cell was already blank, which is not a failure.
      if (!document) return true
      return (await write(removeMark, { doctype: STUDENT_ATTENDANCE, name: document })).ok
    }
    if (document) {
      return (
        await write(changeMark, {
          doctype: STUDENT_ATTENDANCE,
          name: document,
          fieldname: JSON.stringify(markValues(mark)),
        })
      ).ok
    }
    const created = await write(insertMark, {
      doc: JSON.stringify(newMark(session.name, student, mark)),
    })
    if (!created.ok || !created.data) return false
    // The id the row was given, so the next click on this cell changes it
    // rather than trying to create a second one.
    registerData.setMark(session.name, student, mark, created.data.name)
    return true
  })

  if (saved) return
  registerData.setMark(session.name, student, was, document)
  toast.error(writeError() ?? 'That mark could not be saved')
}

/**
 * Everybody present, for a session that already exists.
 *
 * The other half of the habit the new-session dialog serves: a class happened,
 * and the marking left to do is the exceptions. Split into the students who
 * have no row yet — one `insert_many`, and so one transaction — and the few who
 * have one that says something else.
 *
 * A failure here re-reads rather than undoing: several rows were in play and
 * some may have landed, and the register as the server has it is the only
 * honest thing to show.
 */
async function markAllPresent(session: Session) {
  const group = register.value.groups.find((row) => row.name === session.group)
  if (!group) return

  const fresh = group.students.filter(
    (row) => !registerData.markDocument(session.name, row.student),
  )
  const changed = group.students.filter((row) => {
    const document = registerData.markDocument(session.name, row.student)
    return document && session.marks[row.student]?.mark !== 'Present'
  })
  if (!fresh.length && !changed.length) return

  for (const row of group.students) registerData.setMark(session.name, row.student, 'Present')

  const saved = await hold(session.name, async () => {
    if (fresh.length) {
      const inserted = await write(insertMarks, {
        docs: JSON.stringify(fresh.map((row) => newMark(session.name, row.student, 'Present'))),
      })
      if (!inserted.ok || !inserted.data) return false
      // `insert_many` answers with the ids in the order it was given them.
      fresh.forEach((row, index) =>
        registerData.setMark(session.name, row.student, 'Present', inserted.data![index]),
      )
    }
    for (const row of changed) {
      const done = await write(changeMark, {
        doctype: STUDENT_ATTENDANCE,
        name: registerData.markDocument(session.name, row.student),
        fieldname: JSON.stringify(markValues('Present')),
      })
      if (!done.ok) return false
    }
    return true
  })

  if (saved) return
  toast.error(writeError() ?? 'Those marks could not be saved')
  reloadRegister()
}

/** Hold a session's row still while a write is in flight. */
async function hold(session: string, write: () => Promise<boolean>): Promise<boolean> {
  busy.value = new Set(busy.value).add(session)
  try {
    return await write()
  } finally {
    const rest = new Set(busy.value)
    rest.delete(session)
    busy.value = rest
  }
}

/** Whichever of the write calls has just refused, in the server's own words —
 *  a duplicate mark, a holiday, or a student who is not in the group. */
function writeError(): string | undefined {
  return (
    insertMark.error?.message ??
    insertMarks.error?.message ??
    changeMark.error?.message ??
    removeMark.error?.message
  )
}
</script>
