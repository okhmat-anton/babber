<template>
  <div class="chat-panel">
    <!-- ═══ Header ═══ -->
    <div class="chat-header d-flex align-center px-3">
      <v-btn
        v-if="!sessionsExpanded && chatStore.currentSession"
        icon
        size="x-small"
        variant="text"
        @click="sessionsExpanded = true"
        class="mr-1"
      >
        <v-icon size="18">mdi-arrow-left</v-icon>
        <v-tooltip activator="parent" location="bottom">Back to chats</v-tooltip>
      </v-btn>
      <v-icon v-else size="small" color="primary" class="mr-2">mdi-chat</v-icon>
      <span class="text-subtitle-2 font-weight-medium flex-grow-1 text-truncate">
        {{ sessionsExpanded ? 'Chats' : (chatStore.currentSession ? chatStore.currentSession.title : 'New Chat') }}
      </span>
      <v-btn icon size="x-small" variant="text" @click="newChat">
        <v-icon size="18">mdi-plus</v-icon>
        <v-tooltip activator="parent" location="bottom">New Chat</v-tooltip>
      </v-btn>
      <v-btn icon size="x-small" variant="text" @click="chatStore.closePanel()">
        <v-icon size="18">mdi-close</v-icon>
      </v-btn>
    </div>

    <!-- ═══ Sessions List (full view, shown when sessionsExpanded) ═══ -->
    <template v-if="sessionsExpanded">
      <div class="sessions-view">
        <div class="px-2 py-1">
          <v-text-field
            v-model="sessionSearch"
            placeholder="Filter chats..."
            density="compact"
            variant="outlined"
            prepend-inner-icon="mdi-magnify"
            hide-details
            single-line
            class="session-filter"
          />
        </div>
        <div class="sessions-scroll">
          <div
            v-for="session in filteredSessions"
            :key="session.id"
            class="session-row d-flex align-center px-3 py-1"
            :class="{ active: chatStore.currentSession?.id === session.id }"
            @click="loadSession(session.id)"
          >
            <v-icon size="14" class="mr-2 flex-shrink-0" :color="session.multi_model ? 'warning' : 'primary'">
              {{ session.multi_model ? 'mdi-brain' : 'mdi-chat-outline' }}
            </v-icon>
            <div class="flex-grow-1 text-truncate">
              <div class="text-caption text-truncate">{{ session.title }}</div>
            </div>
            <span class="text-caption text-medium-emphasis ml-2 flex-shrink-0">{{ formatDate(session.updated_at) }}</span>
            <v-btn
              icon
              size="x-small"
              variant="text"
              class="ml-1 session-delete flex-shrink-0"
              @click.stop="deleteSession(session.id)"
            >
              <v-icon size="14">mdi-close</v-icon>
            </v-btn>
          </div>
          <div v-if="filteredSessions.length === 0" class="text-caption text-medium-emphasis text-center pa-3">
            No chats
          </div>
        </div>
      </div>
    </template>

    <!-- ═══ Chat View (shown when NOT sessionsExpanded) ═══ -->
    <template v-else>
    <div ref="messagesContainer" class="messages-container">
      <!-- Empty state -->
      <div v-if="!chatStore.currentSession && chatStore.messages.length === 0" class="empty-state">
        <v-icon size="40" color="grey-lighten-1" class="mb-2">mdi-chat-processing-outline</v-icon>
        <p class="text-body-2 text-medium-emphasis">Ask anything to start a new chat</p>
      </div>

      <!-- Messages -->
      <div
        v-for="msg in chatStore.messages"
        :key="msg.id"
        class="message-bubble"
        :class="msg.role"
      >
        <div class="message-header d-flex align-center mb-1">
          <v-icon size="14" :color="msg.role === 'user' ? 'primary' : 'success'" class="mr-1">
            {{ msg.role === 'user' ? 'mdi-account' : 'mdi-robot' }}
          </v-icon>
          <span class="text-caption font-weight-medium">
            {{ msg.role === 'user' ? 'You' : (msg.model_name || 'Assistant') }}
          </span>
          <v-spacer />
          <span v-if="msg.duration_ms" class="text-caption text-medium-emphasis">
            {{ (msg.duration_ms / 1000).toFixed(1) }}s
          </span>
        </div>

        <div class="message-content text-body-2" v-html="renderMarkdown(msg.content)"></div>

        <!-- Multi-model individual responses -->
        <v-expand-transition>
          <div v-if="msg.model_responses && expandedResponses[msg.id]" class="mt-2">
            <v-divider class="mb-2" />
            <div v-for="(resp, modelName) in msg.model_responses" :key="modelName" class="mb-2">
              <div class="text-caption font-weight-bold text-warning">{{ modelName }}</div>
              <div class="text-caption" v-html="renderMarkdown(resp)"></div>
            </div>
          </div>
        </v-expand-transition>
        <div v-if="msg.model_responses" class="mt-1">
          <v-btn size="x-small" variant="text" @click="expandedResponses[msg.id] = !expandedResponses[msg.id]">
            <v-icon size="small" start>{{ expandedResponses[msg.id] ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
            {{ expandedResponses[msg.id] ? 'Hide' : 'Show' }} individual responses
          </v-btn>
        </div>
        <div v-if="msg.total_tokens" class="text-caption text-medium-emphasis mt-1">
          {{ msg.total_tokens }} tokens
        </div>
      </div>

      <!-- Typing indicator -->
      <div v-if="chatStore.sending" class="message-bubble assistant">
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
    </template>

    <!-- ═══ Input Area (bottom, always visible) ═══ -->
    <div class="input-area">
      <!-- Model / settings bar -->
      <div class="input-toolbar d-flex align-center px-3 py-1">
        <v-autocomplete
          v-model="selectedModels"
          :items="modelItems"
          item-title="name"
          item-value="id"
          :label="multiModel ? 'Models' : 'Model'"
          :multiple="multiModel"
          :chips="multiModel"
          closable-chips
          density="compact"
          variant="plain"
          hide-details
          single-line
          class="model-select flex-grow-1"
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps">
              <template #prepend>
                <v-icon size="small" :color="item.raw.type === 'agent' ? 'success' : 'primary'">
                  {{ item.raw.type === 'agent' ? 'mdi-robot' : 'mdi-cube-outline' }}
                </v-icon>
              </template>
              <template #subtitle>
                <span class="text-caption">{{ item.raw.provider }}</span>
              </template>
            </v-list-item>
          </template>
        </v-autocomplete>
        <v-btn
          icon
          size="x-small"
          variant="text"
          :color="multiModel ? 'warning' : undefined"
          @click="multiModel = !multiModel"
          class="ml-1"
        >
          <v-icon size="16">mdi-brain</v-icon>
          <v-tooltip activator="parent" location="top">
            {{ multiModel ? 'Multi-Model ON' : 'Multi-Model OFF' }}
          </v-tooltip>
        </v-btn>
        <v-btn
          icon
          size="x-small"
          variant="text"
          @click="showSettings = !showSettings"
          class="ml-0"
        >
          <v-icon size="16">mdi-cog</v-icon>
          <v-tooltip activator="parent" location="top">Settings</v-tooltip>
        </v-btn>
      </div>

      <!-- Expandable settings -->
      <v-expand-transition>
        <div v-if="showSettings" class="px-3 pb-2">
          <v-textarea
            v-model="systemPrompt"
            label="System prompt"
            variant="outlined"
            density="compact"
            rows="2"
            auto-grow
            hide-details
            class="mb-2"
          />
          <div class="d-flex align-center">
            <span class="text-caption mr-2">Temp</span>
            <v-slider v-model="temperature" :min="0" :max="2" :step="0.1" thumb-label hide-details class="flex-grow-1" />
            <span class="text-caption ml-2" style="min-width:24px">{{ temperature }}</span>
          </div>
        </div>
      </v-expand-transition>

      <!-- Text input -->
      <div class="px-3 pb-3 pt-1 d-flex align-end">
        <v-textarea
          ref="inputRef"
          v-model="messageInput"
          :placeholder="chatStore.currentSession ? 'Send a message…' : 'Ask a question to start a new chat…'"
          variant="outlined"
          density="compact"
          rows="4"
          max-rows="16"
          no-resize
          hide-details
          class="flex-grow-1 mr-2 chat-message-input"
          @keydown.enter.exact.prevent="handleSend"
        />
        <v-btn
          icon
          color="primary"
          size="small"
          :disabled="!canSend"
          :loading="chatStore.sending"
          @click="handleSend"
        >
          <v-icon>mdi-send</v-icon>
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, reactive } from 'vue'
import { useChatStore } from '../stores/chat'
import { marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const chatStore = useChatStore()

// State
const selectedModels = ref([])
const multiModel = ref(false)
const systemPrompt = ref('')
const temperature = ref(0.7)
const messageInput = ref('')
const inputRef = ref(null)
const messagesContainer = ref(null)
const showSettings = ref(false)
const sessionSearch = ref('')
const sessionsExpanded = ref(true)
const expandedResponses = reactive({})

let titleTimeout = null

const modelItems = computed(() => chatStore.availableModels || [])

const modelNamesDisplay = computed(() => {
  if (!chatStore.currentSession) return ''
  const ids = chatStore.currentSession.model_ids || []
  return ids.map(id => {
    const m = chatStore.availableModels.find(am => am.id === id)
    return m ? m.name : id
  }).join(', ')
})

const filteredSessions = computed(() => {
  const q = (sessionSearch.value || '').toLowerCase()
  if (!q) return chatStore.sortedSessions
  return chatStore.sortedSessions.filter(s =>
    s.title.toLowerCase().includes(q) ||
    (s.last_message || '').toLowerCase().includes(q)
  )
})

const canSend = computed(() => {
  if (!messageInput.value?.trim()) return false
  const models = resolvedModelIds.value
  return models.length > 0
})

const resolvedModelIds = computed(() => {
  if (Array.isArray(selectedModels.value)) return selectedModels.value.filter(Boolean)
  if (selectedModels.value) return [selectedModels.value]
  return []
})

// Configure marked with syntax highlighting
marked.use(markedHighlight({
  langPrefix: 'hljs language-',
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value } catch {}
    }
    try { return hljs.highlightAuto(code).value } catch {}
    return code
  },
}))
marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(content) {
  if (!content) return ''
  try { return DOMPurify.sanitize(marked.parse(content)) }
  catch { return content }
}

