<!--
  One student group's term, as a grid: sessions down the side, students across
  the top, one mark in every cell.

  The footings under each block carry no colour, which was a deliberate
  retreat: marking every figure below the scheduled hours red made a wall of
  red, because a student who misses one class in a term is below it. A warning
  that fires for everybody warns nobody, and there is no honest threshold to
  pick instead — the marks above are where the exceptions are visible.

  The shape is the register's own and is kept deliberately. A teacher reads it
  across — "who was at Tuesday's seminar" — and down — "how much of this has
  Asmita actually done" — and no list of documents answers either question
  without being rearranged first.

  Nothing in the grid changes a mark. A session's row header and each of its
  cells open that session's details (`AttendanceMarksDialog`), and marks are
  changed there as a draft that is written only on Save. For a while a cell
  was a button that moved one step round Present → Late → Absent → blank on
  every click and saved straight away. A register is scrolled on a tablet in a
  classroom, so stray taps changed real records without anyone noticing. A
  click here can open a dialog, and that is all it can do. The totals are
  worked out in `attendanceRegister.ts`, so this component does no arithmetic.
-->

<template>
  <div class="overflow-x-auto rounded-4 border border-outline-gray-2">
    <table class="w-full border-separate border-spacing-0 text-p-sm">
      <thead>
        <tr>
          <th
            class="sticky left-0 z-20 min-w-56 border-b border-r border-outline-gray-2 bg-surface-white px-3 py-2 text-left align-bottom font-medium text-ink-gray-7"
          >
            Session
          </th>
          <th
            class="border-b border-outline-gray-2 bg-surface-white px-2 py-2 align-bottom text-right font-normal italic text-ink-gray-5"
          >
            <span class="vertical">Scheduled hours</span>
          </th>
          <th
            v-for="student in group.students"
            :key="student.student"
            class="w-10 border-b border-l border-outline-gray-2 bg-surface-white px-1 py-2 align-bottom font-medium text-ink-gray-7"
            :title="student.student_name"
          >
            <span class="vertical">{{ student.student_name }}</span>
          </th>
        </tr>
      </thead>

      <template v-for="block in group.blocks" :key="block.session_type ?? '—'">
        <tbody>
          <tr>
            <th
              :colspan="2 + group.students.length"
              class="sticky left-0 border-b border-t border-outline-gray-2 bg-surface-gray-2 px-3 py-1.5 text-left text-p-sm font-medium text-ink-gray-7"
            >
              {{ sessionTypeLabel(block.session_type) }}
              <span class="font-normal text-ink-gray-5">
                · {{ pluralise(block.sessions.length, 'session') }}
              </span>
            </th>
          </tr>

          <tr v-for="session in block.sessions" :key="session.name">
            <th
              class="sticky left-0 z-10 border-b border-r border-outline-gray-2 bg-surface-white p-0 text-left font-normal"
            >
              <button
                type="button"
                class="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-gray-1"
                :title="`Open ${formatDate(session.schedule_date)}'s session`"
                @click="emit('open', session, null)"
              >
                <div class="min-w-0 flex-1">
                  <div class="truncate text-ink-gray-8">
                    {{ formatDate(session.schedule_date) }}
                    <span class="text-ink-gray-5">
                      {{ formatTime(session.from_time) }}–{{ formatTime(session.to_time) }}
                    </span>
                  </div>
                  <div v-if="session.session_details" class="truncate text-p-sm text-ink-gray-5">
                    {{ session.session_details }}
                  </div>
                </div>
                <span class="lucide-chevron-right size-4 shrink-0 text-ink-gray-4" />
              </button>
            </th>

            <td
              class="border-b border-outline-gray-2 px-2 py-1.5 text-right tabular-nums text-ink-gray-6"
            >
              {{ formatHours(session.hours) }}
            </td>

            <td
              v-for="student in group.students"
              :key="student.student"
              class="border-b border-l border-outline-gray-2 p-0 text-center"
            >
              <button
                type="button"
                class="flex h-8 w-full cursor-pointer items-center justify-center transition-colors hover:brightness-95"
                :class="MARK_COLOURS[markOf(session, student.student)]"
                :title="cellTitle(session, student)"
                :aria-label="cellTitle(session, student)"
                @click="emit('open', session, student.student)"
              >
                <span
                  v-if="glyph(markOf(session, student.student))"
                  :class="glyph(markOf(session, student.student))"
                  class="size-4"
                />
              </button>
            </td>
          </tr>

          <tr v-if="!block.sessions.length">
            <td
              :colspan="2 + group.students.length"
              class="border-b border-outline-gray-2 px-3 py-3 text-p-sm text-ink-gray-5"
            >
              Nothing timetabled.
            </td>
          </tr>

          <!-- The block's footing, and deliberately a row of its own `tbody`
               rather than a `tfoot`. A table may have one foot, and a browser
               moves every `tfoot` it finds to the bottom — which silently put
               the first block's total underneath the last block's sessions. -->
          <tr class="text-ink-gray-7">
            <td
              class="sticky left-0 border-b border-r border-outline-gray-2 bg-surface-gray-1 px-3 py-1.5 text-right font-medium"
            >
              {{ sessionTypeLabel(block.session_type) }} total
            </td>
            <td
              class="border-b border-outline-gray-2 bg-surface-gray-1 px-2 py-1.5 text-right font-medium tabular-nums"
            >
              {{ formatHours(block.scheduled) }}
            </td>
            <td
              v-for="student in group.students"
              :key="student.student"
              class="border-b border-l border-outline-gray-2 bg-surface-gray-1 px-1 py-1.5 text-center tabular-nums"
            >
              {{ formatHours(block.credited[student.student] ?? 0) }}
            </td>
          </tr>
        </tbody>
      </template>

      <tfoot v-if="group.blocks.length > 1">
        <tr class="text-ink-gray-8">
          <td
            class="sticky left-0 border-r border-outline-gray-2 bg-surface-gray-2 px-3 py-2 text-right font-semibold"
          >
            Term total
          </td>
          <td
            class="bg-surface-gray-2 px-2 py-2 text-right font-semibold tabular-nums"
          >
            {{ formatHours(group.scheduled) }}
          </td>
          <td
            v-for="student in group.students"
            :key="student.student"
            class="border-l border-outline-gray-2 bg-surface-gray-2 px-1 py-2 text-center font-semibold tabular-nums"
          >
            {{ formatHours(group.credited[student.student] ?? 0) }}
          </td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>

