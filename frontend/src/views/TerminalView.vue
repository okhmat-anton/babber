<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Terminal</div>
      <v-spacer />
      <v-chip
        v-if="!enabled"
        color="error"
        variant="flat"
        prepend-icon="mdi-lock"
        class="mr-3"
      >
        Disabled — enable in Settings
      </v-chip>
    </div>

    <v-alert v-if="!enabled" type="warning" variant="tonal" class="mb-4">
      System access is disabled.
      <v-btn to="/settings" variant="text" color="warning" size="small" class="ml-2">Go to Settings</v-btn>
    </v-alert>

    <template v-if="enabled">
      <!-- Working directory -->
      <v-card class="mb-4">
        <v-card-text class="pa-3 d-flex align-center ga-2">
          <v-icon size="small">mdi-folder</v-icon>
          <v-text-field
            v-model="cwd"
            density="compact"
            variant="outlined"
            hide-details
            label="Working directory"
            style="max-width: 500px"
          />
          <v-btn size="small" variant="outlined" prepend-icon="mdi-home" @click="cwd = homeDir">Home</v-btn>
          <v-spacer />
          <v-btn
            size="small"
            variant="outlined"
            prepend-icon="mdi-history"
            @click="loadHistory"
          >
            History
          </v-btn>
          <v-btn
            size="small"
            variant="outlined"
            prepend-icon="mdi-delete-sweep"
            @click="output = []; saveState()"
          >
            Clear
          </v-btn>
        </v-card-text>
      </v-card>

      <!-- Terminal output -->
      <v-card class="mb-4 terminal-card">
        <v-card-text class="pa-0">
          <div ref="terminalOutput" class="terminal-output">
            <div v-if="!output.length" class="text-medium-emphasis pa-4">
              Ready. Type a command below and press Enter or click Run.
            </div>
            <div
              v-for="(entry, i) in output"
              :key="i"
              class="terminal-entry"
            >
              <!-- Command line -->
              <div v-if="entry.type === 'command'" class="terminal-command">
                <span class="terminal-prompt">{{ entry.cwd }}$</span>
                <span class="terminal-cmd-text">{{ entry.text }}</span>
                <v-chip
                  v-if="entry.exitCode !== undefined && entry.exitCode !== null"
                  :color="entry.exitCode === 0 ? 'success' : 'error'"
                  size="x-small"
                  variant="flat"
                  class="ml-2"
                >
                  exit {{ entry.exitCode }}
                </v-chip>
                <v-chip v-if="entry.duration" size="x-small" variant="tonal" class="ml-1">
                  {{ entry.duration }}ms
                </v-chip>
                <v-chip v-if="entry.timedOut" color="warning" size="x-small" variant="flat" class="ml-1">
                  TIMEOUT
                </v-chip>
              </div>
              <!-- Stdout -->
              <pre v-if="entry.type === 'stdout' && entry.text" class="terminal-stdout">{{ entry.text }}</pre>
              <!-- Stderr -->
              <pre v-if="entry.type === 'stderr' && entry.text" class="terminal-stderr">{{ entry.text }}</pre>
            </div>
            <div v-if="executing" class="pa-2">
              <v-progress-linear indeterminate color="primary" />
            </div>
          </div>
        </v-card-text>
      </v-card>

      <!-- Command input -->
      <v-card>
        <v-card-text class="pa-3">
          <v-form @submit.prevent="runCommand">
            <div class="d-flex align-center ga-2">
              <span class="text-body-2 text-medium-emphasis font-weight-bold" style="white-space: nowrap">
                $
              </span>
              <v-text-field
                v-model="command"
                density="compact"
                variant="outlined"
                hide-details
                placeholder="Enter command..."
                autofocus
                :disabled="executing"
                @keydown.up="historyUp"
                @keydown.down="historyDown"
                @keydown.tab.prevent="tabComplete"
              />
              <v-text-field
                v-model.number="timeout"
                density="compact"
                variant="outlined"
                hide-details
                type="number"
                label="Timeout (s)"
                style="max-width: 120px"
              />
              <v-btn
                type="submit"
                color="primary"
                :loading="executing"
                prepend-icon="mdi-play"
              >
                Run
              </v-btn>
            </div>
          </v-form>
        </v-card-text>
      </v-card>

      <!-- Quick commands -->
      <v-card class="mt-4">
        <v-card-title class="text-body-1">Quick Commands</v-card-title>
        <v-card-text class="d-flex flex-wrap ga-2">
          <v-chip
            v-for="qc in quickCommands"
            :key="qc.cmd"
            variant="outlined"
            size="small"
            @click="command = qc.cmd; runCommand()"
          >
            {{ qc.label }}
          </v-chip>
        </v-card-text>
      </v-card>
    </template>

    <!-- History dialog -->
    <v-dialog v-model="historyDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title>Shell History</v-card-title>
        <v-divider />
        <v-card-text style="max-height: 60vh">
          <v-list density="compact">
            <v-list-item
              v-for="(h, i) in shellHistory"
              :key="i"
              :title="h"
              @click="command = h; historyDialog = false"
              style="cursor: pointer"
            >
              <template #prepend>
                <span class="text-caption text-medium-emphasis mr-2">{{ shellHistory.length - i }}</span>
              </template>
            </v-list-item>
          </v-list>
          <div v-if="!shellHistory.length" class="text-center pa-4 text-medium-emphasis">
            No history found
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer /><v-btn @click="historyDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, inject } from 'vue'
import api from '../api'
import { useSettingsStore } from '../stores/settings'

