import { ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useCall } from 'frappe-ui'

/**
 * The desk's To Do sidebar widget, on this app's sidebar.
 *
 * Both endpoints are the desk widget's own (`frappe/core/todos.py`) rather
 * than anything of this app's. The list, the count and what "mine" means are
 * one question, and a person crossing between the two sidebars all day must
 * not be told two different numbers -- so there is one answer, in Frappe's
 * Core module, and two front ends asking it.
 *
 * What that answer is: open ToDos allocated to you, plus open ToDos you
 * created and never allocated. Not everything you are *permitted* to read --
 * a ToDo role grants sight of the whole site's backlog.
 */

export type TodoSort = 'due_date' | 'urgency' | 'doctype' | 'recent'

export interface OpenTodo {
  name: string
  /** The description with its markup taken off, done server-side. */
  title: string
  status: string
  priority: 'High' | 'Medium' | 'Low' | null
  /** Due date, `YYYY-MM-DD`. Null for a ToDo with no deadline. */
  date: string | null
  overdue: boolean
  color: string | null
  reference_type: string | null
  reference_name: string | null
  assigned_by: string | null
  allocated_to: string | null
  owner: string
  creation: string
  modified: string
}

export interface OpenTodos {
  todos: OpenTodo[]
  /** Every open ToDo, which can exceed the rows returned. See `truncated`. */
  count: number
  sort_by: TodoSort
  truncated: boolean
}

/** The desk widget's four, in its order and with its wording. */
export const TODO_SORTS: { value: TodoSort; label: string }[] = [
  { value: 'due_date', label: 'Due date' },
  { value: 'urgency', label: 'Urgency' },
  { value: 'doctype', label: 'Document type' },
  { value: 'recent', label: 'Recently created' },
]

const SORT_STORAGE_KEY = 'commons:todos:sort'

function storedSort(): TodoSort {
  const saved = localStorage.getItem(SORT_STORAGE_KEY)
  return TODO_SORTS.some((option) => option.value === saved)
    ? (saved as TodoSort)
    : 'due_date'
}

/**
 * The chosen sort, remembered the way the desk widget remembers it.
 *
 * Module state, and outside the component: the panel is destroyed every time
 * it closes, and a sort that reset itself on each open would be no choice at
 * all. A preference rather than a cache -- Reload deliberately leaves it be.
 */
export const todoSort = ref<TodoSort>(storedSort())
watch(todoSort, (value) => localStorage.setItem(SORT_STORAGE_KEY, value))

export function useOpenTodos(sortBy: MaybeRefOrGetter<TodoSort>) {
  const todos = useCall<OpenTodos, { sort_by: TodoSort }>({
    url: '/api/v2/method/frappe.core.todos.get_open_todos',
    params: () => ({ sort_by: toValue(sortBy) }),
    immediate: false,
  })
  watch(
    () => toValue(sortBy),
    () => todos.reload(),
    { immediate: true },
  )
  return todos
}

export function useCloseTodo() {
  return useCall<{ name: string; count: number }, { name: string }>({
    url: '/api/v2/method/frappe.core.todos.close_todo',
    method: 'POST',
    immediate: false,
  })
}

/**
 * Rows under a heading, for the two sorts that group.
 *
 * Due date and recency are continuous -- there is no honest line to draw
 * between one day and the next -- so those come back as a single unlabelled
 * run, which is what the desk widget shows.
 */
export function groupTodos(rows: OpenTodo[], sort: TodoSort) {
  const groups: { label: string | null; rows: OpenTodo[] }[] = []

  for (const row of rows) {
    const label =
      sort === 'doctype'
        ? (row.reference_type ?? 'Not linked')
        : sort === 'urgency'
          ? (row.priority ?? 'Medium')
          : null
    const last = groups[groups.length - 1]
    if (last && last.label === label) last.rows.push(row)
    else groups.push({ label, rows: [row] })
  }

  return groups
}

/** frappe-ui's Badge themes; it has no orange, so Medium takes amber --
 *  which is also what this app's approval counts wear. */
const PRIORITY_THEME = {
  High: 'red',
  Medium: 'amber',
  Low: 'blue',
} as const

export function priorityTheme(priority: OpenTodo['priority']) {
  return PRIORITY_THEME[priority ?? 'Medium'] ?? 'gray'
}

/** `frappe.router.slug`: how a doctype reads in a desk URL. */
function slug(name: string): string {
  return name.toLowerCase().replace(/ /g, '-')
}

/**
 * The desk form a ToDo points at, or the ToDo itself when it points nowhere.
 *
 * Every one of these is a desk page, so the caller must not offer them to
 * somebody whose roles do not open the desk -- see `hasDeskAccess`, and the
 * same rule everywhere else in this app that links to `/app`.
 */
export function todoDeskUrl(todo: OpenTodo): string {
  const doctype =
    todo.reference_type && todo.reference_name ? todo.reference_type : 'ToDo'
  const name =
    todo.reference_type && todo.reference_name ? todo.reference_name : todo.name
  return `/app/${slug(doctype)}/${encodeURIComponent(name)}`
}

/** The whole open list in the desk, which is where "See all" goes. */
export const allTodosDeskUrl = '/app/todo?status=Open'
