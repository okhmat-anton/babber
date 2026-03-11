<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Analysis</div>
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
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreateDialog">
        New Topic
      </v-btn>
    </div>

    <!-- Error alert -->
    <v-alert v-if="errorMsg" type="error" closable class="mb-4" @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <!-- Filters -->
    <div class="d-flex align-center ga-3 mb-4 flex-wrap">
      <v-chip-group v-model="filterStatus" selected-class="text-primary" @update:model-value="loadTopics">
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
        @update:model-value="loadTopics"
      />
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="outlined"
        placeholder="Search topics..."
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        style="max-width: 280px;"
        @update:model-value="debouncedLoad"
      />
    </div>

    <!-- Topics grouped by category -->
    <div v-if="!filterCategory && groupedTopics.length > 1">
      <div v-for="group in groupedTopics" :key="group.category" class="mb-6">
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
              @click:row="(_, { item }) => openDetail(item)"
            >
              <template #item.status="{ item }">
                <v-chip :color="statusColor(item.status)" size="small" variant="tonal">{{ item.status }}</v-chip>
              </template>
              <template #item.title="{ item }">
                <div>
                  <span class="font-weight-medium">{{ item.title }}</span>
                  <div v-if="item.description" class="text-caption text-grey text-truncate" style="max-width: 400px;">{{ item.description }}</div>
                </div>
              </template>
              <template #item.agent_id="{ item }">
                <v-chip v-if="item.agent_id" size="small" variant="tonal" color="blue">{{ agentName(item.agent_id) }}</v-chip>
                <v-chip v-else size="small" variant="tonal" color="grey">Global</v-chip>
              </template>
              <template #item.category="{ item }">
                <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
              </template>
              <template #item.fact_ids="{ item }">
                <v-chip size="small" variant="tonal" color="teal">{{ item.fact_ids?.length || 0 }} facts</v-chip>
              </template>
              <template #item.links="{ item }">
                <span class="text-caption">{{ linkedCount(item) || '' }}</span>
              </template>
              <template #item.created_at="{ item }">{{ formatDate(item.created_at) }}</template>
              <template #item.actions="{ item }">
                <v-btn icon size="small" variant="text" @click.stop="editTopic(item)"><v-icon>mdi-pencil</v-icon></v-btn>
                <v-btn icon size="small" variant="text" color="error" @click.stop="deleteTopic(item.id)"><v-icon>mdi-delete</v-icon></v-btn>
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
          :items="topics"
          :loading="loading"
          show-select
          return-object
          hover
          @click:row="(_, { item }) => openDetail(item)"
        >
          <template #item.status="{ item }">
            <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
              {{ item.status }}
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

          <template #item.agent_id="{ item }">
            <v-chip v-if="item.agent_id" size="small" variant="tonal" color="blue">
              {{ agentName(item.agent_id) }}
            </v-chip>
            <v-chip v-else size="small" variant="tonal" color="grey">Global</v-chip>
          </template>

          <template #item.category="{ item }">
            <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
          </template>

          <template #item.fact_ids="{ item }">
            <v-chip size="small" variant="tonal" color="teal">
              {{ item.fact_ids?.length || 0 }} facts
            </v-chip>
          </template>

          <template #item.links="{ item }">
            <span class="text-caption">{{ linkedCount(item) || '' }}</span>
          </template>

          <template #item.created_at="{ item }">
            {{ formatDate(item.created_at) }}
          </template>

          <template #item.actions="{ item }">
            <v-btn icon size="small" variant="text" @click.stop="editTopic(item)">
              <v-icon>mdi-pencil</v-icon>
            </v-btn>
            <v-btn icon size="small" variant="text" color="error" @click.stop="deleteTopic(item.id)">
              <v-icon>mdi-delete</v-icon>
            </v-btn>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Topic Detail Dialog -->
    <v-dialog v-model="detailDialog" max-width="900" scrollable>
      <v-card v-if="currentTopic">
        <v-card-title class="d-flex align-center pa-4">
          <v-chip :color="statusColor(currentTopic.status)" size="small" class="mr-3">
            {{ currentTopic.status }}
          </v-chip>
          <span class="text-h6 flex-grow-1">{{ currentTopic.title }}</span>
          <v-spacer />
          <v-btn icon size="small" variant="text" @click="detailDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height: 65vh; overflow-y: auto;">
          <!-- Description -->
          <div v-if="currentTopic.description" class="mb-4 pa-3 rounded-lg" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);">
            {{ currentTopic.description }}
          </div>

          <!-- Metadata -->
          <div class="d-flex align-center ga-2 mb-4 flex-wrap">
            <v-chip v-if="currentTopic.agent_id" size="small" variant="tonal" color="blue">
              <v-icon start size="14">mdi-robot</v-icon>
              {{ agentName(currentTopic.agent_id) }}
            </v-chip>
            <v-chip v-else size="small" variant="tonal" color="grey">Global</v-chip>
            <v-chip v-for="tag in currentTopic.tags" :key="tag" size="small" variant="tonal" color="blue-grey">{{ tag }}</v-chip>
            <v-chip size="x-small" variant="tonal">{{ currentTopic.created_by }}</v-chip>
            <v-chip size="x-small" variant="tonal">{{ formatDate(currentTopic.created_at) }}</v-chip>
          </div>

          <v-divider class="mb-4" />

          <!-- Linked Entities -->
          <div v-if="currentTopic.linked_video_ids?.length || currentTopic.linked_idea_ids?.length" class="mb-4">
            <div class="text-subtitle-2 font-weight-bold mb-2">
              <v-icon size="18" class="mr-1">mdi-link-variant</v-icon>
              Linked Entities
            </div>
            <div class="d-flex flex-wrap ga-2">
              <v-chip v-for="vid in (currentTopic.linked_video_ids || [])" :key="'v-'+vid" size="small" variant="tonal" color="red" closable @click:close="unlinkFromTopic('video', vid)">
                <v-icon start size="14">mdi-video-outline</v-icon>
                Video
              </v-chip>
              <v-chip v-for="iid in (currentTopic.linked_idea_ids || [])" :key="'i-'+iid" size="small" variant="tonal" color="amber" closable @click:close="unlinkFromTopic('idea', iid)">
                <v-icon start size="14">mdi-lightbulb-on-outline</v-icon>
                Idea
              </v-chip>
            </div>
          </div>

          <!-- Connected Facts -->
          <div class="d-flex align-center mb-3">
            <div class="text-subtitle-1 font-weight-bold">
              <v-icon class="mr-1" size="20">mdi-check-decagram</v-icon>
              Connected Facts ({{ connectedFacts.length }})
            </div>
            <v-spacer />
            <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-link-plus" @click="openConnectFactDialog">
              Connect Fact
            </v-btn>
          </div>

          <div v-if="connectedFacts.length">
            <v-card v-for="f in connectedFacts" :key="f.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-start">
                <v-icon :color="f.type === 'fact' ? 'teal' : 'orange'" size="18" class="mr-2 mt-1">
                  {{ f.type === 'fact' ? 'mdi-check-decagram' : 'mdi-help-circle-outline' }}
                </v-icon>
                <div class="flex-grow-1">
                  <div class="text-body-2">{{ f.content }}</div>
                  <div class="d-flex ga-1 mt-1">
                    <v-chip :color="f.type === 'fact' ? 'teal' : 'orange'" size="x-small" variant="flat">{{ f.type }}</v-chip>
                    <v-chip v-if="f.agent_id" size="x-small" variant="tonal" color="blue">{{ agentName(f.agent_id) }}</v-chip>
                    <v-chip size="x-small" variant="tonal">conf: {{ (f.confidence * 100).toFixed(0) }}%</v-chip>
                  </div>
                </div>
                <v-btn icon size="x-small" variant="text" color="error" @click="disconnectFact(f.id)">
                  <v-icon>mdi-link-off</v-icon>
                  <v-tooltip activator="parent" location="top">Disconnect</v-tooltip>
                </v-btn>
              </div>
            </v-card>
          </div>
          <div v-else class="text-center text-grey pa-4">
            <v-icon size="40" class="mb-2">mdi-link-variant-off</v-icon>
            <div>No facts connected yet</div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Create/Edit Topic Dialog -->
    <v-dialog v-model="formDialog" max-width="600">
      <v-card>
        <v-card-title>{{ editingTopic ? 'Edit Topic' : 'New Analysis Topic' }}</v-card-title>
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
          <v-btn color="primary" :loading="saving" @click="saveTopic">{{ editingTopic ? 'Update' : 'Create' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">Delete Topic</v-card-title>
        <v-card-text>
          Are you sure you want to delete this topic? This action cannot be undone.
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
          <v-btn color="error" :disabled="deleteConfirmText !== 'DELETE'" @click="doDeleteTopic">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Connect Fact Dialog -->
    <v-dialog v-model="connectFactDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center">
          Connect Fact
          <v-spacer />
          <v-text-field
            v-model="factSearchQuery"
            density="compact"
            variant="outlined"
            placeholder="Search facts..."
            prepend-inner-icon="mdi-magnify"
            hide-details
            clearable
            style="max-width: 260px;"
            @update:model-value="debouncedLoadAvailableFacts"
          />
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height: 50vh; overflow-y: auto;">
          <div v-if="availableFactsLoading" class="text-center pa-4">
            <v-progress-circular indeterminate size="24" />
          </div>
          <div v-else-if="availableFacts.length">
            <v-card
              v-for="f in availableFacts"
              :key="f.id"
              variant="outlined"
              class="mb-2 pa-3"
              :class="{ 'border-opacity-50': isFactConnected(f.id) }"
              @click="connectFact(f.id)"
              style="cursor: pointer;"
            >
              <div class="d-flex align-center">
                <v-icon :color="f.type === 'fact' ? 'teal' : 'orange'" size="18" class="mr-2">
                  {{ f.type === 'fact' ? 'mdi-check-decagram' : 'mdi-help-circle-outline' }}
                </v-icon>
                <div class="flex-grow-1">
                  <div class="text-body-2">{{ f.content }}</div>
                  <div class="d-flex ga-1 mt-1">
                    <v-chip v-if="f.agent_id" size="x-small" variant="tonal" color="blue">{{ agentName(f.agent_id) }}</v-chip>
                    <v-chip size="x-small" variant="tonal">{{ f.source }}</v-chip>
                  </div>
                </div>
                <v-icon v-if="isFactConnected(f.id)" color="success" size="20">mdi-check-circle</v-icon>
                <v-icon v-else color="grey" size="20">mdi-link-plus</v-icon>
              </div>
            </v-card>
          </div>
          <div v-else class="text-center text-grey pa-4">No facts found</div>
        </v-card-text>
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
const topics = ref([])
const loading = ref(false)
const errorMsg = ref(null)
const filterStatus = ref('')
const searchQuery = ref('')

const detailDialog = ref(false)
const currentTopic = ref(null)
const connectedFacts = ref([])

const formDialog = ref(false)
const editingTopic = ref(null)
const saving = ref(false)
const formData = ref({ title: '', description: '', status: 'active', agent_id: null, category: '', tags: [] })
const filterCategory = ref(null)
const selectedItems = ref([])

const connectFactDialog = ref(false)
const availableFacts = ref([])
const availableFactsLoading = ref(false)
const factSearchQuery = ref('')

const deleteDialog = ref(false)
const deleteTopicId = ref(null)
const deleteConfirmText = ref('')

const agents = ref([])

const statuses = [
  { value: 'draft', label: 'Draft', color: 'grey', icon: 'mdi-pencil-outline' },
  { value: 'active', label: 'Active', color: 'blue', icon: 'mdi-play-circle-outline' },
  { value: 'completed', label: 'Completed', color: 'success', icon: 'mdi-check-circle-outline' },
  { value: 'archived', label: 'Archived', color: 'brown', icon: 'mdi-archive-outline' },
]

const headers = [
  { title: 'Status', key: 'status', width: 120 },
  { title: 'Title', key: 'title' },
  { title: 'Agent', key: 'agent_id', width: 150 },
  { title: 'Category', key: 'category', width: 140 },
  { title: 'Facts', key: 'fact_ids', width: 100 },
  { title: 'Links', key: 'links', width: 80, sortable: false },
  { title: 'Created', key: 'created_at', width: 140 },
  { title: 'Actions', key: 'actions', sortable: false, width: 100 },
]

const agentOptions = computed(() => agents.value)

const categoryOptions = computed(() => {
  const cats = [...new Set(topics.value.map(t => t.category).filter(Boolean))]
  return cats.sort()
})

const groupedTopics = computed(() => {
  const groups = {}
  for (const t of topics.value) {
    const cat = t.category || ''
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(t)
  }
  return Object.entries(groups)
    .sort(([a], [b]) => { if (!a) return 1; if (!b) return -1; return a.localeCompare(b) })
    .map(([cat, items]) => ({ category: cat, items }))
})

onMounted(async () => {
  await Promise.all([loadTopics(), loadAgents()])
})

async function loadAgents() {
  try {
    await agentsStore.fetchAgents()
    agents.value = agentsStore.agents
  } catch (e) {
    console.error('Failed to load agents:', e)
  }
}

async function loadTopics() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (filterStatus.value) params.status = filterStatus.value
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await api.get('/analysis-topics', { params })
    topics.value = data.items || []
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to load topics'
  } finally {
    loading.value = false
  }
}

