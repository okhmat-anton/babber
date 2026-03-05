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
                <v-icon :color="p.is_default ? 'amber' : 'blue-grey'" size="20">{{ p.is_default ? 'mdi-star' : 'mdi-head-cog' }}</v-icon>
                <span class="text-subtitle-1 font-weight-bold">{{ p.name }}</span>
                <v-chip v-if="p.is_default" size="x-small" color="amber" variant="tonal">default</v-chip>
              </div>
              <div class="text-caption text-grey mt-1">{{ p.description || 'No description' }}</div>
              <div class="text-caption text-grey mt-1">{{ stepsCount(p) }} steps · {{ loopsCount(p) }} loops</div>
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
            <ProtocolFlow :steps="selectedProtocol.steps" />
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Create / Edit Dialog -->
    <v-dialog v-model="formDialog" max-width="960" persistent scrollable>
      <v-card>
        <v-card-title>{{ editingId ? 'Edit Protocol' : 'New Protocol' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="form.name" label="Name" class="mb-2" density="compact" />
          <v-textarea v-model="form.description" label="Description" rows="2" density="compact" class="mb-4" />

          <div class="text-subtitle-2 mb-2">Steps</div>
          <draggable-steps v-model="form.steps" @add="addStep" @remove="removeStep" />

          <!-- Add step buttons -->
          <div class="d-flex ga-2 mt-3">
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="addStep('action')">Action</v-btn>
            <v-btn size="small" variant="tonal" color="orange" prepend-icon="mdi-refresh" @click="addStep('loop')">Loop</v-btn>
            <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-help-circle" @click="addStep('decision')">Decision</v-btn>
          </div>

          <!-- Steps editor -->
          <div class="mt-4">
            <div v-for="(step, idx) in form.steps" :key="idx" class="mb-3">
              <v-card variant="outlined" :class="stepBorderColor(step.type)">
                <v-card-text class="pa-3">
                  <div class="d-flex align-center ga-2 mb-2">
                    <v-icon :color="stepColor(step.type)" size="18">{{ stepIcon(step.type) }}</v-icon>
                    <v-chip :color="stepColor(step.type)" size="x-small" variant="tonal">{{ step.type }}</v-chip>
                    <span class="text-caption text-grey">Step {{ idx + 1 }}</span>
                    <v-spacer />
                    <v-btn icon="mdi-arrow-up" size="x-small" variant="text" :disabled="idx === 0" @click="moveStep(idx, -1)" />
                    <v-btn icon="mdi-arrow-down" size="x-small" variant="text" :disabled="idx === form.steps.length - 1" @click="moveStep(idx, 1)" />
                    <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="removeStep(idx)" />
                  </div>
                  <v-row dense>
                    <v-col cols="12" md="4">
                      <v-text-field v-model="step.name" label="Name" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" md="4">
                      <v-select v-model="step.category" :items="categories" label="Category" density="compact" hide-details />
                    </v-col>
                    <v-col v-if="step.type === 'loop'" cols="12" md="4">
                      <v-text-field v-model.number="step.max_iterations" label="Max Iterations" type="number" density="compact" hide-details />
                    </v-col>
                  </v-row>
                  <v-textarea v-model="step.instruction" label="Instruction" rows="2" density="compact" class="mt-2" hide-details />
                  <v-text-field v-if="step.type === 'loop' || step.type === 'decision'" v-model="step.exit_condition" label="Exit Condition" density="compact" class="mt-2" hide-details />

                  <!-- Nested steps for loops -->
                  <div v-if="step.type === 'loop'" class="mt-3 pl-4" style="border-left: 2px solid rgba(255,152,0,0.3)">
                    <div class="text-caption text-grey mb-2">Loop body steps:</div>
                    <div v-for="(sub, si) in step.steps" :key="si" class="mb-2">
                      <v-card variant="flat" class="bg-grey-darken-4 pa-2">
                        <div class="d-flex align-center ga-2 mb-1">
                          <v-icon :color="stepColor(sub.type)" size="14">{{ stepIcon(sub.type) }}</v-icon>
                          <v-chip :color="stepColor(sub.type)" size="x-small" variant="tonal">{{ sub.type }}</v-chip>
                          <v-spacer />
                          <v-btn icon="mdi-arrow-up" size="x-small" variant="text" :disabled="si === 0" @click="moveSubStep(idx, si, -1)" />
                          <v-btn icon="mdi-arrow-down" size="x-small" variant="text" :disabled="si === step.steps.length - 1" @click="moveSubStep(idx, si, 1)" />
                          <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="removeSubStep(idx, si)" />
                        </div>
                        <v-row dense>
                          <v-col cols="6"><v-text-field v-model="sub.name" label="Name" density="compact" hide-details /></v-col>
                          <v-col cols="6"><v-select v-model="sub.type" :items="['action','decision']" label="Type" density="compact" hide-details /></v-col>
                        </v-row>
                        <v-textarea v-model="sub.instruction" label="Instruction" rows="1" density="compact" class="mt-1" hide-details />
                        <v-text-field v-if="sub.type === 'decision'" v-model="sub.exit_condition" label="Exit Condition" density="compact" class="mt-1" hide-details />
                      </v-card>
                    </div>
                    <div class="d-flex ga-2">
                      <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="addSubStep(idx, 'action')">Action</v-btn>
                      <v-btn size="x-small" variant="tonal" color="teal" prepend-icon="mdi-plus" @click="addSubStep(idx, 'decision')">Decision</v-btn>
                    </div>
                  </div>
                </v-card-text>
              </v-card>
            </div>
          </div>

          <!-- Live preview -->
          <div v-if="form.steps.length" class="mt-6">
            <div class="text-subtitle-2 mb-2">
              <v-icon size="18" class="mr-1">mdi-eye</v-icon>
              Live Preview
            </div>
            <v-sheet class="pa-4 rounded" color="grey-darken-4">
              <ProtocolFlow :steps="form.steps" />
            </v-sheet>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="formDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="saveProtocol" :loading="saving">{{ editingId ? 'Update' : 'Create' }}</v-btn>
        </v-card-actions>
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
import { ref, onMounted } from 'vue'
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

const categories = ['analysis', 'planning', 'execution', 'verification', 'output', 'other']

const form = ref({
  name: '',
  description: '',
  steps: [],
})

const stepColor = (type) => ({ action: 'primary', loop: 'orange', decision: 'teal' }[type] || 'grey')
const stepIcon = (type) => ({ action: 'mdi-play-circle', loop: 'mdi-refresh', decision: 'mdi-help-rhombus' }[type] || 'mdi-circle')
const stepBorderColor = (type) => ({
  action: 'border-s-primary border-s-lg',
  loop: 'border-s-warning border-s-lg',
  decision: 'border-s-teal border-s-lg',
}[type] || '')

const stepsCount = (p) => {
  let count = 0
  const countSteps = (steps) => { steps.forEach(s => { count++; if (s.steps) countSteps(s.steps) }) }
  countSteps(p.steps || [])
  return count
}
const loopsCount = (p) => (p.steps || []).filter(s => s.type === 'loop').length

const load = async () => {
  loading.value = true
  try {
    const { data } = await api.get('/protocols')
    protocols.value = data
  } finally { loading.value = false }
}

const selectProtocol = (p) => {
  selectedProtocol.value = selectedProtocol.value?.id === p.id ? null : p
}

const openCreate = () => {
  editingId.value = null
  form.value = { name: '', description: '', steps: [] }
  formDialog.value = true
}

const openEdit = (p) => {
  editingId.value = p.id
  form.value = {
    name: p.name,
    description: p.description,
    steps: JSON.parse(JSON.stringify(p.steps || [])),
  }
  formDialog.value = true
}

const addStep = (type) => {
  const step = { type, name: '', instruction: '', category: 'other', steps: [] }
  if (type === 'loop') { step.max_iterations = 5; step.exit_condition = '' }
  if (type === 'decision') { step.exit_condition = '' }
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
