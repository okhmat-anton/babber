<template>
  <div class="skill-ide" :style="{ height: 'calc(100vh - 100px)' }">
    <!-- Header -->
    <div class="ide-header d-flex align-center px-4 py-2">
      <v-btn icon="mdi-arrow-left" variant="text" size="small" @click="$router.back()" />
      <div class="text-h6 font-weight-bold ml-2">{{ isEdit ? (skill?.display_name || 'Edit Skill') : 'New Skill' }}</div>
      <v-chip v-if="isReadOnly" color="info" size="x-small" class="ml-2" variant="flat">
        <v-icon start size="x-small">mdi-eye</v-icon> Preview
      </v-chip>
      <v-chip v-else-if="skill?.is_system" color="primary" size="x-small" class="ml-2">System</v-chip>
      <v-spacer />
      <v-btn v-if="!isEdit" color="primary" size="small" variant="flat" :loading="saving" @click="handleCreate" class="mr-2">
        <v-icon start>mdi-content-save</v-icon> Create
      </v-btn>
      <v-btn v-if="isEdit && !isReadOnly" color="success" size="small" variant="flat" :loading="fileSaving" @click="saveCurrentFile" :disabled="!currentFile">
        <v-icon start>mdi-content-save-outline</v-icon> Save File
        <span v-if="fileModified" class="ml-1">*</span>
      </v-btn>
    </div>

    <div class="ide-body d-flex" style="height: calc(100% - 52px)">
      <!-- Left Panel: File Tree OR New Skill Form -->
      <div class="ide-sidebar" :style="{ width: sidebarWidth + 'px', minWidth: '200px', maxWidth: '400px' }">
        <!-- New skill form (create mode) -->
        <div v-if="!isEdit" class="pa-3" style="overflow-y: auto; height: 100%">
          <v-text-field v-model="createForm.name" label="Name (snake_case)" density="compact" class="mb-2" />
          <v-text-field v-model="createForm.display_name" label="Display Name" density="compact" class="mb-2" />
          <v-textarea v-model="createForm.description" label="Description (human)" rows="2" density="compact" class="mb-2" />
          <v-textarea v-model="createForm.description_for_agent" label="Description (for Agent)" rows="2" density="compact" class="mb-2" />
          <v-select v-model="createForm.category" :items="categories" label="Category" density="compact" class="mb-2" />
          <v-text-field v-model="createForm.version" label="Version" density="compact" class="mb-2" />
          <v-switch v-model="createForm.is_shared" label="Shared" color="primary" density="compact" />
        </div>

        <!-- File tree (edit mode) -->
        <div v-else class="ide-file-tree">
          <div class="d-flex align-center px-2 py-1 tree-header">
            <span class="text-caption text-uppercase font-weight-bold text-grey">Files</span>
            <v-spacer />
            <v-btn v-if="!isReadOnly" icon="mdi-file-plus-outline" size="x-small" variant="text" @click="showNewFileDialog" title="New File" />
            <v-btn v-if="!isReadOnly" icon="mdi-folder-plus-outline" size="x-small" variant="text" @click="showNewFolderDialog" title="New Folder" />
            <v-btn icon="mdi-refresh" size="x-small" variant="text" @click="loadFiles" title="Refresh" />
          </div>
          <div class="tree-content" style="overflow-y: auto; height: calc(100% - 36px)">
            <tree-node
              v-for="node in fileTree"
              :key="node.path"
              :node="node"
              :selected-path="currentFile?.path || ''"
              :depth="0"
              :read-only="isReadOnly"
              @select="openFile"
              @delete-file="confirmDeleteFile"
            />
            <div v-if="!fileTree.length" class="text-center text-grey pa-4 text-caption">
              No files yet
            </div>
          </div>
        </div>
      </div>

      <!-- Resize handle -->
      <div class="ide-resize-handle" @mousedown="startResize" />

      <!-- Right Panel: Editor -->
      <div class="ide-editor-area" style="flex: 1; min-width: 0">
        <!-- Tab bar -->
        <div v-if="currentFile" class="editor-tab-bar d-flex align-center px-2">
          <v-icon size="small" class="mr-1">{{ getFileIcon(currentFile.path) }}</v-icon>
          <span class="text-body-2">{{ currentFile.path }}</span>
          <v-chip v-if="fileModified" color="warning" size="x-small" class="ml-2" variant="flat">modified</v-chip>
          <v-spacer />
          <span class="text-caption text-grey mr-2">{{ currentFile.language }}</span>
        </div>

        <!-- CodeMirror Editor -->
        <div v-if="currentFile" ref="editorContainer" class="editor-container" />

        <!-- Empty state -->
        <div v-else class="d-flex align-center justify-center" style="height: 100%">
          <div class="text-center text-grey">
            <v-icon size="64" class="mb-4">mdi-code-braces</v-icon>
            <div class="text-h6">{{ isEdit ? (isReadOnly ? 'Select a file to preview' : 'Select a file to edit') : 'Fill in skill details and click Create' }}</div>
            <div class="text-body-2 mt-1" v-if="isEdit">Choose a file from the tree on the left</div>
          </div>
        </div>
      </div>
    </div>

    <!-- New File Dialog -->
    <v-dialog v-model="newFileDialog" max-width="450">
      <v-card>
        <v-card-title>{{ newFileIsDir ? 'New Folder' : 'New File' }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newFilePath"
            :label="newFileIsDir ? 'Folder path (e.g. utils)' : 'File path (e.g. utils/helper.py)'"
            density="compact"
            autofocus
            @keyup.enter="createNewFile"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="newFileDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="createNewFile">Create</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete File Confirm -->
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
  </div>
</template>

<script>
import { defineComponent, ref, computed, onMounted, onBeforeUnmount, nextTick, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
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

// ---------- Recursive FileTreeNode ----------
const TreeNode = defineComponent({
  name: 'TreeNode',
  props: {
    node: { type: Object, required: true },
    selectedPath: { type: String, default: '' },
    depth: { type: Number, default: 0 },
    readOnly: { type: Boolean, default: false },
  },
  emits: ['select', 'delete-file'],
  setup(props, { emit }) {
    const expanded = ref(true)

    const getIcon = () => {
      if (props.node.is_dir) return expanded.value ? 'mdi-folder-open' : 'mdi-folder'
      const ext = props.node.name.split('.').pop().toLowerCase()
      const map = {
        py: 'mdi-language-python', js: 'mdi-language-javascript', ts: 'mdi-language-typescript',
        sh: 'mdi-console', bash: 'mdi-console', json: 'mdi-code-json',
        yaml: 'mdi-file-cog', yml: 'mdi-file-cog', md: 'mdi-language-markdown',
        html: 'mdi-language-html5', css: 'mdi-language-css3', sql: 'mdi-database',
      }
      return map[ext] || 'mdi-file-outline'
    }

    return () => {
      const children = []
      const isSelected = props.selectedPath === props.node.path

      children.push(h('div', {
        class: ['tree-node', { 'tree-node-selected': isSelected }],
        style: { paddingLeft: (props.depth * 16 + 8) + 'px' },
        onClick: () => {
          if (props.node.is_dir) { expanded.value = !expanded.value }
          else { emit('select', props.node) }
        },
      }, [
        h('i', {
          class: ['mdi', getIcon(), 'tree-icon', props.node.is_dir ? 'text-amber' : 'text-grey-lighten-1'],
          style: { fontSize: '16px', marginRight: '6px' },
        }),
        h('span', { class: 'tree-name' }, props.node.name),
        (!props.readOnly && props.node.name !== 'manifest.json')
          ? h('i', {
              class: 'mdi mdi-close tree-delete',
              onClick: (e) => { e.stopPropagation(); emit('delete-file', props.node.path) },
              title: 'Delete',
            })
          : null,
      ]))

      if (props.node.is_dir && expanded.value && props.node.children) {
        for (const child of props.node.children) {
          children.push(h(TreeNode, {
            node: child,
            selectedPath: props.selectedPath,
            depth: props.depth + 1,
            readOnly: props.readOnly,
            onSelect: (n) => emit('select', n),
            'onDelete-file': (p) => emit('delete-file', p),
          }))
        }
      }

      return h('div', {}, children)
    }
  },
})

export default defineComponent({
  name: 'SkillFormView',
  components: { TreeNode },
  setup() {
    const route = useRoute()
    const router = useRouter()

    const isEdit = computed(() => !!route.params.id)
    const isReadOnly = computed(() => !!skill.value?.is_system)
    const skill = ref(null)
    const saving = ref(false)
    const fileSaving = ref(false)
    const fileTree = ref([])
    const currentFile = ref(null)
    const fileContent = ref('')
    const fileModified = ref(false)
    const sidebarWidth = ref(parseInt(localStorage.getItem('skill_sidebar_width') || '260'))
    const editorContainer = ref(null)
    let editorView = null

    const categories = ['general', 'web', 'files', 'code', 'data', 'custom']

    const createForm = ref({
      name: '', display_name: '', description: '', description_for_agent: '',
      category: 'general', version: '1.0.0', code: '', is_shared: false,
      input_schema: {}, output_schema: {},
    })

    // Dialogs
    const newFileDialog = ref(false)
    const newFileIsDir = ref(false)
    const newFilePath = ref('')
    const deleteFileDialog = ref(false)
    const deleteFilePath = ref('')

    // ===== Load =====
    onMounted(async () => {
      if (isEdit.value) {
        await loadSkill()
        await loadFiles()
        // Restore last opened file
        const savedPath = localStorage.getItem(`skill_open_file_${route.params.id}`)
        if (savedPath) {
          const findNode = (nodes, path) => {
            for (const n of nodes) {
              if (n.path === path && !n.is_dir) return n
              if (n.children) { const found = findNode(n.children, path); if (found) return found }
            }
            return null
          }
          const node = findNode(fileTree.value, savedPath)
          if (node) await openFile(node)
        }
      }
    })

    const loadSkill = async () => {
      const { data } = await api.get(`/skills/${route.params.id}`)
      skill.value = data
    }

    const loadFiles = async () => {
      if (!isEdit.value) return
      try {
        const { data } = await api.get(`/skills/${route.params.id}/files`)
        fileTree.value = data
      } catch { fileTree.value = [] }
    }

    // ===== File ops =====
    const openFile = async (node) => {
      if (node.is_dir) return
      if (fileModified.value && currentFile.value) {
        if (!confirm('Current file has unsaved changes. Discard?')) return
      }
      try {
        const { data } = await api.get(`/skills/${route.params.id}/files/read`, { params: { path: node.path } })
        currentFile.value = data
        fileContent.value = data.content
        fileModified.value = false
        localStorage.setItem(`skill_open_file_${route.params.id}`, node.path)
        await nextTick()
        initEditor(data.content, data.language)
      } catch (e) { console.error('Failed to open file:', e) }
    }

    const saveCurrentFile = async () => {
      if (!currentFile.value) return
      fileSaving.value = true
      try {
        const content = editorView ? editorView.state.doc.toString() : fileContent.value
        await api.put(`/skills/${route.params.id}/files/write`, {
          path: currentFile.value.path,
          content,
        })
        fileContent.value = content
        fileModified.value = false
        // If manifest was saved, reload skill metadata
        if (currentFile.value.path === 'manifest.json') await loadSkill()
      } finally { fileSaving.value = false }
    }

    const showNewFileDialog = () => { newFileIsDir.value = false; newFilePath.value = ''; newFileDialog.value = true }
    const showNewFolderDialog = () => { newFileIsDir.value = true; newFilePath.value = ''; newFileDialog.value = true }

    const createNewFile = async () => {
      if (!newFilePath.value.trim()) return
      try {
        await api.post(`/skills/${route.params.id}/files/create`, {
          path: newFilePath.value.trim(), is_dir: newFileIsDir.value, content: '',
        })
        newFileDialog.value = false
        await loadFiles()
        if (!newFileIsDir.value) await openFile({ path: newFilePath.value.trim(), is_dir: false })
      } catch (e) { alert(e.response?.data?.detail || 'Failed to create') }
    }

    const confirmDeleteFile = (path) => { deleteFilePath.value = path; deleteFileDialog.value = true }

    const doDeleteFile = async () => {
      try {
        await api.delete(`/skills/${route.params.id}/files/delete`, { params: { path: deleteFilePath.value } })
        deleteFileDialog.value = false
        if (currentFile.value?.path === deleteFilePath.value || currentFile.value?.path.startsWith(deleteFilePath.value + '/')) {
          currentFile.value = null; destroyEditor()
        }
        await loadFiles()
      } catch (e) { alert(e.response?.data?.detail || 'Failed to delete') }
    }

    // ===== Create skill =====
    const handleCreate = async () => {
      if (!createForm.value.name) return
      saving.value = true
      try {
        const { data } = await api.post('/skills', createForm.value)
        router.replace(`/skills/${data.id}`)
      } catch (e) { alert(e.response?.data?.detail || 'Failed to create') }
      finally { saving.value = false }
    }

    // ===== CodeMirror =====
    const getLanguageExtension = (lang) => {
      const map = {
        python: python(), javascript: javascript(), typescript: javascript({ typescript: true }),
        json: jsonLang(), markdown: markdown(), html: html(), css: css(), yaml: yaml(), sql: sql(),
      }
      return map[lang] || []
    }

    const initEditor = (content, language) => {
      destroyEditor()
      if (!editorContainer.value) return

      const readOnly = isReadOnly.value

      const extensions = [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightSpecialChars(),
        ...(readOnly ? [] : [history()]),
        foldGutter(),
        drawSelection(),
        ...(readOnly ? [] : [dropCursor()]),
        EditorState.allowMultipleSelections.of(true),
        ...(readOnly ? [] : [indentOnInput()]),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        bracketMatching(),
        ...(readOnly ? [] : [closeBrackets(), autocompletion()]),
        rectangularSelection(),
        crosshairCursor(),
        highlightActiveLine(),
        highlightSelectionMatches(),
        keymap.of([
          ...(readOnly ? [] : closeBracketsKeymap), ...defaultKeymap, ...searchKeymap,
          ...(readOnly ? [] : historyKeymap), ...foldKeymap, ...(readOnly ? [] : completionKeymap),
          ...(readOnly ? [] : [indentWithTab]),
          ...(readOnly ? [] : [{ key: 'Mod-s', run: () => { saveCurrentFile(); return true } }]),
        ]),
        oneDark,
        ...(readOnly ? [] : [EditorView.updateListener.of((update) => { if (update.docChanged) fileModified.value = true })]),
        EditorView.theme({ '&': { height: '100%' }, '.cm-scroller': { overflow: 'auto' } }),
        getLanguageExtension(language),
        ...(readOnly ? [EditorState.readOnly.of(true), EditorView.editable.of(false)] : []),
      ].flat()

      editorView = new EditorView({
        state: EditorState.create({ doc: content, extensions }),
        parent: editorContainer.value,
      })
    }

    const destroyEditor = () => { if (editorView) { editorView.destroy(); editorView = null } }
    onBeforeUnmount(destroyEditor)

    // ===== Resize =====
    let resizing = false
    const startResize = (e) => {
      resizing = true
      const startX = e.clientX; const startW = sidebarWidth.value
      const onMove = (ev) => { if (!resizing) return; sidebarWidth.value = Math.max(200, Math.min(400, startW + ev.clientX - startX)) }
      const onUp = () => { resizing = false; localStorage.setItem('skill_sidebar_width', sidebarWidth.value); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    }

    // ===== Helpers =====
    const getFileIcon = (path) => {
      const ext = path.split('.').pop().toLowerCase()
      const icons = {
        py: 'mdi-language-python', js: 'mdi-language-javascript', ts: 'mdi-language-typescript',
        sh: 'mdi-console', bash: 'mdi-console', json: 'mdi-code-json',
        yaml: 'mdi-file-cog', yml: 'mdi-file-cog', md: 'mdi-language-markdown',
        html: 'mdi-language-html5', css: 'mdi-language-css3', sql: 'mdi-database', txt: 'mdi-file-document-outline',
      }
      return icons[ext] || 'mdi-file-outline'
    }

    return {
      isEdit, isReadOnly, skill, saving, fileSaving, fileTree, currentFile, fileContent, fileModified,
      sidebarWidth, editorContainer, categories, createForm,
      newFileDialog, newFileIsDir, newFilePath, deleteFileDialog, deleteFilePath,
      loadFiles, openFile, saveCurrentFile, showNewFileDialog, showNewFolderDialog,
      createNewFile, confirmDeleteFile, doDeleteFile, handleCreate, startResize, getFileIcon,
    }
  },
})
</script>

<style scoped>
.skill-ide {
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
}

.ide-header {
  background: #252526;
  border-bottom: 1px solid #3c3c3c;
  height: 52px;
  flex-shrink: 0;
}

.ide-body {
  flex: 1;
  min-height: 0;
}

.ide-sidebar {
  background: #252526;
  border-right: 1px solid #3c3c3c;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ide-resize-handle {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.2s;
  flex-shrink: 0;
}

.ide-resize-handle:hover {
  background: #007acc;
}

.ide-editor-area {
  display: flex;
  flex-direction: column;
  background: #1e1e1e;
  overflow: hidden;
}

.editor-tab-bar {
  background: #2d2d2d;
  border-bottom: 1px solid #3c3c3c;
  height: 36px;
  flex-shrink: 0;
}

.editor-container {
  flex: 1;
  overflow: hidden;
}

.editor-container :deep(.cm-editor) {
  height: 100%;
}

.editor-container :deep(.cm-scroller) {
  overflow: auto;
}

.tree-header {
  border-bottom: 1px solid #3c3c3c;
  height: 36px;
  flex-shrink: 0;
}

.tree-content {
  flex: 1;
}

.tree-node {
  display: flex;
  align-items: center;
  padding: 3px 8px;
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  color: #ccc;
  position: relative;
}

.tree-node:hover {
  background: #2a2d2e;
}

.tree-node-selected {
  background: #094771 !important;
  color: #fff;
}

.tree-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-delete {
  display: none;
  font-size: 14px;
  color: #888;
  cursor: pointer;
  margin-left: 4px;
}

.tree-node:hover .tree-delete {
  display: inline;
}

.tree-delete:hover {
  color: #f44;
}

.tree-icon {
  flex-shrink: 0;
}

.ide-file-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>
