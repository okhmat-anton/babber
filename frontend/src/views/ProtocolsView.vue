<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Thinking Protocols</div>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">New Protocol</v-btn>
    </div>

    <v-row>
      <!-- Protocol List -->
      <v-col cols="12" :md="selectedProtocol ? 5 : 12">
        <v-card v-for="p in protocols" :key="p.id" class="mb-3" :variant="selectedProtocol?.id === p.id ? 'tonal' : 'elevated'" @click="selectProtocol(p)" style="cursor:pointer">
          <v-card-text class="d-flex align-center">
            <div class="flex-grow-1">
              <div class="d-flex align-center ga-2">
                <v-icon :color="p.is_default ? 'amber' : (p.type === 'orchestrator' ? 'orange' : p.type === 'loop' ? 'green' : 'blue-grey')" size="20">{{ p.is_default ? 'mdi-star' : (p.type === 'orchestrator' ? 'mdi-crown' : p.type === 'loop' ? 'mdi-sync' : 'mdi-head-cog') }}</v-icon>
                <span class="text-subtitle-1 font-weight-bold">{{ p.name }}</span>
                <v-chip v-if="p.is_default" size="x-small" color="amber" variant="tonal">default</v-chip>
                <v-chip size="x-small" :color="p.type === 'orchestrator' ? 'orange' : p.type === 'loop' ? 'green' : 'blue-grey'" variant="tonal">{{ p.type || 'standard' }}</v-chip>
                <v-chip v-if="p.response_style" size="x-small" :color="styleColor(p.response_style)" variant="tonal">
                  <v-icon start size="12">{{ styleIcon(p.response_style) }}</v-icon>
                  {{ p.response_style }}
                </v-chip>
              </div>
              <div class="text-caption text-grey mt-1">{{ p.description || 'No description' }}</div>
              <div class="text-caption text-grey mt-1">{{ stepsCount(p) }} steps · {{ loopsCount(p) }} loops{{ delegateCount(p) ? ' · ' + delegateCount(p) + ' delegates' : '' }}</div>
            </div>
            <div class="d-flex ga-1">
              <v-btn icon="mdi-pencil" size="small" variant="text" @click.stop="openEdit(p)" />
              <v-btn icon="mdi-content-copy" size="small" variant="text" @click.stop="duplicateProtocol(p)" />
              <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click.stop="confirmDelete(p)" :disabled="p.is_default" />
            </div>
          </v-card-text>
        </v-card>
        <v-alert v-if="!loading && !protocols.length" type="info" variant="tonal">
          No protocols yet. Create one to define how agents should think.
        </v-alert>
        <div v-if="loading" class="text-center py-6"><v-progress-circular indeterminate /></div>
      </v-col>

      <!-- Visual Preview -->
      <v-col v-if="selectedProtocol" cols="12" md="7">
        <v-card>
          <v-card-title class="d-flex align-center">
            <v-icon class="mr-2" color="primary">mdi-sitemap</v-icon>
            {{ selectedProtocol.name }}
            <v-spacer />
            <v-btn icon="mdi-close" size="small" variant="text" @click="selectedProtocol = null" />
          </v-card-title>
          <v-card-subtitle v-if="selectedProtocol.description">{{ selectedProtocol.description }}</v-card-subtitle>
          <v-card-text>
            <ProtocolFlow :steps="selectedProtocol.steps" :protocols="protocols" />
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Create / Edit Dialog — 70% screen -->
    <v-dialog v-model="formDialog" width="70vw" max-width="1400" persistent scrollable content-class="protocol-editor-dialog">
      <v-card class="d-flex flex-column" style="height: 80vh; overflow: hidden;">
        <!-- Header -->
        <div class="protocol-editor-header px-5 py-3 d-flex align-center" style="border-bottom: 1px solid rgba(255,255,255,0.08); flex-shrink: 0;">
          <v-icon :color="form.type === 'orchestrator' ? 'amber' : 'primary'" size="24" class="mr-3">
            {{ form.type === 'orchestrator' ? 'mdi-crown' : 'mdi-head-cog' }}
          </v-icon>
          <div>
            <div class="text-h6 font-weight-medium">{{ editingId ? 'Edit Protocol' : 'New Protocol' }}</div>
            <div class="text-caption text-medium-emphasis">{{ form.name || 'Untitled' }} · {{ form.steps.length }} steps</div>
          </div>
          <v-spacer />
          <v-chip :color="form.type === 'orchestrator' ? 'amber' : 'blue-grey'" variant="tonal" size="small" class="mr-3">
            <v-icon start size="14">{{ form.type === 'orchestrator' ? 'mdi-crown' : 'mdi-head-cog' }}</v-icon>
            {{ form.type }}
          </v-chip>
          <v-btn icon="mdi-close" size="small" variant="text" @click="formDialog = false" />
        </div>

        <!-- Two-column body -->
        <div class="d-flex flex-grow-1" style="overflow: hidden; min-height: 0;">

          <!-- LEFT: Editor -->
          <div class="protocol-editor-left d-flex flex-column" style="width: 55%; border-right: 1px solid rgba(255,255,255,0.06); overflow: hidden;">
            <div class="pa-5 flex-grow-1" style="overflow-y: auto;">

              <!-- Meta fields -->
              <div class="d-flex ga-3 mb-4">
                <v-text-field
                  v-model="form.name"
                  label="Protocol Name"
                  density="compact"
                  hide-details
                  variant="outlined"
                  class="flex-grow-1"
                  placeholder="e.g. Standard Problem Solving"
                />
                <v-select
                  v-model="form.type"
                  :items="protocolTypes"
                  label="Type"
                  density="compact"
                  hide-details
                  variant="outlined"
                  style="max-width: 180px;"
                >
                  <template #selection="{ item }">
                    <v-icon size="16" class="mr-1" :color="item.value === 'orchestrator' ? 'amber' : 'blue-grey'">
                      {{ item.value === 'orchestrator' ? 'mdi-crown' : 'mdi-head-cog' }}
                    </v-icon>
                    {{ item.title }}
                  </template>
                </v-select>
              </div>
              <div class="d-flex ga-3 mb-4">
                <v-select
                  v-model="form.response_style"
                  :items="responseStyles"
                  item-title="name"
                  item-value="key"
                  label="Response Style"
                  density="compact"
                  hide-details
                  variant="outlined"
                  clearable
                  placeholder="Default (no style)"
                  prepend-inner-icon="mdi-format-text-variant"
                >
                  <template #selection="{ item }">
                    <v-icon size="16" class="mr-1" :color="item.raw.color">{{ item.raw.icon }}</v-icon>
                    {{ item.raw.name }}
                  </template>
                  <template #item="{ item, props }">
                    <v-list-item v-bind="props">
                      <template #prepend>
                        <v-icon :color="item.raw.color" size="20">{{ item.raw.icon }}</v-icon>
                      </template>
                      <v-list-item-subtitle>{{ item.raw.description }}</v-list-item-subtitle>
                    </v-list-item>
                  </template>
                </v-select>
              </div>
              <v-textarea
                v-model="form.description"
                label="Description"
                rows="2"
                density="compact"
                hide-details
                variant="outlined"
                class="mb-5"
                placeholder="Describe what this protocol does..."
              />

              <!-- Divider with add buttons -->
              <div class="d-flex align-center mb-4">
                <div class="text-subtitle-2 text-medium-emphasis">
                  <v-icon size="16" class="mr-1">mdi-format-list-numbered</v-icon>
                  Steps ({{ form.steps.length }})
                </div>
                <v-spacer />
                <div class="d-flex ga-1 flex-wrap">
                  <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="addStep('action')" rounded>Action</v-btn>
                  <v-btn size="x-small" variant="tonal" color="orange" prepend-icon="mdi-refresh" @click="addStep('loop')" rounded>Loop</v-btn>
                  <v-btn size="x-small" variant="tonal" color="teal" prepend-icon="mdi-help-circle" @click="addStep('decision')" rounded>Decision</v-btn>
                  <v-btn size="x-small" variant="tonal" color="light-green" prepend-icon="mdi-format-list-checks" @click="addStep('todo')" rounded>Todo List</v-btn>
                  <v-btn v-if="form.type === 'orchestrator'" size="x-small" variant="tonal" color="amber" prepend-icon="mdi-call-split" @click="addStep('delegate')" rounded>Delegate</v-btn>
                </div>
              </div>

              <!-- Steps editor -->
              <div v-if="!form.steps.length" class="text-center py-10">
                <v-icon size="48" color="grey-darken-1" class="mb-3">mdi-format-list-checks</v-icon>
                <div class="text-body-2 text-medium-emphasis">No steps yet</div>
                <div class="text-caption text-grey">Add steps using the buttons above to build the protocol flow</div>
              </div>

              <div v-for="(step, idx) in form.steps" :key="idx" class="mb-3 protocol-step-card">
                <v-card variant="outlined" :class="['step-card', stepBorderClass(step.type)]" rounded="lg">
                  <v-card-text class="pa-0">
                    <!-- Step header bar -->
                    <div class="step-header d-flex align-center px-3 py-2" :style="stepHeaderBg(step.type)">
                      <v-icon :color="stepColor(step.type)" size="18">{{ stepIcon(step.type) }}</v-icon>
                      <v-chip :color="stepColor(step.type)" size="x-small" variant="flat" class="ml-2 font-weight-bold text-uppercase" label>{{ step.type }}</v-chip>
                      <span class="text-caption text-medium-emphasis ml-2">{{ step.name || 'Step ' + (idx + 1) }}</span>
                      <v-spacer />
                      <v-btn-group density="compact" variant="text" divided>
                        <v-btn icon="mdi-chevron-up" size="x-small" :disabled="idx === 0" @click="moveStep(idx, -1)" />
                        <v-btn icon="mdi-chevron-down" size="x-small" :disabled="idx === form.steps.length - 1" @click="moveStep(idx, 1)" />
                        <v-btn icon="mdi-delete-outline" size="x-small" color="error" @click="removeStep(idx)" />
                      </v-btn-group>
                    </div>

                    <!-- Step body -->
                    <div class="px-3 py-3">
                      <v-row dense>
                        <v-col cols="12" :md="step.type === 'loop' ? 4 : 6">
                          <v-text-field v-model="step.name" label="Name" density="compact" hide-details variant="outlined" />
                        </v-col>
                        <v-col cols="12" :md="step.type === 'loop' ? 4 : 6">
                          <v-select v-model="step.category" :items="categories" label="Category" density="compact" hide-details variant="outlined">
                            <template #selection="{ item }">
                              <v-chip :color="catColor(item.value)" size="x-small" variant="tonal" label class="mr-1">{{ item.title }}</v-chip>
                            </template>
                          </v-select>
                        </v-col>
                        <v-col v-if="step.type === 'loop'" cols="12" md="4">
                          <v-text-field v-model.number="step.max_iterations" label="Max Iterations" type="number" density="compact" hide-details variant="outlined" />
                        </v-col>
                      </v-row>
                      <v-textarea v-model="step.instruction" label="Instruction" rows="2" density="compact" class="mt-3" hide-details variant="outlined" />

                      <!-- Model Role selector -->
                      <v-select
                        v-model="step.model_role"
                        :items="modelRoleItems"
                        item-title="label"
                        item-value="role"
                        label="Model Role"
                        density="compact"
                        class="mt-3"
                        hide-details
                        variant="outlined"
                        clearable
                        placeholder="Default (agent model)"
                        prepend-inner-icon="mdi-brain"
                      />

                      <v-text-field v-if="step.type === 'loop' || step.type === 'decision'" v-model="step.exit_condition" label="Exit / Branch Condition" density="compact" class="mt-3" hide-details variant="outlined" prepend-inner-icon="mdi-help-circle-outline" />

                      <!-- Delegate: protocol selector -->
                      <div v-if="step.type === 'delegate'" class="mt-3">
                        <v-select
                          v-model="step.protocol_ids"
                          :items="delegatableProtocols"
                          item-title="name"
                          item-value="id"
                          label="Child Protocols to Delegate"
                          multiple
                          chips
                          closable-chips
                          density="compact"
                          hide-details
                          variant="outlined"
                          prepend-inner-icon="mdi-call-split"
                        >
                          <template #item="{ item, props }">
                            <v-list-item v-bind="props">
                              <template #prepend>
                                <v-icon size="18" color="blue-grey">mdi-head-cog</v-icon>
                              </template>
                              <v-list-item-subtitle>{{ item.raw.description || 'No description' }}</v-list-item-subtitle>
                            </v-list-item>
                          </template>
                        </v-select>
                      </div>

                      <!-- Nested steps for loops -->
                      <div v-if="step.type === 'loop'" class="mt-4 loop-body-area pa-3 rounded-lg">
                        <div class="d-flex align-center mb-3">
                          <v-icon size="14" color="orange" class="mr-1">mdi-subdirectory-arrow-right</v-icon>
                          <span class="text-caption font-weight-bold text-orange">LOOP BODY</span>
                          <v-spacer />
                          <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="addSubStep(idx, 'action')" rounded class="mr-1">Action</v-btn>
                          <v-btn size="x-small" variant="tonal" color="teal" prepend-icon="mdi-plus" @click="addSubStep(idx, 'decision')" rounded>Decision</v-btn>
                        </div>
                        <div v-if="!step.steps?.length" class="text-center py-3">
                          <div class="text-caption text-medium-emphasis">Empty loop body — add steps above</div>
                        </div>
                        <div v-for="(sub, si) in step.steps" :key="si" class="mb-2">
                          <v-card variant="flat" class="sub-step-card pa-3" rounded="lg">
                            <div class="d-flex align-center ga-2 mb-2">
                              <v-icon :color="stepColor(sub.type)" size="14">{{ stepIcon(sub.type) }}</v-icon>
                              <v-chip :color="stepColor(sub.type)" size="x-small" variant="flat" label class="text-uppercase font-weight-bold">{{ sub.type }}</v-chip>
                              <span class="text-caption text-medium-emphasis">{{ sub.name || 'Sub-step ' + (si + 1) }}</span>
                              <v-spacer />
                              <v-btn icon="mdi-chevron-up" size="x-small" variant="text" :disabled="si === 0" @click="moveSubStep(idx, si, -1)" />
                              <v-btn icon="mdi-chevron-down" size="x-small" variant="text" :disabled="si === step.steps.length - 1" @click="moveSubStep(idx, si, 1)" />
                              <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error" @click="removeSubStep(idx, si)" />
                            </div>
                            <v-row dense>
                              <v-col cols="6"><v-text-field v-model="sub.name" label="Name" density="compact" hide-details variant="outlined" /></v-col>
                              <v-col cols="6"><v-select v-model="sub.type" :items="['action','decision']" label="Type" density="compact" hide-details variant="outlined" /></v-col>
                            </v-row>
                            <v-textarea v-model="sub.instruction" label="Instruction" rows="1" density="compact" class="mt-2" hide-details variant="outlined" />
                            <v-row dense class="mt-2">
                              <v-col cols="6">
                                <v-select v-model="sub.model_role" :items="modelRoleItems" item-title="label" item-value="role" label="Model Role" density="compact" hide-details variant="outlined" clearable placeholder="Default" prepend-inner-icon="mdi-brain" />
                              </v-col>
                              <v-col cols="6">
                                <v-text-field v-if="sub.type === 'decision'" v-model="sub.exit_condition" label="Exit Condition" density="compact" hide-details variant="outlined" />
                              </v-col>
                            </v-row>
                          </v-card>
                        </div>
                      </div>
                    </div>
                  </v-card-text>
                </v-card>
              </div>

            </div>
          </div>

          <!-- RIGHT: Live Preview -->
          <div class="protocol-editor-right d-flex flex-column" style="width: 45%; overflow: hidden;">
            <div class="px-4 py-3 d-flex align-center" style="border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0;">
              <v-icon size="18" color="primary" class="mr-2">mdi-eye</v-icon>
              <span class="text-subtitle-2 text-medium-emphasis">Live Preview</span>
              <v-spacer />
              <v-chip size="x-small" variant="tonal" color="primary">{{ form.steps.length }} steps</v-chip>
            </div>
            <div class="flex-grow-1 pa-4" style="overflow-y: auto; background: rgba(0,0,0,0.15);">
              <div v-if="!form.steps.length" class="d-flex flex-column align-center justify-center" style="height: 100%; opacity: 0.4;">
                <v-icon size="56" class="mb-3">mdi-sitemap</v-icon>
                <div class="text-body-2">Add steps to see the flow</div>
              </div>
              <ProtocolFlow v-else :steps="form.steps" :protocols="protocols" />
            </div>
          </div>

        </div>

        <!-- Footer -->
        <div class="px-5 py-3 d-flex align-center" style="border-top: 1px solid rgba(255,255,255,0.08); flex-shrink: 0;">
          <v-btn variant="text" prepend-icon="mdi-close" @click="formDialog = false">Cancel</v-btn>
          <v-spacer />
          <v-btn color="primary" variant="elevated" prepend-icon="mdi-content-save" @click="saveProtocol" :loading="saving" size="large">
            {{ editingId ? 'Update Protocol' : 'Create Protocol' }}
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- Delete Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Delete Protocol</v-card-title>
        <v-card-text>Are you sure you want to delete "{{ deleteTarget?.name }}"?</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" @click="doDelete">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import ProtocolFlow from '../components/ProtocolFlow.vue'

