<template>
  <div>
    <div class="d-flex align-center mb-6">
      <div class="text-h4 font-weight-bold">Skills</div>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" to="/skills/new">New Skill</v-btn>
    </div>

    <v-row class="mb-3">
      <v-col cols="3">
        <v-select v-model="filterCategory" :items="['all','general','web','files','code','data','custom']" label="Category" density="compact" />
      </v-col>
    </v-row>

    <v-card>
      <v-card-text class="pa-0">
        <v-data-table :headers="headers" :items="skills" :loading="loading" hover>
          <template #item.is_system="{ item }">
            <v-chip v-if="item.is_system" color="primary" size="x-small" variant="flat">System</v-chip>
          </template>
          <template #item.is_shared="{ item }">
            <v-icon v-if="item.is_shared" color="success" size="small">mdi-share-variant</v-icon>
          </template>
          <template #item.category="{ item }">
            <v-chip size="x-small" variant="tonal">{{ item.category }}</v-chip>
          </template>
          <template #item.actions="{ item }">
            <v-btn v-if="item.is_system" icon="mdi-eye" size="small" variant="text" @click="$router.push(`/skills/${item.id}`)" title="Preview" />
            <v-btn v-if="!item.is_system" icon="mdi-pencil" size="small" variant="text" @click="$router.push(`/skills/${item.id}`)" />
            <v-btn v-if="!item.is_shared && !item.is_system" icon="mdi-share" size="small" variant="text" color="success" @click="share(item)" title="Share" />
            <v-btn v-if="item.is_shared && !item.is_system" icon="mdi-share-off" size="small" variant="text" color="grey" @click="unshare(item)" title="Unshare" />
            <v-btn icon="mdi-content-copy" size="small" variant="text" @click="duplicate(item)" />
            <v-btn v-if="!item.is_system" icon="mdi-delete" size="small" variant="text" color="error" @click="handleDelete(item)" />
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <ConfirmDeleteDialog
      v-model="deleteDialog"
      title="Delete Skill"
      :message="`Are you sure you want to delete &quot;${deleteTarget?.display_name}&quot;?`"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import api from '../api'
import ConfirmDeleteDialog from '../components/ConfirmDeleteDialog.vue'

const skills = ref([])
const loading = ref(false)
const filterCategory = ref('all')
const deleteDialog = ref(false)
const deleteTarget = ref(null)

const headers = [
  { title: 'Name', key: 'display_name' },
  { title: 'Category', key: 'category', width: 100 },
  { title: 'System', key: 'is_system', width: 80 },
  { title: 'Shared', key: 'is_shared', width: 80 },
  { title: 'Version', key: 'version', width: 80 },
  { title: 'Actions', key: 'actions', sortable: false, width: 200 },
]

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterCategory.value !== 'all') params.category = filterCategory.value
    const { data } = await api.get('/skills', { params })
    skills.value = data
  } finally {
    loading.value = false
  }
}

watch(filterCategory, load)
onMounted(load)

const share = async (s) => { await api.post(`/skills/${s.id}/share`); load() }
const unshare = async (s) => { await api.post(`/skills/${s.id}/unshare`); load() }
const duplicate = async (s) => { await api.post(`/skills/${s.id}/duplicate`); load() }
const handleDelete = (s) => {
  deleteTarget.value = s
  deleteDialog.value = true
}
const confirmDelete = async () => {
  await api.delete(`/skills/${deleteTarget.value.id}`)
  deleteDialog.value = false
  load()
}
</script>
