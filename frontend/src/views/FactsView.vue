<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Facts</div>
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
      <v-btn color="teal" prepend-icon="mdi-plus" @click="openCreateDialog">
        Add Fact
      </v-btn>
    </div>

    <!-- Error alert -->
    <v-alert v-if="errorMsg" type="error" closable class="mb-4" @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <!-- Filters -->
    <div class="d-flex align-center ga-3 mb-4 flex-wrap">
      <v-btn-toggle v-model="filterType" density="compact" variant="outlined" mandatory @update:model-value="loadFacts">
        <v-btn value="all" size="small">All</v-btn>
        <v-btn value="fact" size="small">
          <v-icon size="16" class="mr-1">mdi-check-decagram</v-icon> Facts
        </v-btn>
        <v-btn value="hypothesis" size="small">
          <v-icon size="16" class="mr-1">mdi-help-circle-outline</v-icon> Hypotheses
        </v-btn>
      </v-btn-toggle>
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
        @update:model-value="loadFacts"
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
        @update:model-value="loadFacts"
      />
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="outlined"
        placeholder="Search facts..."
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        style="max-width: 280px;"
        @update:model-value="debouncedLoad"
      />
    </div>

    <!-- Facts grouped by category -->
    <div v-if="!filterCategory && groupedFacts.length > 1">
      <div v-for="group in groupedFacts" :key="group.category" class="mb-6">
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
              <template #item.type="{ item }">
                <v-chip :color="item.type === 'fact' ? 'teal' : 'orange'" size="small" variant="tonal">
                  <v-icon start size="14">{{ item.type === 'fact' ? 'mdi-check-decagram' : 'mdi-help-circle-outline' }}</v-icon>
                  {{ item.type }}
                </v-chip>
              </template>
              <template #item.content="{ item }">
                <div class="text-truncate" style="max-width: 500px;">{{ item.content }}</div>
              </template>
              <template #item.agent_id="{ item }">
                <v-chip v-if="isGlobalFact(item)" size="small" variant="tonal" color="teal">
                  <v-icon start size="14">mdi-earth</v-icon> Global
                </v-chip>
                <span v-else>
                  <v-chip v-for="aid in (item.agent_ids && item.agent_ids.length ? item.agent_ids : [item.agent_id])" :key="aid" size="small" variant="tonal" color="blue" class="mr-1">{{ agentName(aid) }}</v-chip>
                </span>
              </template>
              <template #item.category="{ item }">
                <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
              </template>
              <template #item.links="{ item }">
                <span class="text-caption">{{ linkedCount(item) || '' }}</span>
              </template>
              <template #item.verified="{ item }">
                <v-icon v-if="item.verified" color="green" size="20">mdi-check-circle</v-icon>
                <v-icon v-else color="grey" size="20">mdi-minus-circle-outline</v-icon>
              </template>
              <template #item.confidence="{ item }">
                <v-chip size="small" variant="tonal">{{ (item.confidence * 100).toFixed(0) }}%</v-chip>
              </template>
              <template #item.created_at="{ item }">{{ formatDate(item.created_at) }}</template>
              <template #item.actions="{ item }">
                <v-btn v-if="item.type === 'hypothesis' && !item.verified" icon size="small" variant="text" color="green" @click.stop="verifyFact(item)"><v-icon>mdi-check-circle</v-icon></v-btn>
                <v-btn icon size="small" variant="text" @click.stop="editFact(item)"><v-icon>mdi-pencil</v-icon></v-btn>
                <v-btn icon size="small" variant="text" color="error" @click.stop="deleteFact(item.id)"><v-icon>mdi-delete</v-icon></v-btn>
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
          :items="facts"
          :loading="loading"
          show-select
          return-object
          hover
        >
          <template #item.type="{ item }">
            <v-chip :color="item.type === 'fact' ? 'teal' : 'orange'" size="small" variant="tonal">
              <v-icon start size="14">{{ item.type === 'fact' ? 'mdi-check-decagram' : 'mdi-help-circle-outline' }}</v-icon>
              {{ item.type }}
            </v-chip>
          </template>

          <template #item.content="{ item }">
            <div class="text-truncate" style="max-width: 500px;">{{ item.content }}</div>
          </template>

          <template #item.agent_id="{ item }">
            <v-chip v-if="isGlobalFact(item)" size="small" variant="tonal" color="teal">
              <v-icon start size="14">mdi-earth</v-icon> Global
            </v-chip>
            <span v-else>
              <v-chip v-for="aid in (item.agent_ids && item.agent_ids.length ? item.agent_ids : [item.agent_id])" :key="aid" size="small" variant="tonal" color="blue" class="mr-1">{{ agentName(aid) }}</v-chip>
            </span>
          </template>

          <template #item.category="{ item }">
            <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
          </template>

          <template #item.links="{ item }">
            <span class="text-caption">{{ linkedCount(item) || '' }}</span>
          </template>

          <template #item.verified="{ item }">
            <v-icon v-if="item.verified" color="green" size="20">mdi-check-circle</v-icon>
            <v-icon v-else color="grey" size="20">mdi-minus-circle-outline</v-icon>
          </template>

          <template #item.confidence="{ item }">
            <v-chip size="small" variant="tonal">{{ (item.confidence * 100).toFixed(0) }}%</v-chip>
          </template>

          <template #item.created_at="{ item }">
            {{ formatDate(item.created_at) }}
          </template>

          <template #item.actions="{ item }">
            <v-btn
              v-if="item.type === 'hypothesis' && !item.verified"
              icon size="small" variant="text" color="green"
              @click.stop="verifyFact(item)"
            >
              <v-icon>mdi-check-circle</v-icon>
              <v-tooltip activator="parent" location="top">Verify</v-tooltip>
            </v-btn>
            <v-btn icon size="small" variant="text" @click.stop="editFact(item)">
              <v-icon>mdi-pencil</v-icon>
            </v-btn>
            <v-btn icon size="small" variant="text" color="error" @click.stop="deleteFact(item.id)">
              <v-icon>mdi-delete</v-icon>
            </v-btn>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">Delete Fact</v-card-title>
        <v-card-text>
          Are you sure you want to delete this fact? This action cannot be undone.
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
          <v-btn color="error" :disabled="deleteConfirmText !== 'DELETE'" @click="doDeleteFact">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Create/Edit Fact Dialog -->
    <v-dialog v-model="formDialog" max-width="600">
      <v-card>
        <v-card-title>{{ editingFact ? 'Edit Fact' : 'New Fact' }}</v-card-title>
        <v-card-text>
          <!-- Global toggle -->
          <v-switch
            v-model="formGlobal"
            label="Global (all agents)"
            color="teal"
            density="compact"
            class="mb-2"
            :disabled="!!editingFact"
            hide-details
          />
          <!-- Multi-agent selector (hidden when global) -->
          <v-select
            v-if="!formGlobal"
            v-model="formData.agent_ids"
            :items="agentOptions"
            item-title="name"
            item-value="id"
            label="Agents"
            variant="outlined"
            density="compact"
            class="mb-3"
            prepend-inner-icon="mdi-robot"
            multiple
            chips
            closable-chips
            :disabled="!!editingFact"
          />
          <v-select
            v-model="formData.type"
            :items="['fact', 'hypothesis']"
            label="Type"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-textarea
            v-model="formData.content"
            label="Content"
            variant="outlined"
            density="compact"
            rows="4"
            class="mb-3"
          />
          <v-text-field
            v-model="formData.source"
            label="Source"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-slider
            v-model="formData.confidence"
            label="Confidence"
            min="0"
            max="1"
            step="0.05"
            thumb-label
            class="mb-3"
          />
          <v-checkbox
            v-model="formData.verified"
            label="Verified"
            density="compact"
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
          <v-btn color="teal" :loading="saving" @click="saveFact">{{ editingFact ? 'Update' : 'Create' }}</v-btn>
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
const facts = ref([])
const loading = ref(false)
const errorMsg = ref(null)
const filterType = ref('all')
const filterAgent = ref(null)
const filterCategory = ref(null)
const searchQuery = ref('')

