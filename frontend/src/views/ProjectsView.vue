<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <h1 class="text-h4">Projects</h1>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New Project
      </v-btn>
    </div>

    <!-- Filter -->
    <v-row class="mb-2">
      <v-col cols="3">
        <v-select
          v-model="statusFilter"
          :items="statusOptions"
          label="Status"
          clearable
          density="compact"
          variant="outlined"
        />
      </v-col>
    </v-row>

    <!-- Projects Grid -->
    <v-row v-if="!loading && filteredProjects.length">
      <v-col v-for="project in filteredProjects" :key="project.slug" cols="12" sm="6" md="4" lg="3">
        <v-card
          class="project-card"
          :class="{ 'border-warning': project.status === 'paused', 'border-success': project.status === 'completed' }"
          hover
          @click="goToProject(project)"
        >
          <v-card-item>
            <template #prepend>
              <v-icon :color="statusColor(project.status)" size="28">{{ statusIcon(project.status) }}</v-icon>
            </template>
            <v-card-title class="text-truncate">{{ project.name }}</v-card-title>
            <v-card-subtitle v-if="project.tech_stack && project.tech_stack.length" class="text-truncate">
              {{ Array.isArray(project.tech_stack) ? project.tech_stack.join(', ') : project.tech_stack }}
            </v-card-subtitle>
          </v-card-item>

          <v-card-text v-if="project.description" class="text-medium-emphasis" style="min-height:40px">
            {{ truncate(project.description, 100) }}
          </v-card-text>

          <!-- Stats -->
          <v-card-text class="pt-0">
            <div class="d-flex align-center ga-3">
              <v-chip size="x-small" variant="tonal" color="info" prepend-icon="mdi-file-document-outline">
                {{ project.file_count }} files
              </v-chip>
              <v-chip size="x-small" variant="tonal" color="primary" prepend-icon="mdi-clipboard-list-outline">
                {{ project.task_stats?.total || 0 }} tasks
              </v-chip>
              <v-chip v-if="project.task_stats?.done" size="x-small" variant="tonal" color="success" prepend-icon="mdi-check">
                {{ project.task_stats.done }}
              </v-chip>
            </div>
            <div v-if="project.tags?.length" class="mt-2 d-flex ga-1 flex-wrap">
              <v-chip v-for="tag in project.tags" :key="tag" size="x-small" variant="outlined" color="grey">
                {{ tag }}
              </v-chip>
            </div>
          </v-card-text>

          <v-divider />
          <v-card-actions>
            <v-chip size="x-small" :color="statusColor(project.status)" variant="flat">
              {{ project.status }}
            </v-chip>
            <v-spacer />
            <v-btn icon size="small" variant="text" @click.stop="editProject(project)">
              <v-icon size="18">mdi-pencil</v-icon>
            </v-btn>
            <v-btn icon size="small" variant="text" color="error" @click.stop="confirmDelete(project)">
              <v-icon size="18">mdi-delete</v-icon>
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- Empty state -->
    <v-card v-if="!loading && !filteredProjects.length" class="text-center pa-8">
      <v-icon size="64" color="grey">mdi-folder-code-outline</v-icon>
      <h3 class="text-h6 mt-4">No projects yet</h3>
      <p class="text-medium-emphasis">Create your first project to start coding</p>
      <v-btn color="primary" class="mt-4" @click="showCreateDialog = true">Create Project</v-btn>
    </v-card>

    <!-- Loading -->
    <v-row v-if="loading">
      <v-col v-for="i in 4" :key="i" cols="12" sm="6" md="4" lg="3">
        <v-skeleton-loader type="card" />
      </v-col>
    </v-row>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="650" persistent>
      <v-card>
        <v-card-title>{{ editingProject ? 'Edit Project' : 'New Project' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="form.name"
            label="Project Name *"
            placeholder="My Awesome Project"
            variant="outlined"
            density="compact"
            class="mb-2"
            :rules="[v => !!v || 'Name is required']"
          />
          <v-textarea
            v-model="form.description"
            label="Description"
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-2"
          />
          <v-textarea
            v-model="form.goals"
            label="Goals"
            hint="What should this project achieve?"
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-2"
          />
          <v-textarea
            v-model="form.success_criteria"
            label="Success Criteria"
            hint="How do we know the project is done?"
            variant="outlined"
            density="compact"
            rows="2"
            class="mb-2"
          />
          <v-combobox
            v-model="form.tech_stack"
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
            <v-col cols="6">
              <v-select
                v-model="form.status"
                :items="statusOptions.filter(s => s.value)"
                label="Status"
                variant="outlined"
                density="compact"
              />
            </v-col>
            <v-col cols="6">
              <v-select
                v-model="form.access_level"
                :items="[{title: 'All Agents', value: 'full'}, {title: 'Restricted', value: 'restricted'}]"
                label="Access"
                variant="outlined"
                density="compact"
              />
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="6">
              <v-select
                v-model="form.execution_access"
                :items="[{title: 'Restricted (project dir)', value: 'restricted'}, {title: 'Full System', value: 'full'}]"
                label="Execution Access"
                variant="outlined"
                density="compact"
              />
            </v-col>
            <v-col cols="6">
              <v-combobox
                v-model="form.tags"
                label="Tags"
                variant="outlined"
                density="compact"
                multiple
                chips
                closable-chips
              />
            </v-col>
          </v-row>
          <v-select
            v-model="form.allowed_agent_ids"
            :items="agentOptions"
            label="Assigned Agents"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            class="mb-2"
            hint="Agents that can work on this project"
            persistent-hint
          />
          <v-select
            v-model="form.lead_agent_id"
            :items="agentOptions"
            label="Lead Agent"
            variant="outlined"
            density="compact"
            clearable
            hint="Agent coordinating work on this project"
            persistent-hint
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="closeDialog">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="saveProject" :disabled="!form.name">
            {{ editingProject ? 'Update' : 'Create' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirmation -->
    <v-dialog v-model="showDeleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-error">Delete Project</v-card-title>
        <v-card-text>
          <p>Are you sure you want to delete <strong>{{ deleteTarget?.name }}</strong>?</p>
          <p class="text-error mt-2">This will permanently delete all code, tasks, and logs.</p>
          <v-text-field
            v-model="deleteConfirm"
            label="Type DELETE to confirm"
            variant="outlined"
            density="compact"
            class="mt-3"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="showDeleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :disabled="deleteConfirm !== 'DELETE'" :loading="deleting" @click="doDelete">
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectsStore } from '../stores/projects'
import { useAgentsStore } from '../stores/agents'

const router = useRouter()
const store = useProjectsStore()
const agentsStore = useAgentsStore()

const loading = ref(false)
const statusFilter = ref(null)
const showCreateDialog = ref(false)
const editingProject = ref(null)
const saving = ref(false)
const showDeleteDialog = ref(false)
const deleteTarget = ref(null)
const deleteConfirm = ref('')
const deleting = ref(false)

const defaultForm = () => ({
  name: '',
  description: '',
  goals: '',
  success_criteria: '',
  tech_stack: [],
  status: 'active',
  access_level: 'full',
  allowed_agent_ids: [],
  lead_agent_id: null,
  execution_access: 'restricted',
  tags: [],
})

const allAgents = ref([])
const agentOptions = computed(() =>
  allAgents.value.map(a => ({ title: a.name, value: String(a.id) }))
)

const form = ref(defaultForm())

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

const statusOptions = [
  { title: 'Active', value: 'active' },
  { title: 'Paused', value: 'paused' },
  { title: 'Completed', value: 'completed' },
  { title: 'Archived', value: 'archived' },
]

const filteredProjects = computed(() => {
  if (!statusFilter.value) return store.projects
  return store.projects.filter(p => p.status === statusFilter.value)
})

function statusColor(s) {
  return { active: 'success', paused: 'warning', completed: 'info', archived: 'grey' }[s] || 'grey'
}

function statusIcon(s) {
  return {
    active: 'mdi-folder-open',
    paused: 'mdi-pause-circle',
    completed: 'mdi-check-circle',
    archived: 'mdi-archive',
  }[s] || 'mdi-folder'
}

function truncate(text, len) {
  return text && text.length > len ? text.slice(0, len) + '...' : text
}

async function load() {
  loading.value = true
  try {
    await store.fetchProjects()
  } finally {
    loading.value = false
  }
}

function goToProject(project) {
  router.push(`/projects/${project.slug}`)
}

function editProject(project) {
  editingProject.value = project
  form.value = { ...project }
  showCreateDialog.value = true
}

function closeDialog() {
  showCreateDialog.value = false
  editingProject.value = null
  form.value = defaultForm()
}

async function saveProject() {
  if (!form.value.name) return
  saving.value = true
  try {
    const payload = { ...form.value }
    // Ensure lead_agent_id sends empty string (not null) so backend doesn't skip it
    if (payload.lead_agent_id === null || payload.lead_agent_id === undefined) {
      payload.lead_agent_id = ''
    }
    if (editingProject.value) {
      await store.updateProject(editingProject.value.slug, payload)
    } else {
      await store.createProject(payload)
    }
    closeDialog()
    await load()
  } finally {
    saving.value = false
  }
}

function confirmDelete(project) {
  deleteTarget.value = project
  deleteConfirm.value = ''
  showDeleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await store.deleteProject(deleteTarget.value.slug)
    showDeleteDialog.value = false
  } finally {
    deleting.value = false
  }
}

async function loadAgents() {
  try {
    await agentsStore.fetchAgents()
    allAgents.value = agentsStore.agents || []
  } catch (e) { console.error('Failed to load agents', e) }
}

onMounted(async () => {
  await Promise.all([load(), loadAgents()])
})
</script>

<style scoped>
.project-card {
  transition: transform 0.15s, box-shadow 0.15s;
  cursor: pointer;
}
.project-card:hover {
  transform: translateY(-2px);
}
</style>
