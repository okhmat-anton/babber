<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Research Resources</div>
      <v-spacer />
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="outlined"
        placeholder="Search resources..."
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        class="mr-3"
        style="max-width: 300px"
        @update:model-value="debouncedSearch"
      />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">New Resource</v-btn>
    </div>

    <!-- Filters -->
    <div class="d-flex align-center ga-3 mb-4">
      <v-chip-group v-model="filterCategory" selected-class="text-primary" @update:model-value="loadResources">
        <v-chip value="" variant="tonal" size="small">All</v-chip>
        <v-chip v-for="cat in categories" :key="cat.value" :value="cat.value" variant="tonal" size="small">
          <v-icon start size="14">{{ cat.icon }}</v-icon>
          {{ cat.label }}
        </v-chip>
      </v-chip-group>
      <v-spacer />
      <v-chip-group v-model="filterTrust" selected-class="text-primary" @update:model-value="loadResources">
        <v-chip value="" variant="tonal" size="small">Any trust</v-chip>
        <v-chip v-for="t in trustLevels" :key="t.value" :value="t.value" variant="tonal" size="small" :color="t.color">
          {{ t.label }}
        </v-chip>
      </v-chip-group>
    </div>

    <!-- Resources Table -->
    <v-card>
      <v-card-text class="pa-0">
        <v-data-table
          :headers="headers"
          :items="store.resources"
          :loading="store.loading"
          hover
          @click:row="(_, { item }) => openEdit(item)"
        >
          <template #item.name="{ item }">
            <div class="d-flex align-center">
              <v-icon :color="categoryMeta(item.category).color" size="20" class="mr-2">
                {{ categoryMeta(item.category).icon }}
              </v-icon>
              <div>
                <span class="font-weight-medium">{{ item.name }}</span>
                <div class="text-caption text-grey">{{ item.url }}</div>
              </div>
            </div>
          </template>

          <template #item.trust_level="{ item }">
            <v-chip :color="trustColor(item.trust_level)" size="small" variant="tonal">
              {{ item.trust_level }}
            </v-chip>
          </template>

          <template #item.user_rating="{ item }">
            <v-rating
              :model-value="item.user_rating / 2"
              density="compact"
              size="16"
              half-increments
              readonly
              color="amber"
              active-color="amber"
            />
            <span class="text-caption ml-1">{{ item.user_rating.toFixed(1) }}</span>
          </template>

          <template #item.agent_rating="{ item }">
            <span class="text-caption">{{ item.agent_rating.toFixed(1) }}/10</span>
          </template>

          <template #item.is_active="{ item }">
            <v-switch
              :model-value="item.is_active"
              color="success"
              density="compact"
              hide-details
              @update:model-value="toggleActive(item, $event)"
              @click.stop
            />
          </template>

          <template #item.use_count="{ item }">
            <span class="text-caption">{{ item.use_count }}</span>
          </template>

          <template #item.added_by="{ item }">
            <v-chip :color="item.added_by === 'agent' ? 'purple' : 'blue'" size="x-small" variant="tonal">
              <v-icon start size="12">{{ item.added_by === 'agent' ? 'mdi-robot' : 'mdi-account' }}</v-icon>
              {{ item.added_by }}
            </v-chip>
          </template>

          <template #item.actions="{ item }">
            <div class="d-flex ga-0">
              <v-btn icon size="small" variant="text" @click.stop="openEdit(item)">
                <v-icon>mdi-pencil</v-icon>
                <v-tooltip activator="parent" location="top">Edit</v-tooltip>
              </v-btn>
              <v-btn icon size="small" variant="text" color="error" @click.stop="confirmDelete(item)">
                <v-icon>mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">Delete</v-tooltip>
              </v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Create / Edit Dialog -->
    <v-dialog v-model="formDialog" max-width="700" persistent>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2" color="primary">mdi-earth-plus</v-icon>
          {{ editingId ? 'Edit Resource' : 'New Research Resource' }}
          <v-spacer />
          <v-btn icon="mdi-close" size="small" variant="text" @click="formDialog = false" />
        </v-card-title>

        <v-card-text>
          <v-form ref="formRef">
            <v-row dense>
              <v-col cols="12" md="8">
                <v-text-field
                  v-model="form.name"
                  label="Name *"
                  placeholder="e.g. Stack Overflow"
                  :rules="[v => !!v || 'Required']"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-select
                  v-model="form.category"
                  :items="categories"
                  item-title="label"
                  item-value="value"
                  label="Category"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12">
                <v-text-field
                  v-model="form.url"
                  label="URL *"
                  placeholder="https://stackoverflow.com"
                  :rules="[v => !!v || 'Required']"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12">
                <v-textarea
                  v-model="form.description"
                  label="Description"
                  placeholder="What kind of information can be found here..."
                  variant="outlined"
                  density="compact"
                  rows="2"
                  auto-grow
                />
              </v-col>

              <v-col cols="12" md="4">
                <v-select
                  v-model="form.trust_level"
                  :items="trustLevels"
                  item-title="label"
                  item-value="value"
                  label="Trust Level"
                  variant="outlined"
                  density="compact"
                >
                  <template #item="{ item: tlItem, props: tlProps }">
                    <v-list-item v-bind="tlProps">
                      <template #prepend>
                        <v-icon :color="tlItem.raw.color" size="18">mdi-shield-check</v-icon>
                      </template>
                    </v-list-item>
                  </template>
                </v-select>
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="form.user_rating"
                  label="User Rating (0-10)"
                  type="number"
                  :min="0"
                  :max="10"
                  :step="0.5"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model.number="form.agent_rating"
                  label="Agent Rating (0-10)"
                  type="number"
                  :min="0"
                  :max="10"
                  :step="0.5"
                  variant="outlined"
                  density="compact"
                />
              </v-col>

              <v-col cols="12">
                <v-textarea
                  v-model="form.search_instructions"
                  label="Search Instructions"
                  placeholder="How the agent should search on this resource. E.g.: 'Use site search at /search?q=..., look for accepted answers, prefer posts with high vote counts.'"
                  variant="outlined"
                  density="compact"
                  rows="3"
                  auto-grow
                />
              </v-col>

              <v-col cols="12">
                <v-combobox
                  v-model="form.tags"
                  label="Tags"
                  variant="outlined"
                  density="compact"
                  multiple
                  chips
                  closable-chips
                  clearable
                  placeholder="Type and press Enter to add tags"
                />
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>

        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="formDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="elevated" :loading="saving" @click="saveResource">
            {{ editingId ? 'Save' : 'Create' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirmation -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Delete Resource</v-card-title>
        <v-card-text>
          Are you sure you want to delete <strong>{{ deleteTarget?.name }}</strong>?
          <br /><br />
          Type <strong>DELETE</strong> to confirm:
          <v-text-field
            v-model="deleteConfirm"
            variant="outlined"
            density="compact"
            class="mt-2"
            placeholder="DELETE"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :disabled="deleteConfirm !== 'DELETE'" @click="doDelete">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useResearchResourcesStore } from '../stores/researchResources'

const store = useResearchResourcesStore()

// ── Table config ──
const headers = [
  { title: 'Resource', key: 'name', sortable: true },
  { title: 'Trust', key: 'trust_level', width: 110, sortable: true },
  { title: 'User Rating', key: 'user_rating', width: 150, sortable: true },
  { title: 'Agent Rating', key: 'agent_rating', width: 100, sortable: true },
  { title: 'Active', key: 'is_active', width: 80 },
  { title: 'Uses', key: 'use_count', width: 70, sortable: true },
  { title: 'Added by', key: 'added_by', width: 100 },
  { title: '', key: 'actions', width: 100, sortable: false },
]

const categories = [
  { value: 'general', label: 'General', icon: 'mdi-web', color: 'blue-grey' },
  { value: 'docs', label: 'Docs', icon: 'mdi-file-document', color: 'blue' },
  { value: 'forum', label: 'Forum', icon: 'mdi-forum', color: 'orange' },
  { value: 'wiki', label: 'Wiki', icon: 'mdi-wikipedia', color: 'grey' },
  { value: 'news', label: 'News', icon: 'mdi-newspaper', color: 'red' },
  { value: 'code', label: 'Code', icon: 'mdi-code-braces', color: 'green' },
  { value: 'academic', label: 'Academic', icon: 'mdi-school', color: 'purple' },
  { value: 'social', label: 'Social', icon: 'mdi-account-group', color: 'pink' },
  { value: 'search', label: 'Search', icon: 'mdi-magnify', color: 'amber' },
]

const trustLevels = [
  { value: 'low', label: 'Low', color: 'grey' },
  { value: 'medium', label: 'Medium', color: 'blue' },
  { value: 'high', label: 'High', color: 'green' },
  { value: 'highest', label: 'Highest', color: 'amber' },
]

// ── Filters ──
const filterCategory = ref('')
const filterTrust = ref('')
const searchQuery = ref('')
let searchTimeout = null

const debouncedSearch = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => loadResources(), 400)
}

