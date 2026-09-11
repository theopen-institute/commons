<template>
  <Sidebar class="border-r border-outline-gray-1" width="15rem">
    <SidebarHeader
      :title="currentApp.title"
      :subtitle="user.full_name"
      :menu-items="accountMenuItems"
    >
      <template #prefix>
        <!-- Bound, not a literal `src`: a literal absolute path is treated as
             an import to bundle, and this asset is served by Frappe from the
             app's public folder. -->
        <img :src="currentApp.logo" alt="" class="size-7 rounded-4" />
      </template>
    </SidebarHeader>

    <!-- One app's navigation only. The two apps are separate tiles on the
         desk apps screen and stay separate here; the switcher in the header
         dropdown is the only way across. -->
    <div class="flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
      <template v-if="currentApp.key === 'employees'">
        <SidebarLabel class="px-2">People</SidebarLabel>
        <SidebarItem
          label="Employees"
          icon="lucide-users"
          :to="{ name: 'EmployeeList' }"
          :active="route.name === 'EmployeeList' || route.name === 'Employee'"
        />
        <SidebarItem
          v-if="can.create"
          label="New employee"
          icon="lucide-user-plus"
          :to="{ name: 'NewEmployee' }"
        />
      </template>

      <template v-else>
        <SidebarLabel class="px-2">Leave</SidebarLabel>
        <SidebarItem
          label="My leave"
          icon="lucide-palmtree"
          :to="{ name: 'MyLeave' }"
        />
        <SidebarItem
          v-if="leaveCan.approve"
          label="Approvals"
          icon="lucide-check-check"
          :to="{ name: 'LeaveApprovals' }"
        >
          <template v-if="leaveCan.pending_approvals" #suffix>
            <Badge theme="amber" variant="subtle">
              {{ leaveCan.pending_approvals }}
            </Badge>
          </template>
        </SidebarItem>
      </template>
    </div>

    <div class="border-t border-outline-gray-1 px-2 py-2">
      <SidebarItem
        label="Open in desk"
        icon="lucide-external-link"
        @click="openDesk"
      />
      <SidebarItem
        :label="colorScheme === 'dark' ? 'Light mode' : 'Dark mode'"
        :icon="colorScheme === 'dark' ? 'lucide-sun' : 'lucide-moon'"
        @click="toggleColorScheme"
      />
    </div>
  </Sidebar>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Badge,
  Sidebar,
  SidebarHeader,
  SidebarItem,
  SidebarLabel,
  useColorScheme,
} from 'frappe-ui'
import { can, logout, user } from '@/data/session'
import { leaveCan } from '@/data/leave'
import { apps, availableApps, type AppDefinition } from '@/data/apps'

const route = useRoute()
const router = useRouter()
const { colorScheme, toggleColorScheme } = useColorScheme()

// The route says which app we are in. Employees is the fallback for the
// landing route, which redirects away before this matters.
const currentApp = computed<AppDefinition>(
  () => apps[route.meta.app ?? 'employees'],
)

// A full page load, not a router push: the desk is a different app served off
// the same site.
function openDesk() {
  window.location.href =
    currentApp.value.key === 'leave' ? '/app/leave-application' : '/app/employee'
}

const accountMenuItems = computed(() => [
  // Only the apps this user can actually open, and never the one they are in.
  ...availableApps.value
    .filter((app) => app.key !== currentApp.value.key)
    .map((app) => ({
      label: app.title,
      icon: 'lucide-arrow-right-left',
      onClick: () => router.push(app.home),
    })),
  {
    label: 'All apps',
    icon: 'lucide-layout-grid',
    onClick: () => {
      window.location.href = '/apps'
    },
  },
  {
    label: 'Log out',
    icon: 'lucide-log-out',
    onClick: logout,
  },
])
</script>
