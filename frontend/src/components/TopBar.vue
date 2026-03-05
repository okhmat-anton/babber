<template>
  <v-system-bar
    class="top-bar px-4"
    height="36"
    color="grey-darken-4"
    window
  >
    <!-- Ollama Status -->
    <div class="d-flex align-center mr-4">
      <v-icon
        :color="ollama.running ? 'success' : 'error'"
        size="14"
        class="mr-1"
      >{{ ollama.running ? 'mdi-circle' : 'mdi-circle-outline' }}</v-icon>
      <span class="text-caption font-weight-medium mr-2">Ollama</span>
      <v-btn
        v-if="!ollama.running"
        size="x-small"
        variant="tonal"
        color="success"
        density="compact"
        :loading="ollamaStarting"
        @click="startOllama"
        class="mr-1"
        style="min-width: 0; padding: 0 6px; height: 22px;"
      >
        <v-icon size="12">mdi-play</v-icon>
      </v-btn>
      <v-btn
        v-else
        size="x-small"
        variant="tonal"
        color="error"
        density="compact"
        :loading="ollamaStopping"
        @click="stopOllama"
        class="mr-1"
        style="min-width: 0; padding: 0 6px; height: 22px;"
      >
        <v-icon size="12">mdi-stop</v-icon>
      </v-btn>
    </div>

    <v-divider vertical class="mx-2" />

    <!-- Model selector + load/unload -->
    <div class="d-flex align-center mr-4">
      <v-icon size="14" color="blue-grey-lighten-1" class="mr-1">mdi-cube-outline</v-icon>
      <v-select
        v-model="selectedModel"
        :items="modelItems"
        item-title="label"
        item-value="name"
        density="compact"
        variant="plain"
        hide-details
        :disabled="!ollama.running"
        class="top-bar-select mr-1"
        placeholder="Model..."
        :menu-props="{ maxHeight: 300 }"
      >
        <template #item="{ item, props: itemProps }">
          <v-list-item v-bind="itemProps">
            <template #prepend>
              <v-icon
                :color="isModelLoaded(item.raw.name) ? 'success' : 'grey'"
                size="12"
                class="mr-1"
              >{{ isModelLoaded(item.raw.name) ? 'mdi-circle' : 'mdi-circle-outline' }}</v-icon>
            </template>
            <template #append>
              <span class="text-caption text-grey ml-2">{{ item.raw.size_hr }}</span>
            </template>
          </v-list-item>
        </template>
        <template #selection="{ item }">
          <v-icon
            :color="isModelLoaded(item.raw.name) ? 'success' : 'grey'"
            size="10"
            class="mr-1"
          >{{ isModelLoaded(item.raw.name) ? 'mdi-circle' : 'mdi-circle-outline' }}</v-icon>
          <span class="text-caption">{{ item.raw.name }}</span>
        </template>
      </v-select>
      <v-btn
        v-if="selectedModel && !isModelLoaded(selectedModel)"
        size="x-small"
        variant="tonal"
        color="success"
        density="compact"
        :loading="modelLoading"
        :disabled="!ollama.running"
        @click="loadModel"
        style="min-width: 0; padding: 0 6px; height: 22px;"
        title="Load model into memory"
      >
        <v-icon size="12">mdi-play</v-icon>
      </v-btn>
      <v-btn
        v-else-if="selectedModel && isModelLoaded(selectedModel)"
        size="x-small"
        variant="tonal"
        color="warning"
        density="compact"
        :loading="modelUnloading"
        @click="unloadModel"
        style="min-width: 0; padding: 0 6px; height: 22px;"
        title="Unload model from memory"
      >
        <v-icon size="12">mdi-eject</v-icon>
      </v-btn>
    </div>

    <v-divider vertical class="mx-2" />

    <!-- Running models count -->
    <div class="d-flex align-center mr-4" v-if="runningModels.length">
      <v-icon size="14" color="success" class="mr-1">mdi-lightning-bolt</v-icon>
      <span class="text-caption">{{ runningModels.length }} loaded</span>
    </div>

    <v-divider vertical class="mx-2" v-if="runningModels.length" />

    <!-- Running agents -->
    <div class="d-flex align-center">
      <v-icon size="14" color="blue" class="mr-1">mdi-robot</v-icon>
      <span class="text-caption">
        {{ runningAgentsCount }} agent{{ runningAgentsCount !== 1 ? 's' : '' }} running
      </span>
    </div>

    <v-spacer />

    <!-- Refresh -->
    <v-btn
      size="x-small"
      variant="text"
      density="compact"
      :loading="refreshingAll"
      @click="refreshAll"
      style="min-width: 0; padding: 0 4px; height: 22px;"
      title="Refresh status"
    >
      <v-icon size="14">mdi-refresh</v-icon>
    </v-btn>
  </v-system-bar>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import api from '../api'
