<template>
  <div>

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
      <v-card-title class="d-flex align-center flex-wrap">
        <div>
          <v-icon class="mr-2">mdi-volume-high</v-icon>Kie.ai Settings (audio, gpt, gemini, <a href="https://kie.ai/market" target="_blank">models market</a>) <a href="https://kie.ai/api-key" target="_blank" class="text-primary font-weight-medium">API Key</a>
        </div>
        <v-spacer />
        <v-btn
          variant="tonal"
          color="amber"
          size="small"
          :loading="checkingKieaiBalance"
          :disabled="!audioSettings.kieai_api_key"
          @click="checkKieaiBalance"
          class="ml-2"
        >
          <v-icon start size="16">mdi-wallet-outline</v-icon>
          {{ kieaiBalance !== null ? kieaiBalance : 'Balance' }}
        </v-btn>
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12">
            <v-text-field
              v-model="audioSettings.kieai_api_key"
              label="kie.ai API Key"
              :type="showKieaiKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="Enter your kie.ai API key"
              :append-inner-icon="showKieaiKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showKieaiKey = !showKieaiKey"
            />
          </v-col>
        </v-row>
        <v-row>
          <v-col cols="4">
            <v-text-field
              v-model.number="audioSettings.tts_timeout"
              label="TTS Timeout (seconds)"
              type="number"
              variant="outlined"
              density="compact"
              hide-details
              :min="30"
              :max="600"
              hint="Max time to wait for audio generation (30-600s)"
            />
          </v-col>
        </v-row>
        <v-row class="mt-2">
          <v-col cols="12" class="d-flex align-center ga-2">
            <v-btn
              color="primary"
              :disabled="!audioSettingsChanged"
              :loading="savingAudio"
              @click="saveAudioSettings"
            >
              <v-icon start>mdi-content-save</v-icon>
              Save
            </v-btn>
            <v-btn
              variant="tonal"
              color="info"
              :loading="testingKieai === 'gpt'"
              :disabled="!audioSettings.kieai_api_key || !!testingKieai"
              @click="testKieaiModel('gpt-5-2', 'gpt')"
            >
              <v-icon start>mdi-connection</v-icon>
              Test GPT
            </v-btn>
            <v-btn
              variant="tonal"
              color="info"
              :loading="testingKieai === 'gemini'"
              :disabled="!audioSettings.kieai_api_key || !!testingKieai"
              @click="testKieaiModel('gemini-3.1-pro', 'gemini')"
            >
              <v-icon start>mdi-connection</v-icon>
              Test Gemini
            </v-btn>
          </v-col>
        </v-row>
        <v-alert
          v-if="kieaiTestResult"
          :type="kieaiTestResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="kieaiTestResult = null"
        >
          {{ kieaiTestResult.message }}
        </v-alert>
        <v-alert
          v-if="kieaiBalanceResult"
          :type="kieaiBalanceResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="kieaiBalanceResult = null"
        >
          <span v-html="kieaiBalanceResult.message"></span>
        </v-alert>
        <v-alert type="info" variant="tonal" density="compact" class="mt-4">
          kie.ai API key is used for TTS (Text-to-Speech), STT (Speech-to-Text), and LLM models (GPT-5.2, Gemini 3.1 Pro, Gemini 3 Pro).
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- Anthropic (Claude) API -->
    <v-card class="mb-6">
      <v-card-title class="d-flex align-center flex-wrap">
        <div>
          <v-icon class="mr-2" color="deep-purple">mdi-creation</v-icon>Anthropic (Claude) <a href="https://platform.claude.com/settings/keys" target="_blank" class="text-primary font-weight-medium">API Key</a>
        </div>
        <v-spacer />
        <v-btn
          variant="tonal"
          color="deep-purple"
          size="small"
          :loading="checkingAnthropicBalance"
          :disabled="!anthropicSettings.anthropic_api_key"
          @click="checkAnthropicBalance"
          class="ml-2"
        >
          <v-icon start size="16">mdi-wallet-outline</v-icon>
          {{ anthropicBalance !== null ? anthropicBalance : 'Balance' }}
        </v-btn>
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="8">
            <v-text-field
              v-model="anthropicSettings.anthropic_api_key"
              label="Anthropic API Key"
              :type="showAnthropicKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="sk-ant-..."
              :append-inner-icon="showAnthropicKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showAnthropicKey = !showAnthropicKey"
            />
          </v-col>
          <v-col cols="12" md="4" class="d-flex align-center ga-2">
            <v-btn
              color="primary"
              :disabled="!anthropicSettingsChanged"
              :loading="savingAnthropic"
              @click="saveAnthropicSettings"
            >
              <v-icon start>mdi-content-save</v-icon>
              Save
            </v-btn>
            <v-btn
              variant="tonal"
              color="info"
              :loading="testingAnthropic"
              :disabled="!anthropicSettings.anthropic_api_key"
              @click="testAnthropicConnection"
            >
              <v-icon start>mdi-connection</v-icon>
              Test
            </v-btn>
          </v-col>
        </v-row>
        <v-alert
          v-if="anthropicTestResult"
          :type="anthropicTestResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="anthropicTestResult = null"
        >
          {{ anthropicTestResult.message }}
        </v-alert>
        <v-alert
          v-if="anthropicBalanceResult"
          :type="anthropicBalanceResult.type"
          variant="tonal"
          density="compact"
          class="mt-3"
          closable
          @click:close="anthropicBalanceResult = null"
        >
          <span v-html="anthropicBalanceResult.message"></span>
        </v-alert>
        <v-alert type="info" variant="tonal" density="compact" class="mt-3">
          Get your API key at <a href="https://console.anthropic.com/settings/keys" target="_blank" class="text-primary">console.anthropic.com</a>.
          After saving the key, select "anthropic" as provider when adding a model in <strong>Models</strong>.
        </v-alert>
      </v-card-text>
    </v-card>

    <!-- ScrapeCreators (Video Transcripts) -->
    <v-card class="mb-6">
      <v-card-title>
        <v-icon class="mr-2" color="teal">mdi-video-outline</v-icon>ScrapeCreators (Video Transcripts) <a href="https://app.scrapecreators.com" target="_blank" class="text-primary font-weight-medium">API Key</a>
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="8">
            <v-text-field
              v-model="scrapcreatorsSettings.scrapecreators_api_key"
              label="ScrapeCreators API Key"
              :type="showScrapcreatorsKey ? 'text' : 'password'"
              variant="outlined"
              density="compact"
              hide-details
              placeholder="Enter your ScrapeCreators API key"
              :append-inner-icon="showScrapcreatorsKey ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="showScrapcreatorsKey = !showScrapcreatorsKey"
            />
          </v-col>
          <v-col cols="12" md="4" class="d-flex align-center ga-2">
            <v-btn
              color="primary"
              :disabled="!scrapcreatorsSettingsChanged"
              :loading="savingScrapcreators"
              @click="saveScrapcreatorsSettings"
            >
              <v-icon start>mdi-content-save</v-icon>
              Save
            </v-btn>
          </v-col>
        </v-row>
        <v-alert type="info" variant="tonal" density="compact" class="mt-3">
          ScrapeCreators API is used by the <strong>video_watch</strong> skill to fetch video transcripts from
          YouTube, TikTok, Instagram, Facebook, and Twitter.
          Get your API key at <a href="https://app.scrapecreators.com" target="_blank" class="text-primary">app.scrapecreators.com</a>.
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
import { ref, inject, onMounted, computed } from 'vue'
import { useSettingsStore } from '../stores/settings'
import api from '../api'

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
  kieai_api_key: '',
  tts_timeout: 120,
})
const originalAudioSettings = ref({
  kieai_api_key: '',
  tts_timeout: 120,
})
const showKieaiKey = ref(false)
const savingAudio = ref(false)