<script setup lang="ts">
import { formatDate, pluralise } from '@/data/format'
import {
  formatHours,
  formatTime,
  MARK_COLOURS,
  MARK_GLYPHS,
  MARK_LABELS,
  sessionTypeLabel,
  type GroupRegister,
  type GroupStudent,
  type Mark,
  type Session,
} from '@/data/attendance'

defineProps<{
  group: GroupRegister
}>()

/** A session's details were asked for — from its row, or from one student's
 *  cell in it, in which case that student is picked out in the dialog. */
const emit = defineEmits<{
  open: [session: Session, student: string | null]
}>()

/** What one cell says. A student with no `Student Attendance` row is unmarked,
 *  which the grid draws as blank and which is not the same as absent. */
function markOf(session: Session, student: string): Mark {
  return session.marks[student]?.mark ?? ''
}

function glyph(mark: Mark): string {
  return MARK_GLYPHS[mark]
}

/**
 * What the cell says to a screen reader, and on hover.
 *
 * The student's name in it, because a cell in the middle of a wide grid is a
 * long way from both the column it is under and the row it is in — which is the
 * one thing a grid this shape is genuinely bad at.
 */
function cellTitle(session: Session, student: GroupStudent): string {
  const mark = markOf(session, student.student)
  return `${student.student_name} · ${formatDate(session.schedule_date)} · ${MARK_LABELS[mark]}`
}
</script>

<style scoped>
/*
  Student names, turned on their side. A group of twenty is twenty columns and
  no screen is wide enough for twenty horizontal names; rotated, each costs
  40px. `rotate(180deg)` over `vertical-rl` is what puts them bottom-to-top, so
  they read upwards from the grid rather than downwards into it.
*/
.vertical {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  white-space: nowrap;
  line-height: 1;
}
</style>