const formDialog = ref(false)
const editingFact = ref(null)
const saving = ref(false)
const formGlobal = ref(true)
const formData = ref({
  agent_ids: [], type: 'fact', content: '', source: 'user',
  verified: false, confidence: 0.8, category: '', tags: [],
})

const deleteDialog = ref(false)
const deleteFactId = ref(null)
const deleteConfirmText = ref('')
const selectedItems = ref([])

const agents = ref([])
const agentOptions = computed(() => agents.value)

const categoryOptions = computed(() => {
  const cats = [...new Set(facts.value.map(f => f.category).filter(Boolean))]
  return cats.sort()
})

const groupedFacts = computed(() => {
  const groups = {}
  for (const f of facts.value) {
    const cat = f.category || ''
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(f)
  }
  return Object.entries(groups)
    .sort(([a], [b]) => { if (!a) return 1; if (!b) return -1; return a.localeCompare(b) })
    .map(([cat, items]) => ({ category: cat, items }))
})

const headers = [
  { title: 'Type', key: 'type', width: 130 },
  { title: 'Content', key: 'content' },
  { title: 'Agent', key: 'agent_id', width: 200 },
  { title: 'Category', key: 'category', width: 140 },
  { title: 'Links', key: 'links', width: 80, sortable: false },
  { title: 'Verified', key: 'verified', width: 90 },
  { title: 'Confidence', key: 'confidence', width: 110 },
  { title: 'Created', key: 'created_at', width: 140 },
  { title: 'Actions', key: 'actions', sortable: false, width: 140 },
]

