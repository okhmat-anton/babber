<template>
  <div>
    <!-- Cloud MongoDB Configuration -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2" color="green">mdi-database-sync</v-icon>Cloud MongoDB
      </v-card-title>
      <v-card-text>
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Connect a remote MongoDB instance to sync data between devices.
          Use MongoDB Atlas, self-hosted, or any MongoDB provider.
        </v-alert>

        <v-row>
          <v-col cols="12">
            <v-text-field
              v-model="mongoSettings.cloud_mongodb_url"
              label="Cloud MongoDB URL"
              :type="showMongoUrl ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="mongodb+srv://user:pass@cluster.mongodb.net/ai_agents"
              :append-inner-icon="showMongoUrl ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showMongoUrl = !showMongoUrl"
            />
          </v-col>
        </v-row>

        <v-row class="mt-2">
          <v-col cols="12" class="d-flex align-center ga-2">
            <v-btn
              color="primary"
              :disabled="!mongoSettingsChanged"
              :loading="savingMongo"
              @click="saveMongoSettings"
            >
              <v-icon start>mdi-content-save</v-icon>
              Save
            </v-btn>
            <v-btn
              variant="tonal"
              color="info"
              :loading="testingMongo"
              :disabled="!mongoSettings.cloud_mongodb_url"
              @click="testMongoConnection"
            >
              <v-icon start>mdi-connection</v-icon>
              Test Connection
            </v-btn>
          </v-col>
        </v-row>

        <v-alert
          v-if="mongoTestResult"
          :type="mongoTestResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="mongoTestResult = null"
        >
          <span v-html="mongoTestResult.message"></span>
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- S3 Storage Configuration -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2" color="orange">mdi-cloud-upload</v-icon>S3 File Storage
      </v-card-title>
      <v-card-text>
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Store uploaded files (avatars, audio, chat media) in S3-compatible storage.
          Supports AWS S3, MinIO, DigitalOcean Spaces, Backblaze B2, Cloudflare R2.
        </v-alert>

        <v-row>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="s3Settings.s3_endpoint_url"
              label="S3 Endpoint URL (optional for AWS)"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="https://s3.amazonaws.com or https://nyc3.digitaloceanspaces.com"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="s3Settings.s3_region"
              label="Region"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="us-east-1"
            />
          </v-col>
        </v-row>

        <v-row>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="s3Settings.s3_bucket_name"
              label="Bucket Name"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="my-ai-agents-bucket"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="s3Settings.s3_access_key"
              label="Access Key"
              :type="showS3AccessKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              :append-inner-icon="showS3AccessKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showS3AccessKey = !showS3AccessKey"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="s3Settings.s3_secret_key"
              label="Secret Key"
              :type="showS3SecretKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              :append-inner-icon="showS3SecretKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showS3SecretKey = !showS3SecretKey"
            />
          </v-col>
        </v-row>

        <v-row class="mt-2">
          <v-col cols="12" class="d-flex align-center ga-2">
            <v-btn
              color="primary"
              :disabled="!s3SettingsChanged"
              :loading="savingS3"
              @click="saveS3Settings"
            >
              <v-icon start>mdi-content-save</v-icon>
              Save
            </v-btn>
            <v-btn
              variant="tonal"
              color="info"
              :loading="testingS3"
              :disabled="!s3Settings.s3_access_key || !s3Settings.s3_secret_key || !s3Settings.s3_bucket_name"
              @click="testS3Connection"
            >
              <v-icon start>mdi-connection</v-icon>
              Test Connection
            </v-btn>
          </v-col>
        </v-row>

        <v-alert
          v-if="s3TestResult"
          :type="s3TestResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="s3TestResult = null"
        >
          <span v-html="s3TestResult.message"></span>
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- Data Synchronization -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2" color="blue">mdi-sync</v-icon>Data Synchronization
      </v-card-title>
      <v-card-text>
        <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
          Sync appends only missing documents — existing data is never overwritten or deleted.
        </v-alert>

        <!-- Sync Status -->
        <div v-if="syncStatus" class="mb-4">
          <div class="text-subtitle-2 mb-2">Database Comparison</div>
          <v-table density="compact" class="mb-3">
            <thead>
              <tr>
                <th>Collection</th>
                <th class="text-right">Local</th>
                <th class="text-right">Cloud</th>
                <th class="text-right">Diff</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in syncStatus.collections" :key="c.collection">
                <td>{{ c.collection }}</td>
                <td class="text-right">{{ c.local_count }}</td>
                <td class="text-right">{{ c.cloud_count }}</td>
                <td class="text-right">
                  <v-chip
                    v-if="c.diff !== 0"
                    :color="c.diff > 0 ? 'blue' : 'orange'"
                    size="x-small"
                    variant="flat"
                  >
                    {{ c.diff > 0 ? '+' : '' }}{{ c.diff }}
                  </v-chip>
                  <v-chip v-else color="success" size="x-small" variant="flat">
                    =
                  </v-chip>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="font-weight-bold">
                <td>Total</td>
                <td class="text-right">{{ syncStatus.total_local }}</td>
                <td class="text-right">{{ syncStatus.total_cloud }}</td>
                <td class="text-right">
                  {{ syncStatus.total_local - syncStatus.total_cloud > 0 ? '+' : '' }}{{ syncStatus.total_local - syncStatus.total_cloud }}
                </td>
              </tr>
            </tfoot>
          </v-table>
        </div>

        <v-row>
          <v-col cols="12" class="d-flex flex-wrap ga-2">
            <v-btn
              variant="tonal"
              color="info"
              :loading="loadingSyncStatus"
              :disabled="!mongoSettings.cloud_mongodb_url"
              @click="fetchSyncStatus"
            >
              <v-icon start>mdi-compare-horizontal</v-icon>
              Compare Databases
            </v-btn>

            <v-btn
              color="blue"
              :loading="syncingLocalToCloud"
              :disabled="!mongoSettings.cloud_mongodb_url"
              @click="startSync('local_to_cloud', 'db')"
            >
              <v-icon start>mdi-cloud-upload</v-icon>
              Local → Cloud (DB)
            </v-btn>

            <v-btn
              color="orange"
              :loading="syncingCloudToLocal"
              :disabled="!mongoSettings.cloud_mongodb_url"
              @click="startSync('cloud_to_local', 'db')"
            >
              <v-icon start>mdi-cloud-download</v-icon>
              Cloud → Local (DB)
            </v-btn>
          </v-col>
        </v-row>

        <!-- File Sync (S3) -->
        <v-divider class="my-4" />
        <div class="text-subtitle-2 mb-2">File Synchronization (S3)</div>

        <v-row>
          <v-col cols="12" class="d-flex flex-wrap ga-2">
            <v-btn
              color="blue"
              variant="tonal"
              :loading="syncingFilesUp"
              :disabled="!s3Configured"
              @click="startSync('local_to_cloud', 'files')"
            >
              <v-icon start>mdi-folder-upload</v-icon>
              Upload Files → S3
            </v-btn>

            <v-btn
              color="orange"
              variant="tonal"
              :loading="syncingFilesDown"
              :disabled="!s3Configured"
              @click="startSync('cloud_to_local', 'files')"
            >
              <v-icon start>mdi-folder-download</v-icon>
              Download Files ← S3
            </v-btn>
          </v-col>
        </v-row>

        <v-alert
          v-if="syncResult"
          :type="syncResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="syncResult = null"
        >
          <span v-html="syncResult.message"></span>
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- Backup to Cloud -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2" color="purple">mdi-backup-restore</v-icon>Cloud Backups
      </v-card-title>
      <v-card-text>
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Create full system backups and store them in S3. Backups include all MongoDB data, ChromaDB vectors, and data files.
        </v-alert>

        <v-row>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="backupNote"
              label="Backup note (optional)"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="Description for this backup"
            />
          </v-col>
          <v-col cols="12" md="6" class="d-flex align-center ga-2">
            <v-btn
              color="success"
              :loading="creatingLocalBackup"
              @click="createLocalBackup"
            >
              <v-icon start>mdi-content-save</v-icon>
              Local Backup
            </v-btn>
            <v-btn
              color="purple"
              :loading="creatingS3Backup"
              :disabled="!s3Configured"
              @click="createS3Backup"
            >
              <v-icon start>mdi-cloud-lock</v-icon>
              Backup to S3
            </v-btn>
            <v-btn
              variant="tonal"
              :loading="loadingS3Backups"
              :disabled="!s3Configured"
              @click="fetchS3Backups"
            >
              <v-icon start>mdi-format-list-bulleted</v-icon>
              S3 Backups
            </v-btn>
          </v-col>
        </v-row>

        <v-alert
          v-if="backupResult"
          :type="backupResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="backupResult = null"
        >
          <span v-html="backupResult.message"></span>
        </v-alert>

        <!-- S3 Backups List -->
        <div v-if="s3Backups.length > 0" class="mt-4">
          <div class="text-subtitle-2 mb-2">Backups in S3</div>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Filename</th>
                <th class="text-right">Size</th>
                <th class="text-right">Date</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in s3Backups" :key="b.s3_key">
                <td>{{ b.filename }}</td>
                <td class="text-right">{{ formatSize(b.size_bytes) }}</td>
                <td class="text-right">{{ formatDate(b.last_modified) }}</td>
                <td class="text-right">
                  <v-btn
                    variant="text"
                    color="blue"
                    size="small"
                    :loading="restoringBackup === b.filename"
                    @click="restoreFromS3(b.filename)"
                  >
                    <v-icon>mdi-restore</v-icon>
                    Restore
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-card-text>
    </v-card>

    <!-- Confirm Restore Dialog -->
    <v-dialog v-model="confirmRestoreDialog" max-width="520" persistent>
      <v-card>
        <v-card-title class="text-h6">
          <v-icon color="warning" class="mr-2">mdi-alert</v-icon>
          Restore from S3 Backup?
        </v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" class="mb-4">
            This will <strong>replace all current data</strong> with the backup data.
            Current data will be lost. Make a local backup first if needed.
          </v-alert>
          <p class="mb-3">To confirm, type <strong>RESTORE</strong> below:</p>
          <v-text-field
            v-model="confirmRestoreText"
            label="Type RESTORE to confirm"
            variant="outlined"
            density="compact"
            autofocus
            @keyup.enter="confirmRestoreText === 'RESTORE' && doRestore()"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="confirmRestoreDialog = false">Cancel</v-btn>
          <v-btn
            color="warning"
            variant="flat"
            :disabled="confirmRestoreText !== 'RESTORE'"
            :loading="restoringBackup !== null"
            @click="doRestore"
          >
            Restore
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, inject, onMounted } from 'vue'
import { useSettingsStore } from '../stores/settings'
import api from '../api'