const protocols = ref([])
const loading = ref(false)
const selectedProtocol = ref(null)
const formDialog = ref(false)
const editingId = ref(null)
const saving = ref(false)
const deleteDialog = ref(false)
const deleteTarget = ref(null)
const modelRoles = ref([])  // [{role, label}]
const responseStyles = ref([])  // [{key, name, description, icon, color}]

const modelRoleItems = computed(() => modelRoles.value.filter(r => r.role !== 'base'))

const categories = ['analysis', 'planning', 'execution', 'verification', 'output', 'other']
const protocolTypes = ['standard', 'orchestrator', 'loop']

const form = ref({
  name: '',
  description: '',
  type: 'standard',
  response_style: null,
  steps: [],
})

const stepColor = (type) => ({ action: 'primary', loop: 'orange', decision: 'teal', delegate: 'amber', todo: 'light-green' }[type] || 'grey')
const stepIcon = (type) => ({ action: 'mdi-play-circle', loop: 'mdi-refresh', decision: 'mdi-help-rhombus', delegate: 'mdi-call-split', todo: 'mdi-format-list-checks' }[type] || 'mdi-circle')
const stepBorderColor = (type) => ({
  action: 'border-s-primary border-s-lg',
  loop: 'border-s-warning border-s-lg',
  decision: 'border-s-teal border-s-lg',
  delegate: 'border-s-amber border-s-lg',
  todo: 'border-s-light-green border-s-lg',
}[type] || '')

