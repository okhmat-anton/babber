<template>
  <div v-if="project">
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <v-btn icon variant="text" class="mr-2" @click="$router.push('/projects')">
        <v-icon>mdi-arrow-left</v-icon>
      </v-btn>
      <div>
        <h1 class="text-h4">{{ project.name }}</h1>
        <div class="text-medium-emphasis text-body-2">
          <v-chip size="x-small" :color="statusColor(project.status)" variant="flat" class="mr-2">
            {{ project.status }}
          </v-chip>
          <v-chip v-for="tech in (project.tech_stack || [])" :key="tech" size="x-small" variant="tonal" color="cyan" class="mr-1">{{ tech }}</v-chip>
        </div>
      </div>
      <v-spacer />
      <v-chip variant="tonal" color="info" class="mr-2" prepend-icon="mdi-file-document-outline">
        {{ project.file_count }} files
      </v-chip>
      <v-chip variant="tonal" color="primary" prepend-icon="mdi-clipboard-list-outline">
        {{ project.task_stats?.done || 0 }}/{{ project.task_stats?.total || 0 }} tasks
      </v-chip>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="tasks" prepend-icon="mdi-clipboard-list">Backlog</v-tab>
      <v-tab value="code" prepend-icon="mdi-code-braces">Code</v-tab>
      <v-tab value="terminal" prepend-icon="mdi-console">Terminal</v-tab>
      <v-tab value="logs" prepend-icon="mdi-text-box-search">Logs</v-tab>
      <v-tab value="settings" prepend-icon="mdi-cog">Settings</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">

      <!-- ═══ TASKS TAB ═══ -->
      <v-window-item value="tasks">
        <div class="d-flex align-center mb-3">
          <v-btn-toggle v-model="taskViewMode" density="compact" mandatory variant="outlined" divided>
            <v-btn value="list" icon="mdi-format-list-bulleted" size="small" />
            <v-btn value="kanban" icon="mdi-view-column" size="small" />
          </v-btn-toggle>
          <v-spacer />
          <v-btn size="small" color="primary" prepend-icon="mdi-plus" @click="showTaskDialog = true">
            New Task
          </v-btn>
        </div>

        <!-- List View -->
        <template v-if="taskViewMode === 'list'">
          <v-data-table
            :headers="taskHeaders"
            :items="tasks"
            :loading="tasksLoading"
            hover
            density="compact"
            items-per-page="50"
            no-data-text="No tasks yet. Create your first task!"
            @click:row="(e, { item }) => openTaskDetail(item)"
            style="cursor: pointer"
          >
            <template #item.key="{ item }">
              <span class="font-weight-medium text-info">{{ item.key }}</span>
            </template>
            <template #item.status="{ item }">
              <v-select
                :model-value="item.status"
                :items="taskStatuses"
                density="compact"
                variant="plain"
                hide-details
                style="max-width: 140px"
                @update:model-value="moveTask(item, $event)"
                @click.stop
              >
                <template #selection="{ item: statusItem }">
                  <v-chip size="x-small" :color="taskStatusColor(statusItem.value)" variant="flat">
                    {{ statusItem.title }}
                  </v-chip>
                </template>
              </v-select>
            </template>
            <template #item.priority="{ item }">
              <v-chip size="x-small" :color="priorityColor(item.priority)" variant="tonal">
                {{ item.priority }}
              </v-chip>
            </template>
            <template #item.assignee="{ item }">
              <span class="text-caption">{{ item.assignee || '—' }}</span>
            </template>
            <template #item.actions="{ item }">
              <v-btn icon size="x-small" variant="text" @click.stop="editTask(item)">
                <v-icon size="16">mdi-pencil</v-icon>
              </v-btn>
              <v-btn icon size="x-small" variant="text" color="error" @click.stop="removeTask(item)">
                <v-icon size="16">mdi-delete</v-icon>
              </v-btn>
            </template>
          </v-data-table>
        </template>

        <!-- Kanban View -->
        <template v-if="taskViewMode === 'kanban'">
          <div class="kanban-board d-flex ga-3" style="overflow-x: auto">
            <div
              v-for="col in kanbanColumns"
              :key="col.value"
              class="kanban-column"
              style="min-width: 220px; flex: 1; max-width: 300px"
            >
              <div class="d-flex align-center mb-2 px-1">
                <v-chip size="x-small" :color="taskStatusColor(col.value)" variant="flat">
                  {{ col.title }}
                </v-chip>
                <v-spacer />
                <span class="text-caption text-medium-emphasis">{{ kanbanTasks(col.value).length }}</span>
              </div>
              <div
                class="kanban-drop-zone rounded-lg pa-1"
                style="min-height: 100px; background: rgba(var(--v-theme-surface-variant), 0.3)"
                @dragover.prevent
                @drop="onDrop($event, col.value)"
              >
                <v-card
                  v-for="task in kanbanTasks(col.value)"
                  :key="task.id"
                  class="mb-2 kanban-card"
                  variant="outlined"
                  density="compact"
                  draggable="true"
                  @dragstart="onDragStart($event, task)"
                  @click="openTaskDetail(task)"
                >
                  <v-card-text class="pa-2">
                    <div class="d-flex align-center">
                      <span class="text-caption text-info mr-1">{{ task.key }}</span>
                      <v-chip v-if="task.priority !== 'medium'" size="x-small" :color="priorityColor(task.priority)" variant="tonal" class="ml-auto">
                        {{ task.priority[0].toUpperCase() }}
                      </v-chip>
                    </div>
                    <div class="text-body-2 mt-1">{{ task.title }}</div>
                    <div v-if="task.assignee" class="text-caption text-medium-emphasis mt-1">
                      <v-icon size="12">mdi-account</v-icon> {{ task.assignee }}
                    </div>
                    <div v-if="task.comments && task.comments.length" class="text-caption text-medium-emphasis mt-1">
                      <v-icon size="12">mdi-comment-outline</v-icon> {{ task.comments.length }}
                    </div>
                  </v-card-text>
                </v-card>
              </div>
            </div>
          </div>
        </template>
      </v-window-item>

      <!-- ═══ CODE TAB ═══ -->
      <v-window-item value="code">
        <div class="d-flex" style="height: calc(100vh - 280px)">
          <!-- File Tree -->
          <div class="file-tree-panel" :style="{ width: treePanelWidth + 'px' }">
            <div class="d-flex align-center pa-2">
              <span class="text-subtitle-2">Files</span>
              <v-spacer />
              <v-btn icon size="x-small" variant="text" @click="createNewFile(false)" title="New File">
                <v-icon size="16">mdi-file-plus</v-icon>
              </v-btn>
              <v-btn icon size="x-small" variant="text" @click="createNewFile(true)" title="New Folder">
                <v-icon size="16">mdi-folder-plus</v-icon>
              </v-btn>
              <v-btn icon size="x-small" variant="text" @click="loadFiles" title="Refresh">
                <v-icon size="16">mdi-refresh</v-icon>
              </v-btn>
            </div>
            <v-divider />
            <div class="file-tree-content" style="overflow-y: auto; height: calc(100% - 44px)">
              <div v-if="!files.length" class="text-center text-medium-emphasis pa-4 text-caption">
                Empty project. Create your first file!
              </div>
              <file-tree-node
                v-for="item in files"
                :key="item.path"
                :item="item"
                :depth="0"
                :selected-path="selectedFile?.path"
                @select="selectFile"
                @delete="deleteFileItem"
              />
            </div>
          </div>

          <!-- Resize handle -->
          <div
            class="resize-handle"
            style="width: 4px; cursor: col-resize; background: rgba(var(--v-theme-on-surface), 0.1)"
            @mousedown="startResize"
          />

          <!-- Editor -->
          <div class="flex-grow-1 d-flex flex-column" style="min-width: 0">
            <div v-if="selectedFile" class="d-flex align-center pa-2 bg-surface-variant">
              <v-icon size="16" class="mr-1">mdi-file-document</v-icon>
              <span class="text-body-2">{{ selectedFile.path }}</span>
              <v-chip v-if="fileModified" size="x-small" color="warning" variant="tonal" class="ml-2">Modified</v-chip>
              <v-spacer />
              <v-btn size="small" variant="tonal" color="primary" @click="saveFile" :disabled="!fileModified" :loading="fileSaving" class="mr-2">
                <v-icon size="16" class="mr-1">mdi-content-save</v-icon> Save
              </v-btn>
              <v-btn size="small" variant="tonal" color="success" @click="runCurrentFile" :loading="codeRunning" :disabled="!selectedFile">
                <v-icon size="16" class="mr-1">mdi-play</v-icon> Run
              </v-btn>
            </div>
            <div v-if="selectedFile" ref="editorContainer" class="code-editor-container" :style="{ flexGrow: 1, flexShrink: 1, minHeight: '100px', height: codeOutput ? 'auto' : '100%' }" />
            <!-- Inline run output -->
            <div v-if="codeOutput !== null && selectedFile" class="code-run-output">
              <div class="d-flex align-center px-2 py-1" style="background: #2d2d2d; border-top: 1px solid rgba(255,255,255,0.1)">
                <v-icon size="14" class="mr-1" :color="codeOutput.exit_code === 0 ? 'success' : 'error'">{{ codeOutput.exit_code === 0 ? 'mdi-check-circle' : 'mdi-alert-circle' }}</v-icon>
                <span class="text-caption" :class="codeOutput.exit_code === 0 ? 'text-success' : 'text-error'">Exit {{ codeOutput.exit_code }}</span>
                <span class="text-caption text-medium-emphasis ml-2">{{ codeOutput.duration_ms }}ms</span>
                <v-chip v-if="codeOutput.timed_out" size="x-small" color="warning" variant="flat" class="ml-2">timeout</v-chip>
                <v-spacer />
                <v-btn icon size="x-small" variant="text" @click="codeOutput = null">
                  <v-icon size="14">mdi-close</v-icon>
                </v-btn>
              </div>
              <pre class="code-run-output-text"><template v-if="codeOutput.stdout">{{ codeOutput.stdout }}</template><template v-if="codeOutput.stderr"><span class="text-error">{{ codeOutput.stderr }}</span></template><template v-if="!codeOutput.stdout && !codeOutput.stderr"><span class="text-medium-emphasis">(no output)</span></template></pre>
            </div>
            <div v-else class="d-flex align-center justify-center flex-grow-1 text-medium-emphasis">
              <div class="text-center">
                <v-icon size="48" color="grey">mdi-file-code-outline</v-icon>
                <p class="mt-2">Select a file to edit</p>
              </div>
            </div>
          </div>
        </div>
      </v-window-item>

      <!-- ═══ TERMINAL TAB ═══ -->
      <v-window-item value="terminal">
        <v-card variant="outlined">
          <v-card-text>
            <div ref="terminalOutput" class="terminal-output mb-3" style="height: 400px; overflow-y: auto; background: #1e1e1e; border-radius: 4px; padding: 12px; font-family: monospace; font-size: 13px; color: #d4d4d4">
              <div v-for="(line, i) in terminalLines" :key="i" :class="line.type === 'stderr' ? 'text-error' : line.type === 'command' ? 'text-info' : ''">
                <span v-if="line.type === 'command'" class="text-success mr-1">$</span>{{ line.text }}
              </div>
              <div v-if="terminalRunning" class="d-flex align-center mt-1">
                <v-progress-circular size="14" width="2" indeterminate class="mr-2" />
                <span class="text-medium-emphasis">Running...</span>
              </div>
            </div>
            <div class="d-flex ga-2">
              <v-text-field
                v-model="terminalCommand"
                label="Command"
                placeholder="python main.py"
                variant="outlined"
                density="compact"
                hide-details
                class="flex-grow-1"
                prepend-inner-icon="mdi-console"
                @keydown.enter="runCommand"
                :disabled="terminalRunning"
              />
              <v-btn color="primary" :loading="terminalRunning" @click="runCommand" :disabled="!terminalCommand">
                <v-icon>mdi-play</v-icon>
              </v-btn>
              <v-btn variant="outlined" @click="terminalLines = []">
                <v-icon>mdi-delete-sweep</v-icon>
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- ═══ LOGS TAB ═══ -->
      <v-window-item value="logs">
        <div class="d-flex align-center mb-3">
          <v-select
            v-model="logLevel"
            :items="['all', 'info', 'warning', 'error']"
            label="Level"
            density="compact"
            variant="outlined"
            style="max-width: 150px"
            hide-details
            class="mr-3"
          />
          <v-select
            v-model="logSource"
            :items="['all', 'system', 'user', 'execution', 'agent']"
            label="Source"
            density="compact"
            variant="outlined"
            style="max-width: 150px"
            hide-details
          />
          <v-spacer />
          <v-btn icon size="small" variant="text" @click="loadLogs">
            <v-icon>mdi-refresh</v-icon>
          </v-btn>
        </div>
        <v-data-table
          :headers="logHeaders"
          :items="logs"
          :loading="logsLoading"
          density="compact"
          items-per-page="50"
          no-data-text="No logs yet"
        >
          <template #item.level="{ item }">
            <v-chip size="x-small" :color="logLevelColor(item.level)" variant="flat">
              {{ item.level }}
            </v-chip>
          </template>
          <template #item.timestamp="{ item }">
            <span class="text-caption">{{ formatTime(item.timestamp) }}</span>
          </template>
          <template #item.source="{ item }">
            <v-chip size="x-small" variant="tonal">{{ item.source }}</v-chip>
          </template>
        </v-data-table>
      </v-window-item>

      <!-- ═══ SETTINGS TAB ═══ -->
      <v-window-item value="settings">
        <v-card variant="outlined" class="mb-4">
          <v-card-title>Project Settings</v-card-title>
          <v-card-text>
            <v-text-field
              v-model="settingsForm.name"
              label="Project Name"
              variant="outlined"
              density="compact"
              class="mb-2"
            />
            <v-textarea
              v-model="settingsForm.description"
              label="Description"
              variant="outlined"
              density="compact"
              rows="3"
              class="mb-2"
            />
            <v-textarea
              v-model="settingsForm.goals"
              label="Goals"
              variant="outlined"
              density="compact"
              rows="3"
              class="mb-2"
            />
            <v-textarea
              v-model="settingsForm.success_criteria"
              label="Success Criteria"
              variant="outlined"
              density="compact"
              rows="3"
              class="mb-2"
            />
            <v-combobox
              v-model="settingsForm.tech_stack"
              :items="techStackOptions"
              label="Tech Stack"
              multiple
              chips
              closable-chips
              variant="outlined"
              density="compact"
              class="mb-2"
              hint="Select or type custom technologies"
            />
            <v-row>
              <v-col cols="4">
                <v-select
                  v-model="settingsForm.status"
                  :items="[{title:'Active',value:'active'},{title:'Paused',value:'paused'},{title:'Completed',value:'completed'},{title:'Archived',value:'archived'}]"
                  label="Status"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="4">
                <v-select
                  v-model="settingsForm.access_level"
                  :items="[{title:'All Agents',value:'full'},{title:'Restricted',value:'restricted'}]"
                  label="Access Level"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="4">
                <v-select
                  v-model="settingsForm.execution_access"
                  :items="[{title:'Restricted (project dir)',value:'restricted'},{title:'Full System',value:'full'}]"
                  label="Execution Access"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
            </v-row>

            <!-- Agent Assignment -->
            <v-select
              v-model="settingsForm.allowed_agent_ids"
              :items="agentOptions"
              label="Assigned Agents"
              variant="outlined"
              density="compact"
              multiple
              chips
              closable-chips
              class="mb-2"
              hint="Select agents that can work on this project"
              persistent-hint
            />
            <v-select
              v-model="settingsForm.lead_agent_id"
              :items="leadAgentOptions"
              label="Lead Agent"
              variant="outlined"
              density="compact"
              clearable
              class="mb-2"
              hint="Agent responsible for coordinating work on this project"
              persistent-hint
            />

            <v-combobox
              v-model="settingsForm.tags"
              label="Tags"
              variant="outlined"
              density="compact"
              multiple
              chips
              closable-chips
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" :loading="settingsSaving" @click="saveSettings">
              Save Settings
            </v-btn>
          </v-card-actions>
        </v-card>

        <v-card variant="outlined" color="error">
          <v-card-title class="text-error">Danger Zone</v-card-title>
          <v-card-text>
            <p class="mb-3">Permanently delete this project and all its code, tasks, and logs.</p>
            <v-text-field
              v-model="dangerDeleteConfirm"
              label="Type DELETE to confirm"
              variant="outlined"
              density="compact"
              style="max-width: 300px"
              class="mb-3"
            />
            <v-btn
              color="error"
              variant="outlined"
              :disabled="dangerDeleteConfirm !== 'DELETE'"
              :loading="dangerDeleting"
              @click="dangerDeleteProject"
            >
              Delete this project
            </v-btn>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- Task Create/Edit Dialog -->
    <v-dialog v-model="showTaskDialog" max-width="550" persistent>
      <v-card>
        <v-card-title>{{ editingTask ? 'Edit Task' : 'New Task' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="taskForm.title"
            label="Task Title *"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-textarea
            v-model="taskForm.description"
            label="Description"
            variant="outlined"
            density="compact"
            rows="3"
            class="mb-2"
          />
          <v-row>
            <v-col cols="4">
              <v-select
                v-model="taskForm.status"
                :items="taskStatuses"
                label="Status"
                variant="outlined"
                density="compact"
              />
            </v-col>
            <v-col cols="4">
              <v-select
                v-model="taskForm.priority"
                :items="priorityItems"
                label="Priority"
                variant="outlined"
                density="compact"
              />
            </v-col>
            <v-col cols="4">
              <v-text-field
                v-model.number="taskForm.story_points"
                label="Story Points"
                type="number"
                variant="outlined"
                density="compact"
              />
            </v-col>
          </v-row>
          <v-text-field
            v-model="taskForm.assignee"
            label="Assignee"
            placeholder="Agent name or 'human'"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-combobox
            v-model="taskForm.labels"
            label="Labels"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="closeTaskDialog">Cancel</v-btn>
          <v-btn color="primary" :loading="taskSaving" @click="saveTask" :disabled="!taskForm.title">
            {{ editingTask ? 'Update' : 'Create' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Task Detail Modal -->
    <v-dialog v-model="showTaskDetail" max-width="800" scrollable>
      <v-card v-if="detailTask">
        <v-card-title class="d-flex align-center">
          <v-chip size="small" color="info" variant="tonal" class="mr-2">{{ detailTask.key }}</v-chip>
          <span class="text-truncate">{{ detailTask.title }}</span>
          <v-spacer />
          <v-btn icon size="small" variant="text" @click="showTaskDetail = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-tabs v-model="detailTab" density="compact">
          <v-tab value="info">Details</v-tab>
          <v-tab value="comments">
            Comments
            <v-badge v-if="detailComments.length" :content="detailComments.length" color="info" inline />
          </v-tab>
          <v-tab value="history">History</v-tab>
        </v-tabs>

        <v-divider />

        <v-card-text style="min-height: 350px; max-height: 60vh; overflow-y: auto">
          <v-window v-model="detailTab">
            <!-- ── Details tab ── -->
            <v-window-item value="info">
              <div class="mb-3">
                <div class="d-flex align-center ga-2 mb-3">
                  <v-chip :color="taskStatusColor(detailTask.status)" variant="flat" size="small">
                    {{ taskStatuses.find(s => s.value === detailTask.status)?.title || detailTask.status }}
                  </v-chip>
                  <v-chip :color="priorityColor(detailTask.priority)" variant="tonal" size="small">
                    {{ detailTask.priority }}
                  </v-chip>
                  <v-chip v-if="detailTask.story_points" variant="outlined" size="small">
                    {{ detailTask.story_points }} SP
                  </v-chip>
                  <v-chip v-if="detailTask.assignee" variant="tonal" size="small" prepend-icon="mdi-account">
                    {{ detailTask.assignee }}
                  </v-chip>
                </div>
              </div>
              <div v-if="detailTask.description" class="mb-4">
                <div class="text-subtitle-2 mb-1">Description</div>
                <div class="text-body-2" style="white-space: pre-wrap">{{ detailTask.description }}</div>
              </div>
              <div v-if="!detailTask.description" class="text-medium-emphasis text-body-2 mb-4">
                No description provided.
              </div>
              <div v-if="detailTask.labels && detailTask.labels.length" class="mb-3">
                <div class="text-subtitle-2 mb-1">Labels</div>
                <v-chip v-for="label in detailTask.labels" :key="label" size="small" variant="outlined" class="mr-1">
                  {{ label }}
                </v-chip>
              </div>
              <v-divider class="mb-3" />
              <div class="d-flex ga-4 text-caption text-medium-emphasis">
                <span>Created: {{ formatTime(detailTask.created_at) }}</span>
                <span>Updated: {{ formatTime(detailTask.updated_at) }}</span>
              </div>
            </v-window-item>

            <!-- ── Comments tab ── -->
            <v-window-item value="comments">
              <div class="mb-3">
                <v-textarea
                  v-model="newComment"
                  label="Add a comment..."
                  variant="outlined"
                  density="compact"
                  rows="2"
                  auto-grow
                  hide-details
                />
                <div class="d-flex justify-end mt-1">
                  <v-btn
                    size="small"
                    color="primary"
                    :disabled="!newComment.trim()"
                    :loading="commentSaving"
                    @click="addComment"
                  >
                    Add Comment
                  </v-btn>
                </div>
              </div>
              <v-divider class="mb-3" />
              <div v-if="!detailComments.length" class="text-center text-medium-emphasis pa-4">
                No comments yet.
              </div>
              <div v-for="comment in detailComments" :key="comment.id" class="mb-3">
                <div class="d-flex align-center mb-1">
                  <v-chip size="x-small" variant="tonal" :color="comment.author === 'user' ? 'primary' : 'info'">
                    {{ comment.author }}
                  </v-chip>
                  <span class="text-caption text-medium-emphasis ml-2">{{ formatTime(comment.created_at) }}</span>
                  <v-spacer />
                  <v-btn icon size="x-small" variant="text" color="error" @click="deleteComment(comment.id)">
                    <v-icon size="14">mdi-delete</v-icon>
                  </v-btn>
                </div>
                <div class="text-body-2 pl-1" style="white-space: pre-wrap">{{ comment.content }}</div>
              </div>
            </v-window-item>

            <!-- ── History tab ── -->
            <v-window-item value="history">
              <div v-if="detailLogsLoading" class="text-center pa-4">
                <v-progress-circular indeterminate size="24" />
              </div>
              <div v-else-if="!detailLogs.length" class="text-center text-medium-emphasis pa-4">
                No history for this task yet.
              </div>
              <v-timeline v-else density="compact" side="end">
                <v-timeline-item
                  v-for="log in detailLogs"
                  :key="log.id"
                  :dot-color="logLevelColor(log.level)"
                  size="x-small"
                >
                  <div class="d-flex align-center">
                    <span class="text-body-2">{{ log.message }}</span>
                    <v-spacer />
                    <v-chip size="x-small" variant="tonal" class="ml-2">{{ log.source }}</v-chip>
                    <span class="text-caption text-medium-emphasis ml-2">{{ formatTime(log.timestamp) }}</span>
                  </div>
                </v-timeline-item>
              </v-timeline>
            </v-window-item>
          </v-window>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- New File Dialog -->
    <v-dialog v-model="showNewFileDialog" max-width="400">
      <v-card>
        <v-card-title>{{ newFileIsDir ? 'New Folder' : 'New File' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newFilePath"
            :label="newFileIsDir ? 'Folder path' : 'File path'"
            :placeholder="newFileIsDir ? 'src/utils' : 'src/main.py'"
            variant="outlined"
            density="compact"
            autofocus
            @keydown.enter="doCreateFile"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="showNewFileDialog = false">Cancel</v-btn>
          <v-btn color="primary" :disabled="!newFilePath" @click="doCreateFile">Create</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>

  <!-- Loading state -->
  <div v-else class="d-flex justify-center align-center" style="height: 300px">
    <v-progress-circular indeterminate size="48" />
  </div>
</template>

<script>
// Recursive file tree component
const FileTreeNode = {
  name: 'FileTreeNode',
  props: {
    item: Object,
    depth: { type: Number, default: 0 },
    selectedPath: String,
  },
  emits: ['select', 'delete'],
  data() {
    return { expanded: this.depth < 2 }
  },
  methods: {
    toggle() {
      if (this.item.is_dir) this.expanded = !this.expanded
      else this.$emit('select', this.item)
    },
    getIcon() {
      if (this.item.is_dir) return this.expanded ? 'mdi-folder-open' : 'mdi-folder'
      const lang = this.item.language
      if (lang === 'python') return 'mdi-language-python'
      if (lang === 'javascript' || lang === 'typescript') return 'mdi-language-javascript'
      if (lang === 'html') return 'mdi-language-html5'
      if (lang === 'css' || lang === 'scss') return 'mdi-language-css3'
      if (lang === 'json') return 'mdi-code-json'
      if (lang === 'markdown') return 'mdi-language-markdown'
      return 'mdi-file-document-outline'
    },
  },
  template: `
    <div>
      <div
        class="file-tree-item d-flex align-center px-2 py-1"
        :class="{ 'bg-primary-darken-2': selectedPath === item.path && !item.is_dir }"
        :style="{ paddingLeft: (depth * 16 + 4) + 'px', cursor: 'pointer' }"
        @click="toggle"
        @contextmenu.prevent="$emit('delete', item)"
      >
        <v-icon :size="16" class="mr-1" :color="item.is_dir ? 'amber' : 'grey'">{{ getIcon() }}</v-icon>
        <span class="text-body-2 text-truncate">{{ item.name }}</span>
        <span v-if="!item.is_dir" class="text-caption text-medium-emphasis ml-auto">
          {{ item.size < 1024 ? item.size + 'B' : (item.size / 1024).toFixed(1) + 'K' }}
        </span>
      </div>
      <div v-if="item.is_dir && expanded && item.children">
        <file-tree-node
          v-for="child in item.children"
          :key="child.path"
          :item="child"
          :depth="depth + 1"
          :selected-path="selectedPath"
          @select="$emit('select', $event)"
          @delete="$emit('delete', $event)"
        />
      </div>
    </div>
  `,
}

export default { components: { FileTreeNode } }
</script>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectsStore } from '../stores/projects'
import { useAgentsStore } from '../stores/agents'
import api from '../api'

// ── CodeMirror ──
import { EditorView, keymap, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection, dropCursor, rectangularSelection, crosshairCursor, highlightActiveLine } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { syntaxHighlighting, defaultHighlightStyle, indentOnInput, bracketMatching, foldGutter, foldKeymap } from '@codemirror/language'
import { oneDark } from '@codemirror/theme-one-dark'
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search'
import { autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete'
import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
import { json as jsonLang } from '@codemirror/lang-json'
import { markdown } from '@codemirror/lang-markdown'
import { html } from '@codemirror/lang-html'
import { css } from '@codemirror/lang-css'
import { yaml } from '@codemirror/lang-yaml'
import { sql } from '@codemirror/lang-sql'

const route = useRoute()
const router = useRouter()
const store = useProjectsStore()
const agentsStore = useAgentsStore()

const slug = computed(() => route.params.slug)
const project = ref(null)
const activeTab = ref('tasks')

// ── Tasks ──
const tasks = ref([])
const tasksLoading = ref(false)
const taskViewMode = ref('kanban')
const showTaskDialog = ref(false)
const editingTask = ref(null)
const taskSaving = ref(false)
const draggedTask = ref(null)
const showTaskDetail = ref(false)
const detailTask = ref(null)
const detailTab = ref('info')
const detailComments = ref([])
const detailLogs = ref([])
const detailLogsLoading = ref(false)
const newComment = ref('')
const commentSaving = ref(false)

const taskHeaders = [
  { title: 'Key', key: 'key', width: '70px' },
  { title: 'Title', key: 'title' },
  { title: 'Status', key: 'status', width: '150px' },
  { title: 'Priority', key: 'priority', width: '100px' },
  { title: 'Assignee', key: 'assignee', width: '120px' },
  { title: 'SP', key: 'story_points', width: '50px' },
  { title: '', key: 'actions', width: '80px', sortable: false },
]

const taskStatuses = [
  { title: 'Backlog', value: 'backlog' },
  { title: 'Todo', value: 'todo' },
  { title: 'In Progress', value: 'in_progress' },
  { title: 'Review', value: 'review' },
  { title: 'Done', value: 'done' },
  { title: 'Cancelled', value: 'cancelled' },
]

const kanbanColumns = taskStatuses.filter(s => s.value !== 'cancelled')

const priorityItems = [
  { title: 'Lowest', value: 'lowest' },
  { title: 'Low', value: 'low' },
  { title: 'Medium', value: 'medium' },
  { title: 'High', value: 'high' },
  { title: 'Highest', value: 'highest' },
]

const defaultTaskForm = () => ({
  title: '', description: '', status: 'backlog', priority: 'medium',
  assignee: '', labels: [], story_points: null,
})
const taskForm = ref(defaultTaskForm())

function taskStatusColor(s) {
  return { backlog: 'grey', todo: 'blue-grey', in_progress: 'info', review: 'warning', done: 'success', cancelled: 'error' }[s] || 'grey'
}

function priorityColor(p) {
  return { lowest: 'grey', low: 'blue-grey', medium: 'info', high: 'warning', highest: 'error' }[p] || 'grey'
}

function statusColor(s) {
  return { active: 'success', paused: 'warning', completed: 'info', archived: 'grey' }[s] || 'grey'
}

function kanbanTasks(status) {
  return tasks.value.filter(t => t.status === status)
}

function onDragStart(evt, task) {
  draggedTask.value = task
  evt.dataTransfer.effectAllowed = 'move'
}

async function onDrop(evt, status) {
  if (!draggedTask.value) return
  await moveTask(draggedTask.value, status)
  draggedTask.value = null
}

async function moveTask(task, newStatus) {
  try {
    await store.updateTask(slug.value, task.id, { status: newStatus })
    task.status = newStatus
  } catch (e) { console.error(e) }
}

async function loadTasks() {
  tasksLoading.value = true
  try {
    tasks.value = await store.fetchTasks(slug.value)
  } finally { tasksLoading.value = false }
}

function editTask(task) {
  editingTask.value = task
  taskForm.value = { ...task }
  showTaskDialog.value = true
}

function closeTaskDialog() {
  showTaskDialog.value = false
  editingTask.value = null
  taskForm.value = defaultTaskForm()
}

async function saveTask() {
  if (!taskForm.value.title) return
  taskSaving.value = true
  try {
    if (editingTask.value) {
      await store.updateTask(slug.value, editingTask.value.id, taskForm.value)
    } else {
      await store.createTask(slug.value, taskForm.value)
    }
    closeTaskDialog()
    await loadTasks()
  } finally { taskSaving.value = false }
}

async function removeTask(task) {
  try {
    await store.deleteTask(slug.value, task.id)
    await loadTasks()
  } catch (e) { console.error(e) }
}

// ── Task Detail Modal ──
async function openTaskDetail(task) {
  detailTask.value = task
  detailTab.value = 'info'
  newComment.value = ''
  detailComments.value = task.comments || []
  detailLogs.value = []
  showTaskDetail.value = true
  // Load comments and logs in parallel
  await Promise.all([loadDetailComments(task.id), loadDetailLogs(task.id)])
}

async function loadDetailComments(taskId) {
  try {
    detailComments.value = await store.fetchTaskComments(slug.value, taskId)
  } catch (e) { console.error('Failed to load comments', e) }
}

async function loadDetailLogs(taskId) {
  detailLogsLoading.value = true
  try {
    detailLogs.value = await store.fetchTaskLogs(slug.value, taskId)
  } catch (e) { console.error('Failed to load task logs', e) }
  finally { detailLogsLoading.value = false }
}

async function addComment() {
  if (!newComment.value.trim() || !detailTask.value) return
  commentSaving.value = true
  try {
    const comment = await store.addTaskComment(slug.value, detailTask.value.id, {
      content: newComment.value.trim(),
      author: 'user',
    })
    detailComments.value.push(comment)
    newComment.value = ''
  } catch (e) { console.error('Failed to add comment', e) }
  finally { commentSaving.value = false }
}

async function deleteComment(commentId) {
  if (!detailTask.value) return
  try {
    await store.deleteTaskComment(slug.value, detailTask.value.id, commentId)
    detailComments.value = detailComments.value.filter(c => c.id !== commentId)
  } catch (e) { console.error('Failed to delete comment', e) }
}

// ── Code / Files ──
const files = ref([])
const selectedFile = ref(null)
const fileContent = ref('')
const originalContent = ref('')
const fileModified = computed(() => fileContent.value !== originalContent.value)
const fileSaving = ref(false)
const treePanelWidth = ref(250)
const showNewFileDialog = ref(false)
const newFilePath = ref('')
const newFileIsDir = ref(false)
const editorContainer = ref(null)
let editorView = null

const getLanguageExtension = (lang) => {
  const map = {
    python: python(), javascript: javascript(), typescript: javascript({ typescript: true }),
    json: jsonLang(), markdown: markdown(), html: html(), css: css(), scss: css(),
    yaml: yaml(), sql: sql(),
  }
  return map[lang] || []
}

function initEditor(content, language) {
  destroyEditor()
  if (!editorContainer.value) return

  const extensions = [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    history(),
    foldGutter(),
    drawSelection(),
    dropCursor(),
    EditorState.allowMultipleSelections.of(true),
    indentOnInput(),
    syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    bracketMatching(),
    closeBrackets(),
    autocompletion(),
    rectangularSelection(),
    crosshairCursor(),
    highlightActiveLine(),
    highlightSelectionMatches(),
    keymap.of([
      ...closeBracketsKeymap, ...defaultKeymap, ...searchKeymap,
      ...historyKeymap, ...foldKeymap, ...completionKeymap,
      indentWithTab,
      { key: 'Mod-s', run: () => { saveFile(); return true } },
    ]),
    oneDark,
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        fileContent.value = update.state.doc.toString()
      }
    }),
    EditorView.theme({ '&': { height: '100%' }, '.cm-scroller': { overflow: 'auto' } }),
    getLanguageExtension(language),
  ].flat()

  editorView = new EditorView({
    state: EditorState.create({ doc: content, extensions }),
    parent: editorContainer.value,
  })
}

function destroyEditor() {
  if (editorView) { editorView.destroy(); editorView = null }
}

onBeforeUnmount(destroyEditor)

const codeRunning = ref(false)
const codeOutput = ref(null)

const RUN_COMMANDS = {
  python: (f) => `python3 ${f}`,
  javascript: (f) => `node ${f}`,
  typescript: (f) => `npx ts-node ${f}`,
  shell: (f) => `bash ${f}`,
  bash: (f) => `bash ${f}`,
  html: (f) => `open ${f}`,
}

async function runCurrentFile() {
  if (!selectedFile.value || codeRunning.value) return
  // Auto-save if modified
  if (fileModified.value) await saveFile()
  const lang = selectedFile.value.language || ''
  const getCmd = RUN_COMMANDS[lang]
  const cmd = getCmd ? getCmd(selectedFile.value.path) : selectedFile.value.path
  codeRunning.value = true
  codeOutput.value = null
  try {
    const result = await store.executeCommand(slug.value, { command: cmd, timeout: 60 })
    codeOutput.value = result
  } catch (e) {
    codeOutput.value = { stdout: '', stderr: e.response?.data?.detail || e.message, exit_code: -1, duration_ms: 0, timed_out: false }
  } finally {
    codeRunning.value = false
  }
}

async function loadFiles() {
  try {
    files.value = await store.fetchFiles(slug.value)
  } catch (e) { console.error(e) }
}

async function selectFile(item) {
  if (item.is_dir) return
  try {
    const data = await store.readFile(slug.value, item.path)
    selectedFile.value = item
    fileContent.value = data.content
    originalContent.value = data.content
    await nextTick()
    initEditor(data.content, data.language || item.language || '')
  } catch (e) { console.error(e) }
}

async function saveFile() {
  if (!selectedFile.value || !fileModified.value) return
  fileSaving.value = true
  try {
    const content = editorView ? editorView.state.doc.toString() : fileContent.value
    await store.writeFile(slug.value, selectedFile.value.path, content)
    fileContent.value = content
    originalContent.value = content
  } finally { fileSaving.value = false }
}

function createNewFile(isDir) {
  newFileIsDir.value = isDir
  newFilePath.value = ''
  showNewFileDialog.value = true
}

async function doCreateFile() {
  if (!newFilePath.value) return
  try {
    await store.createFile(slug.value, { path: newFilePath.value, is_dir: newFileIsDir.value, content: '' })
    showNewFileDialog.value = false
    await loadFiles()
  } catch (e) { console.error(e) }
}

async function deleteFileItem(item) {
  if (!confirm(`Delete ${item.is_dir ? 'folder' : 'file'} "${item.path}"?`)) return
  try {
    await store.deleteFile(slug.value, item.path)
    if (selectedFile.value?.path === item.path) {
      destroyEditor()
      selectedFile.value = null
      fileContent.value = ''
      originalContent.value = ''
    }
    await loadFiles()
  } catch (e) { console.error(e) }
}

let resizing = false
function startResize(evt) {
  resizing = true
  const startX = evt.clientX
  const startWidth = treePanelWidth.value
  const onMove = (e) => {
    if (!resizing) return
    treePanelWidth.value = Math.max(150, Math.min(500, startWidth + e.clientX - startX))
  }
  const onUp = () => { resizing = false; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ── Terminal ──
const terminalCommand = ref('')
const terminalLines = ref([])
const terminalRunning = ref(false)
const terminalOutput = ref(null)

async function runCommand() {
  if (!terminalCommand.value || terminalRunning.value) return
  const cmd = terminalCommand.value
  terminalLines.value.push({ type: 'command', text: cmd })
  terminalCommand.value = ''
  terminalRunning.value = true
  try {
    const result = await store.executeCommand(slug.value, { command: cmd, timeout: 60 })
    if (result.stdout) {
      result.stdout.split('\n').forEach(line => {
        if (line) terminalLines.value.push({ type: 'stdout', text: line })
      })
    }
    if (result.stderr) {
      result.stderr.split('\n').forEach(line => {
        if (line) terminalLines.value.push({ type: 'stderr', text: line })
      })
    }
    terminalLines.value.push({ type: 'info', text: `[exit ${result.exit_code}] ${result.duration_ms}ms${result.timed_out ? ' (timed out)' : ''}` })
  } catch (e) {
    terminalLines.value.push({ type: 'stderr', text: `Error: ${e.response?.data?.detail || e.message}` })
  } finally {
    terminalRunning.value = false
    await nextTick()
    if (terminalOutput.value) terminalOutput.value.scrollTop = terminalOutput.value.scrollHeight
  }
}

// ── Logs ──
const logs = ref([])
const logsLoading = ref(false)
const logLevel = ref('all')
const logSource = ref('all')

const logHeaders = [
  { title: 'Time', key: 'timestamp', width: '170px' },
  { title: 'Level', key: 'level', width: '80px' },
  { title: 'Source', key: 'source', width: '100px' },
  { title: 'Message', key: 'message' },
]

function logLevelColor(level) {
  return { info: 'info', warning: 'warning', error: 'error' }[level] || 'grey'
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const params = { limit: 200 }
    if (logLevel.value && logLevel.value !== 'all') params.level = logLevel.value
    if (logSource.value && logSource.value !== 'all') params.source = logSource.value
    logs.value = await store.fetchLogs(slug.value, params)
  } finally { logsLoading.value = false }
}

watch([logLevel, logSource], loadLogs)

// ── Settings ──
const settingsForm = ref({})
const settingsSaving = ref(false)
const allAgents = ref([])
const dangerDeleteConfirm = ref('')
const dangerDeleting = ref(false)

const agentOptions = computed(() =>
  allAgents.value.map(a => ({ title: a.name, value: String(a.id) }))
)
const leadAgentOptions = computed(() => {
  // Lead can be any agent (not only from allowed list)
  return allAgents.value.map(a => ({ title: a.name, value: String(a.id) }))
})

async function loadAgents() {
  try {
    await agentsStore.fetchAgents()
    allAgents.value = agentsStore.agents || []
  } catch (e) { console.error('Failed to load agents', e) }
}

const techStackOptions = [
  'Python', 'JavaScript', 'TypeScript', 'Go', 'Rust', 'Java', 'C', 'C++', 'C#',
  'Ruby', 'PHP', 'Swift', 'Kotlin', 'Dart', 'Scala', 'R', 'Lua', 'Perl',
  'Shell', 'Bash', 'PowerShell', 'SQL',
  'HTML', 'CSS', 'SCSS', 'Tailwind CSS',
  'React', 'Vue.js', 'Angular', 'Svelte', 'Next.js', 'Nuxt.js',
  'Node.js', 'Express', 'FastAPI', 'Django', 'Flask', 'Spring Boot', 'Rails', 'Laravel', '.NET',
  'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'SQLite', 'Elasticsearch',
  'Docker', 'Kubernetes', 'Terraform', 'Nginx',
  'GraphQL', 'REST API', 'gRPC', 'WebSocket',
  'TensorFlow', 'PyTorch', 'LangChain', 'OpenAI', 'Ollama',
  'Git', 'GitHub Actions', 'CI/CD',
]

async function saveSettings() {
  settingsSaving.value = true
  try {
    const payload = { ...settingsForm.value }
    // Ensure lead_agent_id is sent as empty string (not null) so backend exclude_none doesn't skip it
    if (payload.lead_agent_id === null || payload.lead_agent_id === undefined) {
      payload.lead_agent_id = ''
    }
    const data = await store.updateProject(slug.value, payload)
    project.value = data
  } finally { settingsSaving.value = false }
}

async function dangerDeleteProject() {
  if (dangerDeleteConfirm.value !== 'DELETE') return
  dangerDeleting.value = true
  try {
    await store.deleteProject(slug.value)
    router.push('/projects')
  } catch (e) {
    console.error('Failed to delete project', e)
  } finally {
    dangerDeleting.value = false
  }
}

// ── Load project ──
async function loadProject() {
  try {
    const data = await store.fetchProject(slug.value)
    project.value = data
    settingsForm.value = {
      name: data.name, description: data.description, goals: data.goals,
      success_criteria: data.success_criteria, tech_stack: data.tech_stack || [],
      status: data.status, access_level: data.access_level,
      allowed_agent_ids: data.allowed_agent_ids || [],
      lead_agent_id: data.lead_agent_id || null,
      execution_access: data.execution_access, tags: data.tags || [],
    }
    // Load all sub-data
    await Promise.all([loadTasks(), loadFiles(), loadLogs(), loadAgents()])
  } catch (e) {
    console.error(e)
    router.push('/projects')
  }
}

onMounted(loadProject)
watch(slug, loadProject)
</script>

<style scoped>
.file-tree-panel {
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow: hidden;
  flex-shrink: 0;
}

.file-tree-item:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}

.code-editor-container {
  overflow: hidden;
}

.code-editor-container :deep(.cm-editor) {
  height: 100%;
}

.code-editor-container :deep(.cm-scroller) {
  overflow: auto;
}

.kanban-card {
  cursor: grab;
}
.kanban-card:active {
  cursor: grabbing;
}

.code-run-output {
  max-height: 200px;
  display: flex;
  flex-direction: column;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  flex-shrink: 0;
}

.code-run-output-text {
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.4;
  padding: 8px 12px;
  margin: 0;
  overflow: auto;
  max-height: 150px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
