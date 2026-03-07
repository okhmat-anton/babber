<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Agents</div>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" to="/agents/new">New Agent</v-btn>
    </div>

    <v-card>
      <v-card-text class="pa-0">
        <v-data-table
          :headers="headers"
          :items="store.agents"
          :loading="store.loading"
          hover
          @click:row="(_, { item }) => $router.push(`/agents/${item.id}/detail`)"
        >
          <template #item.name="{ item }">
            <div class="d-flex align-center">
              <v-avatar :size="32" :color="item.avatar_url ? undefined : 'primary'" variant="tonal" class="mr-2">
                <v-img v-if="item.avatar_url" :src="item.avatar_url" cover />
                <span v-else class="text-caption font-weight-bold">{{ item.name?.charAt(0).toUpperCase() }}</span>
              </v-avatar>
              {{ item.name }}
            </div>
          </template>
          <template #item.enabled="{ item }">
            <v-switch
              :model-value="item.enabled !== false"
              color="success"
              density="compact"
              hide-details
              @update:model-value="toggleEnabled(item, $event)"
              @click.stop
            />
          </template>
          <template #item.status="{ item }">
            <v-chip :color="statusColor(item.status)" size="small" variant="tonal">{{ item.status }}</v-chip>
          </template>
          <template #item.models="{ item }">
            <div v-if="item.agent_models && item.agent_models.length" class="d-flex flex-wrap ga-1">
              <v-chip v-for="am in item.agent_models" :key="am.id" size="x-small" variant="tonal" color="primary">
                {{ am.model_display_name || am.model_name }}
              </v-chip>
            </div>
            <span v-else class="text-grey">—</span>
          </template>
          <template #item.created_at="{ item }">
            {{ new Date(item.created_at).toLocaleDateString() }}
          </template>
          <template #item.actions="{ item }">
            <div class="d-flex align-center ga-0">
              <!-- Chat / Start -->
              <v-btn icon size="small" variant="text" color="success" @click.stop="handleStart(item)" v-if="item.status !== 'running'">
                <v-icon>mdi-chat</v-icon>
                <v-tooltip activator="parent" location="top">Start Chat</v-tooltip>
              </v-btn>
              <v-btn icon size="small" variant="text" color="error" @click.stop="handleStop(item)" v-else>
                <v-icon>mdi-stop</v-icon>
                <v-tooltip activator="parent" location="top">Stop Agent</v-tooltip>
              </v-btn>

              <!-- Autonomous -->
              <v-btn icon size="small" variant="text" color="green" @click.stop="openAutonomousDialog(item)" :disabled="item.status === 'running' || !hasLoopProtocol(item)">
                <v-icon>mdi-sync</v-icon>
                <v-tooltip activator="parent" location="top">
                  {{ !hasLoopProtocol(item) ? 'No loop protocol assigned' : 'Start Autonomous' }}
                </v-tooltip>
              </v-btn>

              <!-- Edit -->
              <v-btn icon size="small" variant="text" @click.stop="$router.push(`/agents/${item.id}`)">
                <v-icon>mdi-pencil</v-icon>
                <v-tooltip activator="parent" location="top">Edit</v-tooltip>
              </v-btn>

              <!-- Duplicate -->
              <v-btn icon size="small" variant="text" @click.stop="handleDuplicate(item)">
                <v-icon>mdi-content-copy</v-icon>
                <v-tooltip activator="parent" location="top">Duplicate</v-tooltip>
              </v-btn>

              <!-- Delete -->
              <v-btn icon size="small" variant="text" color="error" @click.stop="handleDelete(item)">
                <v-icon>mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">Delete</v-tooltip>
              </v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Delete confirm -->
    <ConfirmDeleteDialog
      v-model="deleteDialog"
      title="Delete Agent"
      :message="`Are you sure you want to delete &quot;${deleteTarget?.name}&quot;?`"
      @confirm="confirmDelete"
    />

    <!-- Autonomous Launch Dialog -->
    <v-dialog v-model="autonomousDialog" max-width="550">
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon color="green" class="mr-2">mdi-sync</v-icon>
          Start Autonomous — {{ autoAgent?.name }}
        </v-card-title>
        <v-card-text>
          <div class="text-body-2 text-grey mb-4">The agent will work independently based on its loop protocol, beliefs, aspirations, and available skills.</div>

          <v-select
            v-model="autoForm.protocolId"
            :items="autoLoopProtocols"
            item-title="name"
            item-value="id"
            label="Loop Protocol"
            density="compact"
            variant="outlined"
            class="mb-3"
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps">
                <template #prepend>
                  <v-icon color="green" size="18">mdi-sync</v-icon>
                </template>
                <template #subtitle>
                  <span>{{ item.raw.description || 'No description' }}</span>
                </template>
              </v-list-item>
            </template>
          </v-select>

          <v-radio-group v-model="autoForm.mode" inline class="mb-3">
            <v-radio label="Continuous (until stopped)" value="continuous" />
            <v-radio label="Fixed cycles" value="cycles" />
          </v-radio-group>

          <v-text-field
            v-if="autoForm.mode === 'cycles'"
            v-model.number="autoForm.maxCycles"
            label="Number of cycles"
            type="number"
            min="1"
            max="1000"
            density="compact"
            variant="outlined"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="autonomousDialog = false">Cancel</v-btn>
          <v-btn color="green" variant="flat" @click="startAutonomous" :loading="autonomousStarting" :disabled="!autoForm.protocolId">Start</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { useAgentsStore } from '../stores/agents'
