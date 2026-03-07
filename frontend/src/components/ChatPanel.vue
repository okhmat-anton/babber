<template>
  <div class="chat-panel">
    <!-- ═══ Header ═══ -->
    <div class="chat-header d-flex align-center px-3">
      <v-btn
        v-if="!sessionsExpanded && chatStore.currentSession"
        icon
        size="x-small"
        variant="text"
        @click="goBackToList"
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
        <!-- Chat Type Tabs -->
        <v-tabs
          v-model="activeChatType"
          density="compact"
          color="primary"
          bg-color="transparent"
          class="chat-type-tabs px-2"
          slider-color="primary"
        >
          <v-tab value="user">
            <v-icon size="14" class="mr-1">mdi-account</v-icon>
            <span class="text-caption">My Chats</span>
          </v-tab>
          <v-tab value="agent">
            <v-icon size="14" class="mr-1">mdi-robot</v-icon>
            <span class="text-caption">Agent Chats</span>
            <v-badge v-if="agentChatsUnreadCount > 0" :content="agentChatsUnreadCount" color="error" inline class="ml-1" />
          </v-tab>
          <v-tab value="project_task">
            <v-icon size="14" class="mr-1">mdi-folder</v-icon>
            <span class="text-caption">Projects & Tasks</span>
            <v-badge v-if="projectTaskUnreadCount > 0" :content="projectTaskUnreadCount" color="error" inline class="ml-1" />
          </v-tab>
        </v-tabs>
        
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
            @click="editingSessionId !== session.id && loadSession(session.id)"
          >
            <v-icon size="14" class="mr-2 flex-shrink-0" :color="(session.agent_ids?.length > 1) ? 'success' : session.multi_model ? 'warning' : 'primary'">
              {{ (session.agent_ids?.length > 1) ? 'mdi-robot-outline' : session.multi_model ? 'mdi-brain' : 'mdi-chat-outline' }}
            </v-icon>
            <div class="flex-grow-1 text-truncate">
              <input
                v-if="editingSessionId === session.id"
                v-model="editingSessionTitle"
                class="session-rename-input text-caption"
                @keydown.enter="saveSessionRename(session.id)"
                @keydown.escape="editingSessionId = null"
                @blur="saveSessionRename(session.id)"
                @click.stop
                autofocus
              />
              <div v-else class="text-caption text-truncate d-flex align-center" @dblclick.stop="startRenameSession(session)">
                <span class="text-truncate">{{ session.title }}</span>
                <v-badge 
                  v-if="session.unread_count > 0" 
                  :content="session.unread_count" 
                  color="error" 
                  inline 
                  class="ml-1"
                />
              </div>
            </div>
            <v-btn
              v-if="editingSessionId !== session.id && !session.isPseudo && session.chat_type !== 'agent' && session.chat_type !== 'project_task'"
              icon
              size="x-small"
              variant="text"
              class="ml-1 session-edit flex-shrink-0"
              @click.stop="startRenameSession(session)"
            >
              <v-icon size="12">mdi-pencil</v-icon>
            </v-btn>
            <span class="text-caption text-medium-emphasis ml-1 flex-shrink-0">{{ formatDate(session.updated_at) }}</span>
            <v-btn
              v-if="!(activeChatType === 'agent' && session.chat_type === 'agent') && !(activeChatType === 'project_task' && session.chat_type === 'project_task')"
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

        <!-- Protocol metadata: Todo list -->
        <div v-if="msg.metadata?.todo_list?.length" class="mt-2 protocol-todo-widget">
          <div class="d-flex align-center ga-1 mb-1">
            <v-icon size="14" color="light-green">mdi-format-list-checks</v-icon>
            <span class="text-caption font-weight-bold text-light-green">Task List</span>
            <v-chip size="x-small" variant="tonal" color="light-green">
              {{ msg.metadata.todo_list.filter(t => t.status === 'done').length }}/{{ msg.metadata.todo_list.length }}
            </v-chip>
          </div>
          <div v-for="item in msg.metadata.todo_list" :key="item.id" class="todo-item d-flex align-center ga-1">
            <v-icon size="14" :color="todoStatusColor(item.status)">{{ todoStatusIcon(item.status) }}</v-icon>
            <span class="text-caption" :class="{ 'text-decoration-line-through text-medium-emphasis': item.status === 'done' }">
              {{ item.task }}
            </span>
          </div>
        </div>

        <!-- Protocol metadata: Skill results -->
        <div v-if="msg.metadata?.skill_results?.length" class="mt-2 protocol-skill-results">
          <div class="d-flex align-center ga-1 mb-1">
            <v-icon size="14" color="deep-purple">mdi-lightning-bolt</v-icon>
            <span class="text-caption font-weight-bold text-deep-purple">Skills Executed</span>
          </div>
          <div v-for="(sr, si) in msg.metadata.skill_results" :key="si" class="skill-result-item">
            <v-chip size="x-small" :color="sr.result?.error ? 'error' : 'success'" variant="tonal" class="mr-1">
              <v-icon start size="10">{{ sr.result?.error ? 'mdi-alert-circle' : 'mdi-check' }}</v-icon>
              {{ sr.skill }}
            </v-chip>
          </div>
        </div>

        <!-- Protocol metadata: Delegation -->
        <div v-if="msg.metadata?.delegated_to" class="mt-2">
          <v-chip size="x-small" color="amber" variant="tonal">
            <v-icon start size="12">mdi-call-split</v-icon>
            Delegated to: {{ msg.metadata.delegated_to }}
          </v-chip>
        </div>

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

    <!-- ═══ Input Area (bottom, shown when: user chats always OR agent/project chats when chat is open) ═══ -->
    <div v-if="activeChatType === 'user' || !sessionsExpanded" class="input-area">
      <!-- Model / settings bar (hidden only for agent chats, shown for user and project_task) -->
      <div v-if="activeChatType !== 'agent'" class="input-toolbar d-flex align-center px-3 py-1">
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
            {{ multiModel ? 'Multi-Model / Multi-Agent ON' : 'Multi-Model / Multi-Agent OFF' }}
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

      <!-- Expandable settings (hidden only for agent chats) -->
      <v-expand-transition v-if="activeChatType !== 'agent'">
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
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, reactive } from 'vue'
import { useChatStore } from '../stores/chat'
import { useAgentsStore } from '../stores/agents'
import api from '../api'
import { marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const chatStore = useChatStore()
const agentsStore = useAgentsStore()

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
// Restore active chat type from localStorage, default to 'user'
const activeChatType = ref(localStorage.getItem('chat_active_tab') || 'user') // 'user', 'agent', 'project_task'
const previousChatType = ref('user') // Remember which tab we came from
const allProjects = ref([]) // All projects loaded from API

const editingSessionId = ref(null)
const editingSessionTitle = ref('')

let titleTimeout = null

const modelItems = computed(() => chatStore.availableModels || [])

const modelNamesDisplay = computed(() => {
  if (!chatStore.currentSession) return ''
  const session = chatStore.currentSession
  const ids = session.model_ids || []
  const serverNames = session.model_names || {}
  return ids.map(id => {
    // First try server-provided name (always up-to-date)
    if (serverNames[id]) return serverNames[id]
    // Then try matching from available models
    const m = chatStore.availableModels.find(am => am.id === id)
    return m ? m.name : id
  }).join(', ')
})

// Unread counts by chat type
const agentChatsUnreadCount = computed(() => {
  return chatStore.sortedSessions
    .filter(s => s.chat_type === 'agent')
    .reduce((sum, s) => sum + (s.unread_count || 0), 0)
})

const projectTaskUnreadCount = computed(() => {
  return chatStore.sortedSessions
    .filter(s => s.chat_type === 'project_task')
    .reduce((sum, s) => sum + (s.unread_count || 0), 0)
})

const filteredSessions = computed(() => {
  const q = (sessionSearch.value || '').toLowerCase()
  let results = []

  if (activeChatType.value === 'agent') {
    // For agent chats: show all agents (regardless of sessions)
    const realSessions = chatStore.sortedSessions.filter(s => s.chat_type === 'agent')
    const sessionAgentIds = new Set(realSessions.filter(s => s.agent_ids?.length === 1).map(s => s.agent_ids[0]))

    // Create pseudo-sessions for all agents
    results = agentsStore.agents.map(agent => {
      const existingSession = realSessions.find(s => s.agent_ids?.length === 1 && s.agent_ids[0] === agent.id)
      if (existingSession) {
        return existingSession
      }
      // Create pseudo-session
      return {
        id: `pseudo-agent-${agent.id}`,
        title: agent.name,
        chat_type: 'agent',
        agent_ids: [agent.id],
        isPseudo: true,
        updated_at: new Date(0).toISOString(), // Sort to bottom
        unread_count: 0
      }
    })

    // Add multi-agent sessions that don't match single agent
    const multiAgentSessions = realSessions.filter(s => !s.agent_ids?.length || s.agent_ids.length > 1)
    results.push(...multiAgentSessions)
  } else if (activeChatType.value === 'project_task') {
    // For project/task chats: show all projects (regardless of sessions), but tasks only if they have sessions
    const realSessions = chatStore.sortedSessions.filter(s => s.chat_type === 'project_task')
    const sessionProjectSlugs = new Set(realSessions.filter(s => s.project_slug).map(s => s.project_slug))

    // Create pseudo-sessions for all projects
    results = allProjects.value.map(project => {
      const existingSession = realSessions.find(s => s.project_slug === project.slug && !s.task_id)
      if (existingSession) {
        return existingSession
      }
      // Create pseudo-session for project
      return {
        id: `pseudo-project-${project.slug}`,
        title: project.name || project.slug,
        chat_type: 'project_task',
        project_slug: project.slug,
        lead_agent_id: project.lead_agent_id, // assigned agent for this project
        isPseudo: true,
        updated_at: new Date(0).toISOString(), // Sort to bottom
        unread_count: 0
      }
    })

    // Add task sessions (only real ones)
    const taskSessions = realSessions.filter(s => s.task_id)
    results.push(...taskSessions)
  } else {
    // For user chats: only show real sessions
    results = chatStore.sortedSessions.filter(s => s.chat_type === activeChatType.value)
  }

  // Apply search filter
  if (q) {
    results = results.filter(s =>
      s.title.toLowerCase().includes(q) ||
      (s.last_message || '').toLowerCase().includes(q)
    )
  }

  // Sort: real sessions first (by date), then pseudo-sessions alphabetically
  return results.sort((a, b) => {
    if (a.isPseudo && !b.isPseudo) return 1
    if (!a.isPseudo && b.isPseudo) return -1
    if (a.isPseudo && b.isPseudo) return a.title.localeCompare(b.title)
    return new Date(b.updated_at) - new Date(a.updated_at)
  })
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
  // Strip protocol markers for clean display
  let clean = content
    .replace(/<<<SKILL:\w+>>>\s*[\s\S]*?\s*<<<END_SKILL>>>/g, '')
    .replace(/<<<TODO>>>\s*[\s\S]*?\s*<<<END_TODO>>>/g, '')
    .replace(/<<<DELEGATE:.+?>>>/g, '')
    .trim()
  try { return DOMPurify.sanitize(marked.parse(clean)) }
  catch { return clean }
}

// Todo list helpers
function todoStatusIcon(status) {
  return { pending: 'mdi-checkbox-blank-outline', in_progress: 'mdi-progress-clock', done: 'mdi-checkbox-marked', skipped: 'mdi-skip-forward' }[status] || 'mdi-checkbox-blank-outline'
}
function todoStatusColor(status) {
  return { pending: 'grey', in_progress: 'orange', done: 'success', skipped: 'grey-darken-1' }[status] || 'grey'
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

function goBackToList() {
  chatStore.currentSession = null
  chatStore.messages = []
  sessionsExpanded.value = true
  // Restore the tab we came from
  if (previousChatType.value) {
    activeChatType.value = previousChatType.value
  }
  localStorage.removeItem('chat_current_session_id')
}

async function handleSend() {
  const msg = messageInput.value?.trim()
  if (!msg || chatStore.sending) return
  const models = resolvedModelIds.value
  if (!models.length) return

  messageInput.value = ''

  // If no active session, create one first
  if (!chatStore.currentSession) {
    // Extract agent IDs from selected models for multi-agent support
    const agentIds = models.filter(id => id.startsWith('agent:'))
    await chatStore.createSession({
      model_ids: models,
      agent_ids: agentIds,
      multi_model: multiModel.value,
      system_prompt: systemPrompt.value || null,
      temperature: temperature.value,
    })
  }

  // Switch to chat view
  sessionsExpanded.value = false

  await chatStore.sendMessage(msg)

  // Set title from first message immediately
  if (chatStore.currentSession && chatStore.messages.length <= 3) {
    const title = msg.length > 60 ? msg.substring(0, 60) + '…' : msg
    chatStore.currentSession.title = title
    const idx = chatStore.sessions.findIndex(s => s.id === chatStore.currentSession.id)
    if (idx >= 0) chatStore.sessions[idx].title = title
  }

  scrollToBottom()
}

async function fetchProjects() {
  try {
    const { data } = await api.get('/projects')
    allProjects.value = data.items || []
  } catch (e) {
    console.error('Failed to fetch projects:', e)
  }
}

async function loadSession(sessionId) {
  // Save current tab before opening session
  previousChatType.value = activeChatType.value
  
  // Handle pseudo-sessions: create real session first
  if (sessionId.startsWith('pseudo-')) {
    const session = filteredSessions.value.find(s => s.id === sessionId)
    if (!session) return

    let params = {
      title: session.title,
      chat_type: session.chat_type,
    }

    if (session.chat_type === 'agent' && session.agent_ids) {
      params.agent_ids = session.agent_ids
      // For single agent, set as agent_id too
      if (session.agent_ids.length === 1) {
        params.agent_id = session.agent_ids[0]
      }
    } else if (session.chat_type === 'project_task' && session.project_slug) {
      params.project_slug = session.project_slug
      // If project has assigned lead agent, set it
      if (session.lead_agent_id) {
        params.agent_id = session.lead_agent_id
      }
    }

    try {
      await chatStore.createSession(params)
      // Session is now created and set as current
      // Sync local controls with created session
      if (chatStore.currentSession) {
        const agentIds = chatStore.currentSession.agent_ids || []
        const singleAgentId = chatStore.currentSession.agent_id // Check single agent_id field
        
        if (agentIds.length > 1) {
          selectedModels.value = agentIds.map(id => `agent:${id}`)
          multiModel.value = true
        } else if (agentIds.length === 1) {
          // Single agent from agent_ids array
          selectedModels.value = `agent:${agentIds[0]}`
          multiModel.value = false
        } else if (singleAgentId) {
          // Single agent from agent_id field (used for projects with lead_agent)
          selectedModels.value = `agent:${singleAgentId}`
          multiModel.value = false
        } else {
          selectedModels.value = chatStore.currentSession.model_ids || []
          multiModel.value = chatStore.currentSession.multi_model || false
        }
        systemPrompt.value = chatStore.currentSession.system_prompt || ''
        temperature.value = chatStore.currentSession.temperature ?? 0.7
      }
      sessionsExpanded.value = false
      await nextTick()
      scrollToBottom()
      return
    } catch (e) {
      console.error('Failed to create session from pseudo:', e)
      return
    }
  }

  // Load real session
  await chatStore.loadSession(sessionId)
  // Sync local controls with loaded session
  if (chatStore.currentSession) {
    // For multi-agent sessions, reconstruct agent:UUID selection
    const agentIds = chatStore.currentSession.agent_ids || []
    const singleAgentId = chatStore.currentSession.agent_id // Check single agent_id field
    
    if (agentIds.length > 1) {
      selectedModels.value = agentIds.map(id => `agent:${id}`)
      multiModel.value = true
    } else if (agentIds.length === 1) {
      // Single agent from agent_ids array
      const agentId = `agent:${agentIds[0]}`
      const modelIds = chatStore.currentSession.model_ids || []
      selectedModels.value = multiModel.value ? [agentId, ...modelIds] : agentId
      multiModel.value = chatStore.currentSession.multi_model || false
    } else if (singleAgentId) {
      // Single agent from agent_id field (used for projects with lead_agent)
      selectedModels.value = `agent:${singleAgentId}`
      multiModel.value = false
    } else {
      selectedModels.value = chatStore.currentSession.model_ids || []
      multiModel.value = chatStore.currentSession.multi_model || false
    }
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

function startRenameSession(session) {
  editingSessionId.value = session.id
  editingSessionTitle.value = session.title
}

async function saveSessionRename(sessionId) {
  const newTitle = editingSessionTitle.value?.trim()
  editingSessionId.value = null
  if (!newTitle) return
  const idx = chatStore.sessions.findIndex(s => s.id === sessionId)
  if (idx >= 0) chatStore.sessions[idx].title = newTitle
  if (chatStore.currentSession?.id === sessionId) chatStore.currentSession.title = newTitle
  try {
    await chatStore.updateSession(sessionId, { title: newTitle })
  } catch (e) {
    console.error('Failed to rename session:', e)
  }
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

// Save active chat type to localStorage when it changes
watch(activeChatType, (newType) => {
  if (newType) {
    localStorage.setItem('chat_active_tab', newType)
  }
})

// Poll available models every 10s while panel is open
let modelPollInterval = null

function startModelPolling() {
  stopModelPolling()
  modelPollInterval = setInterval(() => {
    chatStore.fetchAvailableModels()
  }, 10000)
}

function stopModelPolling() {
  if (modelPollInterval) {
    clearInterval(modelPollInterval)
    modelPollInterval = null
  }
}

onMounted(async () => {
  await Promise.all([
    chatStore.fetchAvailableModels(),
    chatStore.fetchSessions(),
    agentsStore.fetchAgents(),
    fetchProjects()
  ])

  // Restore last active session from localStorage
  const savedSessionId = localStorage.getItem('chat_current_session_id')
  if (savedSessionId && chatStore.sessions.find(s => s.id === savedSessionId)) {
    await loadSession(savedSessionId)
  } else {
    // Pre-select first model if available
    if (chatStore.availableModels.length && !selectedModels.value.length) {
      selectedModels.value = multiModel.value ? [] : chatStore.availableModels[0].id
    }
  }
  if (chatStore.panelOpen) startModelPolling()
})

onBeforeUnmount(() => {
  stopModelPolling()
})

watch(() => chatStore.panelOpen, (open) => {
  if (open) {
    chatStore.fetchAvailableModels()
    startModelPolling()
  } else {
    stopModelPolling()
  }
})
</script>

<style scoped>
/* ── Panel Shell ── */
.chat-panel {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 36px);
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
.session-row .session-delete,
.session-row .session-edit {
  opacity: 0;
  transition: opacity 0.15s;
}
.session-row:hover .session-delete,
.session-row:hover .session-edit {
  opacity: 1;
}

.session-rename-input {
  width: 100%;
  background: rgba(var(--v-theme-surface), 0.9);
  border: 1px solid rgba(var(--v-theme-primary), 0.5);
  border-radius: 4px;
  padding: 2px 6px;
  color: inherit;
  font-size: inherit;
  outline: none;
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

/* Protocol widgets */
.protocol-todo-widget {
  background: rgba(139,195,74,0.06);
  border: 1px solid rgba(139,195,74,0.15);
  border-radius: 8px;
  padding: 8px 10px;
}
.todo-item {
  padding: 2px 0;
}
.protocol-skill-results {
  background: rgba(103,58,183,0.06);
  border: 1px solid rgba(103,58,183,0.15);
  border-radius: 8px;
  padding: 8px 10px;
}
.skill-result-item {
  padding: 2px 0;
}
</style>