const showSnackbar = inject('showSnackbar')
const settingsStore = useSettingsStore()

const enabled = ref(false)
const command = ref('')
const cwd = ref('')
const homeDir = ref('')
const timeout = ref(30)
const executing = ref(false)
const output = ref([])
const terminalOutput = ref(null)

// History
const historyDialog = ref(false)
const shellHistory = ref([])
const localHistory = ref([])
const historyIndex = ref(-1)

// Persistence helpers
const STORAGE_KEY_OUTPUT = 'terminal_output'
const STORAGE_KEY_CWD = 'terminal_cwd'
const STORAGE_KEY_HISTORY = 'terminal_local_history'
const MAX_PERSISTED_ENTRIES = 500

function saveState() {
  try {
    const trimmed = output.value.slice(-MAX_PERSISTED_ENTRIES)
    sessionStorage.setItem(STORAGE_KEY_OUTPUT, JSON.stringify(trimmed))
    sessionStorage.setItem(STORAGE_KEY_CWD, cwd.value)
    localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(localHistory.value.slice(0, 200)))
  } catch { /* quota exceeded — ignore */ }
}

function restoreState() {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY_OUTPUT)
    if (saved) output.value = JSON.parse(saved)
    const savedCwd = sessionStorage.getItem(STORAGE_KEY_CWD)
    if (savedCwd) cwd.value = savedCwd
    const savedHistory = localStorage.getItem(STORAGE_KEY_HISTORY)
    if (savedHistory) localHistory.value = JSON.parse(savedHistory)
  } catch { /* corrupted — ignore */ }
}

const quickCommands = [
  { label: 'pwd', cmd: 'pwd' },
  { label: 'whoami', cmd: 'whoami' },
  { label: 'uname -a', cmd: 'uname -a' },
  { label: 'df -h', cmd: 'df -h' },
  { label: 'free -h', cmd: 'free -h 2>/dev/null || vm_stat' },
  { label: 'top (snapshot)', cmd: 'top -l 1 -n 10 2>/dev/null || top -b -n 1 | head -30' },
  { label: 'ls -la', cmd: 'ls -la' },
  { label: 'env', cmd: 'env | sort' },
  { label: 'docker ps', cmd: 'docker ps' },
  { label: 'brew list', cmd: 'brew list 2>/dev/null || echo "brew not found"' },
  { label: 'node -v', cmd: 'node -v' },
  { label: 'python3 --version', cmd: 'python3 --version' },
  { label: 'git status', cmd: 'git status' },
  { label: 'ifconfig', cmd: 'ifconfig 2>/dev/null || ip addr' },
  { label: 'netstat (listen)', cmd: 'netstat -tlnp 2>/dev/null || lsof -i -P -n | head -30' },
]

onMounted(async () => {
  restoreState()
  await settingsStore.fetchSystemSettings()
  enabled.value = settingsStore.systemSettings.system_access_enabled?.value === 'true'
  if (enabled.value) {
    // Get home dir
    try {
      const { data } = await api.post('/terminal/execute', { command: 'echo $HOME', timeout: 5 })
      homeDir.value = data.stdout.trim()
      if (!cwd.value) cwd.value = homeDir.value
    } catch {
      if (!cwd.value) cwd.value = '/tmp'
      homeDir.value = cwd.value || '/tmp'
    }
  }
})