import ConfirmDeleteDialog from '../components/ConfirmDeleteDialog.vue'
import api from '../api'

const store = useAgentsStore()
const showSnackbar = inject('showSnackbar')
const deleteDialog = ref(false)
const deleteTarget = ref(null)

// Autonomous dialog state
const autonomousDialog = ref(false)
const autoAgent = ref(null)
const autoLoopProtocols = ref([])
const autoForm = ref({ mode: 'continuous', maxCycles: 5, protocolId: null })
const autonomousStarting = ref(false)

const headers = [
  { title: 'Name', key: 'name' },
  { title: 'Enabled', key: 'enabled', width: 90 },
  { title: 'Status', key: 'status', width: 120 },
  { title: 'Model', key: 'models', sortable: false },
  { title: 'Created', key: 'created_at', width: 120 },
  { title: 'Actions', key: 'actions', sortable: false, width: 260 },
]

const statusColor = (s) => ({ idle: 'grey', running: 'success', paused: 'warning', error: 'error', stopped: 'grey' }[s] || 'grey')

const hasLoopProtocol = (agent) => {
  return agent.protocols && agent.protocols.some(p => p.type === 'loop')
}

const toggleEnabled = async (agent, enabled) => {
  try {
    await store.updateAgent(agent.id, { enabled })
    agent.enabled = enabled
    showSnackbar(`${agent.name} ${enabled ? 'enabled' : 'disabled'}`)
  } catch (e) {
    showSnackbar('Failed to update agent')
  }
}

const handleStart = async (agent) => {
  await store.startAgent(agent.id)
  showSnackbar(`${agent.name} started`)
}

const handleStop = async (agent) => {
  await store.stopAgent(agent.id)
  showSnackbar(`${agent.name} stopped`)
}

const handleDuplicate = async (agent) => {
  await store.duplicateAgent(agent.id)
  showSnackbar(`${agent.name} duplicated`)
}

const handleDelete = (agent) => {
  deleteTarget.value = agent
  deleteDialog.value = true
}

const confirmDelete = async () => {
  await store.deleteAgent(deleteTarget.value.id)
  deleteDialog.value = false
  showSnackbar('Agent deleted')
}

const openAutonomousDialog = async (agent) => {
  autoAgent.value = agent
  autoLoopProtocols.value = (agent.protocols || []).filter(p => p.type === 'loop')
  autoForm.value = {
    mode: 'continuous',
    maxCycles: 5,
    protocolId: autoLoopProtocols.value.length ? autoLoopProtocols.value[0].id : null,
  }
  autonomousDialog.value = true
}

const startAutonomous = async () => {
  if (!autoAgent.value) return
  autonomousStarting.value = true
  try {
    const payload = {
      mode: autoForm.value.mode,
      loop_protocol_id: autoForm.value.protocolId,
    }
    if (autoForm.value.mode === 'cycles') {
      payload.max_cycles = autoForm.value.maxCycles
    }
    await api.post(`/agents/${autoAgent.value.id}/autonomous/start`, payload)
    autonomousDialog.value = false
    showSnackbar(`Autonomous run started for ${autoAgent.value.name}`)
    await store.fetchAgents()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to start autonomous run')
  }
  autonomousStarting.value = false
}

onMounted(() => store.fetchAgents())
</script>
