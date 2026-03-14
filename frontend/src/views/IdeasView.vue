<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Ideas</div>
      <v-spacer />
      <v-btn
        v-if="selectedItems.length"
        color="deep-purple"
        variant="tonal"
        prepend-icon="mdi-forum"
        class="mr-3"
        @click="discussSelected"
      >
        Discuss ({{ selectedItems.length }})
      </v-btn>
      <v-btn
        color="deep-purple-accent-2"
        variant="tonal"
        prepend-icon="mdi-lightbulb-on"
        class="mr-3"
        @click="openSuggestDialog"
      >
        Suggest Ideas
      </v-btn>
      <v-btn color="amber-darken-2" prepend-icon="mdi-plus" @click="openCreateDialog">
        New Idea
      </v-btn>
    </div>

    <!-- Error alert -->
    <v-alert v-if="errorMsg" type="error" closable class="mb-4" @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <!-- Filters -->
    <div class="d-flex align-center ga-3 mb-4 flex-wrap">
      <v-btn-toggle v-model="filterSource" density="compact" variant="outlined" mandatory @update:model-value="loadIdeas">
        <v-btn value="all" size="small">All</v-btn>
        <v-btn value="user" size="small">
          <v-icon size="16" class="mr-1">mdi-account</v-icon> User
        </v-btn>
        <v-btn value="agent" size="small">
          <v-icon size="16" class="mr-1">mdi-robot</v-icon> Agent
        </v-btn>
      </v-btn-toggle>

      <v-chip-group v-model="filterStatus" selected-class="text-primary" @update:model-value="loadIdeas">
        <v-chip value="" variant="tonal" size="small">All</v-chip>
        <v-chip v-for="s in statuses" :key="s.value" :value="s.value" :color="s.color" variant="tonal" size="small">
          <v-icon start size="14">{{ s.icon }}</v-icon>
          {{ s.label }}
        </v-chip>
      </v-chip-group>

      <v-spacer />

      <v-select
        v-model="filterCategory"
        :items="categoryOptions"
        label="Category"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 200px;"
        prepend-inner-icon="mdi-tag-outline"
        @update:model-value="loadIdeas"
      />
      <v-select
        v-model="filterAgent"
        :items="agentOptions"
        item-title="name"
        item-value="id"
        label="Agent"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 220px;"
        prepend-inner-icon="mdi-robot"
        @update:model-value="loadIdeas"
      />
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="outlined"
        placeholder="Search ideas..."
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        style="max-width: 280px;"
        @update:model-value="debouncedLoad"
      />
    </div>

    <!-- Ideas grouped by category -->
    <div v-if="!filterCategory && groupedIdeas.length > 1">
      <div v-for="group in groupedIdeas" :key="group.category" class="mb-6">
        <div class="text-subtitle-1 font-weight-bold mb-2 d-flex align-center">
          <v-icon size="18" class="mr-2">mdi-tag</v-icon>
          {{ group.category || 'Uncategorized' }}
          <v-chip size="x-small" variant="tonal" class="ml-2">{{ group.items.length }}</v-chip>
        </div>
        <draggable
          :list="group.items"
          item-key="id"
          handle=".drag-handle"
          animation="200"
          ghost-class="drag-ghost"
          @end="onDragEnd(group.category)"
        >
          <template #item="{ element: idea }">
            <v-card variant="outlined" class="mb-1">
              <v-card-text class="pa-2 d-flex align-center ga-2">
                <div class="drag-handle">
                  <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
                </div>
                <v-chip :color="priorityColor(idea.priority)" size="small" variant="tonal">
                  <v-icon start size="14">{{ priorityIcon(idea.priority) }}</v-icon>
                  {{ idea.priority }}
                </v-chip>
                <div class="flex-grow-1" style="min-width: 0;">
                  <span class="font-weight-medium">{{ idea.title }}</span>
                  <div v-if="idea.description" class="text-caption text-grey text-truncate" style="max-width: 400px;">{{ idea.description }}</div>
                </div>
                <v-chip :color="idea.source === 'user' ? 'blue' : 'orange'" size="x-small" variant="tonal">
                  <v-icon start size="12">{{ idea.source === 'user' ? 'mdi-account' : 'mdi-robot' }}</v-icon>
                  {{ idea.source }}
                </v-chip>
                <v-chip v-if="idea.agent_id" size="x-small" variant="tonal" color="blue">{{ agentName(idea.agent_id) }}</v-chip>
                <v-chip :color="statusColor(idea.status)" size="x-small" variant="tonal">{{ idea.status }}</v-chip>
                <span class="text-caption text-grey">{{ formatDate(idea.created_at) }}</span>
                <v-btn icon size="small" variant="text" @click.stop="editIdea(idea)"><v-icon>mdi-pencil</v-icon></v-btn>
                <v-btn icon size="small" variant="text" color="error" @click.stop="deleteIdea(idea.id)"><v-icon>mdi-delete</v-icon></v-btn>
              </v-card-text>
            </v-card>
          </template>
        </draggable>
      </div>
    </div>

    <!-- Flat list -->
    <div v-else>
      <draggable
        :list="ideas"
        item-key="id"
        handle=".drag-handle"
        animation="200"
        ghost-class="drag-ghost"
        @end="onDragEndFlat"
      >
        <template #item="{ element: idea }">
          <v-card variant="outlined" class="mb-1">
            <v-card-text class="pa-2 d-flex align-center ga-2">
              <div class="drag-handle">
                <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
              </div>
              <v-chip :color="priorityColor(idea.priority)" size="small" variant="tonal">
                <v-icon start size="14">{{ priorityIcon(idea.priority) }}</v-icon>
                {{ idea.priority }}
              </v-chip>
              <div class="flex-grow-1" style="min-width: 0;">
                <span class="font-weight-medium">{{ idea.title }}</span>
                <div v-if="idea.description" class="text-caption text-grey text-truncate" style="max-width: 400px;">{{ idea.description }}</div>
              </div>
              <v-chip :color="idea.source === 'user' ? 'blue' : 'orange'" size="x-small" variant="tonal">
                <v-icon start size="12">{{ idea.source === 'user' ? 'mdi-account' : 'mdi-robot' }}</v-icon>
                {{ idea.source }}
              </v-chip>
              <v-chip v-if="idea.agent_id" size="x-small" variant="tonal" color="blue">{{ agentName(idea.agent_id) }}</v-chip>
              <v-chip v-if="idea.category" size="x-small" variant="tonal" color="indigo">{{ idea.category }}</v-chip>
              <v-chip :color="statusColor(idea.status)" size="x-small" variant="tonal">{{ idea.status }}</v-chip>
              <span class="text-caption text-grey">{{ formatDate(idea.created_at) }}</span>
              <v-btn icon size="small" variant="text" @click.stop="editIdea(idea)"><v-icon>mdi-pencil</v-icon></v-btn>
              <v-btn icon size="small" variant="text" color="error" @click.stop="deleteIdea(idea.id)"><v-icon>mdi-delete</v-icon></v-btn>
            </v-card-text>
          </v-card>
        </template>
      </draggable>
    </div>

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">Delete Idea</v-card-title>
        <v-card-text>
          Are you sure you want to delete this idea? This action cannot be undone.
          <v-text-field
            v-model="deleteConfirmText"
            label="Type DELETE to confirm"
            variant="outlined"
            density="compact"
            class="mt-4"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :disabled="deleteConfirmText !== 'DELETE'" @click="doDeleteIdea">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Create/Edit Idea Dialog -->
    <v-dialog v-model="formDialog" max-width="600">
      <v-card>
        <v-card-title>{{ editingIdea ? 'Edit Idea' : 'New Idea' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="formData.title"
            label="Title"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-textarea
            v-model="formData.description"
            label="Description"
            variant="outlined"
            density="compact"
            rows="4"
            class="mb-3"
          />
          <v-select
            v-model="formData.source"
            :items="['user', 'agent']"
            label="Source"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="formData.priority"
            :items="['low', 'medium', 'high']"
            label="Priority"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="formData.status"
            :items="statuses.map(s => s.value)"
            label="Status"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="formData.agent_id"
            :items="agentOptions"
            item-title="name"
            item-value="id"
            label="Agent (optional)"
            variant="outlined"
            density="compact"
            clearable
            prepend-inner-icon="mdi-robot"
            class="mb-3"
            :disabled="!!editingIdea"
          />
          <v-combobox
            v-model="formData.category"
            :items="categoryOptions"
            label="Category"
            variant="outlined"
            density="compact"
            clearable
            prepend-inner-icon="mdi-tag-outline"
            class="mb-3"
          />
          <v-combobox
            v-model="formData.tags"
            label="Tags"
            variant="outlined"
            density="compact"
            chips
            multiple
            closable-chips
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="formDialog = false">Cancel</v-btn>
          <v-btn color="amber-darken-2" :loading="saving" @click="saveIdea">{{ editingIdea ? 'Update' : 'Create' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Suggest Ideas Dialog -->
    <v-dialog v-model="suggestDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2" color="deep-purple-accent-2">mdi-lightbulb-on</v-icon>
          Suggest Ideas
        </v-card-title>
        <v-card-text>
          <v-select
            v-model="suggestAgent"
            :items="agentOptions"
            item-title="name"
            item-value="id"
            label="Select Agent"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-robot"
            class="mb-3"
            :rules="[v => !!v || 'Agent is required']"
          />

          <v-textarea
            v-model="suggestTopic"
            label="Topic (optional)"
            placeholder="What should the agent think about?"
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-3"
          />

          <div class="text-subtitle-2 mb-2">System Context:</div>
          <div class="d-flex flex-wrap ga-1 mb-3">
            <v-checkbox
              v-for="ctx in contextOptions"
              :key="ctx.value"
              v-model="suggestContextTypes"
              :label="ctx.label"
              :value="ctx.value"
              density="compact"
              hide-details
              class="mr-1"
              color="deep-purple-accent-2"
            />
          </div>

          <!-- AKM Advisor section -->
          <div v-if="akmConnected" class="mb-3">
            <div class="text-subtitle-2 mb-2 d-flex align-center">
              <v-icon size="18" class="mr-1" color="cyan">mdi-cloud-outline</v-icon>
              AKM Advisor:
            </div>
            <div class="d-flex flex-wrap ga-1 mb-2">
              <v-checkbox
                v-for="akm in akmContextOptions"
                :key="akm.value"
                v-model="suggestAkmTypes"
                :label="akm.label"
                :value="akm.value"
                density="compact"
                hide-details
                class="mr-1"
                color="cyan"
              />
            </div>
          </div>

          <!-- URLs to fetch -->
          <v-textarea
            v-model="suggestUrls"
            label="URLs to fetch (one per line)"
            placeholder="https://example.com/article&#10;https://another-site.com/page"
            variant="outlined"
            density="compact"
            rows="3"
            class="mb-1"
            prepend-inner-icon="mdi-link-variant"
            hint="Enter URLs separated by Enter — content will be fetched and added to context"
            persistent-hint
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="suggestDialog = false">Cancel</v-btn>
          <v-btn
            color="deep-purple-accent-2"
            :loading="suggestLoading"
            :disabled="!suggestAgent"
            prepend-icon="mdi-head-lightbulb"
            @click="generateSuggestions"
          >
            Think
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Suggest Results Dialog -->
    <v-dialog v-model="suggestResultsDialog" max-width="750">
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2" color="amber-darken-2">mdi-lightbulb-group</v-icon>
          Generated Ideas ({{ suggestions.length }})
        </v-card-title>
        <v-card-text style="max-height: 500px; overflow-y: auto;">
          <v-list lines="three">
            <v-list-item
              v-for="(s, idx) in suggestions"
              :key="idx"
              :class="{ 'bg-green-darken-4': s._accepted }"
              class="mb-2 rounded"
              style="border: 1px solid rgba(255,255,255,0.1);"
            >
              <template #prepend>
                <v-chip :color="priorityColor(s.priority)" size="small" variant="tonal" class="mr-2">
                  <v-icon start size="14">{{ priorityIcon(s.priority) }}</v-icon>
                  {{ s.priority }}
                </v-chip>
              </template>
              <v-list-item-title class="font-weight-bold text-wrap">{{ s.title }}</v-list-item-title>
              <v-list-item-subtitle class="text-wrap mt-1">{{ s.description }}</v-list-item-subtitle>
              <div v-if="s.category" class="mt-1">
                <v-chip size="x-small" variant="tonal" color="indigo">{{ s.category }}</v-chip>
              </div>
              <template #append>
                <v-btn
                  v-if="!s._accepted"
                  icon
                  size="small"
                  color="success"
                  variant="tonal"
                  :loading="s._saving"
                  @click="acceptSuggestion(s)"
                >
                  <v-icon>mdi-check</v-icon>
                  <v-tooltip activator="parent" location="top">Accept</v-tooltip>
                </v-btn>
                <v-icon v-else color="success" class="ml-2">mdi-check-circle</v-icon>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-btn
            variant="tonal"
            color="success"
            :disabled="suggestions.every(s => s._accepted)"
            @click="acceptAllSuggestions"
          >
            Accept All
          </v-btn>
          <v-spacer />
          <v-btn @click="suggestResultsDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import draggable from 'vuedraggable'
import api from '../api'
import { useAgentsStore } from '../stores/agents'
import { useChatStore } from '../stores/chat'
import { useSettingsStore } from '../stores/settings'

const showSnackbar = inject('showSnackbar')
const agentsStore = useAgentsStore()
const chatStore = useChatStore()
const settingsStore = useSettingsStore()

// State
const ideas = ref([])
const loading = ref(false)
const errorMsg = ref(null)
const filterSource = ref('all')
const filterStatus = ref('')
const filterAgent = ref(null)
const filterCategory = ref(null)
const searchQuery = ref('')

const formDialog = ref(false)
const editingIdea = ref(null)
const saving = ref(false)
const formData = ref({
  title: '', description: '', source: 'user', priority: 'medium',
  status: 'new', agent_id: null, category: '', tags: [],
})

const deleteDialog = ref(false)
const deleteIdeaId = ref(null)
const deleteConfirmText = ref('')
const selectedItems = ref([])

const agents = ref([])
const agentOptions = computed(() => agents.value)

// Suggest ideas state
const suggestDialog = ref(false)
const suggestAgent = ref(null)
const suggestTopic = ref('')
const suggestLoading = ref(false)
const suggestResultsDialog = ref(false)
const suggestions = ref([])

const contextOptions = [
  { value: 'ideas', label: 'Ideas' },
  { value: 'notes', label: 'Notes' },
  { value: 'facts', label: 'Facts' },
  { value: 'beliefs', label: 'Beliefs' },
  { value: 'aspirations', label: 'Aspirations' },
  { value: 'events', label: 'Events' },
  { value: 'videos', label: 'Videos' },
  { value: 'projects', label: 'Projects' },
  { value: 'tasks', label: 'Tasks' },
  { value: 'analysis', label: 'Analysis' },
  { value: 'resources', label: 'Resources' },
]

const akmContextOptions = [
  { value: 'projects', label: 'Projects' },
  { value: 'issues', label: 'Issues' },
  { value: 'epics', label: 'Epics' },
  { value: 'sprints', label: 'Sprints' },
  { value: 'leads', label: 'Leads' },
  { value: 'deals', label: 'Deals' },
]

// Restore remembered checkbox selections
const SUGGEST_CTX_KEY = 'ideas_suggest_context_types'
const SUGGEST_AKM_KEY = 'ideas_suggest_akm_types'
const savedCtx = localStorage.getItem(SUGGEST_CTX_KEY)
const savedAkm = localStorage.getItem(SUGGEST_AKM_KEY)
const suggestContextTypes = ref(
  savedCtx ? JSON.parse(savedCtx) : ['ideas', 'notes', 'facts']
)
const suggestAkmTypes = ref(
  savedAkm ? JSON.parse(savedAkm) : []
)
const suggestUrls = ref('')

// AKM connectivity check
const akmConnected = computed(() => {
  const s = settingsStore.systemSettings
  return !!(s.akm_advisor_api_key?.value && s.akm_advisor_url?.value)
})

const statuses = [
  { value: 'new', label: 'New', color: 'blue', icon: 'mdi-lightbulb-on-outline' },
  { value: 'in_progress', label: 'In Progress', color: 'orange', icon: 'mdi-progress-clock' },
  { value: 'done', label: 'Done', color: 'success', icon: 'mdi-check-circle-outline' },
  { value: 'archived', label: 'Archived', color: 'brown', icon: 'mdi-archive-outline' },
]

const headers = [
  { title: 'Priority', key: 'priority', width: 120 },
  { title: 'Title', key: 'title' },
  { title: 'Source', key: 'source', width: 110 },
  { title: 'Agent', key: 'agent_id', width: 150 },
  { title: 'Category', key: 'category', width: 140 },
  { title: 'Links', key: 'links', width: 90 },
  { title: 'Status', key: 'status', width: 120 },
  { title: 'Created', key: 'created_at', width: 140 },
  { title: 'Actions', key: 'actions', sortable: false, width: 100 },
]

const categoryOptions = computed(() => {
  const cats = [...new Set(ideas.value.map(i => i.category).filter(Boolean))]
  return cats.sort()
})

const groupedIdeas = computed(() => {
  const groups = {}
  for (const i of ideas.value) {
    const cat = i.category || ''
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(i)
  }
  return Object.entries(groups)
    .sort(([a], [b]) => { if (!a) return 1; if (!b) return -1; return a.localeCompare(b) })
    .map(([cat, items]) => ({ category: cat, items }))
})

onMounted(async () => {
  await Promise.all([loadIdeas(), loadAgents(), settingsStore.fetchSystemSettings()])
})

async function loadAgents() {
  try {
    await agentsStore.fetchAgents()
    agents.value = agentsStore.agents
  } catch (e) {
    console.error('Failed to load agents:', e)
  }
}

async function loadIdeas() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (filterSource.value && filterSource.value !== 'all') params.source = filterSource.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterAgent.value) params.agent_id = filterAgent.value
    if (filterCategory.value) params.category = filterCategory.value
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await api.get('/ideas', { params })
    ideas.value = data.items || []
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to load ideas'
  } finally {
    loading.value = false
  }
}

let _debounce = null
function debouncedLoad() {
  clearTimeout(_debounce)
  _debounce = setTimeout(() => loadIdeas(), 400)
}

function openCreateDialog() {
  editingIdea.value = null
  formData.value = {
    title: '', description: '', source: 'user', priority: 'medium',
    status: 'new', agent_id: null, category: '', tags: [],
  }
  formDialog.value = true
}

function editIdea(item) {
  editingIdea.value = item
  formData.value = {
    title: item.title,
    description: item.description,
    source: item.source,
    priority: item.priority,
    status: item.status,
    agent_id: item.agent_id,
    category: item.category || '',
    tags: [...(item.tags || [])],
  }
  formDialog.value = true
}

async function saveIdea() {
  if (!formData.value.title.trim()) return
  saving.value = true
  try {
    if (editingIdea.value) {
      await api.patch(`/ideas/${editingIdea.value.id}`, {
        title: formData.value.title,
        description: formData.value.description,
        source: formData.value.source,
        priority: formData.value.priority,
        status: formData.value.status,
        category: formData.value.category || null,
        tags: formData.value.tags,
      })
      showSnackbar?.('Idea updated', 'success')
    } else {
      const payload = { ...formData.value }
      payload.category = payload.category || null
      if (payload.agent_id) {
        await api.post(`/agents/${payload.agent_id}/ideas`, payload)
      } else {
        delete payload.agent_id
        await api.post('/ideas', payload)
      }
      showSnackbar?.('Idea created', 'success')
    }
    formDialog.value = false
    await loadIdeas()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to save idea'
  } finally {
    saving.value = false
  }
}

async function deleteIdea(id) {
  deleteIdeaId.value = id
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

async function doDeleteIdea() {
  const id = deleteIdeaId.value
  deleteDialog.value = false
  try {
    await api.delete(`/ideas/${id}`)
    ideas.value = ideas.value.filter(i => i.id !== id)
    showSnackbar?.('Idea deleted', 'success')
  } catch (e) {
    showSnackbar?.('Failed to delete', 'error')
  }
}

function agentName(agentId) {
  const a = agents.value.find(a => a.id === agentId)
  return a?.name || agentId?.substring(0, 8)
}

function statusColor(s) {
  return { new: 'blue', in_progress: 'orange', done: 'success', archived: 'brown' }[s] || 'grey'
}

function priorityColor(p) {
  return { low: 'blue-grey', medium: 'blue', high: 'red' }[p] || 'grey'
}

function priorityIcon(p) {
  return { low: 'mdi-arrow-down', medium: 'mdi-minus', high: 'mdi-arrow-up' }[p] || 'mdi-minus'
}

function linkedCount(item) {
  return (item.linked_video_ids?.length || 0) + (item.linked_fact_ids?.length || 0) + (item.linked_analysis_ids?.length || 0)
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function onDragEnd(category) {
  const group = groupedIdeas.value.find(g => g.category === (category || ''))
  if (!group) return
  const ids = group.items.map(i => i.id)
  try {
    await api.post('/ideas/reorder', { ids })
  } catch (e) {
    showSnackbar?.('Failed to reorder', 'error')
  }
}

async function onDragEndFlat() {
  const ids = ideas.value.map(i => i.id)
  try {
    await api.post('/ideas/reorder', { ids })
  } catch (e) {
    showSnackbar?.('Failed to reorder', 'error')
  }
}

async function discussSelected() {
  if (!selectedItems.value.length) return
  try {
    const lines = selectedItems.value.map(i => {
      const desc = i.description ? `\n${i.description.substring(0, 300)}` : ''
      return `### ${i.title}${desc}`
    }).join('\n\n')
    const session = await chatStore.createSession({ title: `Discuss ${selectedItems.value.length} idea(s)` })
    chatStore.openPanel()
    await chatStore.sendMessage(`Please analyze and discuss these ideas:\n\n${lines}`)
    selectedItems.value = []
    showSnackbar?.('Chat session created', 'success')
  } catch (e) {
    showSnackbar?.('Failed to create discussion', 'error')
  }
}

// ── Suggest Ideas ──────────────────────────────────

function openSuggestDialog() {
  suggestTopic.value = ''
  suggestUrls.value = ''
  suggestDialog.value = true
}

async function generateSuggestions() {
  if (!suggestAgent.value) return
  suggestLoading.value = true

  // Persist checkbox selections
  localStorage.setItem(SUGGEST_CTX_KEY, JSON.stringify(suggestContextTypes.value))
  localStorage.setItem(SUGGEST_AKM_KEY, JSON.stringify(suggestAkmTypes.value))

  // Parse URLs from textarea
  const urls = suggestUrls.value
    .split('\n')
    .map(u => u.trim())
    .filter(u => u && (u.startsWith('http://') || u.startsWith('https://')))

  try {
    const { data } = await api.post('/ideas/suggest', {
      agent_id: suggestAgent.value,
      topic: suggestTopic.value,
      context_types: suggestContextTypes.value,
      akm_context_types: suggestAkmTypes.value,
      urls,
    })
    suggestions.value = (data.suggestions || []).map(s => ({
      ...s,
      _accepted: false,
      _saving: false,
    }))
    suggestDialog.value = false
    suggestResultsDialog.value = true
  } catch (e) {
    showSnackbar?.(e.response?.data?.detail || 'Failed to generate ideas', 'error')
  } finally {
    suggestLoading.value = false
  }
}

async function acceptSuggestion(s) {
  s._saving = true
  try {
    const payload = {
      title: s.title,
      description: s.description || '',
      source: 'agent',
      priority: s.priority || 'medium',
      status: 'new',
      category: s.category || null,
      tags: [],
    }
    if (suggestAgent.value) {
      await api.post(`/agents/${suggestAgent.value}/ideas`, payload)
    } else {
      await api.post('/ideas', payload)
    }
    s._accepted = true
    showSnackbar?.('Idea saved', 'success')
  } catch (e) {
    showSnackbar?.('Failed to save idea', 'error')
  } finally {
    s._saving = false
  }
}

async function acceptAllSuggestions() {
  const pending = suggestions.value.filter(s => !s._accepted)
  for (const s of pending) {
    await acceptSuggestion(s)
  }
  await loadIdeas()
}
</script>

<style scoped>
.drag-handle {
  cursor: grab;
  opacity: 0.4;
  transition: opacity 0.2s;
}
.drag-handle:hover {
  opacity: 1;
}
.drag-handle:active {
  cursor: grabbing;
}
.drag-ghost {
  opacity: 0.3;
  background: rgba(var(--v-theme-primary), 0.1);
}
</style>
