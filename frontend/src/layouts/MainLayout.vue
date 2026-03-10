<template>
  <v-layout>
    <!-- Navigation Drawer -->
    <v-navigation-drawer v-model="drawer" :rail="rail" permanent>
      <v-list-item
        prepend-icon="mdi-robot-happy"
        title="AI Agents"
        subtitle="Server"
        nav
        @click="rail = !rail"
      />
      <v-divider />
      <v-list density="compact" nav>
        <template v-for="item in navItems" :key="item.path">
          <!-- Collapsible group -->
          <v-list-group v-if="item.children" :value="item.path">
            <template #activator="{ props }">
              <v-list-item
                v-bind="props"
                :prepend-icon="item.icon"
                :title="item.title"
                rounded="xl"
              />
            </template>
            <v-list-item
              v-for="child in item.children"
              :key="child.path"
              :to="child.path"
              :prepend-icon="child.icon"
              :title="child.title"
              :value="child.path"
              rounded="xl"
            />
          </v-list-group>
          <!-- Simple item -->
          <v-list-item
            v-else
            :to="item.path"
            :prepend-icon="item.icon"
            :title="item.title"
            :value="item.path"
            rounded="xl"
          />
        </template>
        <v-divider class="my-2" />
        <v-list-item
          v-for="item in settingsNav"
          :key="item.path"
          :to="item.path"
          :prepend-icon="item.icon"
          :title="item.title"
          :value="item.path"
          rounded="xl"
        />
      </v-list>
      <template #append>
        <v-list density="compact" nav>
          <v-list-item
            prepend-icon="mdi-logout"
            title="Logout"
            @click="handleLogout"
            rounded="xl"
          />
        </v-list>
      </template>
    </v-navigation-drawer>

    <!-- Main + Chat split -->
    <v-main class="main-with-chat">
      <TopBar />
      <div class="layout-split">
        <!-- Main Content -->
        <div ref="mainContentEl" class="main-content" :style="{ marginRight: chatStore.panelOpen ? panelWidth + 'px' : '0' }">
          <v-alert
            v-if="baseModelAlert"
            type="error"
            variant="tonal"
            density="compact"
            class="mx-6 mt-4 mb-0"
            icon="mdi-alert-circle"
          >
            <strong>{{ baseModelAlert }}</strong>
          </v-alert>
          <v-container fluid class="pa-6">
            <router-view />
          </v-container>
        </div>

        <!-- Global Text Selection Popup (for all pages) -->
        <TextSelectionPopup
          ref="globalSelectionPopupRef"
          :container-el="mainContentEl"
          :agents="globalAgents"
          @save="handleGlobalSelectionSave"
        />

        <!-- Chat Side Panel -->
        <transition name="slide-panel">
          <div
            v-if="chatStore.panelOpen"
            class="chat-side-panel"
            :style="{ width: panelWidth + 'px' }"
          >
            <!-- Resize Handle -->
            <div
              class="resize-handle"
              @mousedown="startResize"
            >
              <div class="resize-handle-line"></div>
            </div>
            <ChatPanel />
          </div>
        </transition>

        <!-- Chat FAB -->
        <v-btn
          v-if="!chatStore.panelOpen"
          icon
          color="primary"
          size="large"
          class="chat-fab"
          elevation="8"
          @click="chatStore.openPanel()"
        >
          <v-icon>mdi-chat</v-icon>
          <v-tooltip activator="parent" location="left">AI Chat</v-tooltip>
        </v-btn>
      </div>
    </v-main>
  </v-layout>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'
import { useAgentsStore } from '../stores/agents'
import ChatPanel from '../components/ChatPanel.vue'
import TopBar from '../components/TopBar.vue'
import TextSelectionPopup from '../components/TextSelectionPopup.vue'
import api from '../api'

const router = useRouter()
const auth = useAuthStore()
const chatStore = useChatStore()
const settingsStore = useSettingsStore()
const agentsStore = useAgentsStore()
const drawer = ref(true)
const rail = ref(false)

const globalSelectionPopupRef = ref(null)
const mainContentEl = ref(null)
const globalAgents = ref([])

const baseModelAlert = computed(() => settingsStore.baseModelAlertText)

const MIN_PANEL = 320
const MAX_PANEL = 900
const DEFAULT_PANEL = 420

const panelWidth = ref(
  parseInt(localStorage.getItem('chat_panel_width')) || DEFAULT_PANEL
)

let isResizing = false
let startX = 0
let startWidth = 0

function startResize(e) {
  isResizing = true
  startX = e.clientX
  startWidth = panelWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}

function onResize(e) {
  if (!isResizing) return
  const delta = startX - e.clientX
  const newWidth = Math.min(MAX_PANEL, Math.max(MIN_PANEL, startWidth + delta))
  panelWidth.value = newWidth
}

function stopResize() {
  isResizing = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  localStorage.setItem('chat_panel_width', panelWidth.value)
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
})