let _debounce = null
function debouncedLoad() {
  clearTimeout(_debounce)
  _debounce = setTimeout(() => loadTopics(), 400)
}

function openCreateDialog() {
  editingTopic.value = null
  formData.value = { title: '', description: '', status: 'active', agent_id: null, category: '', tags: [] }
  formDialog.value = true
}

function editTopic(item) {
  editingTopic.value = item
  formData.value = {
    title: item.title,
    description: item.description,
    status: item.status,
    agent_id: item.agent_id,
    category: item.category || '',
    tags: [...(item.tags || [])],
  }
  formDialog.value = true
}

async function saveTopic() {
  saving.value = true
  try {
    if (editingTopic.value) {
      await api.patch(`/analysis-topics/${editingTopic.value.id}`, {
        title: formData.value.title,
        description: formData.value.description,
        status: formData.value.status,
        category: formData.value.category || null,
        tags: formData.value.tags,
      })
      showSnackbar?.('Topic updated', 'success')
    } else {
      const payload = { ...formData.value }
      if (payload.agent_id) {
        await api.post(`/agents/${payload.agent_id}/analysis-topics`, payload)
      } else {
        await api.post('/analysis-topics', payload)
      }
      showSnackbar?.('Topic created', 'success')
    }
    formDialog.value = false
    await loadTopics()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to save topic'
  } finally {
    saving.value = false
  }
}

