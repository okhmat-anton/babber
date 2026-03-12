<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h1 class="text-h5 font-weight-bold">
        <v-icon class="mr-2">mdi-vpn</v-icon>
        VPN / Proxy
      </h1>
      <v-spacer />
      <v-chip v-if="activeVpn" color="success" variant="tonal" class="mr-3">
        <v-icon start size="16">mdi-shield-check</v-icon>
        Active: {{ activeVpn.name }}
      </v-chip>
      <v-chip v-else color="grey" variant="tonal" class="mr-3">
        <v-icon start size="16">mdi-shield-off-outline</v-icon>
        No active VPN
      </v-chip>
      <v-btn variant="tonal" class="mr-2" @click="openBulkDialog" prepend-icon="mdi-playlist-plus">
        Import List
      </v-btn>
      <v-btn color="primary" @click="openVpnDialog()" prepend-icon="mdi-plus">
        Add VPN
      </v-btn>
    </div>

    <!-- Stats bar -->
    <v-row dense class="mb-4">
      <v-col cols="auto">
        <v-chip variant="tonal" size="small">Total: {{ vpns.length }}</v-chip>
      </v-col>
      <v-col cols="auto">
        <v-chip variant="tonal" color="success" size="small">Working: {{ workingCount }}</v-chip>
      </v-col>
      <v-col cols="auto">
        <v-chip variant="tonal" color="error" size="small">Failed: {{ failedCount }}</v-chip>
      </v-col>
      <v-col cols="auto">
        <v-btn size="small" variant="tonal" @click="testAll" :loading="testingAll" prepend-icon="mdi-lan-check">
          Test All
        </v-btn>
      </v-col>
      <v-col cols="auto" v-if="failedCount > 0">
        <v-btn size="small" variant="tonal" color="error" @click="deleteDead" :loading="deletingDead" prepend-icon="mdi-delete-sweep">
          Delete Failed
        </v-btn>
      </v-col>
    </v-row>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <!-- Empty state -->
    <div v-if="!loading && !vpns.length" class="text-center text-medium-emphasis py-12">
      <v-icon size="80" class="mb-4">mdi-vpn</v-icon>
      <div class="text-h6 mb-2">No VPN proxies configured</div>
      <div class="mb-4">Add proxies manually or import a list to get started.</div>
      <v-btn color="primary" @click="openVpnDialog()" prepend-icon="mdi-plus" class="mr-2">Add VPN</v-btn>
      <v-btn variant="tonal" @click="openBulkDialog" prepend-icon="mdi-playlist-plus">Import List</v-btn>
    </div>

    <!-- VPN Table -->
    <v-card v-if="vpns.length" variant="outlined">
      <v-table density="compact" hover>
        <thead>
          <tr>
            <th style="width: 40px"></th>
            <th>Name</th>
            <th>Protocol</th>
            <th>Host</th>
            <th>Port</th>
            <th>Auth</th>
            <th>Status</th>
            <th>IP</th>
            <th>Last Tested</th>
            <th class="text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="vpn in vpns" :key="vpn.id" :class="vpn.is_active ? 'bg-success-darken-4' : ''">
            <td>
              <v-icon :color="vpn.is_active ? 'success' : 'grey'" size="20">
                {{ vpn.is_active ? 'mdi-shield-check' : 'mdi-shield-outline' }}
              </v-icon>
            </td>
            <td class="font-weight-medium">{{ vpn.name }}</td>
            <td><v-chip size="x-small" variant="outlined">{{ vpn.protocol }}</v-chip></td>
            <td>{{ vpn.host }}</td>
            <td>{{ vpn.port }}</td>
            <td>
              <v-icon v-if="vpn.username" size="16" color="success">mdi-account-check</v-icon>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td>
              <v-chip
                v-if="vpn.status === 'working'"
                size="x-small"
                color="success"
                variant="tonal"
              >working</v-chip>
              <v-chip
                v-else-if="vpn.status === 'failed'"
                size="x-small"
                color="error"
                variant="tonal"
              >failed</v-chip>
              <v-chip v-else size="x-small" variant="tonal">unknown</v-chip>
            </td>
            <td class="text-medium-emphasis" style="font-size: 0.8rem">{{ vpn.last_ip || '—' }}</td>
            <td class="text-medium-emphasis" style="font-size: 0.8rem">{{ formatDate(vpn.last_tested) }}</td>
            <td class="text-right">
              <div class="d-flex align-center justify-end ga-1">
                <v-btn
                  v-if="!vpn.is_active"
                  size="small"
                  variant="tonal"
                  color="success"
                  @click="activateVpn(vpn.id)"
                  :loading="activating === vpn.id"
                  prepend-icon="mdi-power"
                >Activate</v-btn>
                <v-btn
                  v-else
                  size="small"
                  variant="tonal"
                  color="warning"
                  @click="deactivateVpn()"
                  :loading="activating === vpn.id"
                  prepend-icon="mdi-power-off"
                >Off</v-btn>
                <v-btn
                  size="small"
                  variant="tonal"
                  @click="testVpn(vpn.id)"
                  :loading="testing === vpn.id"
                  prepend-icon="mdi-connection"
                >Test</v-btn>
                <v-btn
                  size="small"
                  variant="tonal"
                  @click="openVpnDialog(vpn)"
                  prepend-icon="mdi-pencil"
                >Edit</v-btn>
                <v-btn
                  size="small"
                  variant="tonal"
                  color="error"
                  @click="deleteVpn(vpn)"
                  :loading="deleting === vpn.id"
                  prepend-icon="mdi-delete"
                >Delete</v-btn>
              </div>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- Add/Edit Dialog -->
    <v-dialog v-model="vpnDialog" max-width="500" persistent>
      <v-card>
        <v-card-title>{{ vpnEditing ? 'Edit VPN' : 'Add VPN' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="vpnForm.name"
            label="Name"
            variant="outlined"
            density="compact"
            class="mb-3"
            placeholder="e.g. US Proxy, EU SOCKS"
          />
          <v-select
            v-model="vpnForm.protocol"
            :items="['socks5', 'socks5h', 'http', 'https']"
            label="Protocol"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-row dense class="mb-3">
            <v-col cols="8">
              <v-text-field
                v-model="vpnForm.host"
                label="Host"
                variant="outlined"
                density="compact"
                placeholder="proxy.example.com"
              />
            </v-col>
            <v-col cols="4">
              <v-text-field
                v-model.number="vpnForm.port"
                label="Port"
                variant="outlined"
                density="compact"
                type="number"
                placeholder="1080"
              />
            </v-col>
          </v-row>
          <v-text-field
            v-model="vpnForm.username"
            label="Username (optional)"
            variant="outlined"
            density="compact"
            class="mb-3"
            autocomplete="off"
          />
          <v-text-field
            v-model="vpnForm.password"
            label="Password (optional)"
            variant="outlined"
            density="compact"
            :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
            :type="showPassword ? 'text' : 'password'"
            @click:append-inner="showPassword = !showPassword"
            autocomplete="off"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="vpnDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="saving"
            :disabled="!vpnForm.name || !vpnForm.host || !vpnForm.port"
            @click="saveVpn"
          >
            {{ vpnEditing ? 'Update' : 'Create' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Bulk Import Dialog -->
    <v-dialog v-model="bulkDialog" max-width="700" persistent>
      <v-card>
        <v-card-title>Import VPN List</v-card-title>
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Paste proxy list, one per line. Format is auto-detected.
            You can copy proxies from
            <a href="https://free-proxy-list.net/en/" target="_blank" class="text-decoration-none" style="color: #64B5F6">
              free-proxy-list.net
              <v-icon size="12" class="ml-1">mdi-open-in-new</v-icon>
            </a>
            or any other source.
          </p>
          <div class="text-body-2 mb-4 pa-3 rounded" style="background: rgba(255,255,255,0.05); font-family: monospace; font-size: 0.85rem">
            socks5://user:pass@host:port<br>
            host:port:user:pass<br>
            user:pass@host:port<br>
            host:port<br>
            <span class="text-medium-emphasis">// Table rows (space/tab separated):</span><br>
            185.10.70.1&nbsp;&nbsp;8080&nbsp;&nbsp;US&nbsp;&nbsp;United States&nbsp;&nbsp;elite proxy&nbsp;&nbsp;no&nbsp;&nbsp;yes
          </div>
          <v-select
            v-model="bulkProtocol"
            :items="['http', 'https', 'socks5', 'socks5h']"
            label="Fallback protocol (used when not auto-detected)"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-textarea
            v-model="bulkText"
            label="Proxy list"
            variant="outlined"
            rows="10"
            placeholder="Paste proxies here, one per line..."
            auto-grow
          />
          <v-alert v-if="bulkResult" :type="bulkResult.added > 0 ? 'success' : 'warning'" variant="tonal" density="compact" class="mt-3">
            Parsed: {{ bulkResult.total_parsed }} |
            Added (working): {{ bulkResult.added }} |
            Failed: {{ bulkResult.failed }}
          </v-alert>
          <v-expansion-panels v-if="bulkResult && bulkResult.details?.length" variant="accordion" class="mt-3">
            <v-expansion-panel title="Details">
              <v-expansion-panel-text>
                <div v-for="(d, i) in bulkResult.details" :key="i" class="text-body-2 mb-1">
                  <v-icon :color="d.success ? 'success' : 'error'" size="16" class="mr-1">
                    {{ d.success ? 'mdi-check-circle' : 'mdi-close-circle' }}
                  </v-icon>
                  {{ d.proxy }}
                  <span v-if="d.ip" class="text-medium-emphasis"> — {{ d.ip }}</span>
                  <span v-if="d.error" class="text-error"> — {{ d.error }}</span>
                </div>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeBulkDialog">Close</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="bulkImporting"
            :disabled="!bulkText.trim()"
            @click="doBulkImport"
          >
            Import & Test
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import api from '@src/api'

const showSnackbar = inject('showSnackbar')

// State
const vpns = ref([])
const loading = ref(false)

// Single VPN dialog
const vpnDialog = ref(false)
const vpnEditing = ref(null)
const vpnForm = ref({ name: '', protocol: 'socks5', host: '', port: 1080, username: '', password: '' })
const saving = ref(false)
const showPassword = ref(false)

// Actions
const testing = ref(null)
const activating = ref(null)
const deleting = ref(null)
const testingAll = ref(false)
const deletingDead = ref(false)

// Bulk import
const bulkDialog = ref(false)
const bulkText = ref('')
const bulkProtocol = ref('http')
const bulkImporting = ref(false)
const bulkResult = ref(null)

// Computed
const activeVpn = computed(() => vpns.value.find(v => v.is_active))
const workingCount = computed(() => vpns.value.filter(v => v.status === 'working').length)
const failedCount = computed(() => vpns.value.filter(v => v.status === 'failed').length)

// Methods
function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadVpns() {
  loading.value = true
  try {
    const { data } = await api.get('/vpn')
    vpns.value = data.items || []
  } catch (e) {
    console.error('Failed to load VPNs:', e)
  } finally {
    loading.value = false
  }
}

function openVpnDialog(vpn = null) {
  if (vpn) {
    vpnEditing.value = vpn.id
    vpnForm.value = {
      name: vpn.name,
      protocol: vpn.protocol,
      host: vpn.host,
      port: vpn.port,
      username: vpn.username || '',
      password: vpn.password || '',
    }
  } else {
    vpnEditing.value = null
    vpnForm.value = { name: '', protocol: 'socks5', host: '', port: 1080, username: '', password: '' }
  }
  showPassword.value = false
  vpnDialog.value = true
}

async function saveVpn() {
  saving.value = true
  try {
    if (vpnEditing.value) {
      await api.patch(`/vpn/${vpnEditing.value}`, vpnForm.value)
      showSnackbar('VPN updated', 'success')
    } else {
      await api.post('/vpn', vpnForm.value)
      showSnackbar('VPN created', 'success')
    }
    vpnDialog.value = false
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save VPN', 'error')
  } finally {
    saving.value = false
  }
}

async function deleteVpn(vpn) {
  if (!confirm(`Delete VPN "${vpn.name}"?`)) return
  deleting.value = vpn.id
  try {
    await api.delete(`/vpn/${vpn.id}`)
    showSnackbar('VPN deleted', 'success')
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to delete VPN', 'error')
  } finally {
    deleting.value = null
  }
}

async function activateVpn(vpnId) {
  activating.value = vpnId
  try {
    await api.post(`/vpn/${vpnId}/activate`)
    showSnackbar('VPN activated', 'success')
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to activate VPN', 'error')
  } finally {
    activating.value = null
  }
}

async function deactivateVpn() {
  activating.value = activeVpn.value?.id
  try {
    await api.post('/vpn/none/activate')
    showSnackbar('VPN deactivated', 'success')
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to deactivate VPN', 'error')
  } finally {
    activating.value = null
  }
}

async function testVpn(vpnId) {
  testing.value = vpnId
  try {
    const { data } = await api.post(`/vpn/${vpnId}/test`)
    if (data.success) {
      showSnackbar(`VPN working! IP: ${data.ip}`, 'success')
    } else {
      showSnackbar(`VPN test failed: ${data.error}`, 'error')
    }
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'VPN test failed', 'error')
  } finally {
    testing.value = null
  }
}

async function testAll() {
  testingAll.value = true
  try {
    const { data } = await api.post('/vpn/test-all')
    showSnackbar(`Tested ${data.total}: ${data.working} working, ${data.failed} failed`, data.working > 0 ? 'success' : 'warning')
    await loadVpns()
  } catch (e) {
    showSnackbar('Failed to test VPNs', 'error')
  } finally {
    testingAll.value = false
  }
}

async function deleteDead() {
  if (!confirm('Delete all failed VPNs?')) return
  deletingDead.value = true
  try {
    const { data } = await api.delete('/vpn/dead')
    showSnackbar(`Deleted ${data.deleted} failed VPN(s)`, 'success')
    await loadVpns()
  } catch (e) {
    showSnackbar('Failed to delete dead VPNs', 'error')
  } finally {
    deletingDead.value = false
  }
}

function openBulkDialog() {
  bulkText.value = ''
  bulkResult.value = null
  bulkDialog.value = true
}

function closeBulkDialog() {
  bulkDialog.value = false
  if (bulkResult.value?.added > 0) {
    loadVpns()
  }
}

async function doBulkImport() {
  bulkImporting.value = true
  bulkResult.value = null
  try {
    const { data } = await api.post('/vpn/bulk-import', {
      text: bulkText.value,
      default_protocol: bulkProtocol.value,
    })
    bulkResult.value = data
    if (data.added > 0) {
      showSnackbar(`Added ${data.added} working VPN(s)`, 'success')
    } else {
      showSnackbar('No working proxies found', 'warning')
    }
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Import failed', 'error')
  } finally {
    bulkImporting.value = false
  }
}

onMounted(() => {
  loadVpns()
})
</script>