const navItems = [
  { path: '/', icon: 'mdi-view-dashboard', title: 'Dashboard' },
  {
    path: '/creator',
    icon: 'mdi-account-heart',
    title: 'Creator',
    children: [
      { path: '/creator', icon: 'mdi-account', title: 'Context' },
      { path: '/creator/goals', icon: 'mdi-flag-variant', title: 'Goals' },
      { path: '/creator/dreams', icon: 'mdi-creation', title: 'Dreams' },
      { path: '/creator/ideas', icon: 'mdi-lightbulb-on', title: 'Ideas' },
      { path: '/creator/notes', icon: 'mdi-note-text', title: 'Notes' },
    ],
  },
  { path: '/agents', icon: 'mdi-robot', title: 'Agents' },
  { path: '/research-resources', icon: 'mdi-book-search', title: 'Trusted Resources' },
  { path: '/tasks', icon: 'mdi-clipboard-list', title: 'Tasks' },
  { path: '/video', icon: 'mdi-video-outline', title: 'Video' },
  { path: '/analysis', icon: 'mdi-chart-timeline-variant-shimmer', title: 'Analysis' },
  { path: '/facts', icon: 'mdi-check-decagram', title: 'Facts' },
  { path: '/events', icon: 'mdi-calendar-clock', title: 'Events' },
  { path: '/ideas', icon: 'mdi-lightbulb-on', title: 'Ideas' },
  { path: '/projects', icon: 'mdi-folder-wrench', title: 'Projects' },
  { path: '/models', icon: 'mdi-brain', title: 'Models' },
]

const settingsNav = [
  { path: '/settings', icon: 'mdi-cog', title: 'Settings' },
]

onMounted(() => {
  settingsStore.refreshBaseModelStatus()
  // Load agents for global text selection popup
  agentsStore.fetchAgents().then(() => {
    globalAgents.value = agentsStore.agents || []
  }).catch(() => {})
})

// ── Global text selection save handler ──────────────────────────────
async function handleGlobalSelectionSave(target, extra = {}) {
  const text = globalSelectionPopupRef.value?.getSelectedText()
  if (!text?.trim()) return
  const trimmed = text.trim()
  const titleSnippet = trimmed.substring(0, 80).replace(/[#*`\n]/g, '').trim() + (trimmed.length > 80 ? '…' : '')
  
  try {
    // Global targets
    if (target === 'global_fact') {
      // Need an agent for facts - use first available
      const agentId = globalAgents.value[0]?.id
      if (!agentId) {
        globalSelectionPopupRef.value?.showStatus('No agent available', 'error')
        return
      }
      await api.post('/facts', {
        agent_id: agentId,
        type: 'fact',
        content: trimmed,
        source: 'text_selection',
      })
    } else if (target === 'global_analysis') {
      await api.post('/analysis-topics', {
        title: titleSnippet,
        description: trimmed,
        status: 'active',
      })
    } else if (target === 'global_idea') {
      await api.post('/ideas', {
        title: titleSnippet,
        description: trimmed,
        source: 'user',
      })
    } else if (target.startsWith('agent_') && extra.agentId) {
      // Agent targets
      const aid = extra.agentId
      switch (target) {
        case 'agent_fact':
          await api.post(`/agents/${aid}/facts`, {
            type: 'fact', content: trimmed, source: 'text_selection',
          })
          break
        case 'agent_belief':
          await api.post(`/agents/${aid}/beliefs/core`, {
            text: trimmed, category: 'other',
          })
          break
        case 'agent_aspiration':
          await api.post(`/agents/${aid}/aspirations/goals`, {
            text: trimmed, priority: 'medium', locked: true,
          })
          break
        case 'agent_event':
          await api.post(`/agents/${aid}/events`, {
            event_type: 'observation', title: titleSnippet, description: trimmed,
            source: 'text_selection', importance: 'medium',
          })
          break
        case 'agent_task':
          await api.post(`/agents/${aid}/tasks`, {
            title: titleSnippet, description: trimmed,
          })
          break
      }
    } else {
      // Creator items (notes, goals, ideas, dreams)
      await api.post('/creator/append-item', {
        target,
        title: titleSnippet,
        content: trimmed,
      })
    }
    globalSelectionPopupRef.value?.showStatus('Saved!', 'success')
    window.getSelection()?.removeAllRanges()
  } catch (e) {
    console.error('Global selection save failed:', e)
    globalSelectionPopupRef.value?.showStatus('Error', 'error')
  }
}

const handleLogout = async () => {
  await auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.main-with-chat {
  overflow: hidden;
}

.layout-split {
  position: relative;
  height: 100%;
  min-height: calc(100vh - 0px);
}

.main-content {
  height: 100%;
  overflow-y: auto;
  transition: margin-right 0.2s ease;
}

/* ── Chat Side Panel ── */
.chat-side-panel {
  position: fixed;
  top: 36px;
  right: 0;
  bottom: 0;
  z-index: 100;
  display: flex;
  flex-direction: row;
  background: rgb(var(--v-theme-surface));
  border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

/* ── Resize Handle ── */
.resize-handle {
  width: 6px;
  cursor: col-resize;
  position: relative;
  flex-shrink: 0;
  z-index: 10;
  transition: background 0.15s;
}

.resize-handle:hover,
.resize-handle:active {
  background: rgba(var(--v-theme-primary), 0.18);
}

.resize-handle-line {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 32px;
  border-radius: 2px;
  background: rgba(var(--v-theme-on-surface), 0.18);
  transition: height 0.15s, background 0.15s;
}

.resize-handle:hover .resize-handle-line {
  height: 48px;
  background: rgba(var(--v-theme-primary), 0.5);
}

/* ── Transition ── */
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* ── FAB ── */
.chat-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 90;
}
</style>