const audioSettingsChanged = computed(() => {
  return audioSettings.value.kieai_api_key !== originalAudioSettings.value.kieai_api_key
    || String(audioSettings.value.tts_timeout) !== String(originalAudioSettings.value.tts_timeout)
})

// kie.ai test
const testingKieai = ref(null)     // 'gpt' | 'gemini' | null
const kieaiTestResult = ref(null)
const checkingKieaiBalance = ref(false)
const kieaiBalance = ref(null)         // display string or null
const kieaiBalanceResult = ref(null)   // { type, message }

// Anthropic settings
const anthropicSettings = ref({ anthropic_api_key: '' })
const originalAnthropicSettings = ref({ anthropic_api_key: '' })
const showAnthropicKey = ref(false)
const savingAnthropic = ref(false)
const testingAnthropic = ref(false)
const anthropicTestResult = ref(null)
const checkingAnthropicBalance = ref(false)
const anthropicBalance = ref(null)         // display string or null
const anthropicBalanceResult = ref(null)   // { type, message }

const anthropicSettingsChanged = computed(() => {
  return anthropicSettings.value.anthropic_api_key !== originalAnthropicSettings.value.anthropic_api_key
})

// ScrapeCreators settings
const scrapcreatorsSettings = ref({ scrapecreators_api_key: '' })
const originalScrapcreatorsSettings = ref({ scrapecreators_api_key: '' })
const showScrapcreatorsKey = ref(false)
const savingScrapcreators = ref(false)

