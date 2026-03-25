<template>
  <div>
    <div class="text-h4 font-weight-bold mb-6">
      <v-icon class="mr-2" size="32">mdi-cog</v-icon>
      Settings
    </div>

    <v-tabs v-model="currentTab" color="primary" class="mb-4" show-arrows>
      <v-tab
        v-for="t in tabs"
        :key="t.value"
        :value="t.value"
        :prepend-icon="t.icon"
        @click="navigateTab(t.value)"
      >{{ t.label }}</v-tab>
    </v-tabs>

    <router-view v-if="isChildRoute" />
    <keep-alive v-else>
      <component :is="activeComponent" />
    </keep-alive>
  </div>
</template>

<script setup>
import { ref, computed, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const tabs = [
  { value: 'general', label: 'General', icon: 'mdi-tune', path: '/settings' },
  { value: 'akm-advisor', label: 'AKM Advisor', icon: 'mdi-briefcase-outline', path: '/settings/akm-advisor' },
  { value: 'protocols', label: 'Protocols', icon: 'mdi-head-cog', path: '/settings/protocols' },
  { value: 'skills', label: 'Skills', icon: 'mdi-puzzle', path: '/settings/skills' },
  { value: 'agent-errors', label: 'Agent Errors', icon: 'mdi-alert-circle-outline', path: '/settings/agent-errors' },
  { value: 'files', label: 'Files', icon: 'mdi-folder-open', path: '/settings/files' },
  { value: 'terminal', label: 'Terminal', icon: 'mdi-console', path: '/settings/terminal' },
  { value: 'system', label: 'System', icon: 'mdi-monitor-dashboard', path: '/settings/system' },
  { value: 'system-logs', label: 'System Logs', icon: 'mdi-text-box-search', path: '/settings/system-logs' },
  { value: 'cloud-sync', label: 'Cloud & Sync', icon: 'mdi-cloud-sync', path: '/settings/cloud-sync' },
  { value: 'addons', label: 'Addons', icon: 'mdi-puzzle', path: '/settings/addons' },
]

const componentMap = {
  'general': defineAsyncComponent(() => import('./SettingsGeneralTab.vue')),
  'akm-advisor': defineAsyncComponent(() => import('./AkmAdvisorSettingsTab.vue')),
  'protocols': defineAsyncComponent(() => import('./ProtocolsView.vue')),
  'skills': defineAsyncComponent(() => import('./SkillsView.vue')),
  'agent-errors': defineAsyncComponent(() => import('./AgentErrorsView.vue')),
  'files': defineAsyncComponent(() => import('./FileBrowserView.vue')),
  'terminal': defineAsyncComponent(() => import('./TerminalView.vue')),
  'system': defineAsyncComponent(() => import('./SystemView.vue')),
  'system-logs': defineAsyncComponent(() => import('./SystemLogsView.vue')),
  'cloud-sync': defineAsyncComponent(() => import('./CloudSyncSettingsTab.vue')),
  'addons': defineAsyncComponent(() => import('./AddonsSettingsTab.vue')),
}

const tabFromRoute = () => {
  const path = route.path
  if (path === '/settings' || path === '/settings/') return 'general'
  const match = tabs.find(t => t.value !== 'general' && path.startsWith(t.path))
  return match ? match.value : 'general'
}

const currentTab = ref(tabFromRoute())

// Child routes like /settings/skills/new, /settings/skills/:id
const isChildRoute = computed(() => {
  const path = route.path
  return path.startsWith('/settings/skills/') && path !== '/settings/skills'
})

const activeComponent = computed(() => componentMap[currentTab.value] || componentMap['general'])

const navigateTab = (tabValue) => {
  const tab = tabs.find(t => t.value === tabValue)
  if (tab && route.path !== tab.path) {
    router.push(tab.path)
  }
}

watch(() => route.path, () => {
  currentTab.value = tabFromRoute()
})
</script>
