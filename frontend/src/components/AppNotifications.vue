<template>
	<!-- The desk's notification widget, beside To Do in the block of rows that
       belong to the person. Same shape as AppTodoList, deliberately -- the two
       share their chrome, and a reader who has learnt one has learnt the other.

       The row is drawn only while something is unread -- and kept while the
       panel is open, so marking the last one read does not pull the panel out
       from under the press that did it. -->
	<AppSidebarPanel
		v-if="unread || open"
		v-model:open="open"
		label="Notifications"
		icon="lucide-bell"
		:count="unread"
		badge-theme="blue"
	>
		<template #actions>
			<Button
				v-if="unread"
				variant="ghost"
				label="Mark all read"
				:loading="markAllRequest.loading"
				@click="markAllRead"
			/>
		</template>

		<div v-if="feed.loading && !items.length" class="space-y-1.5 p-1">
			<Skeleton v-for="n in 4" :key="n" class="h-12 w-full rounded-4" />
		</div>

		<ErrorMessage v-else-if="feed.error" class="p-3" :message="feed.error.message" />

		<div v-else-if="!items.length" class="px-4 py-10 text-center">
			<p class="text-base-medium text-ink-gray-7">Nothing new</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">You have no notifications.</p>
		</div>

		<template v-else>
			<!-- A link only where it leads somewhere: every destination is a desk
               page, the same rule the rest of this app follows. -->
			<component
				:is="hasDeskAccess ? 'a' : 'div'"
				v-for="item in items"
				:key="item.name"
				:href="hasDeskAccess ? notificationDeskUrl(item) : undefined"
				class="flex items-start gap-2 rounded-4 px-2 py-2 hover:bg-surface-gray-2"
				@click="openItem(item)"
			>
				<!-- The desk's unread dot, in the desk's place: leading the row,
                 aligned with the first line. A button, because dismissing one
                 without going to read it is a thing people do. Once read it
                 becomes a plain spacer rather than a dead circle, so the text
                 of every row still starts in the same column. -->
				<button
					v-if="!isRead(item)"
					type="button"
					class="mt-1.5 size-2 shrink-0 rounded-full bg-surface-blue-6"
					:aria-label="`Mark as read: ${item.text}`"
					title="Mark as read"
					@click.prevent.stop="dismiss(item)"
				/>
				<span v-else class="mt-1.5 size-2 shrink-0" aria-hidden="true" />

				<span class="min-w-0 flex-1">
					<span
						class="line-clamp-2 text-p-sm"
						:class="isRead(item) ? 'text-ink-gray-6' : 'text-ink-gray-8'"
					>
						{{ item.text || 'Notification' }}
					</span>
					<span class="mt-0.5 block text-sm text-ink-gray-5">{{ item.when }}</span>
				</span>
			</component>
		</template>

		<template #footer>
			<a
				v-if="hasDeskAccess"
				:href="allNotificationsDeskUrl"
				class="shrink-0 border-t border-outline-gray-1 px-3 py-2 text-center text-sm text-ink-gray-5 hover:text-ink-gray-8"
			>
				See all activity
			</a>
		</template>
	</AppSidebarPanel>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, ErrorMessage, Skeleton, toast } from 'frappe-ui'
import AppSidebarPanel from '@/components/AppSidebarPanel.vue'
import { hasDeskAccess } from '@/data/session'
import { usePollWhileVisible } from '@/data/sidebarFeeds'
import {
	allNotificationsDeskUrl,
	notificationDeskUrl,
	useMarkAllNotificationsRead,
	useMarkNotificationRead,
	useNotificationFeed,
	type AppNotification,
} from '@/data/notifications'

const open = ref(false)

const feed = useNotificationFeed()
const markRequest = useMarkNotificationRead()
const markAllRequest = useMarkAllNotificationsRead()

const items = computed<AppNotification[]>(() => feed.data?.notifications ?? [])
const unread = computed(() => feed.data?.unread ?? 0)

/**
 * Names marked read since the feed was last fetched.
 *
 * Kept beside the rows rather than written into them: the fetched payload is
 * not ours to mutate, and whether such a mutation would even redraw depends on
 * how deeply the fetch layer happens to wrap its response. The next `reload`
 * makes it moot -- the server's answer arrives already saying `read`.
 */
const readHere = ref(new Set<string>())
const isRead = (item: AppNotification) => item.read || readHere.value.has(item.name)

// The count decides whether the row is drawn at all, so it cannot wait for
// the next page load to catch up. See `usePollWhileVisible`.
usePollWhileVisible(() => feed.reload())

/** The panel is only ever looked at open, so that is when it is worth re-reading. */
watch(open, (isOpen) => {
	if (isOpen) feed.reload()
})

/**
 * The dot, pressed on its own. Marked here before the round trip: the row is
 * under the reader's finger, and a dot that waits to go out reads as a missed
 * press. `reload` afterwards is what corrects the badge.
 */
async function dismiss(item: AppNotification) {
	readHere.value = new Set(readHere.value).add(item.name)
	await markRequest.submit({ docname: item.name })
	// `submit` resolves whether or not the server accepted it, and this endpoint
	// answers with nothing on success -- so the error, not the result, is what
	// says what happened.
	if (markRequest.error) {
		const undone = new Set(readHere.value)
		undone.delete(item.name)
		readHere.value = undone
		toast.error('Could not mark it as read')
		return
	}
	await feed.reload()
}

/**
 * Opening the document is reading the notification, which is what the desk
 * does too. Not awaited, and nothing reloaded: this click is a full page load
 * into the desk, so there is no list left to correct.
 */
function openItem(item: AppNotification) {
	if (!hasDeskAccess.value || isRead(item)) return
	readHere.value = new Set(readHere.value).add(item.name)
	markRequest.submit({ docname: item.name })
}

async function markAllRead() {
	await markAllRequest.submit()
	if (markAllRequest.error) {
		toast.error('Could not mark them as read')
		return
	}
	await feed.reload()
}
</script>