function formatDate(dateStr) {
  const date = new Date(dateStr)
  const diff = Date.now() - date
  if (diff < 60000) return 'now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}d`
  return date.toLocaleDateString()
}

function newChat() {
  chatStore.newChat()
  selectedModels.value = []
  multiModel.value = false
  systemPrompt.value = ''
  temperature.value = 0.7
  messageInput.value = ''
  sessionsExpanded.value = true
}

async function handleSend() {
  const msg = messageInput.value?.trim()
  if (!msg || chatStore.sending) return
  const models = resolvedModelIds.value
  if (!models.length) return

  messageInput.value = ''

  // If no active session, create one first
  if (!chatStore.currentSession) {
    await chatStore.createSession({
      model_ids: models,
      multi_model: multiModel.value,
      system_prompt: systemPrompt.value || null,
      temperature: temperature.value,
    })
  }

  // Switch to chat view
  sessionsExpanded.value = false

  await chatStore.sendMessage(msg)
  scrollToBottom()
}

async function loadSession(sessionId) {
  await chatStore.loadSession(sessionId)
  // Sync local controls with loaded session
  if (chatStore.currentSession) {
    selectedModels.value = chatStore.currentSession.model_ids || []
    multiModel.value = chatStore.currentSession.multi_model || false
    systemPrompt.value = chatStore.currentSession.system_prompt || ''
    temperature.value = chatStore.currentSession.temperature ?? 0.7
    sessionsExpanded.value = false
  }
  await nextTick()
  scrollToBottom()
}

