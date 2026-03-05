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
        <v-tab value="aspirations">Aspirations</v-tab>
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
            <!-- Protocols (multi-protocol) -->
            <v-list-item v-if="agent.protocols && agent.protocols.length">
              <strong>Protocols:</strong>&nbsp;
              <div class="d-flex flex-wrap ga-1 ml-1" style="display:inline-flex">
                <v-chip
                  v-for="p in agent.protocols" :key="p.id"
                  size="small"
                  :color="p.is_main ? 'amber' : 'deep-purple'"
                  variant="tonal"
                  @click="toggleProtocolPreview(p)"
                  style="cursor:pointer"
                >
                  <v-icon start size="14">{{ p.is_main ? 'mdi-crown' : 'mdi-head-cog' }}</v-icon>
                  {{ p.name }}
                  <v-chip v-if="p.type === 'orchestrator'" size="x-small" color="amber" variant="flat" class="ml-1" label>orch</v-chip>
                </v-chip>
              </div>
            </v-list-item>
            <v-list-item v-else-if="agent.thinking_protocol">
              <strong>Thinking Protocol:</strong>&nbsp;
              <v-chip size="small" color="deep-purple" variant="tonal" class="ml-1" @click="showProtocolPreview = !showProtocolPreview" style="cursor:pointer">
                <v-icon start size="14">mdi-head-cog</v-icon>
                {{ agent.thinking_protocol.name }}
                <v-icon end size="14">{{ showProtocolPreview ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
              </v-chip>
            </v-list-item>
          </v-list>

          <!-- Protocol preview -->
          <div v-if="previewProtocol" class="mt-3 mb-3">
            <v-sheet class="pa-4 rounded" color="grey-darken-4">
              <div class="d-flex align-center mb-2">
                <v-icon size="18" :color="previewProtocol.is_main ? 'amber' : 'deep-purple'" class="mr-2">
                  {{ previewProtocol.is_main ? 'mdi-crown' : 'mdi-head-cog' }}
                </v-icon>
                <span class="text-subtitle-2">{{ previewProtocol.name }}</span>
                <v-chip v-if="previewProtocol.type" size="x-small" :color="previewProtocol.type === 'orchestrator' ? 'amber' : 'blue-grey'" variant="tonal" class="ml-2">{{ previewProtocol.type }}</v-chip>
                <v-spacer />
                <v-btn icon="mdi-close" size="x-small" variant="text" @click="previewProtocol = null" />
              </div>
              <ProtocolFlow :steps="previewProtocol.steps || []" :protocols="agent.protocols" />
            </v-sheet>
          </div>
          <div v-else-if="showProtocolPreview && agent.thinking_protocol" class="mt-3 mb-3">
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

          <!-- Aspirations summary -->
          <div v-if="agent.aspirations && (agent.aspirations.dreams?.length || agent.aspirations.desires?.length || agent.aspirations.goals?.length)" class="mt-4">
            <div class="text-subtitle-2 mb-1">Aspirations ({{ (agent.aspirations.dreams?.length || 0) + (agent.aspirations.desires?.length || 0) + (agent.aspirations.goals?.length || 0) }})</div>
            <div class="d-flex flex-wrap ga-1">
              <v-chip v-for="d in (agent.aspirations.dreams || [])" :key="d.id" size="small" color="deep-purple-lighten-2" variant="tonal">
                <v-icon start size="12">mdi-weather-night</v-icon>{{ d.text }}
                <v-icon v-if="d.locked" end size="10" color="amber">mdi-lock</v-icon>
              </v-chip>
              <v-chip v-for="d in (agent.aspirations.desires || [])" :key="d.id" size="small" color="pink-lighten-2" variant="tonal">
                <v-icon start size="12">mdi-heart-outline</v-icon>{{ d.text }}
                <v-icon v-if="d.locked" end size="10" color="amber">mdi-lock</v-icon>
              </v-chip>
              <v-chip v-for="g in (agent.aspirations.goals || [])" :key="g.id" size="small" color="green" variant="tonal">
                <v-icon start size="12">mdi-flag-checkered</v-icon>{{ g.text }}
                <v-icon v-if="g.locked" end size="10" color="amber">mdi-lock</v-icon>
              </v-chip>
            </div>
          </div>

          <div v-if="agent.system_prompt" class="mt-4">
            <div class="text-subtitle-2 mb-1">System Prompt</div>
            <v-sheet rounded class="pa-3 bg-grey-darken-4" style="white-space: pre-wrap; font-family: monospace; font-size: 13px;">{{ agent.system_prompt }}</v-sheet>
          </div>

          <!-- Agent Permissions -->
          <div class="mt-5">
            <div class="text-subtitle-2 mb-2">
              <v-icon size="18" class="mr-1">mdi-shield-lock</v-icon>
              Agent Permissions
            </div>
            <v-alert
              v-if="!globalFsEnabled && !globalSysEnabled"
              type="warning"
              variant="tonal"
              density="compact"
              class="mb-3"
              icon="mdi-shield-off"
            >
              All access is disabled globally. Enable in <strong>Settings → System Access Controls</strong> first.
            </v-alert>
            <v-row dense>
              <v-col cols="12" md="6">
                <v-card variant="outlined" class="pa-3" :class="{ 'border-opacity-25': !globalFsEnabled }">
                  <div class="d-flex align-center">
                    <v-switch
                      :model-value="agent.filesystem_access"
                      color="error"
                      hide-details
                      density="compact"
                      :loading="permSaving"
                      :disabled="!globalFsEnabled"
                      @update:model-value="(v) => toggleAgentPermission('filesystem_access', v)"
                    >
                      <template #label>
                        <div>
                          <span class="font-weight-medium">File System Access</span>
                          <div class="text-caption text-medium-emphasis">Read, write, delete external files</div>
                        </div>
                      </template>
                    </v-switch>
                    <v-spacer />
                    <v-chip v-if="!globalFsEnabled && agent.filesystem_access" color="warning" size="x-small" variant="flat">
                      BLOCKED
                    </v-chip>
                    <v-chip v-else :color="agent.filesystem_access && globalFsEnabled ? 'error' : 'grey'" size="x-small" variant="flat">
                      {{ agent.filesystem_access && globalFsEnabled ? 'ON' : 'OFF' }}
                    </v-chip>
                  </div>
                  <div v-if="!globalFsEnabled && agent.filesystem_access" class="text-caption text-warning mt-1">
                    <v-icon size="12" class="mr-1">mdi-alert</v-icon>Globally disabled — agent setting overridden
                  </div>
                </v-card>
              </v-col>
              <v-col cols="12" md="6">
                <v-card variant="outlined" class="pa-3" :class="{ 'border-opacity-25': !globalSysEnabled }">
                  <div class="d-flex align-center">
                    <v-switch
                      :model-value="agent.system_access"
                      color="error"
                      hide-details
                      density="compact"
                      :loading="permSaving"
                      :disabled="!globalSysEnabled"
                      @update:model-value="(v) => toggleAgentPermission('system_access', v)"
                    >
                      <template #label>
                        <div>
                          <span class="font-weight-medium">System Access</span>
                          <div class="text-caption text-medium-emphasis">Terminal commands, processes, system info</div>
                        </div>
                      </template>
                    </v-switch>
                    <v-spacer />
                    <v-chip v-if="!globalSysEnabled && agent.system_access" color="warning" size="x-small" variant="flat">
                      BLOCKED
                    </v-chip>
                    <v-chip v-else :color="agent.system_access && globalSysEnabled ? 'error' : 'grey'" size="x-small" variant="flat">
                      {{ agent.system_access && globalSysEnabled ? 'ON' : 'OFF' }}
                    </v-chip>
                  </div>
                  <div v-if="!globalSysEnabled && agent.system_access" class="text-caption text-warning mt-1">
                    <v-icon size="12" class="mr-1">mdi-alert</v-icon>Globally disabled — agent setting overridden
                  </div>
                </v-card>
              </v-col>
            </v-row>
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

        <!-- Aspirations Tab (Dreams, Desires, Goals) -->
        <div v-if="tab === 'aspirations'">
          <!-- Dreams -->
          <div class="d-flex align-center mb-3">
            <div class="text-subtitle-1 font-weight-bold">
              <v-icon color="deep-purple-lighten-2" size="20" class="mr-1">mdi-weather-night</v-icon>
              Dreams
            </div>
            <v-chip size="x-small" class="ml-2" variant="tonal" color="deep-purple-lighten-2">long-term visions</v-chip>
            <v-spacer />
            <v-btn color="deep-purple-lighten-2" size="small" variant="tonal" prepend-icon="mdi-plus" @click="openAspirationDialog('dreams')">Add Dream</v-btn>
          </div>
          <div v-if="aspirations.dreams.length" class="mb-6">
            <v-card v-for="a in aspirations.dreams" :key="a.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-icon :color="a.locked ? 'amber' : 'grey'" size="16" class="mr-2">{{ a.locked ? 'mdi-lock' : 'mdi-lock-open-variant' }}</v-icon>
                <v-chip :color="priorityColor(a.priority)" size="x-small" variant="flat" class="mr-2">{{ a.priority }}</v-chip>
                <span class="text-body-1 flex-grow-1">{{ a.text }}</span>
                <v-chip v-if="a.created_by === 'agent'" size="x-small" variant="tonal" color="cyan" class="mr-2">agent</v-chip>
                <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editAspiration(a, 'dreams')" class="mr-1" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="confirmDeleteAspiration(a, 'dreams')" />
              </div>
            </v-card>
          </div>
          <div v-else class="text-center text-grey pa-4 mb-6">No dreams defined</div>

          <!-- Desires -->
          <div class="d-flex align-center mb-3">
            <div class="text-subtitle-1 font-weight-bold">
              <v-icon color="pink-lighten-2" size="20" class="mr-1">mdi-heart-outline</v-icon>
              Desires
            </div>
            <v-chip size="x-small" class="ml-2" variant="tonal" color="pink-lighten-2">wants & preferences</v-chip>
            <v-spacer />
            <v-btn color="pink-lighten-2" size="small" variant="tonal" prepend-icon="mdi-plus" @click="openAspirationDialog('desires')">Add Desire</v-btn>
          </div>
          <div v-if="aspirations.desires.length" class="mb-6">
            <v-card v-for="a in aspirations.desires" :key="a.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-icon :color="a.locked ? 'amber' : 'grey'" size="16" class="mr-2">{{ a.locked ? 'mdi-lock' : 'mdi-lock-open-variant' }}</v-icon>
                <v-chip :color="priorityColor(a.priority)" size="x-small" variant="flat" class="mr-2">{{ a.priority }}</v-chip>
                <span class="text-body-1 flex-grow-1">{{ a.text }}</span>
                <v-chip v-if="a.created_by === 'agent'" size="x-small" variant="tonal" color="cyan" class="mr-2">agent</v-chip>
                <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editAspiration(a, 'desires')" class="mr-1" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="confirmDeleteAspiration(a, 'desires')" />
              </div>
            </v-card>
          </div>
          <div v-else class="text-center text-grey pa-4 mb-6">No desires defined</div>

          <!-- Goals -->
          <div class="d-flex align-center mb-3">
            <div class="text-subtitle-1 font-weight-bold">
              <v-icon color="green" size="20" class="mr-1">mdi-flag-checkered</v-icon>
              Goals
            </div>
            <v-chip size="x-small" class="ml-2" variant="tonal" color="green">actionable objectives</v-chip>
            <v-spacer />
            <v-btn color="green" size="small" variant="tonal" prepend-icon="mdi-plus" @click="openAspirationDialog('goals')">Add Goal</v-btn>
          </div>
          <div v-if="aspirations.goals.length">
            <v-card v-for="a in aspirations.goals" :key="a.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-icon :color="a.locked ? 'amber' : 'grey'" size="16" class="mr-2">{{ a.locked ? 'mdi-lock' : 'mdi-lock-open-variant' }}</v-icon>
                <v-chip :color="priorityColor(a.priority)" size="x-small" variant="flat" class="mr-2">{{ a.priority }}</v-chip>
                <v-chip :color="goalStatusColor(a.status)" size="x-small" variant="tonal" class="mr-2">{{ a.status || 'active' }}</v-chip>
                <span class="text-body-1 flex-grow-1">{{ a.text }}</span>
                <span v-if="a.deadline" class="text-caption text-grey mr-2">{{ a.deadline }}</span>
                <v-chip v-if="a.created_by === 'agent'" size="x-small" variant="tonal" color="cyan" class="mr-2">agent</v-chip>
                <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editAspiration(a, 'goals')" class="mr-1" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="confirmDeleteAspiration(a, 'goals')" />
              </div>
            </v-card>
          </div>
          <div v-else class="text-center text-grey pa-4">No goals defined</div>
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
          <div class="d-flex align-center mb-4">
            <v-text-field
              v-model="skillSearch"
              density="compact"
              variant="outlined"
              prepend-inner-icon="mdi-magnify"
              placeholder="Search skills..."
              hide-details
              style="max-width: 300px"
              clearable
            />
            <v-spacer />
            <v-btn color="primary" size="small" variant="tonal" prepend-icon="mdi-plus" @click="openNewSkillDialog">New Personal Skill</v-btn>
          </div>

          <!-- Personal skills -->
          <div v-if="personalSkills.length" class="mb-5">
            <div class="d-flex align-center mb-2">
              <v-icon color="cyan" size="18" class="mr-2">mdi-account-lock</v-icon>
              <span class="text-subtitle-2 font-weight-bold">Personal Skills</span>
              <v-chip size="x-small" class="ml-2" variant="tonal" color="cyan">owned by this agent</v-chip>
            </div>
            <v-card v-for="s in personalSkills" :key="s.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-switch
                  :model-value="s.enabled"
                  color="success"
                  density="compact"
                  hide-details
                  class="mr-3 flex-grow-0"
                  @update:model-value="toggleSkill(s)"
                />
                <div class="flex-grow-1">
                  <div class="d-flex align-center">
                    <span class="text-body-1 font-weight-medium">{{ s.display_name }}</span>
                    <v-chip size="x-small" variant="tonal" class="ml-2">{{ s.category }}</v-chip>
                    <v-chip v-if="s.is_shared" size="x-small" variant="flat" color="success" class="ml-1">
                      <v-icon start size="10">mdi-share-variant</v-icon>shared
                    </v-chip>
                  </div>
                  <div v-if="s.description" class="text-caption text-grey">{{ s.description }}</div>
                </div>
                <v-btn v-if="!s.is_shared" icon size="x-small" variant="text" color="success" @click="shareSkill(s)" title="Share publicly">
                  <v-icon size="16">mdi-share</v-icon>
                </v-btn>
                <v-btn v-else icon size="x-small" variant="text" color="grey" @click="unshareSkill(s)" title="Make private">
                  <v-icon size="16">mdi-share-off</v-icon>
                </v-btn>
                <v-btn icon size="x-small" variant="text" @click="$router.push(`/skills/${s.id}`)" title="Edit">
                  <v-icon size="16">mdi-pencil</v-icon>
                </v-btn>
              </div>
            </v-card>
          </div>

          <!-- System skills -->
          <div v-if="systemSkills.length" class="mb-5">
            <div class="d-flex align-center mb-2">
              <v-icon color="primary" size="18" class="mr-2">mdi-cog</v-icon>
              <span class="text-subtitle-2 font-weight-bold">System Skills</span>
              <v-chip size="x-small" class="ml-2" variant="tonal" color="primary">built-in</v-chip>
            </div>
            <v-card v-for="s in systemSkills" :key="s.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-switch
                  :model-value="s.enabled"
                  color="success"
                  density="compact"
                  hide-details
                  class="mr-3 flex-grow-0"
                  @update:model-value="toggleSkill(s)"
                />
                <div class="flex-grow-1">
                  <div class="d-flex align-center">
                    <span class="text-body-1 font-weight-medium">{{ s.display_name }}</span>
                    <v-chip size="x-small" variant="tonal" class="ml-2">{{ s.category }}</v-chip>
                  </div>
                  <div v-if="s.description" class="text-caption text-grey">{{ s.description }}</div>
                </div>
                <v-btn icon size="x-small" variant="text" @click="$router.push(`/skills/${s.id}`)" title="View">
                  <v-icon size="16">mdi-eye</v-icon>
                </v-btn>
              </div>
            </v-card>
          </div>

          <!-- Public skills (shared by other agents or users) -->
          <div v-if="publicSkills.length" class="mb-5">
            <div class="d-flex align-center mb-2">
              <v-icon color="green" size="18" class="mr-2">mdi-earth</v-icon>
              <span class="text-subtitle-2 font-weight-bold">Public Skills</span>
              <v-chip size="x-small" class="ml-2" variant="tonal" color="green">shared by others</v-chip>
            </div>
            <v-card v-for="s in publicSkills" :key="s.id" variant="outlined" class="mb-2 pa-3">
              <div class="d-flex align-center">
                <v-switch
                  :model-value="s.enabled"
                  color="success"
                  density="compact"
                  hide-details
                  class="mr-3 flex-grow-0"
                  @update:model-value="toggleSkill(s)"
                />
                <div class="flex-grow-1">
                  <div class="d-flex align-center">
                    <span class="text-body-1 font-weight-medium">{{ s.display_name }}</span>
                    <v-chip size="x-small" variant="tonal" class="ml-2">{{ s.category }}</v-chip>
                  </div>
                  <div v-if="s.description" class="text-caption text-grey">{{ s.description }}</div>
                </div>
                <v-btn icon size="x-small" variant="text" @click="$router.push(`/skills/${s.id}`)" title="View">
                  <v-icon size="16">mdi-eye</v-icon>
                </v-btn>
              </div>
            </v-card>
          </div>

          <div v-if="!allAvailableSkills.length" class="text-center text-grey pa-6">No skills available</div>
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
                    v-if="!['agent.json', 'settings.json', 'beliefs.json', 'aspirations.json'].includes(node.path) && node.path !== 'data'"
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

    <!-- Aspiration Add/Edit Dialog -->
    <v-dialog v-model="aspirationDialog" max-width="600">
      <v-card>
        <v-card-title>{{ aspirationEditId ? 'Edit' : 'Add' }} {{ aspirationTypeLabel(aspirationDialogType) }}</v-card-title>
        <v-card-text>
          <v-textarea v-model="aspirationText" label="Description" rows="3" autofocus density="compact" class="mb-2" />
          <v-row>
            <v-col cols="4">
              <v-select v-model="aspirationPriority" :items="['low', 'medium', 'high']" label="Priority" density="compact" />
            </v-col>
            <v-col cols="4">
              <v-checkbox v-model="aspirationLocked" label="Locked (immutable by agent)" density="compact" hide-details />
            </v-col>
            <v-col v-if="aspirationDialogType === 'goals'" cols="4">
              <v-select v-model="aspirationStatus" :items="['active', 'in_progress', 'completed', 'abandoned']" label="Status" density="compact" />
            </v-col>
          </v-row>
          <v-text-field v-if="aspirationDialogType === 'goals'" v-model="aspirationDeadline" label="Deadline (optional, e.g. 2026-06-01)" density="compact" class="mt-2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="aspirationDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="saveAspiration" :loading="aspirationSaving">{{ aspirationEditId ? 'Save' : 'Add' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Aspiration Dialog -->
    <v-dialog v-model="deleteAspirationDialog" max-width="400">
      <v-card>
        <v-card-title>Delete {{ aspirationTypeLabel(deleteAspirationType) }}</v-card-title>
        <v-card-text>"{{ deleteAspirationItem?.text }}"</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteAspirationDialog = false">Cancel</v-btn>
          <v-btn color="error" @click="doDeleteAspiration">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- New Personal Skill Dialog -->
    <v-dialog v-model="newSkillDialog" max-width="600">
      <v-card>
        <v-card-title>New Personal Skill</v-card-title>
        <v-card-text>
          <v-text-field v-model="newSkillName" label="Name (unique identifier, e.g. my_calculator)" density="compact" class="mb-2" autofocus />
          <v-text-field v-model="newSkillDisplayName" label="Display Name" density="compact" class="mb-2" />
          <v-textarea v-model="newSkillDescription" label="Description" rows="2" density="compact" class="mb-2" />
          <v-textarea v-model="newSkillDescForAgent" label="Description for Agent (how the agent should use it)" rows="2" density="compact" class="mb-2" />
          <v-row>
            <v-col cols="6">
              <v-select v-model="newSkillCategory" :items="['general','web','files','code','data','custom']" label="Category" density="compact" />
            </v-col>
            <v-col cols="6">
              <v-checkbox v-model="newSkillShared" label="Share publicly" density="compact" hide-details />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="newSkillDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="createPersonalSkill" :loading="newSkillSaving">Create</v-btn>
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
import { useSettingsStore } from '../stores/settings'
import ProtocolFlow from '../components/ProtocolFlow.vue'

const route = useRoute()
const router = useRouter()
const agentsStore = useAgentsStore()
const settingsStore = useSettingsStore()
const tab = ref('info')
const agent = ref(null)
const stats = ref({})
const tasks = ref([])
const showProtocolPreview = ref(false)
const previewProtocol = ref(null)
const logs = ref([])
const allAvailableSkills = ref([])
const memories = ref([])
const logLevel = ref('all')
const skillSearch = ref('')
const permSaving = ref(false)
const globalFsEnabled = ref(false)
const globalSysEnabled = ref(false)

// New Skill dialog state
const newSkillDialog = ref(false)
const newSkillName = ref('')
const newSkillDisplayName = ref('')
const newSkillDescription = ref('')
const newSkillDescForAgent = ref('')
const newSkillCategory = ref('custom')
const newSkillShared = ref(false)
const newSkillSaving = ref(false)

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

// Aspirations tab state
const aspirations = ref({ dreams: [], desires: [], goals: [] })
const aspirationDialog = ref(false)
const aspirationDialogType = ref('dreams')
const aspirationText = ref('')
const aspirationPriority = ref('medium')
const aspirationLocked = ref(true)
const aspirationStatus = ref('active')
const aspirationDeadline = ref('')
const aspirationEditId = ref(null)
const aspirationSaving = ref(false)
const deleteAspirationDialog = ref(false)
const deleteAspirationItem = ref(null)
const deleteAspirationType = ref('dreams')

const id = computed(() => route.params.id)

const statusColor = (s) => ({ idle: 'grey', running: 'success', paused: 'warning', error: 'error', stopped: 'grey' }[s] || 'grey')
const taskStatusColor = (s) => ({ pending: 'info', running: 'success', completed: 'success', failed: 'error', cancelled: 'grey' }[s] || 'grey')
const logColor = (l) => ({ debug: 'grey', info: 'info', warning: 'warning', error: 'error', critical: 'error' }[l] || 'grey')
const priorityColor = (p) => ({ low: 'blue-grey', medium: 'orange', high: 'red' }[p] || 'grey')
const goalStatusColor = (s) => ({ active: 'blue', in_progress: 'orange', completed: 'green', abandoned: 'grey' }[s] || 'grey')
const aspirationTypeLabel = (t) => ({ dreams: 'Dream', desires: 'Desire', goals: 'Goal' }[t] || t)

const toggleProtocolPreview = (p) => {
  previewProtocol.value = previewProtocol.value?.id === p.id ? null : p
}

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
  try {
    await settingsStore.fetchSystemSettings()
    globalFsEnabled.value = settingsStore.systemSettings.filesystem_access_enabled?.value === 'true'
    globalSysEnabled.value = settingsStore.systemSettings.system_access_enabled?.value === 'true'
  } catch {}
}

const toggleAgentPermission = async (field, value) => {
  permSaving.value = true
  try {
    await api.put(`/agents/${id.value}`, { [field]: value })
    agent.value = await agentsStore.fetchAgent(id.value)
  } catch (e) { console.error('Toggle permission failed', e) }
  permSaving.value = false
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
  try {
    const { data } = await api.get(`/agents/${id.value}/skills/available`)
    allAvailableSkills.value = data
  } catch { allAvailableSkills.value = [] }
}

const filterBySearch = (list) => {
  if (!skillSearch.value) return list
  const q = skillSearch.value.toLowerCase()
  return list.filter(s => (s.display_name || s.name || '').toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q))
}
const personalSkills = computed(() => filterBySearch(allAvailableSkills.value.filter(s => s.ownership === 'personal')))
const systemSkills = computed(() => filterBySearch(allAvailableSkills.value.filter(s => s.ownership === 'system')))
const publicSkills = computed(() => filterBySearch(allAvailableSkills.value.filter(s => s.ownership === 'public')))

const toggleSkill = async (s) => {
  try {
    await api.post(`/agents/${id.value}/skills/toggle/${s.id}`)
    await loadSkills()
  } catch (e) { console.error('Toggle skill failed', e) }
}

const shareSkill = async (s) => {
  try {
    await api.post(`/agents/${id.value}/skills/${s.id}/share`)
    await loadSkills()
  } catch (e) { console.error('Share skill failed', e) }
}

const unshareSkill = async (s) => {
  try {
    await api.post(`/agents/${id.value}/skills/${s.id}/unshare`)
    await loadSkills()
  } catch (e) { console.error('Unshare skill failed', e) }
}

const openNewSkillDialog = () => {
  newSkillName.value = ''
  newSkillDisplayName.value = ''
  newSkillDescription.value = ''
  newSkillDescForAgent.value = ''
  newSkillCategory.value = 'custom'
  newSkillShared.value = false
  newSkillDialog.value = true
}

const createPersonalSkill = async () => {
  newSkillSaving.value = true
  try {
    await api.post(`/agents/${id.value}/skills/personal`, {
      name: newSkillName.value,
      display_name: newSkillDisplayName.value || undefined,
      description: newSkillDescription.value || undefined,
      description_for_agent: newSkillDescForAgent.value || undefined,
      category: newSkillCategory.value || 'custom',
      is_shared: newSkillShared.value
    })
    newSkillDialog.value = false
    await loadSkills()
  } catch (e) { console.error('Create personal skill failed', e) }
  newSkillSaving.value = false
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

// ===== Aspirations =====
const loadAspirations = async () => {
  try {
    const { data } = await api.get(`/agents/${id.value}/aspirations`)
    aspirations.value = { dreams: data.dreams || [], desires: data.desires || [], goals: data.goals || [] }
  } catch { aspirations.value = { dreams: [], desires: [], goals: [] } }
}

const openAspirationDialog = (type) => {
  aspirationDialogType.value = type
  aspirationText.value = ''
  aspirationPriority.value = 'medium'
  aspirationLocked.value = true
  aspirationStatus.value = 'active'
  aspirationDeadline.value = ''
  aspirationEditId.value = null
  aspirationDialog.value = true
}

const editAspiration = (item, type) => {
  aspirationDialogType.value = type
  aspirationText.value = item.text
  aspirationPriority.value = item.priority || 'medium'
  aspirationLocked.value = item.locked
  aspirationStatus.value = item.status || 'active'
  aspirationDeadline.value = item.deadline || ''
  aspirationEditId.value = item.id
  aspirationDialog.value = true
}

const saveAspiration = async () => {
  if (!aspirationText.value.trim()) return
  aspirationSaving.value = true
  try {
    const type = aspirationDialogType.value
    const payload = {
      text: aspirationText.value.trim(),
      priority: aspirationPriority.value,
      locked: aspirationLocked.value,
    }
    if (type === 'goals') {
      payload.status = aspirationStatus.value
      payload.deadline = aspirationDeadline.value || null
    }
    if (aspirationEditId.value) {
      await api.put(`/agents/${id.value}/aspirations/${type}/${aspirationEditId.value}`, payload)
    } else {
      await api.post(`/agents/${id.value}/aspirations/${type}`, payload)
    }
    aspirationDialog.value = false
    await loadAspirations()
    await loadData()
  } catch (e) { alert(e.response?.data?.detail || 'Failed to save') }
  finally { aspirationSaving.value = false }
}

const confirmDeleteAspiration = (item, type) => {
  deleteAspirationItem.value = item
  deleteAspirationType.value = type
  deleteAspirationDialog.value = true
}

const doDeleteAspiration = async () => {
  try {
    await api.delete(`/agents/${id.value}/aspirations/${deleteAspirationType.value}/${deleteAspirationItem.value.id}`)
    deleteAspirationDialog.value = false
    await loadAspirations()
    await loadData()
  } catch (e) { alert(e.response?.data?.detail || 'Failed to delete') }
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
  if (val === 'aspirations') loadAspirations()
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
