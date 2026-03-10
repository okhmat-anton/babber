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
          Full access is ON — agent can access all sections. Turn it off to restrict access to specific sections.
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

        <!-- Available Resources Info -->
        <div v-if="resourcesLoaded" class="mb-4">
          <v-divider class="mb-3" />
          <div class="text-subtitle-2 mb-2">
            <v-icon size="18" class="mr-1">mdi-cloud-check</v-icon>
            Agent Key Info
          </div>
          <v-row dense>
            <!-- Permissions Overview -->
            <v-col v-if="permissions" cols="12">
              <v-card variant="tonal" density="compact" class="pa-3">
                <div class="d-flex align-center ga-2 mb-3">
                  <v-chip size="small" variant="tonal" :color="permissions.allow_all ? 'success' : 'info'" prepend-icon="mdi-key">
                    {{ permissions.allow_all ? 'Full Access' : 'Restricted Access' }}
                  </v-chip>
                  <span class="font-weight-medium">{{ permissions.key_name }}</span>
                  <v-chip v-if="permissions.key_source" size="x-small" variant="outlined" class="ml-1">
                    {{ permissions.key_source === 'tenant' ? 'Tenant key' : 'Project key' }}
                  </v-chip>
                </div>

                <!-- Allowed Sections -->
                <div v-if="permissions.sections?.length" class="mb-3">
                  <div class="text-caption text-grey mb-1">Allowed Sections ({{ permissions.sections.length }})</div>
                  <div class="d-flex flex-wrap ga-1">
                    <v-chip v-for="sec in permissions.sections" :key="sec" size="x-small" variant="outlined" color="primary">
                      {{ sectionLabel(sec) }}
                    </v-chip>
                  </div>
                </div>

                <!-- Access Scope: Projects, Pipelines -->
                <div class="d-flex flex-wrap ga-3">
                  <!-- Projects -->
                  <div>
                    <div class="text-caption text-grey mb-1">Projects</div>
                    <v-chip v-if="!permissions.projects?.length || (permissions.projects.length === 1 && permissions.projects[0].id === 'all')"
                      size="small" variant="tonal" color="success" prepend-icon="mdi-folder-multiple">
                      All projects
                    </v-chip>
                    <div v-else class="d-flex flex-wrap ga-1">
                      <v-chip v-for="p in permissions.projects" :key="p.id" size="x-small" variant="tonal" color="blue" prepend-icon="mdi-folder">
                        {{ p.name }}
                      </v-chip>
                    </div>
                  </div>
                  <!-- Deal Pipelines -->
                  <div>
                    <div class="text-caption text-grey mb-1">Deal Pipelines</div>
                    <v-chip v-if="!permissions.deal_pipelines?.length || (permissions.deal_pipelines.length === 1 && permissions.deal_pipelines[0].id === 'all')"
                      size="small" variant="tonal" color="success" prepend-icon="mdi-handshake">
                      All pipelines
                    </v-chip>
                    <div v-else class="d-flex flex-wrap ga-1">
                      <v-chip v-for="p in permissions.deal_pipelines" :key="p.id" size="x-small" variant="tonal" color="green" prepend-icon="mdi-handshake">
                        {{ p.name }}
                      </v-chip>
                    </div>
                  </div>
                  <!-- Lead Pipelines -->
                  <div>
                    <div class="text-caption text-grey mb-1">Lead Pipelines</div>
                    <v-chip v-if="!permissions.lead_pipelines?.length || (permissions.lead_pipelines.length === 1 && permissions.lead_pipelines[0].id === 'all')"
                      size="small" variant="tonal" color="success" prepend-icon="mdi-account-arrow-right">
                      All pipelines
                    </v-chip>
                    <div v-else class="d-flex flex-wrap ga-1">
                      <v-chip v-for="p in permissions.lead_pipelines" :key="p.id" size="x-small" variant="tonal" color="blue" prepend-icon="mdi-account-arrow-right">
                        {{ p.name }}
                      </v-chip>
                    </div>
                  </div>
                </div>
              </v-card>
            </v-col>

            <!-- Connected Project Context -->
            <v-col v-if="projectInfo" cols="12" md="6">
              <v-card variant="tonal" density="compact" class="pa-3">
                <div class="text-caption text-grey mb-1">Connected Project</div>
                <div class="d-flex align-center ga-2">
                  <v-chip variant="tonal" color="blue" size="small">{{ projectInfo.key }}</v-chip>
                  <span class="font-weight-medium">{{ projectInfo.name }}</span>
                </div>
                <div v-if="issuesCount" class="text-caption text-grey mt-1">{{ issuesCount }} issues total</div>
                <div v-if="projectInfo.statuses?.length" class="d-flex flex-wrap ga-1 mt-2">
                  <v-chip v-for="st in projectInfo.statuses" :key="st" size="x-small" variant="outlined">{{ st }}</v-chip>
                </div>
              </v-card>
            </v-col>
          </v-row>
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
  { value: 'wiki', label: 'Knowledge Base', icon: 'mdi-book-open-variant' },
  { value: 'email', label: 'Email', icon: 'mdi-email' },
  { value: 'my-tasks', label: 'My Tasks', icon: 'mdi-checkbox-marked-circle' },
  { value: 'business-ideas', label: 'Business Ideas', icon: 'mdi-lightbulb-on' },
  { value: 'leads', label: 'Leads', icon: 'mdi-account-arrow-right' },
  { value: 'deals', label: 'Deals', icon: 'mdi-handshake' },
  { value: 'contacts', label: 'Contacts', icon: 'mdi-contacts' },
  { value: 'companies', label: 'Companies', icon: 'mdi-domain' },
  { value: 'goals', label: 'Goals', icon: 'mdi-flag-checkered' },
  { value: 'projects', label: 'Projects', icon: 'mdi-folder-multiple' },
  { value: 'project-board', label: 'Project Board', icon: 'mdi-view-column' },
  { value: 'backlog', label: 'Backlog', icon: 'mdi-clipboard-list' },
  { value: 'sprints', label: 'Sprints', icon: 'mdi-run-fast' },
  { value: 'roadmap', label: 'Roadmap', icon: 'mdi-map-marker-path' },
]

const access = ref({
  full_access: true,
  allowed_sections: [],
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

const sectionLabel = (id) => {
  const found = allSections.find(s => s.value === id)
  return found ? found.label : id
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
const resourcesLoaded = ref(false)
const projectInfo = ref(null)
const issuesCount = ref(0)
const permissions = ref(null)

const fetchResources = async () => {
  loadingResources.value = true
  try {
    const { data } = await api.get('/settings/akm-advisor/available-resources')
    projectInfo.value = data.project
    issuesCount.value = data.issues_count || 0
    permissions.value = data.permissions
    resourcesLoaded.value = true
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