const store = useSettingsStore()
const showSnackbar = inject('showSnackbar')

// --- MongoDB Settings ---
const mongoSettings = ref({ cloud_mongodb_url: '' })
const originalMongoSettings = ref({ cloud_mongodb_url: '' })
const showMongoUrl = ref(false)
const savingMongo = ref(false)
const testingMongo = ref(false)
const mongoTestResult = ref(null)

const mongoSettingsChanged = computed(() =>
  mongoSettings.value.cloud_mongodb_url !== originalMongoSettings.value.cloud_mongodb_url
)

// --- S3 Settings ---
const s3Settings = ref({
  s3_endpoint_url: '',
  s3_access_key: '',
  s3_secret_key: '',
  s3_bucket_name: '',
  s3_region: 'us-east-1',
})
const originalS3Settings = ref({
  s3_endpoint_url: '',
  s3_access_key: '',
  s3_secret_key: '',
  s3_bucket_name: '',
  s3_region: 'us-east-1',
})
const showS3AccessKey = ref(false)
const showS3SecretKey = ref(false)
const savingS3 = ref(false)
const testingS3 = ref(false)
const s3TestResult = ref(null)

const s3SettingsChanged = computed(() => {
  for (const key of Object.keys(s3Settings.value)) {
    if (s3Settings.value[key] !== originalS3Settings.value[key]) return true
  }
  return false
})