async function deleteSession(sessionId) {
  await chatStore.deleteSession(sessionId)
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// Sync model selector back to session on change
watch([selectedModels, multiModel], () => {
  if (!chatStore.currentSession) return
  clearTimeout(titleTimeout)
  titleTimeout = setTimeout(() => {
    chatStore.updateSession(chatStore.currentSession.id, {
      model_ids: resolvedModelIds.value,
      multi_model: multiModel.value,
    })
  }, 400)
})

watch(() => chatStore.messages.length, () => scrollToBottom())

onMounted(async () => {
  await chatStore.fetchAvailableModels()
  await chatStore.fetchSessions()
  // Pre-select first model if available
  if (chatStore.availableModels.length && !selectedModels.value.length) {
    selectedModels.value = multiModel.value ? [] : chatStore.availableModels[0].id
  }
})

watch(() => chatStore.panelOpen, (open) => {
  if (open) chatStore.fetchAvailableModels()
})
</script>

<style scoped>
/* ── Panel Shell ── */
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  flex: 1;
  min-width: 0;
  background: rgb(var(--v-theme-surface));
}

/* ── Header ── */
.chat-header {
  height: 36px;
  min-height: 36px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  user-select: none;
}

/* ── Sessions View (full panel) ── */
.sessions-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.session-filter {
  font-size: 12px;
}
.session-filter :deep(.v-field__input) {
  min-height: 28px !important;
  font-size: 12px;
}

