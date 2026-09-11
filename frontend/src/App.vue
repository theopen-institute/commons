<template>
  <FrappeUIProvider>
    <DesktopShell>
      <template #sidebar>
        <AppSidebar />
      </template>
      <router-view />
    </DesktopShell>
  </FrappeUIProvider>
</template>

<script setup lang="ts">
import { DesktopShell, FrappeUIProvider } from 'frappe-ui'
import AppSidebar from '@/components/AppSidebar.vue'
</script>