async function runCommand() {
  if (!command.value.trim() || executing.value) return

  const cmd = command.value.trim()

  // Handle cd locally
  if (cmd.startsWith('cd ')) {
    const dir = cmd.slice(3).trim()
    await changeDir(dir)
    command.value = ''
    return
  }
  if (cmd === 'cd') {
    cwd.value = homeDir.value
    output.value.push({ type: 'command', text: cmd, cwd: cwd.value })
    command.value = ''
    scrollToBottom()
    return
  }

  // Add to history
  localHistory.value.unshift(cmd)
  historyIndex.value = -1

  const cmdEntry = { type: 'command', text: cmd, cwd: cwd.value }
  output.value.push(cmdEntry)
  command.value = ''
  executing.value = true
  scrollToBottom()

  try {
    const { data } = await api.post('/terminal/execute', {
      command: cmd,
      cwd: cwd.value,
      timeout: timeout.value,
    })
    cmdEntry.exitCode = data.exit_code
    cmdEntry.duration = data.duration_ms
    cmdEntry.timedOut = data.timed_out

    if (data.stdout) {
      output.value.push({ type: 'stdout', text: data.stdout })
    }
    if (data.stderr) {
      output.value.push({ type: 'stderr', text: data.stderr })
    }
  } catch (e) {
    output.value.push({
      type: 'stderr',
      text: e.response?.data?.detail || 'Error executing command',
    })
  } finally {
    executing.value = false
    saveState()
    scrollToBottom()
  }
}

async function changeDir(dir) {
  try {
    // Resolve the path via shell
    const { data } = await api.post('/terminal/execute', {
      command: `cd "${dir}" && pwd`,
      cwd: cwd.value,
      timeout: 5,
    })
    if (data.exit_code === 0) {
      const newDir = data.stdout.trim()
      output.value.push({ type: 'command', text: `cd ${dir}`, cwd: cwd.value })
      cwd.value = newDir
    } else {
      output.value.push({ type: 'command', text: `cd ${dir}`, cwd: cwd.value, exitCode: data.exit_code })
      if (data.stderr) output.value.push({ type: 'stderr', text: data.stderr })
    }
  } catch (e) {
    output.value.push({ type: 'stderr', text: `cd: ${dir}: No such file or directory` })
  }
  saveState()
  scrollToBottom()
}

function historyUp() {
  if (localHistory.value.length === 0) return
  historyIndex.value = Math.min(historyIndex.value + 1, localHistory.value.length - 1)
  command.value = localHistory.value[historyIndex.value]
}

function historyDown() {
  if (historyIndex.value <= 0) {
    historyIndex.value = -1
    command.value = ''
    return
  }
  historyIndex.value--
  command.value = localHistory.value[historyIndex.value]
}

async function tabComplete() {
  if (!command.value) return
  try {
    const { data } = await api.get('/terminal/completions', {
      params: { text: command.value, cwd: cwd.value },
    })
    if (data.completions?.length === 1) {
      const parts = command.value.split(' ')
      parts[parts.length - 1] = data.completions[0].text
      command.value = parts.join(' ')
    } else if (data.completions?.length > 1) {
      // Show completions in terminal output
      const names = data.completions.map(c => c.text).join('  ')
      output.value.push({ type: 'stdout', text: names })
      scrollToBottom()
    }
  } catch { /* ignore */ }
}

async function loadHistory() {
  try {
    const { data } = await api.get('/terminal/history', { params: { limit: 100 } })
    shellHistory.value = (data.history || []).reverse()
    historyDialog.value = true
  } catch (e) {
    showSnackbar('Failed to load history', 'error')
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (terminalOutput.value) {
      terminalOutput.value.scrollTop = terminalOutput.value.scrollHeight
    }
  })
}
</script>

<style scoped>
.terminal-card {
  background: #1e1e1e !important;
}

.terminal-output {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #d4d4d4;
  min-height: 400px;
  max-height: 65vh;
  overflow-y: auto;
  padding: 12px;
}

.terminal-entry {
  margin-bottom: 4px;
}

.terminal-command {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.terminal-prompt {
  color: #4ec9b0;
  font-weight: bold;
  margin-right: 8px;
  white-space: nowrap;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.terminal-cmd-text {
  color: #dcdcaa;
}

.terminal-stdout {
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 2px 0;
  font-family: inherit;
  font-size: inherit;
}

.terminal-stderr {
  color: #f48771;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 2px 0;
  font-family: inherit;
  font-size: inherit;
}
</style>