const loadResources = () => {
  const params = {}
  if (searchQuery.value) params.search = searchQuery.value
  if (filterCategory.value) params.category = filterCategory.value
  if (filterTrust.value) params.trust_level = filterTrust.value
  store.fetchResources(params)
}

// ── Form ──
const formDialog = ref(false)
const formRef = ref(null)
const editingId = ref(null)
const saving = ref(false)
const form = ref(defaultForm())

function defaultForm() {
  return {
    name: '',
    url: '',
    description: '',
    trust_level: 'medium',
    user_rating: 5.0,
    agent_rating: 5.0,
    search_instructions: '',
    category: 'general',
    tags: [],
  }
}

function openCreate() {
  editingId.value = null
  form.value = defaultForm()
  formDialog.value = true
}

function openEdit(item) {
  editingId.value = item.id
  form.value = {
    name: item.name,
    url: item.url,
    description: item.description || '',
    trust_level: item.trust_level,
    user_rating: item.user_rating,
    agent_rating: item.agent_rating,
    search_instructions: item.search_instructions || '',
    category: item.category,
    tags: item.tags || [],
  }
  formDialog.value = true
}

async function saveResource() {
  const { valid } = await formRef.value.validate()
  if (!valid) return
  saving.value = true
  try {
    if (editingId.value) {
      await store.updateResource(editingId.value, form.value)
    } else {
      await store.createResource(form.value)
    }
    formDialog.value = false
  } finally {
    saving.value = false
  }
}

async function toggleActive(item, val) {
  await store.updateResource(item.id, { is_active: val })
}

// ── Delete ──
const deleteDialog = ref(false)
const deleteTarget = ref(null)
const deleteConfirm = ref('')

function confirmDelete(item) {
  deleteTarget.value = item
  deleteConfirm.value = ''
  deleteDialog.value = true
}

async function doDelete() {
  await store.deleteResource(deleteTarget.value.id)
  deleteDialog.value = false
}

// ── Helpers ──
function categoryMeta(cat) {
  return categories.find(c => c.value === cat) || { icon: 'mdi-web', color: 'blue-grey' }
}

function trustColor(level) {
  const map = { low: 'grey', medium: 'blue', high: 'green', highest: 'amber' }
  return map[level] || 'grey'
}

onMounted(() => loadResources())
</script>