const stepBorderClass = (type) => ({
  action: 'step-card-action',
  loop: 'step-card-loop',
  decision: 'step-card-decision',
  delegate: 'step-card-delegate',
  todo: 'step-card-todo',
}[type] || '')

const stepHeaderBg = (type) => ({
  action: 'background: rgba(33,150,243,0.06)',
  loop: 'background: rgba(255,152,0,0.06)',
  decision: 'background: rgba(0,150,136,0.06)',
  delegate: 'background: rgba(255,193,7,0.06)',
  todo: 'background: rgba(139,195,74,0.06)',
}[type] || '')

const catColor = (cat) => ({
  analysis: 'deep-purple', planning: 'indigo', execution: 'blue',
  verification: 'green', output: 'cyan', other: 'grey',
}[cat] || 'grey')

const stepsCount = (p) => {
  let count = 0
  const countSteps = (steps) => { steps.forEach(s => { count++; if (s.steps) countSteps(s.steps) }) }
  countSteps(p.steps || [])
  return count
}
const loopsCount = (p) => (p.steps || []).filter(s => s.type === 'loop').length
const delegateCount = (p) => (p.steps || []).filter(s => s.type === 'delegate').length

const styleColor = (key) => {
  const s = responseStyles.value.find(rs => rs.key === key)
  return s ? s.color : 'grey'
}
const styleIcon = (key) => {
  const s = responseStyles.value.find(rs => rs.key === key)
  return s ? s.icon : 'mdi-format-text-variant'
}