const s3Configured = computed(() =>
  !!(s3Settings.value.s3_access_key && s3Settings.value.s3_secret_key && s3Settings.value.s3_bucket_name)
)

// --- Sync ---
const syncStatus = ref(null)
const loadingSyncStatus = ref(false)
const syncingLocalToCloud = ref(false)
const syncingCloudToLocal = ref(false)
const syncingFilesUp = ref(false)
const syncingFilesDown = ref(false)
const syncResult = ref(null)

// --- Backups ---
const backupNote = ref('')
const creatingLocalBackup = ref(false)
const creatingS3Backup = ref(false)
const loadingS3Backups = ref(false)
const s3Backups = ref([])
const backupResult = ref(null)
const restoringBackup = ref(null)
const confirmRestoreDialog = ref(false)
const confirmRestoreText = ref('')
const pendingRestoreFilename = ref('')

// --- Init ---
onMounted(async () => {
  try {
    await store.fetchSystemSettings()
    const ss = store.systemSettings

    // MongoDB
    if (ss.cloud_mongodb_url?.value) {
      mongoSettings.value.cloud_mongodb_url = ss.cloud_mongodb_url.value
      originalMongoSettings.value.cloud_mongodb_url = ss.cloud_mongodb_url.value
    }

    // S3
    const s3Keys = ['s3_endpoint_url', 's3_access_key', 's3_secret_key', 's3_bucket_name', 's3_region']
    for (const key of s3Keys) {
      if (ss[key]?.value) {
        s3Settings.value[key] = ss[key].value
        originalS3Settings.value[key] = ss[key].value
      }
    }
  } catch (e) {
    console.error('Failed to load cloud settings', e)
  }
})