import { useAgentsStore } from '../stores/agents'

const agentsStore = useAgentsStore()

// State
const ollama = ref({ running: false, base_url: '', models_count: 0 })
const models = ref([])
const runningModels = ref([])
const selectedModel = ref(null)

// Flags
const ollamaStarting = ref(false)
const ollamaStopping = ref(false)
const modelLoading = ref(false)
const modelUnloading = ref(false)
const refreshingAll = ref(false)

// Computed
const runningAgentsCount = computed(() => {
  return agentsStore.agents.filter(a => a.status === 'running').length
})

const modelItems = computed(() => {
  return models.value.map(m => ({
    name: m.name,
    label: m.name,
    size_hr: m.size_hr || '',
  }))
})

const isModelLoaded = (name) => {
  return runningModels.value.some(m => m.name === name)
}

// Methods
const fetchOllamaStatus = async () => {
  try {
    const { data } = await api.get('/ollama/status')
    ollama.value = data
  } catch {
    ollama.value = { running: false, base_url: '', models_count: 0 }
  }
}

const fetchModels = async () => {
  if (!ollama.value.running) { models.value = []; return }
  try {
    const { data } = await api.get('/ollama/models')
    models.value = data
  } catch { models.value = [] }
}

const fetchRunning = async () => {
  if (!ollama.value.running) { runningModels.value = []; return }
  try {
    const { data } = await api.get('/ollama/running')
    runningModels.value = data
  } catch { runningModels.value = [] }
}

const fetchAgents = async () => {
  try { await agentsStore.fetchAgents() } catch {}
}

const refreshAll = async () => {
  refreshingAll.value = true
  await fetchOllamaStatus()
  await Promise.all([fetchModels(), fetchRunning(), fetchAgents()])
  refreshingAll.value = false
}

const startOllama = async () => {
  ollamaStarting.value = true
  try {
    await api.post('/ollama/start')
    await fetchOllamaStatus()
    await Promise.all([fetchModels(), fetchRunning()])
  } catch {}
  ollamaStarting.value = false
}

const stopOllama = async () => {
  ollamaStopping.value = true
  try {
    await api.post('/ollama/stop')
    await fetchOllamaStatus()
    models.value = []
    runningModels.value = []
  } catch {}
  ollamaStopping.value = false
}

const loadModel = async () => {
  if (!selectedModel.value) return
  modelLoading.value = true
  try {
    await api.post(`/ollama/models/${encodeURIComponent(selectedModel.value)}/load`)
    await fetchRunning()
  } catch {}
  modelLoading.value = false
}

const unloadModel = async () => {
  if (!selectedModel.value) return
  modelUnloading.value = true
  try {
    await api.post(`/ollama/models/${encodeURIComponent(selectedModel.value)}/unload`)
    await fetchRunning()
  } catch {}
  modelUnloading.value = false
}

// Auto-refresh every 30s
let timer = null
onMounted(async () => {
  await refreshAll()
  // Auto-select first running model if any
  if (runningModels.value.length && !selectedModel.value) {
    selectedModel.value = runningModels.value[0].name
  } else if (models.value.length && !selectedModel.value) {
    selectedModel.value = models.value[0].name
  }
  timer = setInterval(refreshAll, 30000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.top-bar {
  border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  user-select: none;
}

.top-bar-select {
  max-width: 220px;
  min-width: 140px;
}

.top-bar-select :deep(.v-field__input) {
  font-size: 12px;
  padding: 0 4px;
  min-height: 22px;
}

.top-bar-select :deep(.v-field) {
  --v-field-padding-start: 4px;
  --v-field-padding-end: 4px;
}

.top-bar-select :deep(.v-input__details) {
  display: none;
}
</style>
