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
        <v-list-item
          v-for="item in navItems"
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
      <div class="layout-split">
        <!-- Main Content -->
        <div class="main-content" :style="{ marginRight: chatStore.panelOpen ? panelWidth + 'px' : '0' }">
          <v-container fluid class="pa-6">
            <router-view />
          </v-container>
        </div>

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
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import ChatPanel from '../components/ChatPanel.vue'

const router = useRouter()
const auth = useAuthStore()
const chatStore = useChatStore()
const drawer = ref(true)
const rail = ref(false)

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
  { path: '/agents', icon: 'mdi-robot', title: 'Agents' },
  { path: '/protocols', icon: 'mdi-head-cog', title: 'Protocols' },
  { path: '/tasks', icon: 'mdi-clipboard-list', title: 'Tasks' },
  { path: '/skills', icon: 'mdi-puzzle', title: 'Skills (Codes)' },
  { path: '/settings', icon: 'mdi-cog', title: 'Settings' },
  { path: '/ollama', icon: 'mdi-creation', title: 'Ollama' },
  { path: '/files', icon: 'mdi-folder-open', title: 'Files' },
  { path: '/terminal', icon: 'mdi-console', title: 'Terminal' },
  { path: '/system', icon: 'mdi-monitor-dashboard', title: 'System' },
  { path: '/system/logs', icon: 'mdi-text-box-search', title: 'System Logs' },
]

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
  top: 0;
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
