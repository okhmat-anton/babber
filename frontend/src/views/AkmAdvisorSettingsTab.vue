<template>
  <div>
    <!-- Connection Settings -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2" color="blue">mdi-briefcase-outline</v-icon>
        Connection
        <a href="https://app.akm-advisor.com/settings/agent" target="_blank" class="text-primary font-weight-medium ml-2" style="font-size:14px">
          <v-icon size="14">mdi-open-in-new</v-icon> API
        </a>
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="5">
            <v-text-field
              v-model="conn.api_key"
              label="Agent API Key (X-Agent-Key)"
              :type="showKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="agent_xxxxxxxxxxxxx"
              :append-inner-icon="showKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showKey = !showKey"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="conn.url"
              label="Agent API URL"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="https://app.akm-advisor.com/api/v1/agent/..."
            />
          </v-col>
          <v-col cols="12" md="3" class="d-flex align-center ga-2">
            <v-btn
              color="primary"
              :disabled="!connChanged"
              :loading="savingConn"
              @click="saveConnection"
            >
              <v-icon start>mdi-content-save</v-icon> Save
            </v-btn>
            <v-btn
              variant="tonal"
              color="info"
              :loading="testing"
              :disabled="!conn.api_key || !conn.url"
              @click="testConnection"
            >
              <v-icon start>mdi-connection</v-icon> Test
            </v-btn>
          </v-col>
        </v-row>

        <v-alert
          v-if="testResult"
          :type="testResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="testResult = null"
        >
          {{ testResult.message }}
        </v-alert>

        <v-alert type="info" variant="tonal" density="compact" class="mt-3">
          Get your Agent API key and URL at
          <a href="https://app.akm-advisor.com/settings/agent" target="_blank" class="text-primary">
            akm-advisor.com &rarr; Settings &rarr; Agent
          </a>.
          URL format: <code>https://app.akm-advisor.com/api/v1/agent/YOUR_PROJECT_ID</code>
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- Access Control -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2" color="orange">mdi-shield-key</v-icon>
        Agent Access Control
      </v-card-title>
      <v-card-text>
        <!-- Full Access Toggle -->
        <v-switch
          v-model="access.full_access"
          color="success"
          density="compact"
          hide-details
          class="mb-4"
        >
          <template #label>
            <div>
              <strong>Full Access</strong>
              <span class="text-grey ml-2">Agent has unrestricted access to all AKM Advisor resources</span>
            </div>
          </template>
        </v-switch>

        <v-divider class="mb-4" />

        <v-alert v-if="access.full_access" type="info" variant="tonal" density="compact" class="mb-4">
          Full access is ON — agent can access all sections and boards. Turn it off to restrict access to specific sections.
        </v-alert>

        <!-- Sections (always visible) -->
        <div class="text-subtitle-2 mb-2">
          <v-icon size="18" class="mr-1">mdi-view-grid</v-icon>
          Allowed Sections
          <span v-if="access.full_access" class="text-grey font-weight-regular ml-1">(all allowed — full access is ON)</span>
        </div>
        <div class="d-flex flex-wrap ga-2 mb-6">
          <v-chip
            v-for="s in allSections"
            :key="s.value"
            :color="access.full_access || access.allowed_sections.includes(s.value) ? 'primary' : 'default'"
            :variant="access.full_access || access.allowed_sections.includes(s.value) ? 'flat' : 'outlined'"
            :prepend-icon="s.icon"
            :disabled="access.full_access"
            @click="toggleSection(s.value)"
          >
            {{ s.label }}
          </v-chip>
        </div>

        <!-- Lead Boards -->
        <div v-if="access.full_access || access.allowed_sections.includes('leads')" class="mb-6">
          <div class="d-flex align-center mb-2">
            <v-icon size="18" class="mr-1" color="green">mdi-account-filter</v-icon>
            <span class="text-subtitle-2">Lead Boards</span>
            <v-chip v-if="!access.allowed_lead_boards.length" size="x-small" variant="tonal" color="success" class="ml-2">All boards</v-chip>
            <v-btn
              v-if="!leadBoards.length"
              variant="text"
              size="x-small"
              color="primary"
              :loading="loadingResources"
              class="ml-2"
              @click="fetchResources"
            >
              <v-icon start size="14">mdi-refresh</v-icon> Load boards
            </v-btn>
          </div>
          <div v-if="leadBoards.length" class="d-flex flex-wrap ga-2">
            <v-chip
              v-for="b in leadBoards"
              :key="b.id || b.name"
              :color="access.allowed_lead_boards.includes(b.id || b.name) ? 'green' : 'default'"
              :variant="access.allowed_lead_boards.includes(b.id || b.name) ? 'flat' : 'outlined'"
              :disabled="access.full_access"
              @click="toggleBoard('lead', b.id || b.name)"
            >
              {{ b.name || b.title || b.id }}
            </v-chip>
            <v-chip
              v-if="access.allowed_lead_boards.length"
              variant="text"
              size="small"
              color="grey"
              :disabled="access.full_access"
              @click="access.allowed_lead_boards = []"
            >Clear (allow all)</v-chip>
          </div>
          <div v-else class="text-grey text-body-2">
            No lead boards found in this project. Empty list = all boards allowed.
          </div>
        </div>

        <!-- Deal Boards -->
        <div v-if="access.full_access || access.allowed_sections.includes('deals')" class="mb-6">
          <div class="d-flex align-center mb-2">
            <v-icon size="18" class="mr-1" color="purple">mdi-handshake</v-icon>
            <span class="text-subtitle-2">Deal Boards</span>
            <v-chip v-if="!access.allowed_deal_boards.length" size="x-small" variant="tonal" color="success" class="ml-2">All boards</v-chip>
            <v-btn
              v-if="!dealBoards.length"
              variant="text"
              size="x-small"
              color="primary"
              :loading="loadingResources"
              class="ml-2"
              @click="fetchResources"
            >
              <v-icon start size="14">mdi-refresh</v-icon> Load boards
            </v-btn>
          </div>
          <div v-if="dealBoards.length" class="d-flex flex-wrap ga-2">
            <v-chip
              v-for="b in dealBoards"
              :key="b.id || b.name"
              :color="access.allowed_deal_boards.includes(b.id || b.name) ? 'purple' : 'default'"
              :variant="access.allowed_deal_boards.includes(b.id || b.name) ? 'flat' : 'outlined'"
              :disabled="access.full_access"
              @click="toggleBoard('deal', b.id || b.name)"
            >
              {{ b.name || b.title || b.id }}
            </v-chip>
            <v-chip
              v-if="access.allowed_deal_boards.length"
              variant="text"
              size="small"
              color="grey"
              :disabled="access.full_access"
              @click="access.allowed_deal_boards = []"
            >Clear (allow all)</v-chip>
          </div>
          <div v-else class="text-grey text-body-2">
            No deal boards found in this project. Empty list = all boards allowed.
          </div>
        </div>

        <!-- Project Info -->
        <div v-if="projectInfo" class="mb-4">
          <v-divider class="mb-3" />
          <div class="text-subtitle-2 mb-2">
            <v-icon size="18" class="mr-1">mdi-information</v-icon>
            Connected Project
          </div>
          <v-chip variant="tonal" color="blue" class="mr-2">
            <v-icon start size="14">mdi-key-variant</v-icon>
            {{ projectInfo.key }}
          </v-chip>
          <v-chip variant="tonal" color="primary" class="mr-2">{{ projectInfo.name }}</v-chip>
          <span v-if="projectInfo.description" class="text-grey text-body-2 ml-1">{{ projectInfo.description }}</span>
        </div>

        <!-- Save -->
        <v-divider class="my-4" />
        <div class="d-flex align-center ga-2">
          <v-btn
            color="primary"
            :disabled="!accessChanged"
            :loading="savingAccess"
            @click="saveAccess"
          >
            <v-icon start>mdi-content-save</v-icon> Save Access Settings
          </v-btn>
          <v-btn
            variant="tonal"
            color="secondary"
            :loading="loadingResources"
            :disabled="!conn.api_key || !conn.url"
            @click="fetchResources"
          >
            <v-icon start>mdi-cloud-download</v-icon> Load Available Resources
          </v-btn>
          <v-chip v-if="accessSaved" color="success" variant="tonal" size="small" class="ml-2">
            <v-icon start size="14">mdi-check</v-icon> Saved
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { useSettingsStore } from '../stores/settings'