const scrapcreatorsSettingsChanged = computed(() => {
  return scrapcreatorsSettings.value.scrapecreators_api_key !== originalScrapcreatorsSettings.value.scrapecreators_api_key
})

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
    const audioKeys = ['kieai_api_key', 'tts_timeout']
    for (const key of audioKeys) {
      if (store.systemSettings[key]?.value) {
        const val = key === 'tts_timeout' ? Number(store.systemSettings[key].value) : store.systemSettings[key].value
        audioSettings.value[key] = val
        originalAudioSettings.value[key] = val
      }
    }
    // Load Anthropic settings
    if (store.systemSettings.anthropic_api_key?.value) {
      anthropicSettings.value.anthropic_api_key = store.systemSettings.anthropic_api_key.value
      originalAnthropicSettings.value.anthropic_api_key = store.systemSettings.anthropic_api_key.value
    }
    // Load ScrapeCreators settings
    if (store.systemSettings.scrapecreators_api_key?.value) {
      scrapcreatorsSettings.value.scrapecreators_api_key = store.systemSettings.scrapecreators_api_key.value
      originalScrapcreatorsSettings.value.scrapecreators_api_key = store.systemSettings.scrapecreators_api_key.value
    }
  } catch (e) {
    console.error('Failed to load system settings', e)
  }
})

const saveAnthropicSettings = async () => {
  savingAnthropic.value = true
  try {
    await store.updateSystemSetting('anthropic_api_key', anthropicSettings.value.anthropic_api_key)
    originalAnthropicSettings.value.anthropic_api_key = anthropicSettings.value.anthropic_api_key
    showSnackbar('Anthropic API key saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save Anthropic key', 'error')
  } finally {
    savingAnthropic.value = false
  }
}

const testAnthropicConnection = async () => {
  testingAnthropic.value = true
  anthropicTestResult.value = null
  try {
    // Save first if changed
    if (anthropicSettingsChanged.value) {
      await store.updateSystemSetting('anthropic_api_key', anthropicSettings.value.anthropic_api_key)
      originalAnthropicSettings.value.anthropic_api_key = anthropicSettings.value.anthropic_api_key
    }
    const { data } = await api.post('/settings/anthropic/test')
    anthropicTestResult.value = { type: 'success', message: data.message }
  } catch (e) {
    anthropicTestResult.value = { type: 'error', message: e.response?.data?.detail || 'Connection failed' }
  } finally {
    testingAnthropic.value = false
  }
}

