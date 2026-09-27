<template>
	<AppPageHeader>
		<div class="flex min-w-0 items-center gap-3">
			<span class="text-lg font-semibold text-ink-gray-8">{{ title }}</span>
		</div>
		<template #actions>
			<AppPageActions :actions="actions" />
		</template>
	</AppPageHeader>

	<BankReconciliationScreen
		:query="query"
		@title="title = $event || 'Bank Reconciliation'"
		@actions="actions = $event"
		@replace-query="replaceQuery"
	/>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppPageActions from '@/components/AppPageActions.vue'
import AppPageHeader from '@/components/AppPageHeader.vue'
import BankReconciliationScreen from '@/screens/BankReconciliationScreen.vue'
import type { PageAction, ScreenQuery } from '@/islands/contract'

/**
 * `/commons/banking`: the reconciliation screen under the SPA's header and
 * router. The screen is also the `commons.banking` desk island, so it reports
 * its title and actions and its view of the query string rather than drawing
 * or writing them itself. See `screens/BankReconciliationScreen.vue`.
 */

const route = useRoute()
const router = useRouter()

const title = ref('Bank Reconciliation')
const actions = ref<PageAction[]>([])

const query = computed<ScreenQuery>(() =>
	Object.fromEntries(
		Object.entries(route.query).flatMap(([key, value]) =>
			typeof value === 'string' ? [[key, value]] : []
		)
	)
)

function replaceQuery(next: Record<string, string | undefined>) {
	router.replace({ query: { ...route.query, ...next } })
}
</script>
