<template>
	<!-- The desk's To Do widget, in the place the desk keeps it: among the rows
       that belong to the person rather than to the workspace, right under
       Search. In the desk that block is Search, Notification, To Do.

       The row is drawn only while something is open -- and kept while the panel
       is, so closing the last to-do does not pull the panel out from under the
       press that did it. -->
	<AppSidebarPanel
		v-if="count || open"
		v-model:open="open"
		label="To Do"
		icon="lucide-list-todo"
		:count="count"
	>
		<!-- Gray, not amber -- an approval queue is somebody else held up, a
         to-do list is just a list. -->
		<template #actions>
			<Select
				v-model="todoSort"
				:options="TODO_SORTS"
				size="sm"
				variant="ghost"
				aria-label="Sort by"
			/>
		</template>

		<!-- Only on the first load. A re-sort swaps rows for skeletons and
             back, which reads as the list being fetched from scratch when the
             server has merely put it in another order. -->
		<div v-if="loading && !todos.length" class="space-y-1.5 p-1">
			<Skeleton v-for="n in 4" :key="n" class="h-12 w-full rounded-4" />
		</div>

		<ErrorMessage v-else-if="request.error" class="p-3" :message="request.error.message" />

		<div v-else-if="!todos.length" class="px-4 py-10 text-center">
			<p class="text-base-medium text-ink-gray-7">Nothing to do</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">You have no open to-dos.</p>
		</div>

		<template v-else>
			<div v-for="(group, index) in groups" :key="group.label ?? index">
				<div
					v-if="group.label"
					class="px-2 pb-1 pt-2 text-sm text-ink-gray-5"
					:class="{ 'pt-1': index === 0 }"
				>
					{{ group.label }}
				</div>
				<div
					v-for="todo in group.rows"
					:key="todo.name"
					class="group/todo flex items-start gap-2 rounded-4 px-2 py-2 hover:bg-surface-gray-2"
					:class="{ 'opacity-40': closing === todo.name }"
				>
					<!-- The desk's circle that fills in when you reach for it. A
                   button in its own right, not part of the link: closing a
                   to-do and going to read it are two different intentions.
                   It asks first rather than closing on the press — a list in
                   the sidebar is brushed past all day, and a to-do closed by a
                   stray click is gone from here with nothing to say so. -->
					<button
						type="button"
						class="mt-0.5 grid size-4.5 shrink-0 place-items-center rounded-full border border-outline-gray-2 text-ink-gray-5 transition hover:border-outline-gray-4 hover:text-ink-gray-8"
						:disabled="Boolean(closing)"
						:aria-label="`Mark as closed: ${todo.title}`"
						title="Mark as closed"
						@click="confirmClose(todo)"
					>
						<span
							class="lucide-check size-3 opacity-0 transition group-hover/todo:opacity-100"
						/>
					</button>

					<!-- Always a link: AppSidebar renders this widget only for somebody
                   who can open the desk, which is where every one of these
                   leads. -->
					<a :href="todoDeskUrl(todo)" class="min-w-0 flex-1">
						<div class="line-clamp-2 text-p-sm text-ink-gray-8">
							{{ todo.title || 'No description' }}
						</div>
						<div
							class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-gray-5"
						>
							<span
								v-if="todo.reference_type && todo.reference_name"
								class="truncate"
							>
								{{ todo.reference_type }}: {{ todo.reference_name }}
							</span>
							<span v-if="todo.date" :class="{ 'text-ink-red-3': todo.overdue }">
								{{ todo.overdue ? 'Overdue' : 'Due' }}
								{{ formatDate(todo.date) }}
							</span>
							<!-- Redundant once the list is grouped by it. -->
							<Badge
								v-if="todo.priority && todoSort !== 'urgency'"
								:theme="priorityTheme(todo.priority)"
								variant="subtle"
							>
								{{ todo.priority }}
							</Badge>
						</div>
					</a>
				</div>
			</div>
		</template>

		<template #footer>
			<a
				:href="allTodosDeskUrl"
				class="shrink-0 border-t border-outline-gray-1 px-3 py-2 text-center text-sm text-ink-gray-5 hover:text-ink-gray-8"
			>
				{{ truncated ? `See all ${count} to-dos` : 'See all to-dos' }}
			</a>
		</template>
	</AppSidebarPanel>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Badge, ErrorMessage, Select, Skeleton, dialog, toast } from 'frappe-ui'
import AppSidebarPanel from '@/components/AppSidebarPanel.vue'
import { usePollWhileVisible } from '@/data/sidebarFeeds'
import { formatDate } from '@/data/format'
import {
	allTodosDeskUrl,
	groupTodos,
	priorityTheme,
	todoDeskUrl,
	todoSort,
	useCloseTodo,
	useOpenTodos,
	TODO_SORTS,
	type OpenTodo,
} from '@/data/todos'

const open = ref(false)

const request = useOpenTodos(todoSort)
const closeRequest = useCloseTodo()

const todos = computed<OpenTodo[]>(() => request.data?.todos ?? [])
const count = computed(() => request.data?.count ?? 0)
const truncated = computed(() => Boolean(request.data?.truncated))
const loading = computed(() => request.loading)
const groups = computed(() => groupTodos(todos.value, todoSort.value))

// The count decides whether the row is drawn at all, so it cannot wait for
// the next page load to catch up. See `usePollWhileVisible`.
usePollWhileVisible(() => request.reload())

/** The panel is only ever looked at open, so that is when it is worth re-reading. */
watch(open, (isOpen) => {
	if (isOpen) request.reload()
})

/** Which row is in flight, so only the one pressed dims — and the others'
 *  circles wait: one close at a time is what keeps each one's answer its own. */
const closing = ref('')

/**
 * Close a to-do, once the person has said so.
 *
 * A confirmation rather than a one-press write, by the rule the rest of this
 * app keeps: nothing is written from a base screen without a deliberate step.
 * The dialog names the to-do, so the press that sent it is checked against
 * what it is about to close.
 */
function confirmClose(todo: OpenTodo) {
	const about =
		todo.reference_type && todo.reference_name
			? ` (${todo.reference_type}: ${todo.reference_name})`
			: ''
	dialog.confirm({
		title: 'Close to-do',
		message: `${todo.title || 'No description'}${about}`,
		confirmLabel: 'Close to-do',
		onConfirm: async () => {
			closing.value = todo.name
			try {
				await closeRequest.submit({ name: todo.name })
				// `submit` resolves whether or not the server accepted it, so the
				// error, not the result, is what says what happened. Throwing keeps
				// the dialog open with the reason inline.
				if (closeRequest.error) {
					throw new Error(closeRequest.error.message || 'Could not close the to-do')
				}
			} finally {
				closing.value = ''
			}
			toast.success('Closed')
			// The server's count is the one that counts -- it sees ToDos closed in
			// the desk, or by an assignment being completed there, in the same
			// breath. Re-reading the list is how this panel learns about those too.
			// Not awaited: the dialog has done its job and should not sit there
			// spinning over a list it is covering.
			request.reload()
		},
	})
}
</script>