const store = useSettingsStore()

// ── Snackbar ──
const snackbar = ref({ show: false, text: '', color: 'success' })
const showSnackbar = (text, color = 'success') => {
  snackbar.value = { show: true, text, color }
}

// ── Connection ──
const conn = ref({ api_key: '', url: '' })
const origConn = ref({ api_key: '', url: '' })
const showKey = ref(false)
const savingConn = ref(false)
const testing = ref(false)
const testResult = ref(null)

const connChanged = computed(() =>
  conn.value.api_key !== origConn.value.api_key || conn.value.url !== origConn.value.url
)

const saveConnection = async () => {
  savingConn.value = true
  try {
    await store.updateSystemSetting('akm_advisor_api_key', conn.value.api_key)
    await store.updateSystemSetting('akm_advisor_url', conn.value.url)
    origConn.value = { ...conn.value }
    showSnackbar('AKM Advisor connection saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save', 'error')
  } finally {
    savingConn.value = false
  }
}

const testConnection = async () => {
  testing.value = true
  testResult.value = null
  try {
    if (connChanged.value) {
      await store.updateSystemSetting('akm_advisor_api_key', conn.value.api_key)
      await store.updateSystemSetting('akm_advisor_url', conn.value.url)
      origConn.value = { ...conn.value }
    }
    const { data } = await api.post('/settings/akm-advisor/test')
    testResult.value = { type: 'success', message: data.message }
    // Auto-fetch resources on successful test
    fetchResources()
  } catch (e) {
    testResult.value = { type: 'error', message: e.response?.data?.detail || 'Connection failed' }
  } finally {
    testing.value = false
  }
}

