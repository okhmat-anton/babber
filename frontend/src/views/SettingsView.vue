<template>
  <div>
    <div class="text-h4 font-weight-bold mb-6">Settings</div>

    <!-- System Settings -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2">mdi-shield-lock</v-icon>System Access Controls
      </v-card-title>
      <v-card-text>
        <!-- File System Access -->
        <v-row align="center" class="mb-2">
          <v-col cols="auto">
            <v-switch
              v-model="fsAccessEnabled"
              color="error"
              :loading="fsToggling"
              hide-details
              @update:model-value="(v) => onToggle('filesystem_access_enabled', v, 'fs')"
            >
              <template #label>
                <div>
                  <span class="font-weight-medium">File System Access</span>
                  <div class="text-caption text-medium-emphasis">
                    Read, write, and delete files on this computer
                  </div>
                </div>
              </template>
            </v-switch>
          </v-col>
          <v-col cols="auto">
            <v-chip :color="fsAccessEnabled ? 'error' : 'grey'" size="small" variant="flat">
              {{ fsAccessEnabled ? 'ENABLED' : 'DISABLED' }}
            </v-chip>
          </v-col>
        </v-row>

        <!-- System Access (Terminal + Processes) -->
        <v-row align="center" class="mb-2">
          <v-col cols="auto">
            <v-switch
              v-model="sysAccessEnabled"
              color="error"
              :loading="sysToggling"
              hide-details
              @update:model-value="(v) => onToggle('system_access_enabled', v, 'sys')"
            >
              <template #label>
                <div>
                  <span class="font-weight-medium">System Access</span>
                  <div class="text-caption text-medium-emphasis">
                    Execute terminal commands, manage processes, view system info
                  </div>
                </div>
              </template>
            </v-switch>
          </v-col>
          <v-col cols="auto">
            <v-chip :color="sysAccessEnabled ? 'error' : 'grey'" size="small" variant="flat">
              {{ sysAccessEnabled ? 'ENABLED' : 'DISABLED' }}
            </v-chip>
          </v-col>
        </v-row>

        <v-alert v-if="fsAccessEnabled || sysAccessEnabled" type="warning" variant="tonal" density="compact" class="mt-3">
          <strong>Warning:</strong>
          <span v-if="fsAccessEnabled && sysAccessEnabled">Full system access is enabled — the system can modify files, execute commands and manage processes.</span>
          <span v-else-if="fsAccessEnabled">File system access is enabled — the system can read, modify, and delete any files.</span>
          <span v-else>System access is enabled — the system can execute commands and manage processes.</span>
          Use with caution.
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- Change Password -->
    <v-card class="mb-6">
      <v-card-title>Change Password</v-card-title>
      <v-card-text>
        <v-form @submit.prevent="changePassword">
          <v-row>
            <v-col cols="4">
              <v-text-field v-model="oldPass" label="Old Password" type="password" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="newPass" label="New Password" type="password" />
            </v-col>
            <v-col cols="4" class="d-flex align-center">
              <v-btn type="submit" color="primary" :loading="saving">Change</v-btn>
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>
    </v-card>

    <!-- Audio & AI API Keys -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2">mdi-volume-high</v-icon>Audio & AI API Keys
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="6">
            <v-select
              v-model="audioSettings.tts_provider"
              :items="['openai', 'minimax']"
              label="TTS Provider"
              variant="outlined"
              density="compact"
              hide-details
              @update:model-value="(v) => saveAudioSetting('tts_provider', v)"
            />
          </v-col>
          <v-col cols="6">
            <v-select
              v-model="audioSettings.stt_provider"
              :items="['openai']"
              label="STT Provider"
              variant="outlined"
              density="compact"
              hide-details
              @update:model-value="(v) => saveAudioSetting('stt_provider', v)"
            />
          </v-col>
        </v-row>
        <v-row class="mt-2">
          <v-col cols="12">
            <v-text-field
              v-model="audioSettings.openai_api_key"
              label="OpenAI API Key"
              :type="showOpenaiKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="sk-..."
              :append-inner-icon="showOpenaiKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showOpenaiKey = !showOpenaiKey"
              @blur="saveAudioSetting('openai_api_key', audioSettings.openai_api_key)"
            />
          </v-col>
        </v-row>
        <v-row class="mt-2">
          <v-col cols="8">
            <v-text-field
              v-model="audioSettings.minimax_api_key"
              label="MiniMax API Key"
              :type="showMinimaxKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              :append-inner-icon="showMinimaxKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showMinimaxKey = !showMinimaxKey"
              @blur="saveAudioSetting('minimax_api_key', audioSettings.minimax_api_key)"
            />
          </v-col>
          <v-col cols="4">
            <v-text-field
              v-model="audioSettings.minimax_group_id"
              label="MiniMax Group ID"
              variant="outlined"
              density="compact"
              hide-details
              @blur="saveAudioSetting('minimax_group_id', audioSettings.minimax_group_id)"
            />
          </v-col>
        </v-row>
        <v-alert type="info" variant="tonal" density="compact" class="mt-4">
          API keys are used for TTS (Text-to-Speech) and STT (Speech-to-Text) features.
          OpenAI key is required for Whisper STT and TTS-1. MiniMax key for MiniMax TTS.
        </v-alert>
      </v-card-text>
    </v-card>

    <v-row>
      <v-col cols="6">
        <v-card>
          <v-card-title>
            <v-icon class="mr-2">mdi-brain</v-icon>Models
          </v-card-title>
          <v-card-text>Manage LLM provider connections</v-card-text>
          <v-card-actions><v-btn to="/models" color="primary">Manage Models</v-btn></v-card-actions>
        </v-card>
      </v-col>
      <v-col cols="6">
        <v-card>
          <v-card-title>
            <v-icon class="mr-2">mdi-key</v-icon>API Keys
          </v-card-title>
          <v-card-text>Manage API keys for VSCode / external clients</v-card-text>
          <v-card-actions><v-btn to="/settings/api-keys" color="primary">Manage Keys</v-btn></v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- Confirmation dialog for enabling dangerous features -->
    <v-dialog v-model="confirmDialog" max-width="520" persistent>
      <v-card>
        <v-card-title class="text-h6">
          <v-icon color="error" class="mr-2">mdi-shield-alert</v-icon>
          {{ confirmTitle }}
        </v-card-title>
        <v-card-text>
          <v-alert type="error" variant="tonal" class="mb-4">
            {{ confirmMessage }}
          </v-alert>
          <p class="mb-3">To confirm, type <strong>ENABLE</strong> below:</p>
          <v-text-field
            v-model="confirmText"
            label="Type ENABLE to confirm"
            variant="outlined"
            density="compact"
            autofocus
            @keyup.enter="confirmText === 'ENABLE' && doEnable()"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="cancelToggle">Cancel</v-btn>
          <v-btn
            color="error"
            variant="flat"
            :disabled="confirmText !== 'ENABLE'"
            :loading="fsToggling || sysToggling"
            @click="doEnable"
          >
            Enable Access
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, inject, onMounted } from 'vue'
import { useSettingsStore } from '../stores/settings'

