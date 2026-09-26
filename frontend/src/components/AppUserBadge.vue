<template>
	<!-- Who is signed in, as the foot of the desk's sidebar shows it. Only the
	     contents: `AppSidebar` decides whether this sits in a menu trigger or a
	     link, which is Commons Settings' "Enable User Menu".

	     40px of content inside 4px of padding, like the desk's row: the minimum
	     is the content's, not the padded box's, or the whole thing comes up 2px
	     short. -->
	<div class="flex min-h-10 items-center" :class="{ 'justify-center': collapsed }">
		<!-- The desk's avatar, not a generic one: two initials on the colour it
		     gives this person everywhere else (see `get_avatar_color`). -->
		<span
			class="flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full text-base leading-none"
			:style="avatarStyle"
			:title="user.full_name"
		>
			<img v-if="user.user_image" :src="user.user_image" alt="" class="size-full object-cover" />
			<template v-else>{{ initials }}</template>
		</span>
		<div v-if="!collapsed" class="ml-2 flex min-w-0 flex-col">
			<span class="truncate text-sm leading-[1.5] text-ink-gray-8">
				{{ user.full_name }}
			</span>
			<!-- The -1px is the desk's, from its own sidebar template: the two lines
			     are a pixel tighter than their line boxes stack to. -->
			<span class="-mt-px truncate text-sm leading-[1.5] text-ink-gray-5">
				{{ user.email ?? user.name }}
			</span>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { user } from '@/data/session'

defineProps<{ collapsed: boolean }>()

// Two initials, like the desk's `get_abbr`: the first letter of each of the
// first two words, left in the case they were written in -- the desk does not
// uppercase them either, so "José da Silva" is "Jd" in both places.
const initials = computed(() =>
	user.value.full_name
		.split(' ')
		.filter(Boolean)
		.slice(0, 2)
		.map((word) => word[0])
		.join(''),
)

// The palette entry is the server's answer; these two variables are the desk's,
// copied into index.css with the rest of its sidebar tokens.
const avatarStyle = computed(() => {
	const color = user.value.avatar_color ?? 'gray'
	return {
		backgroundColor: `var(--${color}-avatar-bg)`,
		color: `var(--${color}-avatar-color)`,
	}
})
</script>