// Protocols available for delegation (all standard protocols, excluding the one being edited)
const delegatableProtocols = computed(() =>
  protocols.value.filter(p => p.type !== 'orchestrator' && p.id !== editingId.value)
)

const load = async () => {
  loading.value = true
  try {
    const [protoRes, rolesRes, stylesRes] = await Promise.all([
      api.get('/protocols'),
      api.get('/settings/model-roles/available').catch(() => ({ data: [] })),
      api.get('/protocols/response-styles').catch(() => ({ data: [] })),
    ])
    protocols.value = protoRes.data
    modelRoles.value = rolesRes.data
    responseStyles.value = stylesRes.data
  } finally { loading.value = false }
}

const selectProtocol = (p) => {
  selectedProtocol.value = selectedProtocol.value?.id === p.id ? null : p
}

const openCreate = () => {
  editingId.value = null
  form.value = { name: '', description: '', type: 'standard', response_style: null, steps: [] }
  formDialog.value = true
}

const openEdit = (p) => {
  editingId.value = p.id
  form.value = {
    name: p.name,
    description: p.description,
    type: p.type || 'standard',
    response_style: p.response_style || null,
    steps: JSON.parse(JSON.stringify(p.steps || [])),
  }
  formDialog.value = true
}

const addStep = (type) => {
  const step = { type, name: '', instruction: '', category: 'other', model_role: null, steps: [] }
  if (type === 'loop') { step.max_iterations = 5; step.exit_condition = '' }
  if (type === 'decision') { step.exit_condition = '' }
  if (type === 'delegate') { step.protocol_ids = [] }
  if (type === 'todo') { step.category = 'planning' }
  form.value.steps.push(step)
}