// --- MongoDB Actions ---
const saveMongoSettings = async () => {
  savingMongo.value = true
  try {
    await store.updateSystemSetting('cloud_mongodb_url', mongoSettings.value.cloud_mongodb_url)
    originalMongoSettings.value.cloud_mongodb_url = mongoSettings.value.cloud_mongodb_url
    showSnackbar('Cloud MongoDB URL saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save', 'error')
  } finally {
    savingMongo.value = false
  }
}

const testMongoConnection = async () => {
  testingMongo.value = true
  mongoTestResult.value = null
  try {
    if (mongoSettingsChanged.value) await saveMongoSettings()
    const { data } = await api.post('/cloud/test-mongodb', { url: mongoSettings.value.cloud_mongodb_url })
    mongoTestResult.value = {
      type: 'success',
      message: `Connected! Database: <strong>${data.database}</strong>, ${data.collections} collections, ${data.total_documents} documents`
    }
  } catch (e) {
    mongoTestResult.value = { type: 'error', message: e.response?.data?.detail || 'Connection failed' }
  } finally {
    testingMongo.value = false
  }
}

// --- S3 Actions ---
const saveS3Settings = async () => {
  savingS3.value = true
  try {
    for (const key of Object.keys(s3Settings.value)) {
      await store.updateSystemSetting(key, s3Settings.value[key])
      originalS3Settings.value[key] = s3Settings.value[key]
    }
    showSnackbar('S3 settings saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save', 'error')
  } finally {
    savingS3.value = false
  }
}

const testS3Connection = async () => {
  testingS3.value = true
  s3TestResult.value = null
  try {
    if (s3SettingsChanged.value) await saveS3Settings()
    const { data } = await api.post('/cloud/test-s3', {
      endpoint_url: s3Settings.value.s3_endpoint_url,
      access_key: s3Settings.value.s3_access_key,
      secret_key: s3Settings.value.s3_secret_key,
      bucket_name: s3Settings.value.s3_bucket_name,
      region: s3Settings.value.s3_region,
    })
    s3TestResult.value = {
      type: 'success',
      message: `Connected! ${data.objects_count} objects, ${formatSize(data.total_size_bytes)} total`
    }
  } catch (e) {
    s3TestResult.value = { type: 'error', message: e.response?.data?.detail || 'Connection failed' }
  } finally {
    testingS3.value = false
  }
}

// --- Sync Actions ---
const fetchSyncStatus = async () => {
  loadingSyncStatus.value = true
  syncResult.value = null
  try {
    const { data } = await api.get('/cloud/sync-status')
    syncStatus.value = data
  } catch (e) {
    syncResult.value = { type: 'error', message: e.response?.data?.detail || 'Failed to compare databases' }
  } finally {
    loadingSyncStatus.value = false
  }
}

