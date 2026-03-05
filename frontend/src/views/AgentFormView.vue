<template>
  <div>
    <div class="d-flex align-center mb-6">
      <v-btn icon="mdi-arrow-left" variant="text" @click="$router.back()" />
      <div class="text-h4 font-weight-bold ml-2">{{ isEdit ? 'Edit Agent' : 'New Agent' }}</div>
    </div>

    <v-card>
      <v-card-text>
        <v-form @submit.prevent="handleSubmit">
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field v-model="form.name" label="Name" required />
            </v-col>
            <v-col cols="12" md="6">
              <v-textarea v-model="form.description" label="Description" rows="2" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="form.system_prompt" label="System Prompt" rows="4" />
            </v-col>
          </v-row>

          <!-- ─── Thinking Protocol ─────────────────── -->
          <div class="text-h6 mt-6 mb-3">Thinking Protocol</div>
          <v-row>
            <v-col cols="12" md="6">
              <v-select
                v-model="form.thinking_protocol_id"
                :items="protocolItems"
                item-title="name"
                item-value="id"
                label="Select Protocol"
                clearable
                density="compact"
                hint="Defines how the agent reasons step by step"
                persistent-hint
              >
                <template #item="{ item, props }">
                  <v-list-item v-bind="props">
                    <v-list-item-subtitle>{{ item.raw.description || 'No description' }}</v-list-item-subtitle>
                  </v-list-item>
                </template>
              </v-select>
            </v-col>
            <v-col cols="12" md="6">
              <v-sheet v-if="selectedProtocolPreview" class="pa-3 rounded bg-grey-darken-4">
                <div class="text-caption text-grey mb-1">{{ selectedProtocolPreview.name }}</div>
                <div class="text-caption">{{ selectedProtocolPreview.steps?.length || 0 }} steps · {{ selectedProtocolPreview.steps?.filter(s => s.type === 'loop').length || 0 }} loops</div>
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
                  :items="models"
                  item-title="name"
                  item-value="id"
                  label="Model"
                  density="compact"
                  hide-details
                  required
                >
                  <template #item="{ item, props }">
                    <v-list-item v-bind="props">
                      <v-list-item-subtitle>{{ item.raw.model_id }}</v-list-item-subtitle>
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

const isEdit = computed(() => !!route.params.id)
const models = computed(() => settingsStore.models)
const protocolItems = computed(() => protocolsList.value)
const selectedProtocolPreview = computed(() =>
  protocolsList.value.find(p => p.id === form.value.thinking_protocol_id) || null
)

const form = ref({
  name: '',
  description: '',
  system_prompt: '',
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
})

const addModel = () => {
  form.value.models.push({
    model_config_id: models.value.length ? models.value[0].id : null,
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
  // Load protocols
  try {
    const { data } = await api.get('/protocols')
    protocolsList.value = data
  } catch { protocolsList.value = [] }

  if (isEdit.value) {
    const agent = await agentsStore.fetchAgent(route.params.id)
    // Copy scalar fields
    const scalarKeys = [
      'name', 'description', 'system_prompt', 'temperature', 'top_p', 'top_k',
      'max_tokens', 'num_ctx', 'repeat_penalty', 'num_thread', 'num_gpu',
    ]
    scalarKeys.forEach((key) => {
      if (agent[key] !== undefined && agent[key] !== null) form.value[key] = agent[key]
    })
    // Load thinking_protocol_id
    form.value.thinking_protocol_id = agent.thinking_protocol_id || null
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
  if (!form.value.models.length && models.value.length) {
    addModel()
  }
})

const handleSubmit = async () => {
  saving.value = true
  try {
    if (isEdit.value) {
      await agentsStore.updateAgent(route.params.id, form.value)
    } else {
      await agentsStore.createAgent(form.value)
    }
    router.push('/agents')
  } finally {
    saving.value = false
  }
}
</script>