.sessions-scroll {
  flex: 1;
  overflow-y: auto;
}

.session-row {
  cursor: pointer;
  min-height: 28px;
  border-radius: 4px;
  margin: 0 4px;
  transition: background 0.1s;
}
.session-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.session-row.active {
  background: rgba(var(--v-theme-primary), 0.1);
}
.session-row .session-delete {
  opacity: 0;
  transition: opacity 0.15s;
}
.session-row:hover .session-delete {
  opacity: 1;
}

/* ── Messages ── */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  opacity: 0.7;
}

.message-bubble {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-radius: 12px;
  max-width: 95%;
}
.message-bubble.user {
  background: rgba(var(--v-theme-primary), 0.08);
  margin-left: auto;
  border-bottom-right-radius: 4px;
}
.message-bubble.assistant {
  background: rgba(var(--v-theme-secondary), 0.2);
  margin-right: auto;
  border-bottom-left-radius: 4px;
}

.message-content {
  line-height: 1.6;
  word-break: break-word;
}
.message-content :deep(pre) {
  background: #0d1117;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
  font-size: 0.85em;
  border: 1px solid #30363d;
}
.message-content :deep(code) {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.9em;
  background: rgba(110, 118, 129, 0.2);
  padding: 2px 6px;
  border-radius: 4px;
  color: #e6edf3;
}
.message-content :deep(pre code) {
  background: none;
  padding: 0;
  border-radius: 0;
  color: #e6edf3;
  font-size: 1em;
}
.message-content :deep(p) {
  margin-bottom: 4px;
}
.message-content :deep(ul),
.message-content :deep(ol) {
  padding-left: 20px;
  margin-bottom: 4px;
}

/* ── Input Area ── */
.input-area {
  flex-shrink: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
}

.chat-message-input :deep(textarea) {
  resize: vertical !important;
  min-height: 96px !important;
  overflow-y: auto !important;
}

.input-toolbar {
  min-height: 32px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.06);
}

.model-select {
  font-size: 13px;
}
.model-select :deep(.v-field__input) {
  min-height: 28px !important;
  padding: 0 !important;
  font-size: 13px;
}

/* ── Typing indicator ── */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}
.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(var(--v-theme-on-surface), 0.4);
  animation: typing 1.4s infinite ease-in-out both;
}
.typing-indicator span:nth-child(1) { animation-delay: 0s; }
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
