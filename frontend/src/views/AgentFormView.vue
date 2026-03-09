<template>
  <div>
    <div class="d-flex align-center mb-6">
      <v-btn icon="mdi-arrow-left" variant="text" @click="$router.back()" />
      <div class="text-h4 font-weight-bold ml-2">{{ isEdit ? 'Edit Agent' : 'New Agent' }}</div>
    </div>

    <v-card>
      <v-card-text>
        <v-form @submit.prevent="handleSubmit">
          <!-- Avatar Upload -->
          <div class="d-flex align-center mb-4">
            <div style="position: relative; cursor: pointer;" @click="triggerAvatarUpload">
              <v-avatar :size="72" :color="avatarPreview || (isEdit && form.avatar_url) ? undefined : 'primary'" variant="tonal">
                <v-img v-if="avatarPreview" :src="avatarPreview" cover />
                <v-img v-else-if="form.avatar_url" :src="form.avatar_url" cover />
                <v-icon v-else size="36">mdi-account</v-icon>
              </v-avatar>
              <v-btn
                icon="mdi-camera"
                size="x-small"
                color="primary"
                variant="flat"
                style="position: absolute; bottom: -2px; right: -2px;"
                @click.stop="triggerAvatarUpload"
              />
              <input
                ref="avatarInput"
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                style="display: none;"
                @change="handleAvatarChange"
              />
            </div>
            <div class="ml-4">
              <div class="text-body-2 text-grey">Agent Avatar</div>
              <div class="text-caption text-grey-darken-1">Photos will be resized. GIFs are kept as-is.</div>
              <v-btn v-if="avatarPreview || form.avatar_url" size="x-small" variant="text" color="error" class="mt-1" @click="removeAvatar">Remove</v-btn>
            </div>
          </div>

          <v-row>
            <v-col cols="12" md="6">
              <v-text-field v-model="form.name" label="Name" required />
            </v-col>
            <v-col cols="12" md="6">
              <v-textarea v-model="form.description" label="Description" rows="2" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="form.mission" label="My Core Mission" rows="3" hint="This is set by the user and cannot be changed by the agent" persistent-hint />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="form.system_prompt" label="System Prompt" rows="4" />
            </v-col>
            <v-col cols="12" md="4">
              <div class="d-flex align-center ga-2">
                <v-select
                  v-model="form.voice"
                  :items="voiceOptions"
                  label="TTS Voice"
                  clearable
                  density="compact"
                  hint="Voice for text-to-speech"
                  persistent-hint
                  prepend-inner-icon="mdi-account-voice"
                  style="flex: 1"
                />
                <v-btn
                  icon
                  size="small"
                  variant="text"
                  :disabled="!form.voice || voicePreviewing"
                  :loading="voicePreviewing"
                  @click="previewVoice(form.voice)"
                  title="Preview voice"
                >
                  <v-icon>mdi-play-circle-outline</v-icon>
                </v-btn>
              </div>
            </v-col>
          </v-row>

          <!-- ─── Thinking Protocols ─────────────────── -->
          <div class="text-h6 mt-6 mb-3">Thinking Protocols</div>
          <v-row>
            <v-col cols="12" md="6">
              <v-select
                v-model="form.protocol_ids"
                :items="protocolItems"
                item-title="name"
                item-value="id"
                label="Available Protocols"
                multiple
                chips
                closable-chips
                density="compact"
                hint="All protocols this agent can use"
                persistent-hint
              >
                <template #item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template #prepend>
                      <v-icon size="18" :color="item.raw.type === 'orchestrator' ? 'amber' : 'blue-grey'">
                        {{ item.raw.type === 'orchestrator' ? 'mdi-crown' : 'mdi-head-cog' }}
                      </v-icon>
                    </template>
                    <v-list-item-subtitle>
                      <v-chip size="x-small" :color="item.raw.type === 'orchestrator' ? 'amber' : 'blue-grey'" variant="tonal" class="mr-1">{{ item.raw.type || 'standard' }}</v-chip>
                      {{ item.raw.description || 'No description' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </template>
              </v-select>
            </v-col>
            <v-col cols="12" md="6">
              <v-select
                v-model="form.thinking_protocol_id"
                :items="mainProtocolItems"
                item-title="name"
                item-value="id"
                label="Main Protocol (Orchestrator)"
                clearable
                density="compact"
                hint="The main protocol that orchestrates others"
                persistent-hint
              >
                <template #item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template #prepend>
                      <v-icon size="18" :color="item.raw.type === 'orchestrator' ? 'amber' : 'blue-grey'">
                        {{ item.raw.type === 'orchestrator' ? 'mdi-crown' : 'mdi-head-cog' }}
                      </v-icon>
                    </template>
                    <v-list-item-subtitle>{{ item.raw.description || 'No description' }}</v-list-item-subtitle>
                  </v-list-item>
                </template>
              </v-select>
            </v-col>
          </v-row>
          <v-row v-if="selectedProtocolPreview">
            <v-col cols="12">
              <v-sheet class="pa-3 rounded bg-grey-darken-4">
                <div class="text-caption text-grey mb-1">
                  <v-icon size="14" class="mr-1">mdi-eye</v-icon>
                  Main: {{ selectedProtocolPreview.name }}
                </div>
                <div class="text-caption">{{ selectedProtocolPreview.steps?.length || 0 }} steps · {{ selectedProtocolPreview.steps?.filter(s => s.type === 'loop').length || 0 }} loops · {{ selectedProtocolPreview.steps?.filter(s => s.type === 'delegate').length || 0 }} delegates</div>
              </v-sheet>
            </v-col>
          </v-row>

          <!-- ─── Models ─────────────────────────────────── -->
          <div class="text-h6 mt-6 mb-3">Models</div>

          <v-card
            v-for="(entry, idx) in form.models"
            :key="idx"
            variant="outlined"
            class="mb-3 pa-3"
          >
            <v-row align="center" dense>
              <v-col cols="12" md="4">
                <v-select
                  v-model="entry.model_config_id"
                  :items="modelChoices"
                  item-title="title"
                  item-value="value"
                  label="Model"
                  density="compact"
                  hide-details
                  required
                >
                  <template #item="{ item, props }">
                    <v-list-item v-bind="props">
                      <template #prepend>
                        <v-icon size="18" :color="item.raw.isRole ? 'amber' : 'blue-grey'">
                          {{ item.raw.isRole ? 'mdi-tag-multiple' : 'mdi-cube-outline' }}
                        </v-icon>
                      </template>
                      <v-list-item-subtitle>{{ item.raw.subtitle }}</v-list-item-subtitle>
                    </v-list-item>
                  </template>
                </v-select>
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="entry.task_type"
                  label="Task Type"
                  density="compact"
                  hide-details
                  placeholder="e.g. code generation"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-combobox
                  v-model="entry.tags"
                  label="Tags"
                  density="compact"
                  hide-details
                  multiple
                  chips
                  closable-chips
                  small-chips
                  placeholder="Press Enter to add"
                />
              </v-col>
              <v-col cols="auto" md="1">
                <v-text-field
                  v-model.number="entry.priority"
                  label="Priority"
                  type="number"
                  density="compact"
                  hide-details
                  style="max-width: 80px"
                />
              </v-col>
              <v-col cols="auto">
                <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="removeModel(idx)" />
              </v-col>
            </v-row>
          </v-card>

          <v-btn
            variant="tonal"
            color="primary"
            prepend-icon="mdi-plus"
            size="small"
            @click="addModel"
          >
            Add Model
          </v-btn>

          <!-- ─── Generation Parameters ──────────────────── -->
          <v-expansion-panels class="mt-6">
            <v-expansion-panel title="Generation Parameters">
              <v-expansion-panel-text>
                <v-row>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.temperature" label="Temperature" type="number" step="0.1" min="0" max="2" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.top_p" label="Top P" type="number" step="0.05" min="0" max="1" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.top_k" label="Top K" type="number" min="1" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.max_tokens" label="Max Tokens" type="number" min="1" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.num_ctx" label="Context Window" type="number" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.repeat_penalty" label="Repeat Penalty" type="number" step="0.05" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.num_thread" label="CPU Threads" type="number" min="1" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model.number="form.num_gpu" label="GPU Layers" type="number" min="0" />
                  </v-col>
                </v-row>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>

          <div class="d-flex mt-6">
            <v-btn color="primary" type="submit" :loading="saving" size="large">
              {{ isEdit ? 'Update' : 'Create' }}
            </v-btn>
            <v-btn class="ml-3" variant="outlined" @click="$router.back()">Cancel</v-btn>
          </div>
        </v-form>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAgentsStore } from '../stores/agents'
import { useSettingsStore } from '../stores/settings'
import api from '../api'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const settingsStore = useSettingsStore()
const saving = ref(false)
const protocolsList = ref([])
const modelRoles = ref([])  // { role, label } from API

// Avatar state
const avatarInput = ref(null)
const avatarFile = ref(null)
const avatarPreview = ref(null)
const avatarRemoved = ref(false)

const triggerAvatarUpload = () => {
  avatarInput.value?.click()
}

const handleAvatarChange = (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  avatarFile.value = file
  avatarPreview.value = URL.createObjectURL(file)
  avatarRemoved.value = false
}

const removeAvatar = () => {
  avatarFile.value = null
  avatarPreview.value = null
  avatarRemoved.value = true
  form.value.avatar_url = null
  if (avatarInput.value) avatarInput.value.value = ''
}

const isEdit = computed(() => !!route.params.id)
const models = computed(() => settingsStore.models)

// Combined list: roles first, then specific models
const modelChoices = computed(() => {
  const roleItems = modelRoles.value.map(r => ({
    title: `🎭 ${r.label}`,
    value: `role:${r.role}`,
    subtitle: `Role — uses whatever model is assigned to "${r.role}"`,
    isRole: true,
  }))
  const modelItems = models.value.map(m => ({
    title: m.name || m.model_id,
    value: m.id,
    subtitle: m.model_id,
    isRole: false,
  }))
  return [...roleItems, ...modelItems]
})
const protocolItems = computed(() => protocolsList.value)
const mainProtocolItems = computed(() =>
  protocolsList.value.filter(p => form.value.protocol_ids.includes(p.id))
)
const selectedProtocolPreview = computed(() =>
  protocolsList.value.find(p => p.id === form.value.thinking_protocol_id) || null
)

const voiceOptions = [
  'Alice', 'Bill', 'Brian', 'Callum', 'Charlie', 'Chris',
  'Daniel', 'Eric', 'George', 'Jessica', 'Laura', 'Liam',
  'Lily', 'Matilda', 'Rachel', 'River', 'Roger', 'Sarah', 'Will',
]

const voicePreviewing = ref(false)
let previewAudio = null
const previewVoice = async (voice) => {
  if (!voice || voicePreviewing.value) return

  // Play from localStorage cache if available
  const cacheKey = `voice-demo-${voice}`
  const cached = localStorage.getItem(cacheKey)
  if (cached) {
    if (previewAudio) { previewAudio.pause() }
    previewAudio = new Audio(cached)
    previewAudio.play()
    return
  }

  voicePreviewing.value = true
  try {
    if (previewAudio) { previewAudio.pause(); previewAudio = null }
    const { data } = await api.post('/audio/tts', { text: 'Hello! This is a voice demo. Testing text-to-speech synthesis.', voice })
    // Download and cache as data URL in localStorage
    const resp = await fetch(data.audio_url)
    const blob = await resp.blob()
    const dataUrl = await new Promise(resolve => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result)
      reader.readAsDataURL(blob)
    })
    localStorage.setItem(cacheKey, dataUrl)
    previewAudio = new Audio(dataUrl)
    previewAudio.play()
  } catch (e) {
    console.error('Voice preview error:', e)
  } finally {
    voicePreviewing.value = false
  }
}