const removeStep = (idx) => { form.value.steps.splice(idx, 1) }

const moveStep = (idx, dir) => {
  const arr = form.value.steps
  const target = idx + dir
  ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
}

const addSubStep = (parentIdx, type) => {
  const sub = { type, name: '', instruction: '' }
  if (type === 'decision') sub.exit_condition = ''
  form.value.steps[parentIdx].steps.push(sub)
}
const removeSubStep = (parentIdx, subIdx) => { form.value.steps[parentIdx].steps.splice(subIdx, 1) }
const moveSubStep = (parentIdx, subIdx, dir) => {
  const arr = form.value.steps[parentIdx].steps
  const target = subIdx + dir
  ;[arr[subIdx], arr[target]] = [arr[target], arr[subIdx]]
}

const saveProtocol = async () => {
  if (!form.value.name.trim()) return
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/protocols/${editingId.value}`, form.value)
    } else {
      await api.post('/protocols', form.value)
    }
    formDialog.value = false
    await load()
    // Update selected if editing
    if (editingId.value && selectedProtocol.value?.id === editingId.value) {
      selectedProtocol.value = protocols.value.find(p => p.id === editingId.value) || null
    }
  } catch (e) { alert(e.response?.data?.detail || 'Failed to save') }
  finally { saving.value = false }
}

const duplicateProtocol = async (p) => {
  await api.post(`/protocols/${p.id}/duplicate`)
  await load()
}

const confirmDelete = (p) => { deleteTarget.value = p; deleteDialog.value = true }
const doDelete = async () => {
  await api.delete(`/protocols/${deleteTarget.value.id}`)
  deleteDialog.value = false
  if (selectedProtocol.value?.id === deleteTarget.value.id) selectedProtocol.value = null
  await load()
}

onMounted(load)
</script>

<style scoped>
.step-card {
  transition: box-shadow 0.2s ease;
  overflow: hidden;
}
.step-card:hover {
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1), 0 4px 12px rgba(0,0,0,0.25);
}
.step-card-action { border-color: rgba(33,150,243,0.25) !important; }
.step-card-loop { border-color: rgba(255,152,0,0.25) !important; }
.step-card-decision { border-color: rgba(0,150,136,0.25) !important; }
.step-card-delegate { border-color: rgba(255,193,7,0.25) !important; }
.step-card-todo { border-color: rgba(139,195,74,0.25) !important; }

.step-header {
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.loop-body-area {
  background: rgba(255,152,0,0.04);
  border: 1px dashed rgba(255,152,0,0.2);
}

.sub-step-card {
  background: rgba(255,255,255,0.03) !important;
  border: 1px solid rgba(255,255,255,0.06) !important;
}

.protocol-step-card {
  transition: transform 0.15s ease;
}
.protocol-step-card:hover {
  transform: translateX(2px);
}

.protocol-editor-right {
  background: rgba(0,0,0,0.08);
}
</style>
