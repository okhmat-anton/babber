<template>
  <div v-if="agent">
    <div class="d-flex align-center mb-6">
      <v-btn icon="mdi-arrow-left" variant="text" @click="$router.push('/agents')" />
      <div class="text-h4 font-weight-bold ml-2">{{ agent.name }}</div>
      <v-chip :color="statusColor(agent.status)" class="ml-3" variant="tonal">{{ agent.status }}</v-chip>
      <v-spacer />
      <v-btn v-if="agent.status !== 'running'" color="success" prepend-icon="mdi-play" @click="start" class="mr-2">Start</v-btn>
      <v-btn v-else color="error" prepend-icon="mdi-stop" @click="stop" class="mr-2">Stop</v-btn>
      <v-btn prepend-icon="mdi-pencil" :to="`/agents/${agent.id}`">Edit</v-btn>
    </div>

    <!-- Stats -->
    <v-row class="mb-4">
      <v-col v-for="s in statItems" :key="s.label" cols="6" md="2">
        <v-card>
          <v-card-text class="text-center">
            <div class="text-h5 font-weight-bold">{{ s.value }}</div>
            <div class="text-caption text-grey">{{ s.label }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Tabs -->
    <v-card>
      <v-tabs v-model="tab">
        <v-tab value="info">Info</v-tab>
        <v-tab value="beliefs">Beliefs</v-tab>
        <v-tab value="files">Files</v-tab>
        <v-tab value="tasks">Tasks</v-tab>
        <v-tab value="logs">Logs</v-tab>
        <v-tab value="skills">Skills</v-tab>
        <v-tab value="memory">Memory</v-tab>
      </v-tabs>
      <v-card-text>
        <!-- Info Tab -->
        <div v-if="tab === 'info'">
          <v-list>
            <v-list-item v-if="agent.agent_models && agent.agent_models.length">
              <strong>Models:</strong>
              <div class="mt-1">
                <v-chip
                  v-for="am in agent.agent_models"
                  :key="am.id"
                  size="small"
                  variant="tonal"
                  color="primary"
                  class="mr-1 mb-1"
                >
                  {{ am.model_display_name || am.model_name }}
                  <v-tooltip activator="parent" location="top">
                    <div><strong>Task:</strong> {{ am.task_type }}</div>
                    <div v-if="am.tags && am.tags.length"><strong>Tags:</strong> {{ am.tags.join(', ') }}</div>
                    <div><strong>Priority:</strong> {{ am.priority }}</div>
                  </v-tooltip>
                </v-chip>
              </div>
            </v-list-item>
            <v-list-item><strong>Temperature:</strong>&nbsp;{{ agent.temperature }}</v-list-item>
            <v-list-item><strong>Top P:</strong>&nbsp;{{ agent.top_p }}&nbsp;&nbsp;<strong>Top K:</strong>&nbsp;{{ agent.top_k }}</v-list-item>
            <v-list-item><strong>Context:</strong>&nbsp;{{ agent.num_ctx }}&nbsp;&nbsp;<strong>Max Tokens:</strong>&nbsp;{{ agent.max_tokens }}</v-list-item>
            <v-list-item><strong>Repeat Penalty:</strong>&nbsp;{{ agent.repeat_penalty }}&nbsp;&nbsp;<strong>Num Predict:</strong>&nbsp;{{ agent.num_predict }}</v-list-item>
            <v-list-item><strong>Threads:</strong>&nbsp;{{ agent.num_thread }}&nbsp;&nbsp;<strong>GPU Layers:</strong>&nbsp;{{ agent.num_gpu }}</v-list-item>
            <v-list-item v-if="agent.description"><strong>Description:</strong>&nbsp;{{ agent.description }}</v-list-item>
            <v-list-item v-if="agent.thinking_protocol">
              <strong>Thinking Protocol:</strong>&nbsp;
              <v-chip size="small" color="deep-purple" variant="tonal" class="ml-1" @click="showProtocolPreview = !showProtocolPreview" style="cursor:pointer">
                <v-icon start size="14">mdi-head-cog</v-icon>
                {{ agent.thinking_protocol.name }}
                <v-icon end size="14">{{ showProtocolPreview ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
              </v-chip>
            </v-list-item>
          </v-list>

          <!-- Protocol preview -->
          <div v-if="showProtocolPreview && agent.thinking_protocol" class="mt-3 mb-3">
            <v-sheet class="pa-4 rounded" color="grey-darken-4">
              <ProtocolFlow :steps="agent.thinking_protocol.steps || []" />
            </v-sheet>
          </div>

          <!-- Principles -->
          <div v-if="agent.beliefs && (agent.beliefs.core?.length || agent.beliefs.additional?.length)" class="mt-4">
            <div class="text-subtitle-2 mb-1">Beliefs ({{ (agent.beliefs.core?.length || 0) + (agent.beliefs.additional?.length || 0) }})</div>
            <div class="d-flex flex-wrap ga-1">
              <v-chip v-for="b in (agent.beliefs.core || [])" :key="b.id" size="small" color="amber" variant="tonal">
                <v-icon start size="12">mdi-shield-lock</v-icon>{{ b.text }}
              </v-chip>
              <v-chip v-for="b in (agent.beliefs.additional || [])" :key="b.id" size="small" color="blue-grey" variant="tonal">
                {{ b.text }}
              </v-chip>
            </div>
          </div>

          <div v-if="agent.system_prompt" class="mt-4">
            <div class="text-subtitle-2 mb-1">System Prompt</div>
            <v-sheet rounded class="pa-3 bg-grey-darken-4" style="white-space: pre-wrap; font-family: monospace; font-size: 13px;">{{ agent.system_prompt }}</v-sheet>
          </div>
        </div>

        <!-- Beliefs Tab -->
        <div v-if="tab === 'beliefs'">
          <!-- Core Beliefs -->
          <div class="d-flex align-center mb-3">
            <div class="text-subtitle-1 font-weight-bold">
              <v-icon color="amber" size="20" class="mr-1">mdi-shield-lock</v-icon>
              Core Beliefs
            </div>
            <v-chip size="x-small" class="ml-2" variant="tonal">weight: 1.0 — immutable by agent</v-chip>
            <v-spacer />
            <v-btn color="amber" size="small" variant="tonal" prepend-icon="mdi-plus" @click="openBeliefDialog('core')">Add Core</v-btn>
          </div>
          <div v-if="beliefs.core.length" class="mb-6">
            <v-card v-for="b in beliefs.core" :key="b.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-chip :color="categoryColor(b.category)" size="x-small" variant="flat" class="mr-2">{{ b.category }}</v-chip>
                <span class="text-body-1 flex-grow-1">{{ b.text }}</span>
                <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editBelief(b, 'core')" class="mr-1" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="confirmDeleteBelief(b, 'core')" />
              </div>
            </v-card>
          </div>
          <div v-else class="text-center text-grey pa-4 mb-6">No core beliefs defined</div>

          <!-- Additional Beliefs -->
          <div class="d-flex align-center mb-3">
            <div class="text-subtitle-1 font-weight-bold">
              <v-icon color="blue-grey" size="20" class="mr-1">mdi-lightbulb-outline</v-icon>
              Additional Beliefs
            </div>
            <v-chip size="x-small" class="ml-2" variant="tonal">weight: 0.5 — editable by agent</v-chip>
            <v-spacer />
            <v-btn color="blue-grey" size="small" variant="tonal" prepend-icon="mdi-plus" @click="openBeliefDialog('additional')">Add</v-btn>
          </div>
          <div v-if="beliefs.additional.length">
            <v-card v-for="b in beliefs.additional" :key="b.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-chip :color="categoryColor(b.category)" size="x-small" variant="flat" class="mr-2">{{ b.category }}</v-chip>
                <span class="text-body-1 flex-grow-1">{{ b.text }}</span>
                <v-chip size="x-small" variant="tonal" class="mr-2">{{ b.created_by }}</v-chip>
                <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editBelief(b, 'additional')" class="mr-1" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="confirmDeleteBelief(b, 'additional')" />
              </div>
            </v-card>
          </div>
          <div v-else class="text-center text-grey pa-4">No additional beliefs</div>
        </div>

        <!-- Tasks Tab -->
        <div v-if="tab === 'tasks'">
          <v-btn color="primary" size="small" prepend-icon="mdi-plus" @click="createAgentTask" class="mb-3">New Task</v-btn>
          <v-data-table :headers="taskHeaders" :items="tasks" density="compact" hover>
            <template #item.status="{ item }">
              <v-chip :color="taskStatusColor(item.status)" size="x-small" variant="tonal">{{ item.status }}</v-chip>
            </template>
          </v-data-table>
        </div>

        <!-- Logs Tab -->
        <div v-if="tab === 'logs'">
          <v-select v-model="logLevel" :items="['all','debug','info','warning','error','critical']" label="Level" density="compact" style="max-width: 200px" class="mb-3" />
          <v-list density="compact" class="log-list" style="max-height: 500px; overflow-y: auto;">
            <v-list-item v-for="log in logs" :key="log.id" class="py-0">
              <div class="d-flex">
                <v-chip :color="logColor(log.level)" size="x-small" variant="flat" class="mr-2" style="min-width: 60px;">{{ log.level }}</v-chip>
                <span class="text-caption text-grey mr-2">{{ new Date(log.created_at).toLocaleTimeString() }}</span>
                <span class="text-body-2">{{ log.message }}</span>
              </div>
            </v-list-item>
          </v-list>
        </div>

        <!-- Skills Tab -->
        <div v-if="tab === 'skills'">
          <v-list v-if="agentSkills.length">
            <v-list-item v-for="s in agentSkills" :key="s.skill_id">
              <v-list-item-title>{{ s.skill?.display_name || s.skill_id }}</v-list-item-title>
              <v-list-item-subtitle>{{ s.skill?.description }}</v-list-item-subtitle>
              <template #append>
                <v-chip :color="s.is_enabled ? 'success' : 'grey'" size="small">{{ s.is_enabled ? 'ON' : 'OFF' }}</v-chip>
              </template>
            </v-list-item>
          </v-list>
          <div v-else class="text-center text-grey pa-6">No skills attached</div>
        </div>

        <!-- Files Tab -->
        <div v-if="tab === 'files'" class="agent-files-tab">
          <div class="d-flex" style="height: 500px;">
            <!-- File tree sidebar -->
            <div class="file-sidebar" style="width: 260px; min-width: 200px; border-right: 1px solid #3c3c3c; overflow-y: auto;">
              <div class="d-flex align-center px-2 py-1" style="border-bottom: 1px solid #3c3c3c; height: 36px;">
                <span class="text-caption text-uppercase font-weight-bold text-grey">Files</span>
                <v-spacer />
                <v-btn icon="mdi-file-plus-outline" size="x-small" variant="text" @click="showNewFile(false)" title="New File" />
                <v-btn icon="mdi-folder-plus-outline" size="x-small" variant="text" @click="showNewFile(true)" title="New Folder" />
                <v-btn icon="mdi-refresh" size="x-small" variant="text" @click="loadFiles" title="Refresh" />
              </div>
              <div class="pa-1">
                <div
                  v-for="node in flatFileTree"
                  :key="node.path"
                  class="file-node d-flex align-center px-2 py-1"
                  :class="{ 'file-node-selected': currentFilePath === node.path }"
                  :style="{ paddingLeft: (node.depth * 16 + 8) + 'px', cursor: 'pointer' }"
                  @click="node.is_dir ? toggleDir(node.path) : openFile(node)"
                >
                  <v-icon size="16" :color="node.is_dir ? 'amber' : 'grey'" class="mr-1">{{ fileIcon(node) }}</v-icon>
                  <span class="text-body-2 flex-grow-1" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ node.name }}</span>
                  <v-icon
                    v-if="!['agent.json', 'settings.json', 'beliefs.json'].includes(node.path) && node.path !== 'data'"
                    size="14" class="file-delete-btn" color="grey"
                    @click.stop="confirmDeleteFile(node.path)"
                  >mdi-close</v-icon>
                </div>
                <div v-if="!fileTree.length" class="text-center text-grey pa-4 text-caption">No files</div>
              </div>
            </div>

            <!-- Editor area -->
            <div class="flex-grow-1 d-flex flex-column" style="min-width: 0;">
              <!-- Tab bar -->
              <div v-if="currentFilePath" class="d-flex align-center px-3" style="height: 36px; background: #2d2d2d; border-bottom: 1px solid #3c3c3c;">
                <span class="text-body-2">{{ currentFilePath }}</span>
                <v-chip v-if="fileModified" color="warning" size="x-small" class="ml-2" variant="flat">modified</v-chip>
                <v-spacer />
                <v-btn v-if="fileModified" color="success" size="x-small" variant="flat" @click="saveFile" :loading="fileSaving">Save</v-btn>
              </div>
              <!-- Textarea editor -->
              <div v-if="currentFilePath" class="flex-grow-1" style="overflow: hidden;">
                <textarea
                  ref="editorArea"
                  v-model="fileContent"
                  class="agent-file-editor"
                  spellcheck="false"
                  @input="fileModified = true"
                  @keydown.ctrl.s.prevent="saveFile"
                  @keydown.meta.s.prevent="saveFile"
                />
              </div>
              <!-- Empty state -->
              <div v-else class="d-flex align-center justify-center flex-grow-1">
                <div class="text-center text-grey">
                  <v-icon size="48" class="mb-2">mdi-file-document-outline</v-icon>
                  <div class="text-body-1">Select a file to view or edit</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Memory Tab -->
        <div v-if="tab === 'memory'">
          <v-data-table :headers="memHeaders" :items="memories" density="compact" hover>
            <template #item.type="{ item }">
              <v-chip size="x-small" variant="tonal">{{ item.type }}</v-chip>
            </template>
            <template #item.importance="{ item }">
              <v-progress-linear :model-value="item.importance * 100" :color="item.importance > 0.7 ? 'success' : 'grey'" height="6" rounded />
            </template>
            <template #item.tags="{ item }">
              <v-chip v-for="t in (item.tags || []).slice(0, 3)" :key="t" size="x-small" class="mr-1">{{ t }}</v-chip>
            </template>
          </v-data-table>
        </div>
      </v-card-text>
    </v-card>

    <!-- New File Dialog -->
    <v-dialog v-model="newFileDialog" max-width="450">
      <v-card>
        <v-card-title>{{ newFileIsDir ? 'New Folder' : 'New File' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newFilePath"
            :label="newFileIsDir ? 'Folder path (e.g. data/reports)' : 'File path (e.g. data/notes.md)'"
            density="compact" autofocus @keyup.enter="createFile"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="newFileDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="createFile">Create</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete File Dialog -->
    <v-dialog v-model="deleteFileDialog" max-width="400">
      <v-card>
        <v-card-title>Delete {{ deleteFilePath }}</v-card-title>
        <v-card-text>This action cannot be undone.</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteFileDialog = false">Cancel</v-btn>
          <v-btn color="error" @click="doDeleteFile">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Belief Add/Edit Dialog -->
    <v-dialog v-model="beliefDialog" max-width="550">
      <v-card>
        <v-card-title>{{ beliefEditId ? 'Edit' : 'Add' }} {{ beliefDialogType === 'core' ? 'Core' : 'Additional' }} Belief</v-card-title>
        <v-card-text>
          <v-textarea v-model="beliefText" label="Belief text" rows="3" autofocus density="compact" class="mb-2" />
          <v-select v-model="beliefCategory" :items="beliefCategories" label="Category" density="compact" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="beliefDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="saveBelief" :loading="beliefSaving">{{ beliefEditId ? 'Save' : 'Add' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Belief Dialog -->
    <v-dialog v-model="deleteBeliefDialog" max-width="400">
      <v-card>
        <v-card-title>Delete Belief</v-card-title>
        <v-card-text>"{{ deleteBeliefItem?.text }}"</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteBeliefDialog = false">Cancel</v-btn>
          <v-btn color="error" @click="doDeleteBelief">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { useAgentsStore } from '../stores/agents'
import ProtocolFlow from '../components/ProtocolFlow.vue'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const tab = ref('info')
const agent = ref(null)
const stats = ref({})
const tasks = ref([])
const showProtocolPreview = ref(false)
const logs = ref([])
const agentSkills = ref([])
const memories = ref([])
const logLevel = ref('all')

// Files tab state
const fileTree = ref([])
const currentFilePath = ref(null)
const fileContent = ref('')
const fileModified = ref(false)
const fileSaving = ref(false)
const expandedDirs = ref(new Set())
const newFileDialog = ref(false)
const newFileIsDir = ref(false)
const newFilePath = ref('')
const deleteFileDialog = ref(false)
const deleteFilePath = ref('')
const editorArea = ref(null)

// Beliefs tab state
const beliefs = ref({ core: [], additional: [] })
const beliefDialog = ref(false)
const beliefDialogType = ref('core')
const beliefText = ref('')
const beliefCategory = ref('other')
const beliefEditId = ref(null)
const beliefSaving = ref(false)
const deleteBeliefDialog = ref(false)
const deleteBeliefItem = ref(null)
const deleteBeliefType = ref('core')
const beliefCategories = ['moral', 'behavioral', 'communication', 'restriction', 'preference', 'goal', 'other']

const id = computed(() => route.params.id)

const statusColor = (s) => ({ idle: 'grey', running: 'success', paused: 'warning', error: 'error', stopped: 'grey' }[s] || 'grey')
const taskStatusColor = (s) => ({ pending: 'info', running: 'success', completed: 'success', failed: 'error', cancelled: 'grey' }[s] || 'grey')
const logColor = (l) => ({ debug: 'grey', info: 'info', warning: 'warning', error: 'error', critical: 'error' }[l] || 'grey')

const statItems = computed(() => [
  { label: 'Tasks', value: stats.value.total_tasks || 0 },
  { label: 'Completed', value: stats.value.completed_tasks || 0 },
  { label: 'Failed', value: stats.value.failed_tasks || 0 },
  { label: 'Logs', value: stats.value.total_logs || 0 },
  { label: 'Memories', value: stats.value.total_memories || 0 },
  { label: 'Skills', value: stats.value.total_skills || 0 },
])

const taskHeaders = [
  { title: 'Title', key: 'title' },
  { title: 'Status', key: 'status', width: 100 },
  { title: 'Priority', key: 'priority', width: 100 },
  { title: 'Created', key: 'created_at', width: 150 },
]

const memHeaders = [
  { title: 'Title', key: 'title' },
  { title: 'Type', key: 'type', width: 100 },
  { title: 'Importance', key: 'importance', width: 120 },
  { title: 'Tags', key: 'tags', width: 200 },
  { title: 'Source', key: 'source', width: 80 },
]

const loadData = async () => {
  agent.value = await agentsStore.fetchAgent(id.value)
  stats.value = await agentsStore.fetchStats(id.value)
}

const loadTasks = async () => {
  const { data } = await api.get(`/agents/${id.value}/tasks`)
  tasks.value = data
}

const loadLogs = async () => {
  const params = logLevel.value !== 'all' ? { level: logLevel.value } : {}
  const { data } = await api.get(`/agents/${id.value}/logs`, { params: { ...params, limit: 100 } })
  logs.value = data
}

const loadSkills = async () => {
  const { data } = await api.get(`/agents/${id.value}/skills`)
  agentSkills.value = data
}

const loadMemories = async () => {
  const { data } = await api.get(`/agents/${id.value}/memory`, { params: { limit: 100 } })
  memories.value = data
}

// ===== Files =====
const loadFiles = async () => {
  try {
    const { data } = await api.get(`/agents/${id.value}/files`)
    fileTree.value = data
    // Auto-expand top-level dirs
    const autoExpand = (nodes) => {
      for (const n of nodes) {
        if (n.is_dir) { expandedDirs.value.add(n.path); if (n.children) autoExpand(n.children) }
      }
    }
    autoExpand(data)
  } catch { fileTree.value = [] }
}

const flatFileTree = computed(() => {
  const result = []
  const walk = (nodes, depth) => {
    for (const n of nodes) {
      result.push({ ...n, depth })
      if (n.is_dir && expandedDirs.value.has(n.path) && n.children) {
        walk(n.children, depth + 1)
      }
    }
  }
  walk(fileTree.value, 0)
  return result
})

const toggleDir = (path) => {
  if (expandedDirs.value.has(path)) expandedDirs.value.delete(path)
  else expandedDirs.value.add(path)
}

const fileIcon = (node) => {
  if (node.is_dir) return expandedDirs.value.has(node.path) ? 'mdi-folder-open' : 'mdi-folder'
  const ext = node.name.split('.').pop().toLowerCase()
  const map = {
    json: 'mdi-code-json', py: 'mdi-language-python', js: 'mdi-language-javascript',
    md: 'mdi-language-markdown', txt: 'mdi-file-document-outline', sh: 'mdi-console',
    yaml: 'mdi-file-cog', yml: 'mdi-file-cog', html: 'mdi-language-html5',
  }
  return map[ext] || 'mdi-file-outline'
}

const openFile = async (node) => {
  if (fileModified.value && currentFilePath.value) {
    if (!confirm('Unsaved changes will be lost. Continue?')) return
  }
  try {
    const { data } = await api.get(`/agents/${id.value}/files/read`, { params: { path: node.path } })
    currentFilePath.value = data.path
    fileContent.value = data.content
    fileModified.value = false
  } catch (e) { console.error('Failed to open file:', e) }
}

const saveFile = async () => {
  if (!currentFilePath.value) return
  fileSaving.value = true
  try {
    await api.put(`/agents/${id.value}/files/write-json`, { path: currentFilePath.value, content: fileContent.value })
    fileModified.value = false
    // Reload agent data if config files changed
    if (['agent.json', 'settings.json'].includes(currentFilePath.value)) {
      await loadData()
    }
    if (currentFilePath.value === 'beliefs.json') {
      await loadBeliefs()
      await loadData()
    }
  } catch (e) { alert(e.response?.data?.detail || 'Failed to save') }
  finally { fileSaving.value = false }
}

const showNewFile = (isDir) => { newFileIsDir.value = isDir; newFilePath.value = ''; newFileDialog.value = true }

const createFile = async () => {
  if (!newFilePath.value.trim()) return
  try {
    await api.post(`/agents/${id.value}/files/create`, {
      path: newFilePath.value.trim(), is_dir: newFileIsDir.value, content: '',
    })
    newFileDialog.value = false
    await loadFiles()
    if (!newFileIsDir.value) await openFile({ path: newFilePath.value.trim(), is_dir: false })
  } catch (e) { alert(e.response?.data?.detail || 'Failed to create') }
}

const confirmDeleteFile = (path) => { deleteFilePath.value = path; deleteFileDialog.value = true }

// ===== Beliefs =====
const categoryColor = (cat) => ({
  moral: 'deep-purple', behavioral: 'teal', communication: 'blue',
  restriction: 'red', preference: 'cyan', goal: 'green', other: 'grey',
}[cat] || 'grey')

const loadBeliefs = async () => {
  try {
    const { data } = await api.get(`/agents/${id.value}/beliefs`)
    beliefs.value = { core: data.core || [], additional: data.additional || [] }
  } catch { beliefs.value = { core: [], additional: [] } }
}

const openBeliefDialog = (type) => {
  beliefDialogType.value = type
  beliefText.value = ''
  beliefCategory.value = 'other'
  beliefEditId.value = null
  beliefDialog.value = true
}

const editBelief = (b, type) => {
  beliefDialogType.value = type
  beliefText.value = b.text
  beliefCategory.value = b.category
  beliefEditId.value = b.id
  beliefDialog.value = true
}

const saveBelief = async () => {
  if (!beliefText.value.trim()) return
  beliefSaving.value = true
  try {
    const type = beliefDialogType.value
    const payload = { text: beliefText.value.trim(), category: beliefCategory.value }
    if (beliefEditId.value) {
      await api.put(`/agents/${id.value}/beliefs/${type}/${beliefEditId.value}`, payload)
    } else {
      await api.post(`/agents/${id.value}/beliefs/${type}`, payload)
    }
    beliefDialog.value = false
    await loadBeliefs()
    await loadData()
  } catch (e) { alert(e.response?.data?.detail || 'Failed to save belief') }
  finally { beliefSaving.value = false }
}

const confirmDeleteBelief = (b, type) => {
  deleteBeliefItem.value = b
  deleteBeliefType.value = type
  deleteBeliefDialog.value = true
}

const doDeleteBelief = async () => {
  try {
    await api.delete(`/agents/${id.value}/beliefs/${deleteBeliefType.value}/${deleteBeliefItem.value.id}`)
    deleteBeliefDialog.value = false
    await loadBeliefs()
    await loadData()
  } catch (e) { alert(e.response?.data?.detail || 'Failed to delete belief') }
}

const doDeleteFile = async () => {
  try {
    await api.delete(`/agents/${id.value}/files/delete`, { params: { path: deleteFilePath.value } })
    deleteFileDialog.value = false
    if (currentFilePath.value === deleteFilePath.value || currentFilePath.value?.startsWith(deleteFilePath.value + '/')) {
      currentFilePath.value = null; fileContent.value = ''; fileModified.value = false
    }
    await loadFiles()
  } catch (e) { alert(e.response?.data?.detail || 'Failed to delete') }
}

watch(tab, (val) => {
  if (val === 'tasks') loadTasks()
  if (val === 'logs') loadLogs()
  if (val === 'skills') loadSkills()
  if (val === 'memory') loadMemories()
  if (val === 'files') loadFiles()
  if (val === 'beliefs') loadBeliefs()
})

watch(logLevel, () => { if (tab.value === 'logs') loadLogs() })

const start = async () => { await agentsStore.startAgent(id.value); await loadData() }
const stop = async () => { await agentsStore.stopAgent(id.value); await loadData() }
const createAgentTask = () => router.push(`/tasks/new?agent_id=${id.value}`)

onMounted(loadData)
</script>

<style scoped>
.agent-file-editor {
  width: 100%;
  height: 100%;
  background: #1e1e1e;
  color: #d4d4d4;
  border: none;
  outline: none;
  resize: none;
  padding: 12px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  tab-size: 2;
}

.file-node:hover {
  background: #2a2d2e;
}

.file-node-selected {
  background: #094771 !important;
}

.file-delete-btn {
  display: none;
}

.file-node:hover .file-delete-btn {
  display: inline-flex;
}

.file-delete-btn:hover {
  color: #f44 !important;
}
</style>