async function deleteTopic(id) {
  deleteTopicId.value = id
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

async function doDeleteTopic() {
  const id = deleteTopicId.value
  deleteDialog.value = false
  try {
    await api.delete(`/analysis-topics/${id}`)
    topics.value = topics.value.filter(t => t.id !== id)
    showSnackbar?.('Topic deleted', 'success')
  } catch (e) {
    showSnackbar?.('Failed to delete', 'error')
  }
}

async function openDetail(item) {
  currentTopic.value = item
  connectedFacts.value = []
  detailDialog.value = true
  await loadConnectedFacts(item.id)
}

async function loadConnectedFacts(topicId) {
  try {
    const { data } = await api.get(`/analysis-topics/${topicId}/facts`)
    connectedFacts.value = data.items || []
  } catch (e) {
    console.error('Failed to load connected facts:', e)
  }
}

function openConnectFactDialog() {
  factSearchQuery.value = ''
  availableFacts.value = []
  connectFactDialog.value = true
  loadAvailableFacts()
}

async function loadAvailableFacts() {
  availableFactsLoading.value = true
  try {
    const params = { limit: 100 }
    if (factSearchQuery.value) params.search = factSearchQuery.value
    const { data } = await api.get('/facts', { params })
    availableFacts.value = data.items || []
  } catch (e) {
    console.error('Failed to load facts:', e)
  } finally {
    availableFactsLoading.value = false
  }
}

let _factDebounce = null
function debouncedLoadAvailableFacts() {
  clearTimeout(_factDebounce)
  _factDebounce = setTimeout(() => loadAvailableFacts(), 400)
}

function isFactConnected(factId) {
  return currentTopic.value?.fact_ids?.includes(factId)
}

async function connectFact(factId) {
  if (isFactConnected(factId)) return
  try {
    const { data } = await api.post(`/analysis-topics/${currentTopic.value.id}/facts/${factId}`)
    currentTopic.value = data
    await loadConnectedFacts(currentTopic.value.id)
    showSnackbar?.('Fact connected', 'success')
  } catch (e) {
    showSnackbar?.('Failed to connect fact', 'error')
  }
}

async function disconnectFact(factId) {
  try {
    const { data } = await api.delete(`/analysis-topics/${currentTopic.value.id}/facts/${factId}`)
    currentTopic.value = data
    await loadConnectedFacts(currentTopic.value.id)
    showSnackbar?.('Fact disconnected', 'success')
  } catch (e) {
    showSnackbar?.('Failed to disconnect fact', 'error')
  }
}

function agentName(agentId) {
  const a = agents.value.find(a => a.id === agentId)
  return a?.name || agentId?.substring(0, 8)
}

function statusColor(s) {
  return { draft: 'grey', active: 'blue', completed: 'success', archived: 'brown' }[s] || 'grey'
}

function linkedCount(item) {
  return (item.linked_video_ids?.length || 0) + (item.linked_idea_ids?.length || 0)
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function discussSelected() {
  if (!selectedItems.value.length) return
  try {
    const lines = selectedItems.value.map(t => {
      const desc = t.description ? `\n${t.description.substring(0, 300)}` : ''
      return `### ${t.title}${desc}`
    }).join('\n\n')
    const session = await chatStore.createSession({ title: `Discuss ${selectedItems.value.length} analysis topic(s)` })
    chatStore.openPanel()
    await chatStore.sendMessage(`Please analyze and discuss these topics:\n\n${lines}`)
    selectedItems.value = []
    showSnackbar?.('Chat session created', 'success')
  } catch (e) {
    showSnackbar?.('Failed to create discussion', 'error')
  }
}

async function unlinkFromTopic(targetType, targetId) {
  if (!currentTopic.value?.id) return
  try {
    const { data } = await api.post(`/analysis-topics/${currentTopic.value.id}/unlink`, {
      target_type: targetType,
      target_id: targetId,
    })
    currentTopic.value = data
    showSnackbar?.('Unlinked', 'success')
  } catch (e) {
    showSnackbar?.('Failed to unlink', 'error')
  }
}
</script>