const store = useSettingsStore()
const showSnackbar = inject('showSnackbar')

// Password
const oldPass = ref('')
const newPass = ref('')
const saving = ref(false)

// Toggles
const fsAccessEnabled = ref(false)
const sysAccessEnabled = ref(false)
const fsToggling = ref(false)
const sysToggling = ref(false)

// Audio settings
const audioSettings = ref({
  tts_provider: 'openai',
  stt_provider: 'openai',
  openai_api_key: '',
  minimax_api_key: '',
  minimax_group_id: '',
})
const showOpenaiKey = ref(false)
const showMinimaxKey = ref(false)

// Confirmation dialog
const confirmDialog = ref(false)
const confirmText = ref('')
const confirmTitle = ref('')
const confirmMessage = ref('')
const pendingKey = ref('')
const pendingType = ref('')

const toggleLabels = {
  filesystem_access_enabled: {
    title: 'Enable File System Access?',
    message: 'This will grant full access to read, write, and delete files on this computer. This is a potentially dangerous operation.',
    enabledMsg: 'File system access enabled',
    disabledMsg: 'File system access disabled',
  },
  system_access_enabled: {
    title: 'Enable System Access?',
    message: 'This will allow executing arbitrary shell commands, managing processes (including killing them), and accessing full system information. This is a potentially dangerous operation.',
    enabledMsg: 'System access enabled',
    disabledMsg: 'System access disabled',
  },
}

onMounted(async () => {
  try {
    await store.fetchSystemSettings()
    fsAccessEnabled.value = store.systemSettings.filesystem_access_enabled?.value === 'true'
    sysAccessEnabled.value = store.systemSettings.system_access_enabled?.value === 'true'
    // Load audio settings
    const audioKeys = ['tts_provider', 'stt_provider', 'openai_api_key', 'minimax_api_key', 'minimax_group_id']
    for (const key of audioKeys) {
      if (store.systemSettings[key]?.value) {
        audioSettings.value[key] = store.systemSettings[key].value
      }
    }
  } catch (e) {
    console.error('Failed to load system settings', e)
  }
})

const saveAudioSetting = async (key, value) => {
  try {
    await store.updateSystemSetting(key, value)
    showSnackbar(`${key} saved`)
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save setting', 'error')
  }
}

const onToggle = (key, newVal, type) => {
  if (newVal) {
    // Revert until confirmed
    if (type === 'fs') fsAccessEnabled.value = false
    if (type === 'sys') sysAccessEnabled.value = false
    const labels = toggleLabels[key]
    confirmTitle.value = labels.title
    confirmMessage.value = labels.message
    pendingKey.value = key
    pendingType.value = type
    confirmText.value = ''
    confirmDialog.value = true
  } else {
    doDisable(key, type)
  }
}

const doEnable = async () => {
  const key = pendingKey.value
  const type = pendingType.value
  const labels = toggleLabels[key]
  const loading = type === 'fs' ? fsToggling : sysToggling
  loading.value = true
  try {
    await store.updateSystemSetting(key, 'true')
    if (type === 'fs') fsAccessEnabled.value = true
    if (type === 'sys') sysAccessEnabled.value = true
    confirmDialog.value = false
    showSnackbar(labels.enabledMsg, 'warning')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Error', 'error')
  } finally {
    loading.value = false
  }
}

const doDisable = async (key, type) => {
  const labels = toggleLabels[key]
  const loading = type === 'fs' ? fsToggling : sysToggling
  loading.value = true
  try {
    await store.updateSystemSetting(key, 'false')
    if (type === 'fs') fsAccessEnabled.value = false
    if (type === 'sys') sysAccessEnabled.value = false
    showSnackbar(labels.disabledMsg)
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Error', 'error')
    // Revert
    if (type === 'fs') fsAccessEnabled.value = true
    if (type === 'sys') sysAccessEnabled.value = true
  } finally {
    loading.value = false
  }
}

const cancelToggle = () => {
  confirmDialog.value = false
  confirmText.value = ''
}

const changePassword = async () => {
  saving.value = true
  try {
    await store.changePassword(oldPass.value, newPass.value)
    showSnackbar('Password changed')
    oldPass.value = ''
    newPass.value = ''
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Error', 'error')
  } finally {
    saving.value = false
  }
}
</script>
