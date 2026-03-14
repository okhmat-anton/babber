<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Events</div>
      <v-spacer />
      <v-btn color="deep-purple" prepend-icon="mdi-plus" @click="openCreateDialog">
        Add Event
      </v-btn>
    </div>

    <!-- Error alert -->
    <v-alert v-if="errorMsg" type="error" closable class="mb-4" @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <!-- Filters -->
    <div class="d-flex align-center ga-3 mb-4 flex-wrap">
      <v-btn-toggle v-model="filterType" density="compact" variant="outlined" mandatory @update:model-value="loadEvents">
        <v-btn value="all" size="small">All</v-btn>
        <v-btn value="conversation" size="small">Conversations</v-btn>
        <v-btn value="observation" size="small">Observations</v-btn>
        <v-btn value="discovery" size="small">Discoveries</v-btn>
        <v-btn value="decision" size="small">Decisions</v-btn>
        <v-btn value="milestone" size="small">Milestones</v-btn>
      </v-btn-toggle>
      <v-spacer />
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
        @update:model-value="loadEvents"
      />
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="outlined"
        placeholder="Search events..."
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        style="max-width: 280px;"
        @update:model-value="debouncedLoad"
      />
    </div>

    <!-- Tag filter -->
    <div v-if="allTags.length" class="d-flex align-center ga-1 mb-3 flex-wrap">
      <v-icon size="18" class="mr-1 text-grey">mdi-tag-multiple</v-icon>
      <v-chip
        v-for="tag in allTags" :key="tag"
        :color="selectedTags.includes(tag) ? 'cyan' : 'default'"
        :variant="selectedTags.includes(tag) ? 'flat' : 'outlined'"
        size="small" @click="toggleTag(tag)"
      >{{ tag }}</v-chip>
      <v-btn v-if="selectedTags.length" variant="text" size="x-small" color="grey" @click="selectedTags = []">Clear</v-btn>
    </div>

    <!-- Events grouped by type -->
    <div v-if="filterType === 'all' && groupedEvents.length > 1">
      <div v-for="group in groupedEvents" :key="group.event_type" class="mb-6">
        <div class="text-subtitle-1 font-weight-bold mb-2 d-flex align-center">
          <v-icon size="18" class="mr-2" :color="eventTypeColor(group.event_type)">{{ eventTypeIcon(group.event_type) }}</v-icon>
          {{ group.event_type }}
          <v-chip size="x-small" variant="tonal" class="ml-2">{{ group.items.length }}</v-chip>
        </div>
        <draggable
          :list="group.items"
          item-key="id"
          handle=".drag-handle"
          animation="200"
          ghost-class="drag-ghost"
          @end="onDragEnd(group.event_type)"
        >
          <template #item="{ element: event }">
            <v-card variant="outlined" class="mb-1">
              <v-card-text class="pa-2 d-flex align-center ga-2">
                <div class="drag-handle">
                  <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
                </div>
                <v-chip :color="eventTypeColor(event.event_type)" size="small" variant="tonal">
                  <v-icon start size="14">{{ eventTypeIcon(event.event_type) }}</v-icon>
                  {{ event.event_type }}
                </v-chip>
                <div class="flex-grow-1" style="min-width: 0;">
                  <span class="font-weight-medium">{{ event.title }}</span>
                  <div v-if="event.description" class="text-caption text-grey text-truncate" style="max-width: 350px;">{{ event.description }}</div>
                </div>
                <div v-if="event.tags && event.tags.length" class="d-flex ga-1 flex-wrap">
                  <v-chip v-for="t in event.tags" :key="t" size="x-small" variant="tonal" color="cyan">{{ t }}</v-chip>
                </div>
                <v-chip size="x-small" variant="tonal" color="blue">{{ agentName(event.agent_id) }}</v-chip>
                <v-chip :color="importanceColor(event.importance)" size="x-small" variant="flat">{{ event.importance }}</v-chip>
                <span class="text-caption text-grey">{{ formatDate(event.event_date) }}</span>
                <v-btn icon size="small" variant="text" @click.stop="editEvent(event)"><v-icon>mdi-pencil</v-icon></v-btn>
                <v-btn icon size="small" variant="text" color="error" @click.stop="deleteEvent(event.id)"><v-icon>mdi-delete</v-icon></v-btn>
              </v-card-text>
            </v-card>
          </template>
        </draggable>
      </div>
    </div>

    <!-- Flat list -->
    <div v-else>
      <draggable
        :list="tagFilteredEvents"
        item-key="id"
        handle=".drag-handle"
        animation="200"
        ghost-class="drag-ghost"
        @end="onDragEndFlat"
      >
        <template #item="{ element: event }">
          <v-card variant="outlined" class="mb-1">
            <v-card-text class="pa-2 d-flex align-center ga-2">
              <div class="drag-handle">
                <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
              </div>
              <v-chip :color="eventTypeColor(event.event_type)" size="small" variant="tonal">
                <v-icon start size="14">{{ eventTypeIcon(event.event_type) }}</v-icon>
                {{ event.event_type }}
              </v-chip>
              <div class="flex-grow-1" style="min-width: 0;">
                <span class="font-weight-medium">{{ event.title }}</span>
                <div v-if="event.description" class="text-caption text-grey text-truncate" style="max-width: 350px;">{{ event.description }}</div>
              </div>
              <div v-if="event.tags && event.tags.length" class="d-flex ga-1 flex-wrap">
                <v-chip v-for="t in event.tags" :key="t" size="x-small" variant="tonal" color="cyan">{{ t }}</v-chip>
              </div>
              <v-chip size="x-small" variant="tonal" color="blue">{{ agentName(event.agent_id) }}</v-chip>
              <v-chip :color="importanceColor(event.importance)" size="x-small" variant="flat">{{ event.importance }}</v-chip>
              <span class="text-caption text-grey">{{ formatDate(event.event_date) }}</span>
              <v-btn icon size="small" variant="text" @click.stop="editEvent(event)"><v-icon>mdi-pencil</v-icon></v-btn>
              <v-btn icon size="small" variant="text" color="error" @click.stop="deleteEvent(event.id)"><v-icon>mdi-delete</v-icon></v-btn>
            </v-card-text>
          </v-card>
        </template>
      </draggable>
    </div>

    <!-- Create/Edit Event Dialog -->
    <v-dialog v-model="formDialog" max-width="600">
      <v-card>
        <v-card-title>{{ editingEvent ? 'Edit Event' : 'New Event' }}</v-card-title>
        <v-card-text>
          <v-select
            v-model="formData.agent_id"
            :items="agentOptions"
            item-title="name"
            item-value="id"
            label="Agent"
            variant="outlined"
            density="compact"
            class="mb-3"
            prepend-inner-icon="mdi-robot"
            :disabled="!!editingEvent"
          />
          <v-text-field
            v-model="formData.title"
            label="Title"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="formData.event_type"
            :items="eventTypes"
            label="Event Type"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-textarea
            v-model="formData.description"
            label="Description"
            variant="outlined"
            density="compact"
            rows="3"
            class="mb-3"
          />
          <v-textarea
            v-model="formData.comment"
            label="Comment / Outcome"
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-3"
          />
          <v-select
            v-model="formData.importance"
            :items="importanceLevels"
            label="Importance"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-text-field
            v-model="formData.source"
            label="Source"
            variant="outlined"
            density="compact"
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
          <v-btn color="deep-purple" :loading="saving" @click="saveEvent">{{ editingEvent ? 'Update' : 'Create' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject, watch } from 'vue'
import draggable from 'vuedraggable'
import api from '../api'
import { useAgentsStore } from '../stores/agents'

const showSnackbar = inject('showSnackbar')
const dataRefreshSignal = inject('dataRefreshSignal', reactive({ type: '', timestamp: 0 }))
watch(() => dataRefreshSignal.timestamp, () => {
  if (dataRefreshSignal.type === 'events') loadEvents()
})
const agentsStore = useAgentsStore()

// State
const events = ref([])
const loading = ref(false)
const errorMsg = ref(null)
const filterType = ref('all')
const filterAgent = ref(null)
const searchQuery = ref('')

const formDialog = ref(false)
const editingEvent = ref(null)
const saving = ref(false)
const formData = ref({
  agent_id: null, title: '', event_type: 'observation',
  description: '', comment: '', source: 'user',
  importance: 'medium', tags: [],
})

const agents = ref([])
const agentOptions = computed(() => agents.value)

const eventTypes = ['conversation', 'observation', 'discovery', 'decision', 'milestone', 'custom']
const importanceLevels = ['low', 'medium', 'high', 'critical']

const selectedTags = ref([])

const headers = [
  { title: 'Type', key: 'event_type', width: 140 },
  { title: 'Title', key: 'title' },
  { title: 'Tags', key: 'tags', width: 160, sortable: false },
  { title: 'Agent', key: 'agent_id', width: 150 },
  { title: 'Importance', key: 'importance', width: 110 },
  { title: 'Date', key: 'event_date', width: 140 },
  { title: 'Actions', key: 'actions', sortable: false, width: 100 },
]

const allTags = computed(() => {
  const tags = new Set()
  events.value.forEach(i => (i.tags || []).forEach(t => tags.add(t)))
  return [...tags].sort()
})

const tagFilteredEvents = computed(() => {
  if (!selectedTags.value.length) return events.value
  return events.value.filter(i => (i.tags || []).some(t => selectedTags.value.includes(t)))
})

const groupedEvents = computed(() => {
  const groups = {}
  const source = tagFilteredEvents.value
  for (const e of source) {
    const type = e.event_type || 'custom'
    if (!groups[type]) groups[type] = []
    groups[type].push(e)
  }
  return Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([type, items]) => ({ event_type: type, items }))
})