const startSync = async (direction, type) => {
  const isDb = type === 'db'
  const isUp = direction === 'local_to_cloud'

  if (isDb) {
    if (isUp) syncingLocalToCloud.value = true
    else syncingCloudToLocal.value = true
  } else {
    if (isUp) syncingFilesUp.value = true
    else syncingFilesDown.value = true
  }

  syncResult.value = null

  try {
    const endpoint = isDb ? '/cloud/sync' : '/cloud/s3-sync-files'
    const { data } = await api.post(endpoint, { direction })

    if (isDb) {
      syncResult.value = {
        type: 'success',
        message: `Sync complete! ${data.documents_copied} documents copied, ${data.documents_skipped} skipped${data.errors?.length ? `, ${data.errors.length} error(s)` : ''}`
      }
      // Refresh status
      await fetchSyncStatus()
    } else {
      syncResult.value = {
        type: 'success',
        message: `File sync complete! ${data.total_files} files ${isUp ? 'uploaded' : 'downloaded'}`
      }
    }
  } catch (e) {
    syncResult.value = { type: 'error', message: e.response?.data?.detail || 'Sync failed' }
  } finally {
    syncingLocalToCloud.value = false
    syncingCloudToLocal.value = false
    syncingFilesUp.value = false
    syncingFilesDown.value = false
  }
}

// --- Backup Actions ---
const createLocalBackup = async () => {
  creatingLocalBackup.value = true
  backupResult.value = null
  try {
    const { data } = await api.post('/backups', { note: backupNote.value || 'Manual backup' })
    backupResult.value = {
      type: 'success',
      message: `Backup created: <strong>${data.filename}</strong> (${formatSize(data.size_bytes)}, ${data.documents_count} docs)`
    }
    backupNote.value = ''
  } catch (e) {
    backupResult.value = { type: 'error', message: e.response?.data?.detail || 'Backup failed' }
  } finally {
    creatingLocalBackup.value = false
  }
}

const createS3Backup = async () => {
  creatingS3Backup.value = true
  backupResult.value = null
  try {
    const { data } = await api.post('/cloud/s3-backup', { note: backupNote.value || 'S3 cloud backup' })
    backupResult.value = {
      type: 'success',
      message: `Backup uploaded to S3: <strong>${data.filename}</strong> (${formatSize(data.size_bytes)}, ${data.documents_count} docs)`
    }
    backupNote.value = ''
    await fetchS3Backups()
  } catch (e) {
    backupResult.value = { type: 'error', message: e.response?.data?.detail || 'S3 backup failed' }
  } finally {
    creatingS3Backup.value = false
  }
}

const fetchS3Backups = async () => {
  loadingS3Backups.value = true
  try {
    const { data } = await api.get('/cloud/s3-backups')
    s3Backups.value = data.backups || []
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to list S3 backups', 'error')
  } finally {
    loadingS3Backups.value = false
  }
}

const restoreFromS3 = (filename) => {
  pendingRestoreFilename.value = filename
  confirmRestoreText.value = ''
  confirmRestoreDialog.value = true
}

const doRestore = async () => {
  const filename = pendingRestoreFilename.value
  restoringBackup.value = filename
  confirmRestoreDialog.value = false
  backupResult.value = null
  try {
    const { data } = await api.post(`/cloud/s3-restore/${filename}`)
    backupResult.value = {
      type: 'success',
      message: `Restored from S3: <strong>${filename}</strong> (${data.documents_count} docs, ${data.data_dirs?.length || 0} directories)`
    }
  } catch (e) {
    backupResult.value = { type: 'error', message: e.response?.data?.detail || 'Restore failed' }
  } finally {
    restoringBackup.value = null
  }
}

// --- Helpers ---
const formatSize = (bytes) => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(1)} ${units[i]}`
}

const formatDate = (isoStr) => {
  if (!isoStr) return ''
  try {
    return new Date(isoStr).toLocaleString()
  } catch {
    return isoStr
  }
}
</script>
