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

  <!-- Wider than the other pages' max-w-3xl, because the register is a grid
       with one 40px column per student and a group of twenty needs about
       1,100px. Wider groups scroll sideways inside the grid, as they already
       did. Capped so the pickers and a small group's columns don't spread
       across a wide monitor. -->
  <div class="mx-auto max-w-6xl px-5 py-4">
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

          <AttendanceGrid v-else :group="group" @open="openMarks" />
        </section>
      </template>
    </template>

    <AttendanceMarksDialog
      v-if="marksGroup"
      v-model:open="marksOpen"
      :group="marksGroup"
      :course="course"
      :session="marksSession"
      :focus="marksFocus"
      :can-mark="attendanceCan.mark"
      :can-schedule="attendanceCan.schedule"
      @saved="reloadRegister"
      @edit-session="editFromMarks"
    />

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
import { Button, ErrorMessage, FormControl, Skeleton } from 'frappe-ui'
import AppPageHeader from '@/components/AppPageHeader.vue'
import AttendanceGrid from '@/components/AttendanceGrid.vue'
import AttendanceMarksDialog from '@/components/AttendanceMarksDialog.vue'
import AttendanceSessionDialog from '@/components/AttendanceSessionDialog.vue'
import { pluralise } from '@/data/format'
import {
  attendanceCan,
  attendancePermissionsLoaded,
  courseChip,
  formatHours,
  termBounds,
  useAttendancePickers,
  useAttendanceRegister,
  type GroupRegister,
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

const dialogOpen = ref(false)
const dialogGroup = ref<GroupRegister | null>(null)
const dialogSession = ref<Session | null>(null)

/**
 * The session whose details are open, held by name rather than as the object
 * the grid handed over. A save re-reads the register, which builds new
 * objects, and the dialog has to show the new ones: after a partial save it
 * works out what is still unwritten against what the server now holds.
 */
const marksOpen = ref(false)
const marksGroupName = ref('')
const marksSessionName = ref('')
const marksFocus = ref<string | null>(null)
const marksGroup = computed(
  () => register.value.groups.find((row) => row.name === marksGroupName.value) ?? null,
)
const marksSession = computed(
  () =>
    marksGroup.value?.blocks
      .flatMap((block) => block.sessions)
      .find((row) => row.name === marksSessionName.value) ?? null,
)

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

function openMarks(session: Session, student: string | null) {
  marksGroupName.value = session.group
  marksSessionName.value = session.name
  marksFocus.value = student
  marksOpen.value = true
}

/** From a session's details to changing the session itself. One dialog at a
 *  time: stacked, a Save in the one underneath would be out of sight. */
function editFromMarks(session: Session) {
  const group = marksGroup.value
  if (!group) return
  marksOpen.value = false
  openDialog(group, session)
}
</script>
