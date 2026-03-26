<template>
  <div>
    <div class="d-flex align-center mb-4">
      <v-chip variant="tonal" size="small">
        {{ enabledCount }} / {{ addons.length }} enabled
      </v-chip>
    </div>

    <v-progress-linear v-if="loading" indeterminate class="mb-4" />

    <v-alert v-if="errorMsg" type="error" variant="tonal" class="mb-4" closable @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <v-row v-if="!loading && addons.length">
      <v-col v-for="addon in addons" :key="addon.id" cols="12" sm="6" md="4" lg="3">
        <v-card
          :class="{ 'addon-disabled': !addon.enabled }"
          variant="outlined"
          rounded="lg"
        >
          <v-card-item>
            <template #prepend>
              <v-avatar :color="addon.enabled ? 'primary' : 'grey'" size="42" rounded="lg">
                <v-icon :icon="addon.icon || 'mdi-puzzle'" />
              </v-avatar>
            </template>
            <v-card-title class="text-body-1 font-weight-bold">{{ addon.name }}</v-card-title>
            <v-card-subtitle class="text-caption">v{{ addon.version || '1.0.0' }}</v-card-subtitle>
          </v-card-item>

          <v-card-text class="pt-0">
            <p class="text-body-2 text-medium-emphasis mb-3" style="min-height: 40px">
              {{ addon.description || 'No description' }}
            </p>

            <!-- Stats -->
            <div class="d-flex ga-3 flex-wrap mb-3">
              <v-chip v-if="addon.skills && addon.skills.length" size="x-small" variant="tonal" color="info">
                <v-icon start size="12">mdi-cog</v-icon>
                {{ addon.skills.length }} skills
              </v-chip>
              <v-chip v-if="addon.protocols && addon.protocols.length" size="x-small" variant="tonal" color="purple">
                <v-icon start size="12">mdi-brain</v-icon>
                {{ addon.protocols.length }} protocols
              </v-chip>
              <v-chip v-if="addon.settings && addon.settings.length" size="x-small" variant="tonal" color="warning">
                <v-icon start size="12">mdi-tune</v-icon>
                {{ addon.settings.length }} settings
              </v-chip>
            </div>

            <!-- Skills details -->
            <div v-if="addon.skills_details && addon.skills_details.length" class="mb-3">
              <div class="text-caption font-weight-bold text-medium-emphasis mb-1">Skills:</div>
              <div
                v-for="skill in addon.skills_details"
                :key="skill.name"
                class="mb-2 pa-2 rounded"
                style="background: rgba(var(--v-theme-on-surface), 0.04);"
              >
                <div class="d-flex align-center mb-1">
                  <v-icon size="14" color="info" class="mr-1">mdi-puzzle</v-icon>
                  <span class="text-caption font-weight-bold">{{ skill.display_name || skill.name }}</span>
                  <v-chip v-if="skill.category" size="x-small" variant="outlined" class="ml-2">{{ skill.category }}</v-chip>
                </div>
                <div class="text-caption text-medium-emphasis">{{ skill.description }}</div>
              </div>
            </div>

            <!-- Settings preview -->
            <div v-if="addon.settings && addon.settings.length && addon.enabled" class="mb-2">
              <div
                v-for="s in addon.settings"
                :key="s.key"
                class="d-flex align-center text-caption text-medium-emphasis mb-1"
              >
                <v-icon size="14" class="mr-1" :color="settingsStore.systemSettings[s.key]?.value ? 'success' : 'grey'">
                  {{ settingsStore.systemSettings[s.key]?.value ? 'mdi-check-circle' : 'mdi-circle-outline' }}
                </v-icon>
                {{ s.key.replace(addon.id + '_', '') }}
              </div>
            </div>
          </v-card-text>

          <v-divider />

          <v-card-actions class="flex-column align-stretch pa-3">
            <div class="d-flex align-center mb-2">
              <v-switch
                :model-value="addon.enabled"
                color="primary"
                density="compact"
                hide-details
                :label="addon.enabled ? 'Enabled' : 'Disabled'"
                :loading="toggling === addon.id"
                @update:model-value="toggleAddon(addon)"
              />
              <v-spacer />
              <v-btn
                v-if="addon.enabled && addon.route"
                :to="addon.route.path"
                size="small"
                variant="tonal"
                color="primary"
              >
                Open
                <v-icon end size="16">mdi-arrow-right</v-icon>
              </v-btn>
            </div>
            <v-select
              v-if="addon.enabled"
              :model-value="addon.menu_mode || 'direct'"
              :items="menuModeOptions"
              item-title="title"
              item-value="value"
              label="Menu Position"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="v => saveMenuMode(addon, v)"
            />
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <v-alert v-if="!loading && !addons.length" type="info" variant="tonal">
      No addons found. Place addon folders in the <code>addons/</code> directory at the project root.
    </v-alert>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000" location="bottom right">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { useSettingsStore } from '../stores/settings'

const settingsStore = useSettingsStore()

const addons = ref([])
const loading = ref(false)
const errorMsg = ref(null)
const toggling = ref(null)

const snack = ref(false)
const snackText = ref('')
const snackColor = ref('success')

const enabledCount = computed(() => addons.value.filter(a => a.enabled).length)

const menuModeOptions = [
  { title: 'Primary Menu (Direct)', value: 'direct' },
  { title: 'Secondary Menu (Grouped)', value: 'secondary' }
]

async function saveMenuMode(addon, value) {
  try {
    await settingsStore.updateSystemSetting(`addon_${addon.id}_menu_mode`, value)
    addon.menu_mode = value
    snackText.value = `${addon.name} menu position updated`
    snackColor.value = 'success'
    snack.value = true
  } catch (e) {
    errorMsg.value = `Failed to update menu position for ${addon.name}`
    console.error(e)
  }
}

async function fetchAddons() {
  loading.value = true
  errorMsg.value = null
  try {
    const { data } = await api.get('/addons')
    addons.value = data
  } catch (e) {
    errorMsg.value = 'Failed to load addons'
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function toggleAddon(addon) {
  toggling.value = addon.id
  try {
    const newEnabled = !addon.enabled
    await api.post(`/addons/${addon.id}/toggle`, { enabled: newEnabled })
    addon.enabled = newEnabled
    snackText.value = `${addon.name} ${newEnabled ? 'enabled' : 'disabled'}`
    snackColor.value = newEnabled ? 'success' : 'warning'
    snack.value = true
  } catch (e) {
    errorMsg.value = `Failed to toggle ${addon.name}`
    console.error(e)
  } finally {
    toggling.value = null
  }
}

onMounted(() => {
  fetchAddons()
  settingsStore.fetchSystemSettings()
})
</script>

<style scoped>
.addon-disabled {
  opacity: 0.6;
}
</style>