const saveScrapcreatorsSettings = async () => {
  savingScrapcreators.value = true
  try {
    await store.updateSystemSetting('scrapecreators_api_key', scrapcreatorsSettings.value.scrapecreators_api_key)
    originalScrapcreatorsSettings.value.scrapecreators_api_key = scrapcreatorsSettings.value.scrapecreators_api_key
    showSnackbar('ScrapeCreators API key saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save ScrapeCreators key', 'error')
  } finally {
    savingScrapcreators.value = false
  }
}

const saveAudioSettings = async () => {
  savingAudio.value = true
  try {
    await store.updateSystemSetting('kieai_api_key', audioSettings.value.kieai_api_key)
    await store.updateSystemSetting('tts_timeout', String(audioSettings.value.tts_timeout))
    originalAudioSettings.value.kieai_api_key = audioSettings.value.kieai_api_key
    originalAudioSettings.value.tts_timeout = audioSettings.value.tts_timeout
    showSnackbar('Kie.ai settings saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save Kie.ai settings', 'error')
  } finally {
    savingAudio.value = false
  }
}

const testKieaiModel = async (modelId, label) => {
  testingKieai.value = label
  kieaiTestResult.value = null
  try {
    // Save first if changed
    if (audioSettingsChanged.value) {
      await store.updateSystemSetting('kieai_api_key', audioSettings.value.kieai_api_key)
      originalAudioSettings.value.kieai_api_key = audioSettings.value.kieai_api_key
    }
    const { data } = await api.post(`/settings/kieai/test?model=${modelId}`)
    kieaiTestResult.value = { type: 'success', message: data.message }
  } catch (e) {
    kieaiTestResult.value = { type: 'error', message: e.response?.data?.detail || 'Connection failed' }
  } finally {
    testingKieai.value = null
  }
}

const checkKieaiBalance = async () => {
  checkingKieaiBalance.value = true
  kieaiBalanceResult.value = null
  try {
    // Save key first if changed
    if (audioSettingsChanged.value) {
      await store.updateSystemSetting('kieai_api_key', audioSettings.value.kieai_api_key)
      originalAudioSettings.value.kieai_api_key = audioSettings.value.kieai_api_key
    }
    const { data } = await api.get('/settings/kieai/balance')
    if (data.available && data.balance != null) {
      kieaiBalance.value = `$${data.balance}`
      kieaiBalanceResult.value = { type: 'success', message: `Balance: <strong>$${data.balance}</strong>` }
    } else {
      // No balance API — open billing page directly
      kieaiBalance.value = data.key_valid ? '✓ Key OK' : '✗'
      window.open(data.url || 'https://kie.ai/market', '_blank')
    }
  } catch (e) {
    kieaiBalanceResult.value = { type: 'error', message: e.response?.data?.detail || 'Failed to check balance' }
  } finally {
    checkingKieaiBalance.value = false
  }
}

const checkAnthropicBalance = async () => {
  checkingAnthropicBalance.value = true
  anthropicBalanceResult.value = null
  try {
    // Save key first if changed
    if (anthropicSettingsChanged.value) {
      await store.updateSystemSetting('anthropic_api_key', anthropicSettings.value.anthropic_api_key)
      originalAnthropicSettings.value.anthropic_api_key = anthropicSettings.value.anthropic_api_key
    }
    const { data } = await api.get('/settings/anthropic/balance')
    if (data.available && data.balance != null) {
      anthropicBalance.value = `$${data.balance}`
      anthropicBalanceResult.value = { type: 'success', message: `Balance: <strong>$${data.balance}</strong>${data.name ? ' (' + data.name + ')' : ''}` }
    } else {
      // No balance API — open billing page directly
      anthropicBalance.value = data.key_valid ? '✓ Key OK' : '✗'
      window.open(data.url || 'https://console.anthropic.com/settings/billing', '_blank')
    }
  } catch (e) {
    anthropicBalanceResult.value = { type: 'error', message: e.response?.data?.detail || 'Failed to check balance' }
  } finally {
    checkingAnthropicBalance.value = false
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
