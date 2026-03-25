<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Notes</div>
      <v-spacer />
      <v-btn
        v-if="notes.length"
        variant="text"
        size="small"
        :prepend-icon="allExpanded ? 'mdi-unfold-less-horizontal' : 'mdi-unfold-more-horizontal'"
        class="mr-3"
        @click="toggleAll"
      >
        {{ allExpanded ? 'Collapse All' : 'Expand All' }}
      </v-btn>
      <v-btn color="teal" prepend-icon="mdi-plus" @click="openCreateDialog">
        New Note
      </v-btn>
    </div>

    <!-- Error alert -->
    <v-alert v-if="errorMsg" type="error" closable class="mb-4" @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <!-- Filters -->
    <div class="d-flex align-center ga-3 mb-4 flex-wrap">
      <v-chip-group v-model="filterStatus" selected-class="text-primary" @update:model-value="loadNotes">
        <v-chip value="" variant="tonal" size="small">All</v-chip>
        <v-chip v-for="s in statuses" :key="s.value" :value="s.value" :color="s.color" variant="tonal" size="small">
          <v-icon start size="14">{{ s.icon }}</v-icon>
          {{ s.label }}
        </v-chip>
      </v-chip-group>

      <v-spacer />

      <v-select
        v-model="filterCategory"
        :items="categoryOptions"
        label="Category"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 200px;"
        prepend-inner-icon="mdi-tag-outline"
        @update:model-value="loadNotes"
      />
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="outlined"
        placeholder="Search notes..."
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        style="max-width: 280px;"
        @update:model-value="debouncedLoad"
      />
    </div>

    <!-- Notes grouped by category -->
    <div v-if="!filterCategory && groupedNotes.length > 1">
      <div v-for="group in groupedNotes" :key="group.category" class="mb-6">
        <div class="text-subtitle-1 font-weight-bold mb-2 d-flex align-center">
          <v-icon size="18" class="mr-2">mdi-tag</v-icon>
          {{ group.category || 'Uncategorized' }}
          <v-chip size="x-small" variant="tonal" class="ml-2">{{ group.items.length }}</v-chip>
        </div>
        <draggable
          :list="group.items"
          item-key="id"
          handle=".drag-handle"
          animation="200"
          ghost-class="drag-ghost"
          class="d-flex flex-column ga-3"
          @end="onDragEnd(group.category)"
        >
          <template #item="{ element: note }">
            <v-card variant="flat" class="note-card" :class="{ 'note-completed': note.status === 'completed', 'note-no-context': !note.in_context }">
              <div class="card-accent" :class="priorityAccentClass(note.priority)" />
              <v-card-text class="pa-5 pl-7">
                <div class="d-flex align-start">
                  <div class="drag-handle mr-2 mt-1" title="Drag to reorder" @click.stop>
                    <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
                  </div>
                  <v-btn
                    icon
                    size="x-small"
                    variant="text"
                    class="mr-2 mt-1"
                    @click.stop="toggleExpand(note.id)"
                  >
                    <v-icon size="16">{{ expandedNotes.has(note.id) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                  </v-btn>
                  <div class="flex-grow-1" @click="toggleExpand(note.id)" style="cursor: pointer;">
                    <div class="d-flex align-center mb-1 ga-2 flex-wrap">
                      <span class="text-subtitle-1 font-weight-medium">{{ note.title }}</span>
                      <v-chip :color="priorityColor(note.priority)" size="x-small" variant="tonal">
                        {{ note.priority }}
                      </v-chip>
                      <v-chip :color="statusColor(note.status)" size="x-small" variant="tonal">
                        {{ note.status }}
                      </v-chip>
                      <v-chip v-if="note.category" size="x-small" variant="tonal" color="indigo">
                        {{ note.category }}
                      </v-chip>
                      <v-chip v-if="!note.in_context" size="x-small" variant="tonal" color="grey">
                        <v-icon start size="12">mdi-brain-off</v-icon>
                        Hidden from context
                      </v-chip>
                      <span class="text-caption text-grey ml-auto">{{ formatDate(note.created_at) }}</span>
                      <span v-if="!expandedNotes.has(note.id) && note.content" class="text-caption text-medium-emphasis text-truncate" style="max-width: 300px;">{{ note.content.substring(0, 80) }}</span>
                    </div>
                    <div v-if="expandedNotes.has(note.id)">
                      <div v-if="note.content" class="text-body-2 text-medium-emphasis note-content mt-1">{{ note.content }}</div>
                      <div v-if="note.tags && note.tags.length" class="d-flex align-center ga-2 mt-2">
                        <v-chip v-for="tag in note.tags" :key="tag" size="x-small" variant="tonal" color="blue-grey">
                          {{ tag }}
                        </v-chip>
                      </div>
                    </div>
                  </div>
                  <div class="d-flex ml-3 ga-1">
                    <v-btn icon size="small" variant="text" @click.stop="editNote(note)">
                      <v-icon>mdi-pencil</v-icon>
                    </v-btn>
                    <v-btn icon size="small" variant="text" :color="note.in_context ? 'info' : 'grey'" @click.stop="toggleContext(note)" :title="note.in_context ? 'In context — click to exclude' : 'Excluded — click to include'">
                      <v-icon>{{ note.in_context ? 'mdi-brain' : 'mdi-brain-off' }}</v-icon>
                    </v-btn>
                    <v-btn icon size="small" variant="text" color="error" @click.stop="deleteNote(note.id)">
                      <v-icon>mdi-delete</v-icon>
                    </v-btn>
                  </div>
                </div>
              </v-card-text>
            </v-card>
          </template>
        </draggable>
      </div>
    </div>

    <!-- Flat list (with drag) -->
    <draggable
      v-else-if="notes.length"
      :list="notes"
      item-key="id"
      handle=".drag-handle"
      animation="200"
      ghost-class="drag-ghost"
      class="d-flex flex-column ga-3"
      @end="onDragEndFlat"
    >
      <template #item="{ element: note }">
        <v-card variant="flat" class="note-card" :class="{ 'note-completed': note.status === 'completed', 'note-no-context': !note.in_context }">
          <div class="card-accent" :class="priorityAccentClass(note.priority)" />
          <v-card-text class="pa-5 pl-7">
            <div class="d-flex align-start">
              <div class="drag-handle mr-2 mt-1" title="Drag to reorder" @click.stop>
                <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
              </div>
              <v-btn
                icon
                size="x-small"
                variant="text"
                class="mr-2 mt-1"
                @click.stop="toggleExpand(note.id)"
              >
                <v-icon size="16">{{ expandedNotes.has(note.id) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
              </v-btn>
              <div class="flex-grow-1" @click="toggleExpand(note.id)" style="cursor: pointer;">
                <div class="d-flex align-center mb-1 ga-2 flex-wrap">
                  <span class="text-subtitle-1 font-weight-medium">{{ note.title }}</span>
                  <v-chip :color="priorityColor(note.priority)" size="x-small" variant="tonal">
                    {{ note.priority }}
                  </v-chip>
                  <v-chip :color="statusColor(note.status)" size="x-small" variant="tonal">
                    {{ note.status }}
                  </v-chip>
                  <v-chip v-if="note.category" size="x-small" variant="tonal" color="indigo">
                    {{ note.category }}
                  </v-chip>
                  <v-chip v-if="!note.in_context" size="x-small" variant="tonal" color="grey">
                    <v-icon start size="12">mdi-brain-off</v-icon>
                    Hidden from context
                  </v-chip>
                  <span class="text-caption text-grey ml-auto">{{ formatDate(note.created_at) }}</span>
                  <span v-if="!expandedNotes.has(note.id) && note.content" class="text-caption text-medium-emphasis text-truncate" style="max-width: 300px;">{{ note.content.substring(0, 80) }}</span>
                </div>
                <div v-if="expandedNotes.has(note.id)">
                  <div v-if="note.content" class="text-body-2 text-medium-emphasis note-content mt-1">{{ note.content }}</div>
                  <div v-if="note.tags && note.tags.length" class="d-flex align-center ga-2 mt-2">
                    <v-chip v-for="tag in note.tags" :key="tag" size="x-small" variant="tonal" color="blue-grey">
                      {{ tag }}
                    </v-chip>
                  </div>
                </div>
              </div>
              <div class="d-flex ml-3 ga-1">
                <v-btn icon size="small" variant="text" @click.stop="editNote(note)">
                  <v-icon>mdi-pencil</v-icon>
                </v-btn>
                <v-btn icon size="small" variant="text" :color="note.in_context ? 'info' : 'grey'" @click.stop="toggleContext(note)" :title="note.in_context ? 'In context — click to exclude' : 'Excluded — click to include'">
                  <v-icon>{{ note.in_context ? 'mdi-brain' : 'mdi-brain-off' }}</v-icon>
                </v-btn>
                <v-btn icon size="small" variant="text" color="error" @click.stop="deleteNote(note.id)">
                  <v-icon>mdi-delete</v-icon>
                </v-btn>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </template>
    </draggable>

    <!-- Empty state -->
    <div v-if="!loading && notes.length === 0" class="empty-state">
      <div class="empty-state-icon">
        <v-icon size="48" color="teal">mdi-note-text</v-icon>
      </div>
      <div class="text-h6 mt-4">No notes yet</div>
      <div class="text-body-2 text-medium-emphasis mt-1 mb-5">
        Write down thoughts, reminders, or context for your agents
      </div>
      <v-btn color="teal" variant="flat" @click="openCreateDialog" prepend-icon="mdi-plus">
        Add First Note
      </v-btn>
    </div>

    <!-- Loading -->
    <v-progress-linear v-if="loading" indeterminate color="teal" class="mb-4" />

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">Delete Note</v-card-title>
        <v-card-text>
          Are you sure you want to delete this note? This action cannot be undone.
          <div class="text-body-2 mt-4 mb-1">
            Type <strong class="text-error" style="cursor: pointer; border-bottom: 1px dashed currentColor" @click="deleteConfirmText = 'DELETE'">DELETE</strong> to confirm
          </div>
          <v-text-field
            v-model="deleteConfirmText"
            placeholder="DELETE"
            variant="outlined"
            density="compact"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :disabled="deleteConfirmText !== 'DELETE'" @click="doDeleteNote">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Create/Edit Note Dialog -->
    <v-dialog v-model="formDialog" max-width="600">
      <v-card>
        <v-card-title>{{ editingNote ? 'Edit Note' : 'New Note' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="formData.title"
            label="Title"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-textarea
            v-model="formData.content"
            label="Content"
            variant="outlined"
            density="compact"
            rows="6"
            class="mb-3"
          />
          <v-select
            v-model="formData.priority"
            :items="['low', 'medium', 'high']"
            label="Priority"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="formData.status"
            :items="statuses.map(s => s.value)"
            label="Status"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-combobox
            v-model="formData.category"
            :items="categoryOptions"
            label="Category"
            variant="outlined"
            density="compact"
            clearable
            prepend-inner-icon="mdi-tag-outline"
            class="mb-3"
          />
          <v-combobox
            v-model="formData.tags"
            label="Tags"
            variant="outlined"
            density="compact"
            chips
            multiple
            closable-chips
            class="mb-3"
          />
          <v-switch
            v-model="formData.in_context"
            label="Include in agent context"
            color="teal"
            density="compact"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="formDialog = false">Cancel</v-btn>
          <v-btn color="teal" :loading="saving" @click="saveNote">{{ editingNote ? 'Update' : 'Create' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject, watch } from 'vue'
import draggable from 'vuedraggable'
import api from '../api'

const showSnackbar = inject('showSnackbar')
const dataRefreshSignal = inject('dataRefreshSignal', reactive({ type: '', timestamp: 0 }))
watch(() => dataRefreshSignal.timestamp, () => {
  if (dataRefreshSignal.type === 'notes') loadNotes()
})

// State
const notes = ref([])
const loading = ref(false)
const errorMsg = ref(null)
const filterStatus = ref('')
const filterCategory = ref(null)
const searchQuery = ref('')

const formDialog = ref(false)
const editingNote = ref(null)
const saving = ref(false)
const formData = ref({
  title: '', content: '', priority: 'medium',
  status: 'active', category: '', tags: [], in_context: true,
})

const deleteDialog = ref(false)
const deleteNoteId = ref(null)
const deleteConfirmText = ref('')
const expandedNotes = ref(new Set())
const allExpanded = ref(false)

const statuses = [
  { value: 'active', label: 'Active', color: 'teal', icon: 'mdi-note-text-outline' },
  { value: 'completed', label: 'Completed', color: 'success', icon: 'mdi-check-circle-outline' },
  { value: 'archived', label: 'Archived', color: 'brown', icon: 'mdi-archive-outline' },
]

const categoryOptions = computed(() => {
  const cats = [...new Set(notes.value.map(n => n.category).filter(Boolean))]
  return cats.sort()
})

const groupedNotes = computed(() => {
  const groups = {}
  for (const n of notes.value) {
    const cat = n.category || ''
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(n)
  }
  return Object.entries(groups)
    .sort(([a], [b]) => { if (!a) return 1; if (!b) return -1; return a.localeCompare(b) })
    .map(([cat, items]) => ({ category: cat, items }))
})

onMounted(async () => {
  await loadNotes()
})

async function loadNotes() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterCategory.value) params.category = filterCategory.value
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await api.get('/notes', { params })
    notes.value = data.items || []
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to load notes'
  } finally {
    loading.value = false
  }
}

let _debounce = null
function debouncedLoad() {
  clearTimeout(_debounce)
  _debounce = setTimeout(() => loadNotes(), 400)
}

function toggleExpand(noteId) {
  if (expandedNotes.value.has(noteId)) {
    expandedNotes.value.delete(noteId)
  } else {
    expandedNotes.value.add(noteId)
  }
  expandedNotes.value = new Set(expandedNotes.value) // trigger reactivity
}

function toggleAll() {
  if (allExpanded.value) {
    expandedNotes.value = new Set()
  } else {
    expandedNotes.value = new Set(notes.value.map(n => n.id))
  }
  allExpanded.value = !allExpanded.value
}

function openCreateDialog() {
  editingNote.value = null
  formData.value = {
    title: '', content: '', priority: 'medium',
    status: 'active', category: '', tags: [], in_context: true,
  }
  formDialog.value = true
}

function editNote(item) {
  editingNote.value = item
  formData.value = {
    title: item.title,
    content: item.content,
    priority: item.priority,
    status: item.status,
    category: item.category || '',
    tags: [...(item.tags || [])],
    in_context: item.in_context !== false,
  }
  formDialog.value = true
}

async function saveNote() {
  if (!formData.value.title.trim()) return
  saving.value = true
  try {
    if (editingNote.value) {
      await api.patch(`/notes/${editingNote.value.id}`, {
        title: formData.value.title,
        content: formData.value.content,
        priority: formData.value.priority,
        status: formData.value.status,
        category: formData.value.category || null,
        tags: formData.value.tags,
        in_context: formData.value.in_context,
      })
      showSnackbar?.('Note updated', 'success')
    } else {
      const payload = { ...formData.value }
      payload.category = payload.category || null
      await api.post('/notes', payload)
      showSnackbar?.('Note created', 'success')
    }
    formDialog.value = false
    await loadNotes()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to save note'
  } finally {
    saving.value = false
  }
}

async function toggleContext(note) {
  try {
    await api.patch(`/notes/${note.id}`, { in_context: !note.in_context })
    note.in_context = !note.in_context
    showSnackbar?.(note.in_context ? 'Added to context' : 'Removed from context', 'success')
  } catch (e) {
    showSnackbar?.('Failed to update', 'error')
  }
}

async function deleteNote(id) {
  deleteNoteId.value = id
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

async function doDeleteNote() {
  const id = deleteNoteId.value
  deleteDialog.value = false
  try {
    await api.delete(`/notes/${id}`)
    notes.value = notes.value.filter(n => n.id !== id)
    showSnackbar?.('Note deleted', 'success')
  } catch (e) {
    showSnackbar?.('Failed to delete', 'error')
  }
}

function statusColor(s) {
  return { active: 'teal', completed: 'success', archived: 'brown' }[s] || 'grey'
}

function priorityColor(p) {
  return { low: 'blue-grey', medium: 'blue', high: 'red' }[p] || 'grey'
}

function priorityAccentClass(p) {
  return { low: 'accent-grey', medium: 'accent-teal', high: 'accent-red' }[p] || 'accent-teal'
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function onDragEnd(category) {
  const group = groupedNotes.value.find(g => g.category === category)
  if (!group) return
  const ids = group.items.map(n => n.id)
  try {
    await api.post('/notes/reorder', { ids })
    await loadNotes()
  } catch (e) {
    console.error('Failed to reorder notes:', e)
  }
}

async function onDragEndFlat() {
  const ids = notes.value.map(n => n.id)
  try {
    await api.post('/notes/reorder', { ids })
    await loadNotes()
  } catch (e) {
    console.error('Failed to reorder notes:', e)
  }
}
</script>

<style scoped>
.note-card {
  position: relative;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.03) !important;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06) !important;
  border-radius: 12px !important;
}

.card-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 3px 0 0 3px;
}

.accent-teal { background: rgb(var(--v-theme-teal, 77, 182, 172)); }
.accent-red { background: rgb(var(--v-theme-error)); }
.accent-grey { background: #9e9e9e; }

.note-completed {
  opacity: 0.5;
}

.note-no-context {
  border-left: 2px dashed rgba(var(--v-theme-on-surface), 0.15) !important;
}

.note-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 64px 24px;
}

.empty-state-icon {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(77, 182, 172, 0.1);
}

/* Drag & Drop */
.drag-handle {
  cursor: grab;
  opacity: 0.4;
  transition: opacity 0.15s;
}

.drag-handle:hover {
  opacity: 0.8;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-ghost {
  opacity: 0.3;
  border: 2px dashed rgba(var(--v-theme-primary), 0.5) !important;
}
</style>