onMounted(async () => {
  await Promise.all([loadFacts(), loadAgents()])
})

async function loadAgents() {
  try {
    await agentsStore.fetchAgents()
    agents.value = agentsStore.agents
  } catch (e) {
    console.error('Failed to load agents:', e)
  }
}

async function loadFacts() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (filterType.value && filterType.value !== 'all') params.type = filterType.value
    if (filterAgent.value) params.agent_id = filterAgent.value
    if (filterCategory.value) params.category = filterCategory.value
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await api.get('/facts', { params })
    facts.value = data.items || []
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to load facts'
  } finally {
    loading.value = false
  }
}

let _debounce = null
function debouncedLoad() {
  clearTimeout(_debounce)
  _debounce = setTimeout(() => loadFacts(), 400)
}

function openCreateDialog() {
  editingFact.value = null
  formGlobal.value = true
  formData.value = {
    agent_ids: [],
    type: 'fact', content: '', source: 'user',
    verified: false, confidence: 0.8, category: '', tags: [],
  }
  formDialog.value = true
}

function editFact(item) {
  editingFact.value = item
  const agentIds = item.agent_ids || []
  formGlobal.value = isGlobalFact(item)
  formData.value = {
    agent_ids: [...agentIds],
    type: item.type,
    content: item.content,
    source: item.source,
    verified: item.verified,
    confidence: item.confidence,
    category: item.category || '',
    tags: [...(item.tags || [])],
  }
  formDialog.value = true
}

async function saveFact() {
  saving.value = true
  try {
    if (editingFact.value) {
      await api.patch(`/facts/${editingFact.value.id}`, {
        type: formData.value.type,
        content: formData.value.content,
        source: formData.value.source,
        verified: formData.value.verified,
        confidence: formData.value.confidence,
        category: formData.value.category || null,
        tags: formData.value.tags,
        agent_ids: formGlobal.value ? [] : formData.value.agent_ids,
      })
      showSnackbar?.('Fact updated', 'success')
    } else {
      const payload = {
        ...formData.value,
        agent_ids: formGlobal.value ? [] : formData.value.agent_ids,
      }
      if (!formGlobal.value && (!payload.agent_ids || !payload.agent_ids.length)) {
        errorMsg.value = 'Please select at least one agent or set as Global'
        saving.value = false
        return
      }
      await api.post('/facts', payload)
      showSnackbar?.('Fact created', 'success')
    }
    formDialog.value = false
    await loadFacts()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to save fact'
  } finally {
    saving.value = false
  }
}

async function verifyFact(item) {
  try {
    await api.patch(`/facts/${item.id}`, { verified: true, type: 'fact' })
    showSnackbar?.('Fact verified', 'success')
    await loadFacts()
  } catch (e) {
    showSnackbar?.('Failed to verify', 'error')
  }
}

async function deleteFact(id) {
  deleteFactId.value = id
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

async function doDeleteFact() {
  const id = deleteFactId.value
  deleteDialog.value = false
  try {
    await api.delete(`/facts/${id}`)
    facts.value = facts.value.filter(f => f.id !== id)
    showSnackbar?.('Fact deleted', 'success')
  } catch (e) {
    showSnackbar?.('Failed to delete', 'error')
  }
}

function agentName(agentId) {
  const a = agents.value.find(a => a.id === agentId)
  return a?.name || agentId?.substring(0, 8)
}

function isGlobalFact(item) {
  return (!item.agent_ids || item.agent_ids.length === 0) && item.agent_id === '__global__'
}

function linkedCount(item) {
  return (item.linked_video_ids?.length || 0) + (item.linked_analysis_ids?.length || 0) + (item.linked_idea_ids?.length || 0)
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function discussSelected() {
  if (!selectedItems.value.length) return
  try {
    const lines = selectedItems.value.map(f => {
      const label = f.type === 'hypothesis' ? 'Hypothesis' : 'Fact'
      return `### ${label}: ${f.content.substring(0, 300)}`
    }).join('\n\n')
    const session = await chatStore.createSession({ title: `Discuss ${selectedItems.value.length} fact(s)` })
    chatStore.openPanel()
    await chatStore.sendMessage(`Please analyze and discuss these facts:\n\n${lines}`)
    selectedItems.value = []
    showSnackbar?.('Chat session created', 'success')
  } catch (e) {
    showSnackbar?.('Failed to create discussion', 'error')
  }
}
</script>