function toggleTag(tag) {
  const idx = selectedTags.value.indexOf(tag)
  if (idx >= 0) selectedTags.value.splice(idx, 1)
  else selectedTags.value.push(tag)
}

onMounted(async () => {
  await Promise.all([loadEvents(), loadAgents()])
})

async function loadAgents() {
  try {
    await agentsStore.fetchAgents()
    agents.value = agentsStore.agents
    if (agents.value.length && !formData.value.agent_id) {
      formData.value.agent_id = agents.value[0].id
    }
  } catch (e) {
    console.error('Failed to load agents:', e)
  }
}

async function loadEvents() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (filterType.value && filterType.value !== 'all') params.event_type = filterType.value
    if (filterAgent.value) params.agent_id = filterAgent.value
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await api.get('/events', { params })
    events.value = data.items || []
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to load events'
  } finally {
    loading.value = false
  }
}

let _debounce = null
function debouncedLoad() {
  clearTimeout(_debounce)
  _debounce = setTimeout(() => loadEvents(), 400)
}

function openCreateDialog() {
  editingEvent.value = null
  formData.value = {
    agent_id: agents.value.length ? agents.value[0].id : null,
    title: '', event_type: 'observation',
    description: '', comment: '', source: 'user',
    importance: 'medium', tags: [],
  }
  formDialog.value = true
}

