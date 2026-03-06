<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">
        <v-icon class="mr-2" size="32">mdi-brain</v-icon>
        Models
      </div>
      <v-spacer />

      <!-- Ollama status chip (always visible) -->
      <v-chip
        :color="ollamaStatus.running ? 'success' : 'error'"
        variant="tonal"
        class="mr-3"
      >
        <v-icon start size="16" :icon="ollamaStatus.running ? 'mdi-check-circle' : 'mdi-close-circle'" />
        Ollama {{ ollamaStatus.running ? 'Running' : 'Stopped' }}
      </v-chip>

      <!-- Tab-specific actions -->
      <v-btn v-if="tab === 'models'" color="primary" prepend-icon="mdi-plus" @click="showDialog()">Add Model</v-btn>
      <template v-if="tab === 'ollama'">
        <v-btn v-if="!ollamaStatus.running" color="success" :loading="starting" @click="startOllama" prepend-icon="mdi-play" class="mr-2">Start</v-btn>
        <v-btn v-if="ollamaStatus.running" color="error" variant="tonal" :loading="stopping" @click="stopOllama" prepend-icon="mdi-stop" class="mr-2">Stop</v-btn>
        <v-btn color="primary" variant="tonal" :loading="ollamaRefreshing" @click="refreshOllama" prepend-icon="mdi-refresh">Refresh</v-btn>
      </template>
    </div>

    <v-tabs v-model="tab" color="primary" class="mb-4">
      <v-tab value="models" prepend-icon="mdi-database">Models</v-tab>
      <v-tab value="ollama" prepend-icon="mdi-creation">Ollama</v-tab>
    </v-tabs>

    <v-window v-model="tab">
      <!-- ═══════════ Tab 1: Registered Models ═══════════ -->
      <v-window-item value="models">

        <v-card>
          <v-card-title class="d-flex align-center">
            <span>Active Models</span>
            <v-chip class="ml-2" size="small" variant="tonal">{{ displayedModels.length }}</v-chip>
            <v-spacer />
            <v-btn size="small" variant="tonal" prepend-icon="mdi-tag-multiple" @click="openRolesDialog" class="mr-2">Assign Roles</v-btn>
          </v-card-title>
          <v-data-table :headers="modelHeaders" :items="displayedModels" hover>
            <template #item.provider="{ item }">
              <v-chip
                size="small" variant="tonal"
                :color="item.provider === 'ollama' ? 'green' : item.provider === 'openai_compatible' ? 'blue' : 'grey'"
              >{{ item.provider }}</v-chip>
            </template>
            <template #item.roles="{ item }">
              <v-chip v-if="isBaseModel(item)" size="x-small" color="amber" variant="flat" class="mr-1 mb-1">
                <v-icon start size="10">mdi-star</v-icon>base
              </v-chip>
              <v-chip v-for="r in getModelRoles(item)" :key="r.role" size="x-small" :color="roleColor(r.role)" variant="tonal" class="mr-1 mb-1">
                {{ r.label }}
              </v-chip>
              <span v-if="!isBaseModel(item) && !getModelRoles(item).length" class="text-caption text-grey">—</span>
            </template>
            <template #item.is_active="{ item }">
              <v-chip :color="item.is_active ? 'success' : 'grey'" size="small" variant="tonal">{{ item.is_active ? 'Active' : 'Inactive' }}</v-chip>
            </template>
            <template #item.actions="{ item }">
              <v-btn icon="mdi-connection" size="small" variant="text" color="info" @click="testModel(item)" title="Test connection" />
              <v-btn icon="mdi-format-list-bulleted" size="small" variant="text" @click="listModels(item)" title="List available models" />
              <v-btn icon="mdi-pencil" size="small" variant="text" @click="showDialog(item)" />
              <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click="handleDelete(item)" />
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <!-- ═══════════ Tab 2: Ollama Management ═══════════ -->
      <v-window-item value="ollama">

        <!-- Pull New Model -->
        <v-card class="mb-6">
          <v-card-title class="d-flex align-center">
            <v-icon class="mr-2">mdi-download</v-icon>
            Pull Model
            <v-spacer />
            <v-btn size="small" variant="tonal" :prepend-icon="showCatalog ? 'mdi-chevron-up' : 'mdi-chevron-down'" @click="toggleCatalog">
              {{ showCatalog ? 'Hide Catalog' : 'Browse Models' }}
            </v-btn>
          </v-card-title>
          <v-card-text>
            <v-row align="center">
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="pullModelName" label="Model name"
                  placeholder="e.g. llama3:8b, qwen2.5-coder:14b, gemma2:9b"
                  variant="outlined" density="compact" hide-details
                  :disabled="!ollamaStatus.running || pulling"
                  @keyup.enter="pullModel"
                />
              </v-col>
              <v-col cols="auto">
                <v-btn color="primary" :loading="pulling && !pullProgress" :disabled="!pullModelName || !ollamaStatus.running || pulling" @click="pullModel" prepend-icon="mdi-download">Pull</v-btn>
              </v-col>
            </v-row>

            <!-- Pull Progress -->
            <div v-if="pulling && pullProgress" class="mt-4">
              <div class="d-flex align-center mb-1">
                <v-icon size="16" color="primary" class="mr-2 pull-spin">mdi-loading</v-icon>
                <span class="text-body-2 font-weight-medium">Pulling {{ pullModelName }}...</span>
                <v-spacer />
                <span class="text-caption text-grey">{{ pullProgress.status }}</span>
              </div>
              <v-progress-linear :model-value="pullProgress.progress" color="primary" height="22" rounded class="mb-1">
                <template #default>
                  <span class="text-caption font-weight-bold" style="color: white; text-shadow: 0 0 3px rgba(0,0,0,0.5)">
                    {{ pullProgress.progress.toFixed(1) }}%
                  </span>
                </template>
              </v-progress-linear>
              <div class="d-flex justify-space-between text-caption text-grey">
                <span v-if="pullProgress.completed && pullProgress.total">{{ formatBytes(pullProgress.completed) }} / {{ formatBytes(pullProgress.total) }}</span>
                <span v-else>{{ pullProgress.status }}</span>
                <span v-if="pullSpeed">{{ pullSpeed }}/s</span>
              </div>
            </div>

            <v-alert v-if="pullResult" :type="pullResult.type" class="mt-3" closable @click:close="pullResult = null">
              {{ pullResult.message }}
            </v-alert>

            <!-- Model Catalog -->
            <v-expand-transition>
              <div v-if="showCatalog" class="mt-4">
                <v-divider class="mb-3" />
                <div class="d-flex align-center mb-3">
                  <div class="text-subtitle-2 font-weight-bold">
                    Available Models
                    <span v-if="catalogModels.length" class="text-caption text-grey ml-1">({{ catalogModels.length }})</span>
                  </div>
                  <v-spacer />
                  <v-text-field
                    v-model="catalogSearch" density="compact" variant="outlined"
                    placeholder="Search models..." prepend-inner-icon="mdi-magnify"
                    hide-details style="max-width: 300px" clearable
                  />
                </div>
                <div v-if="catalogLoading" class="text-center pa-6">
                  <v-progress-circular indeterminate color="primary" size="32" />
                  <div class="text-caption text-grey mt-2">Loading catalog from ollama.com...</div>
                </div>
                <v-table v-else density="compact" class="catalog-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Capabilities</th>
                      <th>Available Sizes</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="m in filteredCatalog" :key="m.name" :class="{ 'installed-row': m.any_installed }">
                      <td style="min-width: 160px">
                        <div class="d-flex align-center">
                          <span class="font-weight-medium">{{ m.name }}</span>
                          <v-icon v-if="m.any_installed" size="14" color="success" class="ml-1" title="Has installed variants">mdi-check-circle</v-icon>
                        </div>
                        <div v-if="m.pulls" class="text-caption text-grey">{{ m.pulls }} pulls</div>
                      </td>
                      <td>
                        <v-chip v-for="cap in m.capabilities" :key="cap" size="x-small" variant="tonal" :color="capColor(cap)" class="mr-1 mb-1">{{ cap }}</v-chip>
                      </td>
                      <td style="min-width: 200px">
                        <template v-if="m.sizes && m.sizes.length">
                          <v-chip
                            v-for="s in m.sizes" :key="s.tag" size="small"
                            :variant="m.installed_sizes?.includes(s.tag) ? 'flat' : 'outlined'"
                            :color="m.installed_sizes?.includes(s.tag) ? 'success' : 'primary'"
                            class="mr-1 mb-1 catalog-size-chip" :disabled="pulling"
                            @click="!m.installed_sizes?.includes(s.tag) && pullFromCatalog(m, s.tag)"
                          >
                            <v-icon v-if="m.installed_sizes?.includes(s.tag)" start size="12">mdi-check</v-icon>
                            <v-icon v-else start size="12">mdi-download</v-icon>
                            {{ s.tag }}
                            <span v-if="s.size_gb" class="text-caption ml-1" style="opacity: 0.7">{{ s.size_gb }}G</span>
                          </v-chip>
                        </template>
                        <v-btn v-else size="small" color="primary" variant="tonal" :disabled="pulling" @click="pullFromCatalog(m, null)" prepend-icon="mdi-download">Pull</v-btn>
                      </td>
                      <td class="text-caption text-grey-lighten-1" style="max-width: 400px">{{ m.description }}</td>
                    </tr>
                  </tbody>
                </v-table>
                <div v-if="!catalogLoading && !filteredCatalog.length" class="text-center text-grey pa-4">No models match your search.</div>
              </div>
            </v-expand-transition>
          </v-card-text>
        </v-card>

        <!-- Running Models (in memory) -->
        <v-card class="mb-6" v-if="ollamaRunningModels.length">
          <v-card-title>
            <v-icon class="mr-2" color="success">mdi-lightning-bolt</v-icon>
            Running in Memory
          </v-card-title>
          <v-card-text>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>RAM / VRAM</th>
                  <th>Expires</th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in ollamaRunningModels" :key="m.name">
                  <td class="font-weight-medium">{{ m.name }}</td>
                  <td>{{ m.size_hr }} / {{ m.size_vram_hr }}</td>
                  <td>{{ formatDate(m.expires_at) }}</td>
                  <td class="text-right">
                    <v-btn size="small" color="primary" variant="tonal" class="mr-1" @click="openChat(m.name)" prepend-icon="mdi-chat">Chat</v-btn>
                    <v-btn size="small" color="warning" variant="tonal" :loading="unloadingModel === m.name" @click="unloadModel(m.name)" prepend-icon="mdi-eject">Unload</v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>

        <!-- Local Models -->
        <v-card>
          <v-card-title>
            <v-icon class="mr-2">mdi-database</v-icon>
            Local Models
            <v-chip class="ml-2" size="small" variant="tonal">{{ ollamaModels.length }}</v-chip>
          </v-card-title>
          <v-card-text>
            <v-alert v-if="!ollamaStatus.running" type="warning" variant="tonal" class="mb-4">
              Ollama is not running. Start it to see local models.
            </v-alert>

            <div v-if="ollamaLoading" class="d-flex justify-center pa-8">
              <v-progress-circular indeterminate color="primary" />
            </div>

            <v-table v-else-if="ollamaModels.length" density="comfortable">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Size</th>
                  <th>Parameters</th>
                  <th>Quantization</th>
                  <th>Family</th>
                  <th>Modified</th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in ollamaModels" :key="m.name">
                  <td>
                    <span class="font-weight-medium">{{ m.name }}</span>
                    <div class="text-caption text-grey">{{ m.digest }}</div>
                  </td>
                  <td>{{ m.size_hr }}</td>
                  <td>{{ m.parameter_size || '—' }}</td>
                  <td>{{ m.quantization || '—' }}</td>
                  <td>{{ m.family || '—' }}</td>
                  <td>{{ formatDate(m.modified_at) }}</td>
                  <td class="text-right" style="white-space: nowrap">
                    <v-btn v-if="!isModelRunning(m.name)" size="small" color="success" variant="tonal" class="mr-1" :loading="loadingModel === m.name" @click="loadModel(m.name)" prepend-icon="mdi-play">Run</v-btn>
                    <v-btn v-else size="small" color="warning" variant="tonal" class="mr-1" :loading="unloadingModel === m.name" @click="unloadModel(m.name)" prepend-icon="mdi-eject">Unload</v-btn>
                    <v-btn icon="mdi-information-outline" size="small" variant="text" @click="showOllamaDetail(m)" />
                    <v-btn icon="mdi-delete-outline" size="small" variant="text" color="error" @click="confirmOllamaDelete(m)" />
                  </td>
                </tr>
              </tbody>
            </v-table>

            <div v-else class="text-center text-grey pa-8">
              No local models found. Pull one to get started.
            </div>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- ═══════════ Dialogs ═══════════ -->

    <!-- Add/Edit Model Config Dialog -->
    <v-dialog v-model="dialog" max-width="600">
      <v-card>
        <v-card-title>{{ editItem ? 'Edit Model' : 'Add Model' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="form.name" label="Display Name" hint="e.g. My Ollama Coder" class="mb-2" />
          <v-text-field v-model="form.model_id" label="Model ID" hint="e.g. qwen2.5-coder:14b" class="mb-2" />
          <v-select v-model="form.provider" :items="['ollama','openai_compatible','custom']" label="Provider" class="mb-2" />
          <v-text-field v-model="form.base_url" label="Base URL" class="mb-2" />
          <v-text-field v-model="form.api_key" label="API Key (optional)" class="mb-2" />
          <v-checkbox v-model="form.is_active" label="Active" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="handleSave" :loading="saving">{{ editItem ? 'Update' : 'Create' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Available models dialog -->
    <v-dialog v-model="availDialog" max-width="500">
      <v-card>
        <v-card-title>Available Models</v-card-title>
        <v-card-text>
          <v-list density="compact">
            <v-list-item v-for="m in availModels" :key="m.name">
              <v-list-item-title>{{ m.name }}</v-list-item-title>
              <template #append v-if="m.size">
                <span class="text-caption text-grey">{{ (m.size / 1e9).toFixed(1) }}GB</span>
              </template>
            </v-list-item>
          </v-list>
          <div v-if="!availModels.length" class="text-center text-grey pa-4">No models found</div>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn @click="availDialog = false">Close</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Ollama Model Detail Dialog -->
    <v-dialog v-model="detailDialog" max-width="700">
      <v-card v-if="detailModel">
        <v-card-title>
          <v-icon class="mr-2">mdi-brain</v-icon>
          {{ detailModel.name }}
        </v-card-title>
        <v-card-text>
          <div v-if="detailLoading" class="d-flex justify-center pa-6">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <div v-else-if="modelDetail">
            <div v-if="modelDetail.parameters" class="mb-4">
              <div class="text-subtitle-2 font-weight-bold mb-1">Parameters</div>
              <pre class="pa-3 bg-grey-lighten-4 rounded text-body-2" style="white-space: pre-wrap">{{ modelDetail.parameters }}</pre>
            </div>
            <div v-if="modelDetail.template" class="mb-4">
              <div class="text-subtitle-2 font-weight-bold mb-1">Template</div>
              <pre class="pa-3 bg-grey-lighten-4 rounded text-body-2" style="white-space: pre-wrap; max-height: 200px; overflow-y: auto">{{ modelDetail.template }}</pre>
            </div>
            <div v-if="modelDetail.system" class="mb-4">
              <div class="text-subtitle-2 font-weight-bold mb-1">System Prompt</div>
              <pre class="pa-3 bg-grey-lighten-4 rounded text-body-2" style="white-space: pre-wrap; max-height: 200px; overflow-y: auto">{{ modelDetail.system }}</pre>
            </div>
            <div v-if="modelDetail.license">
              <div class="text-subtitle-2 font-weight-bold mb-1">License</div>
              <pre class="pa-3 bg-grey-lighten-4 rounded text-body-2" style="white-space: pre-wrap; max-height: 150px; overflow-y: auto">{{ modelDetail.license }}</pre>
            </div>
          </div>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn @click="detailDialog = false">Close</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Chat Dialog -->
    <v-dialog v-model="chatDialog" max-width="800" persistent>
      <v-card height="600" class="d-flex flex-column">
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2" color="primary">mdi-chat</v-icon>
          Chat — {{ chatModel }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="closeChat" />
        </v-card-title>
        <v-divider />
        <v-card-text ref="chatContainer" class="flex-grow-1 overflow-y-auto pa-4" style="min-height: 0">
          <div v-if="!chatMessages.length" class="text-center text-grey pa-8">
            Send a message to start chatting with <strong>{{ chatModel }}</strong>
          </div>
          <div v-for="(msg, i) in chatMessages" :key="i" class="mb-3">
            <div :class="msg.role === 'user' ? 'text-right' : ''">
              <v-chip
                :color="msg.role === 'user' ? 'primary' : 'grey-lighten-3'"
                :text-color="msg.role === 'user' ? 'white' : ''"
                variant="flat" size="small" class="mb-1"
              >
                {{ msg.role === 'user' ? 'You' : chatModel }}
                <span v-if="msg.stats" class="ml-2 text-caption">{{ msg.stats }}</span>
              </v-chip>
              <div
                class="pa-3 rounded-lg text-body-2"
                :class="msg.role === 'user' ? 'bg-primary-lighten-5 ml-auto' : 'bg-grey-lighten-4'"
                style="max-width: 85%; display: inline-block; white-space: pre-wrap; word-break: break-word; text-align: left"
              >{{ msg.content }}</div>
            </div>
          </div>
          <div v-if="chatSending" class="mb-3">
            <v-chip color="grey-lighten-3" variant="flat" size="small" class="mb-1">{{ chatModel }}</v-chip>
            <div class="pa-3 rounded-lg bg-grey-lighten-4" style="max-width: 85%; display: inline-block">
              <v-progress-linear indeterminate color="primary" height="2" />
              <span class="text-caption text-grey mt-1">Thinking...</span>
            </div>
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-text-field v-model="chatInput" placeholder="Type a message..." variant="outlined" density="compact" hide-details :disabled="chatSending" @keyup.enter="sendChat" class="mr-2" />
          <v-btn color="primary" :loading="chatSending" :disabled="!chatInput.trim()" @click="sendChat" icon="mdi-send" />
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Model Config -->
    <ConfirmDeleteDialog
      v-model="deleteDialog"
      title="Delete Model"
      :message="`Are you sure you want to delete &quot;${deleteTarget?.name}&quot;?`"
      @confirm="confirmDelete"
    />

    <!-- Delete Ollama Model -->
    <ConfirmDeleteDialog
      v-model="ollamaDeleteDialog"
      title="Delete Ollama Model"
      :message="`Are you sure you want to delete ${ollamaDeleteTarget?.name}? This will free ${ollamaDeleteTarget?.size_hr} of disk space.`"
      :loading="ollamaDeleting"
      @confirm="deleteOllamaModel"
    />

    <!-- Roles Assignment Dialog -->
    <v-dialog v-model="rolesDialog" max-width="800" scrollable persistent>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2" color="primary">mdi-tag-multiple</v-icon>
          Assign Model Roles
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="rolesDialog = false" />
        </v-card-title>
        <v-card-subtitle>Each role can be assigned to one model. A model can have multiple roles.</v-card-subtitle>

        <!-- Base model warning -->
        <v-alert
          v-if="!hasActiveBaseModel"
          type="error"
          variant="tonal"
          density="compact"
          class="mx-4 mt-2"
          icon="mdi-alert-circle"
        >
          <span v-if="!roleAssignments['base']">Base model is not assigned! The watchdog will auto-assign when a model starts.</span>
          <span v-else>Base model is not available (not running). The watchdog will attempt to restart it.</span>
        </v-alert>

        <!-- Watchdog status -->
        <v-alert
          v-if="watchdogInfo"
          type="info"
          variant="tonal"
          density="compact"
          class="mx-4 mt-2"
          icon="mdi-shield-check"
        >
          <div class="d-flex align-center">
            <span>Watchdog active — auto-recovery enabled</span>
            <v-spacer />
            <v-chip v-if="watchdogInfo.manually_stopped_models?.length" size="x-small" color="warning" variant="tonal" class="ml-2">
              {{ watchdogInfo.manually_stopped_models.length }} manually stopped
            </v-chip>
          </div>
        </v-alert>
        <v-card-text style="max-height: 60vh">
          <v-table density="comfortable">
            <thead>
              <tr>
                <th style="width: 40%">Role</th>
                <th>Model</th>
                <th style="width: 60px">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in availableRoles" :key="r.role" :class="{ 'bg-amber-darken-4': r.role === 'base' }">
                <td>
                  <div class="d-flex align-center">
                    <v-icon v-if="r.role === 'base'" size="16" color="amber" class="mr-2">mdi-star</v-icon>
                    <v-chip v-else size="x-small" :color="roleColor(r.role)" variant="tonal" class="mr-2">{{ r.role }}</v-chip>
                    <span class="font-weight-medium">{{ r.label }}</span>
                  </div>
                </td>
                <td>
                  <v-select
                    :model-value="roleAssignments[r.role] || null"
                    @update:model-value="v => setRoleAssignment(r.role, v)"
                    :items="allActiveModels"
                    item-title="name"
                    item-value="id"
                    density="compact"
                    variant="outlined"
                    hide-details
                    clearable
                    placeholder="Not assigned"
                  >
                    <template #item="{ item, props }">
                      <v-list-item v-bind="props">
                        <template #prepend>
                          <v-icon v-if="isModelOnline(item.raw)" size="14" color="success">mdi-circle</v-icon>
                          <v-icon v-else size="14" color="grey">mdi-circle-outline</v-icon>
                        </template>
                        <template #subtitle>
                          <span class="text-caption">{{ item.raw.model_id }} · {{ item.raw.provider }}</span>
                          <span v-if="!isModelOnline(item.raw)" class="text-caption text-warning ml-1">(offline)</span>
                        </template>
                      </v-list-item>
                    </template>
                  </v-select>
                </td>
                <td class="text-center">
                  <template v-if="roleAssignments[r.role]">
                    <v-icon v-if="isRoleModelOnline(r.role)" size="18" color="success" title="Model is running">mdi-check-circle</v-icon>
                    <v-tooltip v-else location="top">
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          icon size="x-small" variant="text" color="warning"
                          :loading="restartingRole === r.role"
                          @click="restartRoleModel(r.role)"
                        >
                          <v-icon size="18">mdi-restart-alert</v-icon>
                        </v-btn>
                      </template>
                      <span>Model offline — click to restart</span>
                    </v-tooltip>
                  </template>
                  <span v-else class="text-caption text-grey">—</span>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="rolesDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="savingRoles" @click="saveRoles">Save Roles</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useSettingsStore } from '../stores/settings'
import api from '../api'
import ConfirmDeleteDialog from '../components/ConfirmDeleteDialog.vue'

const settingsStore = useSettingsStore()
const showSnackbar = inject('showSnackbar')
const tab = ref('models')

// ═══════════ Models tab state ═══════════
const dialog = ref(false)
const editItem = ref(null)
const saving = ref(false)
const availDialog = ref(false)
const availModels = ref([])
const deleteDialog = ref(false)
const deleteTarget = ref(null)

const modelHeaders = [
  { title: 'Name', key: 'name' },
  { title: 'Model ID', key: 'model_id', width: 200 },
  { title: 'Provider', key: 'provider', width: 120 },
  { title: 'Roles', key: 'roles', sortable: false, width: 250 },
  { title: 'Status', key: 'is_active', width: 100 },
  { title: 'Actions', key: 'actions', sortable: false, width: 180 },
]

const defaultForm = () => ({ name: '', model_id: '', provider: 'ollama', base_url: 'http://host.docker.internal:11434', api_key: '', is_active: true })
const form = ref(defaultForm())

const showDialog = (item = null) => {
  editItem.value = item
  form.value = item ? { ...item } : defaultForm()
  dialog.value = true
}

const handleSave = async () => {
  saving.value = true
  try {
    if (editItem.value) {
      await settingsStore.updateModel(editItem.value.id, form.value)
    } else {
      await settingsStore.createModel(form.value)
    }
    dialog.value = false
    showSnackbar('Model saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Error', 'error')
  } finally {
    saving.value = false
  }
}

const handleDelete = (item) => {
  deleteTarget.value = item
  deleteDialog.value = true
}

const confirmDelete = async () => {
  await settingsStore.deleteModel(deleteTarget.value.id)
  deleteDialog.value = false
  showSnackbar('Model deleted')
}

const testModel = async (item) => {
  try {
    await settingsStore.testModel(item.id)
    showSnackbar('Connection successful')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Connection failed', 'error')
  }
}

const listModels = async (item) => {
  try {
    availModels.value = await settingsStore.listAvailableModels(item.id)
    availDialog.value = true
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Error', 'error')
  }
}

// ═══════════ Model Roles ═══════════
const rolesDialog = ref(false)
const savingRoles = ref(false)
const rolesLoaded = ref(false)
const availableRoles = ref([])
const roleAssignments = ref({})  // { role: model_config_id }

// Models shown on first tab: only running Ollama models + all API models
const runningOllamaNames = computed(() => new Set(ollamaRunningModels.value.map(m => m.name)))
const displayedModels = computed(() => settingsStore.models.filter(m => {
  if (m.provider !== 'ollama') return true
  return runningOllamaNames.value.has(m.model_id)
}))

const activeModels = computed(() => displayedModels.value.filter(m => m.is_active))

// All active models (including offline Ollama) for role assignment dropdown
const allActiveModels = computed(() => settingsStore.models.filter(m => m.is_active))

// Check if a model is online (running for Ollama, always true for API)
const isModelOnline = (model) => {
  if (model.provider !== 'ollama') return true
  return runningOllamaNames.value.has(model.model_id)
}

// Check if the model assigned to a role is online
const isRoleModelOnline = (role) => {
  const modelId = roleAssignments.value[role]
  if (!modelId) return false
  const model = settingsStore.models.find(m => m.id === modelId)
  if (!model) return false
  return isModelOnline(model)
}

// Watchdog info
const watchdogInfo = ref(null)
const restartingRole = ref(null)

const fetchWatchdogInfo = async () => {
  try {
    const { data } = await api.get('/ollama/watchdog')
    watchdogInfo.value = data
  } catch (e) {
    watchdogInfo.value = null
  }
}

// Restart the model assigned to a role
const restartRoleModel = async (role) => {
  const modelId = roleAssignments.value[role]
  if (!modelId) return
  const model = settingsStore.models.find(m => m.id === modelId)
  if (!model || model.provider !== 'ollama') return

  restartingRole.value = role
  try {
    await api.post(`/ollama/models/${encodeURIComponent(model.model_id)}/load`)
    await fetchOllamaRunning()
    showSnackbar(`Model ${model.name} restarted`)
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to restart model', 'error')
  } finally {
    restartingRole.value = null
  }
}

// Check if base model is assigned and available (running ollama or API)
const hasActiveBaseModel = computed(() => {
  const baseId = roleAssignments.value['base']
  if (!baseId) return false
  const model = settingsStore.models.find(m => m.id === baseId)
  if (!model || !model.is_active) return false
  if (model.provider === 'ollama' && !runningOllamaNames.value.has(model.model_id)) return false
  return true
})

const roleColorMap = {
  understanding: 'blue', planning: 'indigo', code_generation: 'deep-purple',
  text_documents: 'teal', data_analysis: 'cyan', embedding: 'orange',
  json_output: 'lime', creative: 'pink', validation: 'green',
  photo_analysis: 'light-blue', video_analysis: 'purple', sound_generation: 'deep-orange',
  speech_recognition: 'brown', translation: 'blue-grey', dialog: 'grey', base: 'amber',
}
const roleColor = (role) => roleColorMap[role] || 'grey'

const getModelRoles = (model) => {
  return availableRoles.value.filter(r => r.role !== 'base' && roleAssignments.value[r.role] === model.id)
}
const isBaseModel = (model) => roleAssignments.value['base'] === model.id

const setRoleAssignment = (role, modelId) => {
  if (modelId) {
    roleAssignments.value[role] = modelId
  } else {
    delete roleAssignments.value[role]
  }
}

const fetchRoles = async () => {
  try {
    const { data } = await api.get('/settings/model-roles')
    availableRoles.value = data.available_roles
    roleAssignments.value = {}
    for (const a of data.assignments) {
      roleAssignments.value[a.role] = a.model_config_id
    }
    rolesLoaded.value = true
    // Sync to global store for base model alert
    settingsStore.roleAssignments = { ...roleAssignments.value }
    settingsStore.rolesLoaded = true
  } catch (e) { console.error('Failed to fetch roles:', e) }
}

const openRolesDialog = async () => {
  await fetchRoles()
  await fetchWatchdogInfo()
  // Keep all assignments including offline models — show status indicator instead of stripping
  rolesDialog.value = true
}

const saveRoles = async () => {
  savingRoles.value = true
  try {
    const assignments = Object.entries(roleAssignments.value)
      .filter(([_, v]) => v)
      .map(([role, model_config_id]) => ({ role, model_config_id }))
    const { data } = await api.put('/settings/model-roles', { assignments })
    roleAssignments.value = {}
    for (const a of data.assignments) {
      roleAssignments.value[a.role] = a.model_config_id
    }
    // Sync to global store
    settingsStore.roleAssignments = { ...roleAssignments.value }
    rolesDialog.value = false
    showSnackbar('Roles saved')
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save roles', 'error')
  } finally {
    savingRoles.value = false
  }
}

// ═══════════ Ollama tab state ═══════════
const ollamaStatus = ref({ running: false, base_url: '', models_count: 0 })
const ollamaModels = ref([])
const ollamaRunningModels = ref([])
const ollamaLoading = ref(false)
const ollamaRefreshing = ref(false)
const starting = ref(false)
const stopping = ref(false)

// Pull
const pullModelName = ref('')
const pulling = ref(false)
const pullResult = ref(null)
const pullProgress = ref(null)
const pullSpeed = ref('')

// Catalog
const showCatalog = ref(false)
const catalogModels = ref([])
const catalogSearch = ref('')
const catalogLoading = ref(false)

const filteredCatalog = computed(() => {
  const q = (catalogSearch.value || '').toLowerCase()
  if (!q) return catalogModels.value
  return catalogModels.value.filter(m =>
    m.name.toLowerCase().includes(q) ||
    m.description.toLowerCase().includes(q) ||
    (m.capabilities || []).some(c => c.toLowerCase().includes(q))
  )
})

// Detail
const detailDialog = ref(false)
const detailModel = ref(null)
const detailLoading = ref(false)
const modelDetail = ref(null)

// Ollama delete
const ollamaDeleteDialog = ref(false)
const ollamaDeleteTarget = ref(null)
const ollamaDeleting = ref(false)

// Load / unload
const loadingModel = ref(null)
const unloadingModel = ref(null)

// Chat
const chatDialog = ref(false)
const chatModel = ref('')
const chatMessages = ref([])
const chatInput = ref('')
const chatSending = ref(false)
const chatContainer = ref(null)

// ═══════════ Helpers ═══════════
const formatDate = (iso) => {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

const formatBytes = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
  if (bytes >= 1e3) return (bytes / 1e3).toFixed(1) + ' KB'
  return bytes + ' B'
}

const isModelRunning = (name) => ollamaRunningModels.value.some(m => m.name === name)

const capColor = (cap) => {
  const colors = { tools: 'indigo', vision: 'teal', thinking: 'deep-purple', embedding: 'orange', cloud: 'blue-grey' }
  return colors[cap] || 'grey'
}

// ═══════════ Ollama methods ═══════════
const fetchOllamaStatus = async () => {
  try {
    const { data } = await api.get('/ollama/status')
    ollamaStatus.value = data
  } catch {
    ollamaStatus.value = { running: false, base_url: '', models_count: 0 }
  }
}

const fetchOllamaModels = async () => {
  if (!ollamaStatus.value.running) { ollamaModels.value = []; return }
  ollamaLoading.value = true
  try {
    const { data } = await api.get('/ollama/models')
    ollamaModels.value = data
  } catch { ollamaModels.value = [] }
  finally { ollamaLoading.value = false }
}

const fetchOllamaRunning = async () => {
  if (!ollamaStatus.value.running) { ollamaRunningModels.value = []; settingsStore.ollamaRunningModels = []; return }
  try {
    const { data } = await api.get('/ollama/running')
    ollamaRunningModels.value = data
    settingsStore.ollamaRunningModels = data
  } catch { ollamaRunningModels.value = []; settingsStore.ollamaRunningModels = [] }
}

const fetchCatalog = async () => {
  catalogLoading.value = true
  try {
    const { data } = await api.get('/ollama/models/catalog')
    catalogModels.value = data
  } catch { catalogModels.value = [] }
  finally { catalogLoading.value = false }
}

const toggleCatalog = () => {
  showCatalog.value = !showCatalog.value
  if (showCatalog.value && !catalogModels.value.length) {
    fetchCatalog()
  }
}

const refreshOllama = async () => {
  ollamaRefreshing.value = true
  await fetchOllamaStatus()
  await Promise.all([fetchOllamaModels(), fetchOllamaRunning()])
  ollamaRefreshing.value = false
}

const startOllama = async () => {
  starting.value = true
  try {
    await api.post('/ollama/start')
    await fetchOllamaStatus()
    await Promise.all([fetchOllamaModels(), fetchOllamaRunning()])
  } catch (e) { console.error('Failed to start Ollama:', e) }
  finally { starting.value = false }
}

const stopOllama = async () => {
  stopping.value = true
  try {
    await api.post('/ollama/stop')
    await fetchOllamaStatus()
    ollamaModels.value = []
    ollamaRunningModels.value = []
  } catch (e) { console.error('Failed to stop Ollama:', e) }
  finally { stopping.value = false }
}

const pullModel = async () => {
  if (!pullModelName.value) return
  pulling.value = true
  pullResult.value = null
  pullProgress.value = { status: 'Starting...', progress: 0, total: 0, completed: 0 }
  pullSpeed.value = ''

  let lastCompleted = 0
  let lastTime = Date.now()

  try {
    const token = localStorage.getItem('access_token')
    const response = await fetch('/api/ollama/models/pull/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ model: pullModelName.value }),
    })

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}))
      throw new Error(errData.detail || `HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))

          if (data.error) {
            pullResult.value = { type: 'error', message: data.status }
            pulling.value = false
            pullProgress.value = null
            return
          }

          if (data.completed === true && data.status === 'success') {
            pullResult.value = { type: 'success', message: `Model "${pullModelName.value}" pulled successfully!` }
            pullModelName.value = ''
            pulling.value = false
            pullProgress.value = null
            await Promise.all([fetchOllamaModels(), fetchCatalog()])
            return
          }

          pullProgress.value = {
            status: data.status || '',
            progress: data.progress || 0,
            total: data.total || 0,
            completed: data.completed || 0,
          }

          const now = Date.now()
          const elapsed = (now - lastTime) / 1000
          if (elapsed >= 0.5 && data.completed > 0) {
            const bytesDelta = (data.completed || 0) - lastCompleted
            if (bytesDelta > 0 && elapsed > 0) pullSpeed.value = formatBytes(bytesDelta / elapsed)
            lastCompleted = data.completed || 0
            lastTime = now
          }
        } catch { /* skip bad JSON */ }
      }
    }

    if (pulling.value) {
      pullResult.value = { type: 'success', message: `Model "${pullModelName.value}" pulled successfully!` }
      pullModelName.value = ''
      await Promise.all([fetchOllamaModels(), fetchCatalog()])
    }
  } catch (e) {
    pullResult.value = { type: 'error', message: e.message || 'Pull failed' }
  } finally {
    pulling.value = false
    pullProgress.value = null
    pullSpeed.value = ''
  }
}

const pullFromCatalog = (m, size) => {
  pullModelName.value = size ? `${m.name}:${size}` : m.name
  pullModel()
}

const showOllamaDetail = async (m) => {
  detailModel.value = m
  detailDialog.value = true
  detailLoading.value = true
  modelDetail.value = null
  try {
    const { data } = await api.get(`/ollama/models/${encodeURIComponent(m.name)}/detail`)
    modelDetail.value = data
  } catch { modelDetail.value = { parameters: 'Failed to load details' } }
  finally { detailLoading.value = false }
}

const confirmOllamaDelete = (m) => {
  ollamaDeleteTarget.value = m
  ollamaDeleteDialog.value = true
}

const deleteOllamaModel = async () => {
  if (!ollamaDeleteTarget.value) return
  ollamaDeleting.value = true
  try {
    await api.delete(`/ollama/models/${encodeURIComponent(ollamaDeleteTarget.value.name)}`)
    ollamaModels.value = ollamaModels.value.filter(m => m.name !== ollamaDeleteTarget.value.name)
    ollamaDeleteDialog.value = false
  } catch (e) { console.error('Failed to delete model:', e) }
  finally { ollamaDeleting.value = false }
}

const loadModel = async (name) => {
  loadingModel.value = name
  try {
    await api.post(`/ollama/models/${encodeURIComponent(name)}/load`)
    await fetchOllamaRunning()
  } catch (e) { console.error('Failed to load model:', e) }
  finally { loadingModel.value = null }
}

const unloadModel = async (name) => {
  unloadingModel.value = name
  try {
    await api.post(`/ollama/models/${encodeURIComponent(name)}/unload`)
    await fetchOllamaRunning()
  } catch (e) { console.error('Failed to unload model:', e) }
  finally { unloadingModel.value = null }
}

const openChat = (name) => {
  chatModel.value = name
  chatMessages.value = []
  chatInput.value = ''
  chatDialog.value = true
}

const closeChat = () => {
  chatDialog.value = false
  chatMessages.value = []
}

const scrollToBottom = () => {
  setTimeout(() => {
    const el = chatContainer.value?.$el || chatContainer.value
    if (el) el.scrollTop = el.scrollHeight
  }, 50)
}

const sendChat = async () => {
  const text = chatInput.value.trim()
  if (!text || chatSending.value) return

  chatMessages.value.push({ role: 'user', content: text })
  chatInput.value = ''
  chatSending.value = true
  scrollToBottom()

  try {
    const { data } = await api.post('/ollama/chat', { model: chatModel.value, message: text })
    const durationSec = data.total_duration ? (data.total_duration / 1e9).toFixed(1) + 's' : ''
    const tokensPerSec = data.eval_duration && data.eval_count
      ? (data.eval_count / (data.eval_duration / 1e9)).toFixed(1) + ' tok/s' : ''
    const stats = [durationSec, tokensPerSec].filter(Boolean).join(' · ')
    chatMessages.value.push({ role: 'assistant', content: data.content, stats })
  } catch (e) {
    chatMessages.value.push({ role: 'assistant', content: '❌ ' + (e.response?.data?.detail || 'Request failed'), stats: '' })
  } finally {
    chatSending.value = false
    scrollToBottom()
  }
}

// ═══════════ Init ═══════════
onMounted(async () => {
  settingsStore.fetchModels()
  fetchRoles()
  await fetchOllamaStatus()
  await Promise.all([fetchOllamaModels(), fetchOllamaRunning()])
})
</script>

<style scoped>
.pull-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.catalog-table :deep(tr) {
  transition: background 0.15s;
}
.installed-row {
  opacity: 0.65;
}
.catalog-size-chip {
  cursor: pointer;
  transition: transform 0.1s, box-shadow 0.1s;
}
.catalog-size-chip:not(.v-chip--disabled):hover {
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(var(--v-theme-primary), 0.3);
}
</style>
