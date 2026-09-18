<template>
  <!-- Absent, not disabled, for someone with nothing to approve: a single tab
       is not a choice, and the page is then what it always was. -->
  <TabButtons
    v-if="config.canApprove.value"
    :model-value="current"
    :options="options"
  >
    <!-- The same number the sidebar row carries, in the other place an
         approver looks: on the tab they would have to open to act on it. -->
    <template #suffix="{ button }">
      <Badge
        v-if="button.value === 'approvals' && config.pending.value"
        theme="amber"
        variant="subtle"
      >
        {{ config.pending.value }}{{ config.atCeiling.value ? '+' : '' }}
      </Badge>
    </template>
  </TabButtons>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, TabButtons } from 'frappe-ui'
import { requestSection, type RequestSectionKey } from '@/data/requests/sections'

const props = defineProps<{ section: RequestSectionKey }>()

// `config`, not `section`: a setup binding of the prop's own name is two
// things called one thing, and which of them a template means is not worth
// having to know.
const config = computed(() => requestSection(props.section))
const route = useRoute()

// Tabs that are routes: each is a RouterLink, so a queue can be linked to, the
// back button works between the two halves of the page, and a reload comes back
// to the tab it was on. The selection is read from the route rather than held
// here, which is what keeps the two in step when either one moves.
const options = computed(() => [
  {
    label: config.value.mineLabel,
    value: 'mine',
    route: { name: config.value.mineRoute },
  },
  {
    label: 'Approvals',
    value: 'approvals',
    route: { name: config.value.approvalsRoute },
  },
])

const current = computed(() =>
  route.name === config.value.approvalsRoute ? 'approvals' : 'mine',
)
</script>
