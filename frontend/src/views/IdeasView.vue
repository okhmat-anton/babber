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
        <v-card>
          <v-card-text class="pa-0">
            <v-data-table
              v-model="selectedItems"
              :headers="headers"
              :items="group.items"
              :loading="loading"
              show-select
              return-object
              hover
              density="compact"
            >
              <template #item.priority="{ item }">
                <v-chip :color="priorityColor(item.priority)" size="small" variant="tonal">
                  <v-icon start size="14">{{ priorityIcon(item.priority) }}</v-icon>
                  {{ item.priority }}
                </v-chip>
              </template>
              <template #item.title="{ item }">
                <div>
                  <span class="font-weight-medium">{{ item.title }}</span>
                  <div v-if="item.description" class="text-caption text-grey text-truncate" style="max-width: 400px;">{{ item.description }}</div>
                </div>
              </template>
              <template #item.source="{ item }">
                <v-chip :color="item.source === 'user' ? 'blue' : 'orange'" size="small" variant="tonal">
                  <v-icon start size="14">{{ item.source === 'user' ? 'mdi-account' : 'mdi-robot' }}</v-icon>
                  {{ item.source }}
                </v-chip>
              </template>
              <template #item.agent_id="{ item }">
                <v-chip v-if="item.agent_id" size="small" variant="tonal" color="blue">{{ agentName(item.agent_id) }}</v-chip>
                <v-chip v-else size="small" variant="tonal" color="grey">Global</v-chip>
              </template>
              <template #item.category="{ item }">
                <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
              </template>
              <template #item.status="{ item }">
                <v-chip :color="statusColor(item.status)" size="small" variant="tonal">{{ item.status }}</v-chip>
              </template>
              <template #item.links="{ item }">
                <span class="text-caption">{{ linkedCount(item) || '' }}</span>
              </template>
              <template #item.created_at="{ item }">{{ formatDate(item.created_at) }}</template>
              <template #item.actions="{ item }">
                <v-btn icon size="small" variant="text" @click.stop="editIdea(item)"><v-icon>mdi-pencil</v-icon></v-btn>
                <v-btn icon size="small" variant="text" color="error" @click.stop="deleteIdea(item.id)"><v-icon>mdi-delete</v-icon></v-btn>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </div>
    </div>

    <!-- Flat table -->
    <v-card v-else>
      <v-card-text class="pa-0">
        <v-data-table
          v-model="selectedItems"
          :headers="headers"
          :items="ideas"
          :loading="loading"
          show-select
          return-object
          hover
        >
          <template #item.priority="{ item }">
            <v-chip :color="priorityColor(item.priority)" size="small" variant="tonal">
              <v-icon start size="14">{{ priorityIcon(item.priority) }}</v-icon>
              {{ item.priority }}
            </v-chip>
          </template>

          <template #item.title="{ item }">
            <div>
              <span class="font-weight-medium">{{ item.title }}</span>
              <div v-if="item.description" class="text-caption text-grey text-truncate" style="max-width: 400px;">
                {{ item.description }}
              </div>
            </div>
          </template>

          <template #item.source="{ item }">
            <v-chip :color="item.source === 'user' ? 'blue' : 'orange'" size="small" variant="tonal">
              <v-icon start size="14">{{ item.source === 'user' ? 'mdi-account' : 'mdi-robot' }}</v-icon>
              {{ item.source }}
            </v-chip>
          </template>

          <template #item.agent_id="{ item }">
            <v-chip v-if="item.agent_id" size="small" variant="tonal" color="blue">
              {{ agentName(item.agent_id) }}
            </v-chip>
            <v-chip v-else size="small" variant="tonal" color="grey">Global</v-chip>
          </template>

          <template #item.category="{ item }">
            <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
          </template>

          <template #item.status="{ item }">
            <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
              {{ item.status }}
            </v-chip>
          </template>

          <template #item.links="{ item }">
            <span class="text-caption">{{ linkedCount(item) || '' }}</span>
          </template>

          <template #item.created_at="{ item }">
            {{ formatDate(item.created_at) }}
          </template>

          <template #item.actions="{ item }">
            <v-btn icon size="small" variant="text" @click.stop="editIdea(item)">
              <v-icon>mdi-pencil</v-icon>
            </v-btn>
            <v-btn icon size="small" variant="text" color="error" @click.stop="deleteIdea(item.id)">
              <v-icon>mdi-delete</v-icon>
            </v-btn>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import api from '../api'
import { useAgentsStore } from '../stores/agents'
import { useChatStore } from '../stores/chat'

const showSnackbar = inject('showSnackbar')
const agentsStore = useAgentsStore()
const chatStore = useChatStore()

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
  await Promise.all([loadIdeas(), loadAgents()])
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
</script>