const form = ref({
  name: '',
  description: '',
  mission: '',
  system_prompt: '',
  voice: null,
  temperature: 0.7,
  top_p: 0.9,
  top_k: 40,
  max_tokens: 2048,
  num_ctx: 32768,
  repeat_penalty: 1.1,
  num_thread: 8,
  num_gpu: 1,
  models: [],  // array of { model_config_id, task_type, tags, priority }
  thinking_protocol_id: null,
  protocol_ids: [],           // all selected protocol IDs
  avatar_url: null,
})

const addModel = () => {
  const defaultValue = modelChoices.value.length ? modelChoices.value[0].value : null
  form.value.models.push({
    model_config_id: defaultValue,
    task_type: 'general',
    tags: [],
    priority: form.value.models.length,
  })
}

const removeModel = (idx) => {
  form.value.models.splice(idx, 1)
}

onMounted(async () => {
  await settingsStore.fetchModels()
  // Load model roles
  try {
    const { data } = await api.get('/settings/model-roles/available')
    modelRoles.value = data
  } catch { modelRoles.value = [] }
  // Load protocols
  try {
    const { data } = await api.get('/protocols')
    protocolsList.value = data
  } catch { protocolsList.value = [] }

  if (isEdit.value) {
    const agent = await agentsStore.fetchAgent(route.params.id)
    // Copy scalar fields
    const scalarKeys = [
      'name', 'description', 'mission', 'system_prompt', 'voice', 'temperature', 'top_p', 'top_k',
      'max_tokens', 'num_ctx', 'repeat_penalty', 'num_thread', 'num_gpu', 'avatar_url',
    ]
    scalarKeys.forEach((key) => {
      if (agent[key] !== undefined && agent[key] !== null) form.value[key] = agent[key]
    })
    // Load thinking_protocol_id
    form.value.thinking_protocol_id = agent.thinking_protocol_id || null
    // Load protocol_ids from multi-protocol
    if (agent.protocols && agent.protocols.length) {
      form.value.protocol_ids = agent.protocols.map(p => p.id)
    } else if (agent.thinking_protocol_id) {
      // Backwards compat: single protocol → protocol_ids
      form.value.protocol_ids = [agent.thinking_protocol_id]
    }
    // Load agent_models
    if (agent.agent_models && agent.agent_models.length) {
      form.value.models = agent.agent_models.map((am) => ({
        model_config_id: am.model_config_id,
        task_type: am.task_type || 'general',
        tags: am.tags || [],
        priority: am.priority ?? 0,
      }))
    }
  }
  // If no models yet, auto-add first available
  if (!form.value.models.length && modelChoices.value.length) {
    addModel()
  }
})

const handleSubmit = async () => {
  saving.value = true
  try {
    let agentData
    if (isEdit.value) {
      agentData = await agentsStore.updateAgent(route.params.id, form.value)
    } else {
      agentData = await agentsStore.createAgent(form.value)
    }
    const agentId = agentData?.id || route.params.id
    // Upload avatar if a new file was selected
    if (avatarFile.value && agentId) {
      await agentsStore.uploadAvatar(agentId, avatarFile.value)
    }
    // Delete avatar if removed
    if (avatarRemoved.value && !avatarFile.value && agentId) {
      await agentsStore.deleteAvatar(agentId)
    }
    router.push('/agents')
  } finally {
    saving.value = false
  }
}
</script>