// ── Access Control ──
const allSections = [
  { value: 'projects', label: 'Projects / Tasks', icon: 'mdi-clipboard-list' },
  { value: 'leads', label: 'Leads', icon: 'mdi-account-filter' },
  { value: 'deals', label: 'Deals', icon: 'mdi-handshake' },
  { value: 'contacts', label: 'Contacts', icon: 'mdi-contacts' },
  { value: 'sprints', label: 'Sprints', icon: 'mdi-run-fast' },
  { value: 'epics', label: 'Epics', icon: 'mdi-bookmark-multiple' },
  { value: 'goals', label: 'Goals', icon: 'mdi-target' },
]

const access = ref({
  full_access: true,
  allowed_sections: ['projects', 'leads', 'deals', 'contacts', 'sprints', 'epics', 'goals'],
  allowed_lead_boards: [],
  allowed_deal_boards: [],
})
const origAccess = ref(null)
const savingAccess = ref(false)
const accessSaved = ref(false)

const accessChanged = computed(() => {
  if (!origAccess.value) return false
  return JSON.stringify(access.value) !== JSON.stringify(origAccess.value)
})

const toggleSection = (val) => {
  const idx = access.value.allowed_sections.indexOf(val)
  if (idx >= 0) access.value.allowed_sections.splice(idx, 1)
  else access.value.allowed_sections.push(val)
}

const toggleBoard = (type, id) => {
  const arr = type === 'lead' ? access.value.allowed_lead_boards : access.value.allowed_deal_boards
  const idx = arr.indexOf(id)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(id)
}

const saveAccess = async () => {
  savingAccess.value = true
  accessSaved.value = false
  try {
    await api.put('/settings/akm-advisor/access', access.value)
    origAccess.value = JSON.parse(JSON.stringify(access.value))
    accessSaved.value = true
    showSnackbar('Access settings saved')
    setTimeout(() => { accessSaved.value = false }, 3000)
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save access settings', 'error')
  } finally {
    savingAccess.value = false
  }
}

// ── Available Resources ──
const loadingResources = ref(false)
const projectInfo = ref(null)
const leadBoards = ref([])
const dealBoards = ref([])

const fetchResources = async () => {
  loadingResources.value = true
  try {
    const { data } = await api.get('/settings/akm-advisor/available-resources')
    projectInfo.value = data.project
    leadBoards.value = data.lead_boards || []
    dealBoards.value = data.deal_boards || []
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to load resources', 'error')
  } finally {
    loadingResources.value = false
  }
}

// ── Init ──
onMounted(async () => {
  try {
    await store.fetchSystemSettings()

    // Connection
    if (store.systemSettings.akm_advisor_api_key?.value) {
      conn.value.api_key = store.systemSettings.akm_advisor_api_key.value
      origConn.value.api_key = store.systemSettings.akm_advisor_api_key.value
    }
    if (store.systemSettings.akm_advisor_url?.value) {
      conn.value.url = store.systemSettings.akm_advisor_url.value
      origConn.value.url = store.systemSettings.akm_advisor_url.value
    }

    // Access settings
    try {
      const { data } = await api.get('/settings/akm-advisor/access')
      access.value = {
        full_access: data.full_access ?? true,
        allowed_sections: data.allowed_sections || [],
        allowed_lead_boards: data.allowed_lead_boards || [],
        allowed_deal_boards: data.allowed_deal_boards || [],
      }
    } catch {
      // Keep defaults
    }
    origAccess.value = JSON.parse(JSON.stringify(access.value))

    // Auto-fetch resources if connected
    if (conn.value.api_key && conn.value.url) {
      fetchResources()
    }
  } catch (e) {
    console.error('Failed to load AKM settings', e)
  }
})
</script>