function editEvent(item) {
  editingEvent.value = item
  formData.value = {
    agent_id: item.agent_id,
    title: item.title,
    event_type: item.event_type,
    description: item.description,
    comment: item.comment || '',
    source: item.source,
    importance: item.importance,
    tags: [...(item.tags || [])],
  }
  formDialog.value = true
}

async function saveEvent() {
  saving.value = true
  try {
    if (editingEvent.value) {
      await api.patch(`/events/${editingEvent.value.id}`, {
        title: formData.value.title,
        event_type: formData.value.event_type,
        description: formData.value.description,
        comment: formData.value.comment,
        source: formData.value.source,
        importance: formData.value.importance,
        tags: formData.value.tags,
      })
      showSnackbar?.('Event updated', 'success')
    } else {
      if (!formData.value.agent_id) {
        errorMsg.value = 'Please select an agent'
        saving.value = false
        return
      }
      await api.post('/events', formData.value)
      showSnackbar?.('Event created', 'success')
    }
    formDialog.value = false
    await loadEvents()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to save event'
  } finally {
    saving.value = false
  }
}

async function deleteEvent(id) {
  try {
    await api.delete(`/events/${id}`)
    events.value = events.value.filter(e => e.id !== id)
    showSnackbar?.('Event deleted', 'success')
  } catch (e) {
    showSnackbar?.('Failed to delete', 'error')
  }
}

function agentName(agentId) {
  const a = agents.value.find(a => a.id === agentId)
  return a?.name || agentId?.substring(0, 8)
}

function eventTypeColor(t) {
  return { conversation: 'blue', observation: 'teal', discovery: 'amber', decision: 'orange', milestone: 'green', custom: 'grey' }[t] || 'grey'
}

function eventTypeIcon(t) {
  return {
    conversation: 'mdi-chat-outline',
    observation: 'mdi-eye-outline',
    discovery: 'mdi-lightbulb-on-outline',
    decision: 'mdi-gavel',
    milestone: 'mdi-flag-variant',
    custom: 'mdi-tag-outline',
  }[t] || 'mdi-calendar'
}

function importanceColor(i) {
  return { low: 'grey', medium: 'blue', high: 'orange', critical: 'red' }[i] || 'grey'
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function onDragEnd(eventType) {
  const group = groupedEvents.value.find(g => g.event_type === eventType)
  if (!group) return
  const ids = group.items.map(e => e.id)
  try {
    await api.post('/events/reorder', { ids })
    await loadEvents()
  } catch (e) {
    showSnackbar?.('Failed to reorder', 'error')
  }
}

async function onDragEndFlat() {
  const items = tagFilteredEvents.value
  const ids = items.map(e => e.id)
  try {
    await api.post('/events/reorder', { ids })
    await loadEvents()
  } catch (e) {
    showSnackbar?.('Failed to reorder', 'error')
  }
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
