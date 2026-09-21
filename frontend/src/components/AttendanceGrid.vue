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

  What changed is that a cell is now a button. The register this replaces drew
  the same grid as static glyphs and put every edit behind a modal with a
  dropdown per student, so correcting one mark meant opening a form, finding the
  name, choosing from four options and saving. Here one click is one mark and
  the next click is the next one along: Present, Late, Absent, blank, round
  again. The totals under each block come back from the server with every write,
  so what a late arrival is worth is settled in one place and this component
  never does arithmetic.
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

          <tr
            v-for="session in block.sessions"
            :key="session.name"
            class="group/row"
            :class="busy.has(session.name) ? 'opacity-60' : ''"
          >
            <th
              class="sticky left-0 z-10 border-b border-r border-outline-gray-2 bg-surface-white px-3 py-1.5 text-left font-normal"
            >
              <div class="flex items-center gap-2">
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
                <!-- Both always drawn rather than revealed on hover: half the
                     people who keep a register are doing it on a tablet in a
                     classroom, where there is no hover to reveal anything. -->
                <div class="flex shrink-0 items-center gap-0.5">
                  <button
                    v-if="canMark && group.students.length"
                    class="rounded p-1 text-ink-gray-4 hover:bg-surface-gray-2 hover:text-ink-gray-7"
                    :title="`Mark all ${group.students.length} present`"
                    :disabled="busy.has(session.name)"
                    @click="emit('markAll', session)"
                  >
                    <span class="lucide-check-check size-4" />
                  </button>
                  <button
                    v-if="canSchedule"
                    class="rounded p-1 text-ink-gray-4 hover:bg-surface-gray-2 hover:text-ink-gray-7"
                    title="Edit session"
                    @click="emit('edit', session)"
                  >
                    <span class="lucide-pencil size-4" />
                  </button>
                </div>
              </div>
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
                class="flex h-8 w-full items-center justify-center transition-colors"
                :class="cellClass(markOf(session, student.student))"
                :disabled="!canMark || busy.has(session.name)"
                :title="cellTitle(session, student)"
                :aria-label="cellTitle(session, student)"
                @click="emit('mark', session, student.student, nextMark(markOf(session, student.student)))"
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
  nextMark,
  sessionTypeLabel,
  type GroupRegister,
  type GroupStudent,
  type Mark,
  type Session,
} from '@/data/attendance'

const props = defineProps<{
  group: GroupRegister
  /** Whether cells are clickable. A reader without it still sees the register. */
  canMark: boolean
  /** Whether sessions may be added or changed. */
  canSchedule: boolean
  /** Sessions with a write in flight — their rows hold still until it lands. */
  busy: Set<string>
}>()

const emit = defineEmits<{
  mark: [session: Session, student: string, mark: Mark]
  markAll: [session: Session]
  edit: [session: Session]
}>()

/**
 * How a mark reads.
 *
 * A tick, a clock and a cross rather than three coloured blocks: colour alone
 * is not a distinction everybody can make, and this grid is read at a glance by
 * whoever is covering the class. The colours are there too, because for
 * everybody else they are what makes a row of absences visible from across the
 * page.
 */
const GLYPHS: Record<Mark, string> = {
  Present: 'lucide-check',
  Late: 'lucide-clock',
  Absent: 'lucide-x',
  '': '',
}

const CELLS: Record<Mark, string> = {
  Present: 'bg-surface-green-2 text-ink-green-3',
  Late: 'bg-surface-amber-2 text-ink-amber-3',
  Absent: 'bg-surface-red-2 text-ink-red-3',
  '': 'bg-surface-white',
}

/** What one cell says. A student with no `Student Attendance` row is unmarked,
 *  which the grid draws as blank and which is not the same as absent. */
function markOf(session: Session, student: string): Mark {
  return session.marks[student]?.mark ?? ''
}

function glyph(mark: Mark): string {
  return GLYPHS[mark]
}

function cellClass(mark: Mark): string {
  const base = CELLS[mark]
  return props.canMark ? `${base} hover:brightness-95 cursor-pointer` : base
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
  return `${student.student_name} · ${formatDate(session.schedule_date)} · ${mark || 'Not marked'}`
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
