<template>
  <div class="creator-page">
    <!-- Header -->
    <div class="creator-header mb-8">
      <div class="d-flex align-center">
        <div class="header-avatar mr-4">
          <v-avatar size="56" color="primary" variant="tonal">
            <v-icon size="28">mdi-account-heart</v-icon>
          </v-avatar>
        </div>
        <div>
          <div class="text-h5 font-weight-bold">{{ form.name || 'Creator Profile' }}</div>
          <div class="text-body-2 text-medium-emphasis mt-1">
            Your personal context that agents use to personalize their behavior
          </div>
        </div>
        <v-spacer />
        <v-btn
          color="primary"
          :loading="saving"
          @click="save"
          variant="flat"
        >
          <v-icon start size="18">mdi-content-save</v-icon>
          Save
        </v-btn>
      </div>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="tab" color="primary" class="creator-tabs mb-6" density="comfortable">
      <v-tab value="profile" rounded="lg" @click="navigateTab('profile')">
        <v-icon start size="18">mdi-account</v-icon>
        Profile
      </v-tab>
      <v-tab value="goals" rounded="lg" @click="navigateTab('goals')">
        <v-icon start size="18" color="amber">mdi-flag-variant</v-icon>
        Goals
        <v-badge v-if="form.goals.length" :content="form.goals.length" color="amber" inline class="ml-1" />
      </v-tab>
      <v-tab value="dreams" rounded="lg" @click="navigateTab('dreams')">
        <v-icon start size="18" color="deep-purple-lighten-2">mdi-creation</v-icon>
        Dreams
        <v-badge v-if="form.dreams.length" :content="form.dreams.length" color="deep-purple" inline class="ml-1" />
      </v-tab>
      <v-tab value="cities" rounded="lg" @click="navigateTab('cities')">
        <v-icon start size="18" color="light-blue">mdi-city-variant</v-icon>
        Cities
        <v-badge v-if="form.cities.length" :content="form.cities.length" color="light-blue" inline class="ml-1" />
      </v-tab>
    </v-tabs>

    <!-- Content -->
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <v-form @submit.prevent="save">
      <v-window v-model="tab">

        <!-- ══════════ TAB: Profile ══════════ -->
        <v-window-item value="profile">
          <div class="profile-grid">

            <!-- Identity Section -->
            <div class="section-block">
              <div class="section-label">
                <v-icon size="16" class="mr-2" color="primary">mdi-account-circle</v-icon>
                Identity
              </div>
              <v-card variant="flat" class="section-card">
                <v-card-text class="pa-5">
                  <v-text-field
                    v-model="form.name"
                    label="Name"
                    variant="outlined"
                    density="compact"
                    hide-details
                    placeholder="How should agents call you?"
                    class="mb-5"
                  />
                  <v-textarea
                    v-model="form.who"
                    label="Who you are"
                    variant="outlined"
                    density="compact"
                    rows="4"
                    auto-grow
                    hide-details
                    placeholder="Brief description: profession, role, identity..."
                  />
                </v-card-text>
              </v-card>
            </div>

            <!-- Strengths Section -->
            <div class="section-block">
              <div class="section-label">
                <v-icon size="16" class="mr-2" color="teal">mdi-arm-flex</v-icon>
                Strengths
              </div>
              <v-card variant="flat" class="section-card">
                <v-card-text class="pa-5">
                  <v-textarea
                    v-model="form.skills_and_abilities"
                    label="Skills & Abilities"
                    variant="outlined"
                    density="compact"
                    rows="4"
                    auto-grow
                    hide-details
                    placeholder="Your skills, expertise, and capabilities..."
                    class="mb-5"
                  />
                  <v-textarea
                    v-model="form.principles"
                    label="Principles & Values"
                    variant="outlined"
                    density="compact"
                    rows="4"
                    auto-grow
                    hide-details
                    placeholder="Your core principles and values..."
                  />
                </v-card-text>
              </v-card>
            </div>

            <!-- Situation Section -->
            <div class="section-block">
              <div class="section-label">
                <v-icon size="16" class="mr-2" color="blue">mdi-compass</v-icon>
                Current Context
              </div>
              <v-card variant="flat" class="section-card">
                <v-card-text class="pa-5">
                  <v-textarea
                    v-model="form.current_situation"
                    label="Current Situation"
                    variant="outlined"
                    density="compact"
                    rows="4"
                    auto-grow
                    hide-details
                    placeholder="What's going on in your life right now..."
                  />
                </v-card-text>
              </v-card>
            </div>

            <!-- Track Record Section -->
            <div class="section-block">
              <div class="section-label">
                <v-icon size="16" class="mr-2" color="amber-darken-1">mdi-chart-timeline-variant</v-icon>
                Track Record
              </div>
              <v-card variant="flat" class="section-card">
                <v-card-text class="pa-5">
                  <v-textarea
                    v-model="form.successes"
                    label="Successes"
                    variant="outlined"
                    density="compact"
                    rows="3"
                    auto-grow
                    hide-details
                    placeholder="What have you achieved?"
                    class="mb-5"
                  />
                  <v-textarea
                    v-model="form.failures"
                    label="Failures & Lessons"
                    variant="outlined"
                    density="compact"
                    rows="3"
                    auto-grow
                    hide-details
                    placeholder="What didn't work? Lessons learned..."
                    class="mb-5"
                  />
                  <v-textarea
                    v-model="form.action_history"
                    label="Action History"
                    variant="outlined"
                    density="compact"
                    rows="3"
                    auto-grow
                    hide-details
                    placeholder="History of your attempts and actions..."
                  />
                </v-card-text>
              </v-card>
            </div>

          </div>
        </v-window-item>

        <!-- ══════════ TAB: Goals ══════════ -->
        <v-window-item value="goals">
          <!-- Empty State -->
          <div v-if="!form.goals.length" class="empty-state">
            <div class="empty-state-icon amber">
              <v-icon size="48" color="amber">mdi-flag-variant</v-icon>
            </div>
            <div class="text-h6 mt-4">No goals yet</div>
            <div class="text-body-2 text-medium-emphasis mt-1 mb-5">Define your goals so agents understand what you're working toward</div>
            <v-btn color="amber-darken-2" variant="flat" @click="openGoalDialog()" prepend-icon="mdi-plus">
              Add First Goal
            </v-btn>
          </div>

          <!-- Goals List -->
          <template v-else>
            <div class="d-flex justify-end mb-4">
              <v-btn variant="tonal" color="amber-darken-2" size="small" @click="openGoalDialog()" prepend-icon="mdi-plus">
                Add Goal
              </v-btn>
            </div>

            <draggable
              v-model="form.goals"
              item-key="id"
              handle=".drag-handle"
              animation="200"
              ghost-class="drag-ghost"
            >
              <template #item="{ element: goal, index: gi }">
                <div class="mb-4">
                  <v-card variant="flat" class="section-card goal-card" :class="{ 'item-completed': goal.completed, 'item-no-context': goal.in_context === false }" @click="openGoalDialog(gi)" style="cursor: pointer;">
                    <div class="card-accent card-accent--amber" />
                    <v-card-text class="pa-5 pl-7">
                      <div class="d-flex align-start">
                        <v-checkbox
                          v-model="goal.completed"
                          density="compact"
                          hide-details
                          color="success"
                          class="mr-1 mt-1 flex-shrink-0"
                          title="Mark as completed"
                          @click.stop
                        />
                        <div class="drag-handle mr-2 mt-2" title="Drag to reorder" @click.stop>
                          <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
                        </div>
                        <div class="flex-grow-1">
                          <div class="d-flex align-center mb-1 ga-2">
                            <span class="text-subtitle-1 font-weight-medium">{{ goal.title || 'Untitled goal' }}</span>
                            <v-chip
                              :color="priorityColor(goal.priority)"
                              size="x-small"
                              variant="tonal"
                            >
                              {{ priorityOptions.find(o => o.value === goal.priority)?.title || 'Medium' }}
                            </v-chip>
                            <v-chip
                              :color="scaleColor(goal.scale)"
                              size="x-small"
                              variant="outlined"
                            >
                              <v-icon start size="10">{{ scaleOptions.find(o => o.value === (goal.scale || 'medium'))?.icon || 'mdi-circle-outline' }}</v-icon>
                              {{ scaleOptions.find(o => o.value === (goal.scale || 'medium'))?.title || 'Medium' }}
                            </v-chip>
                            <v-chip v-if="goal.target_date" size="x-small" variant="tonal" color="blue-grey">
                              <v-icon start size="10">mdi-calendar</v-icon>
                              {{ goal.target_date }}
                            </v-chip>
                          </div>
                          <div v-if="goal.description" class="text-body-2 text-medium-emphasis text-truncate" style="max-width: 600px;">{{ goal.description }}</div>
                          <!-- Sub-goals summary -->
                          <div v-if="goal.children && goal.children.length" class="mt-2">
                            <div v-for="(sub, si) in goal.children" :key="sub.id" class="d-flex align-center ga-1 ml-2 mb-1">
                              <v-icon size="12" color="grey">mdi-subdirectory-arrow-right</v-icon>
                              <v-checkbox
                                v-model="sub.completed"
                                density="compact"
                                hide-details
                                color="success"
                                class="flex-shrink-0"
                                style="max-width: 24px;"
                                @click.stop
                              />
                              <span class="text-body-2" :class="{ 'text-decoration-line-through text-medium-emphasis': sub.completed }">{{ sub.title || 'Untitled' }}</span>
                              <v-chip :color="priorityColor(sub.priority)" size="x-small" variant="tonal">{{ priorityOptions.find(o => o.value === sub.priority)?.title || 'Med' }}</v-chip>
                              <v-chip :color="scaleColor(sub.scale)" size="x-small" variant="outlined">
                                <v-icon start size="10">{{ scaleOptions.find(o => o.value === (sub.scale || 'medium'))?.icon || 'mdi-circle-outline' }}</v-icon>
                                {{ scaleOptions.find(o => o.value === (sub.scale || 'medium'))?.title || 'Med' }}
                              </v-chip>
                            </div>
                          </div>
                        </div>
                        <div class="d-flex flex-column ml-3 ga-1 mt-1">
                          <v-btn icon size="x-small" variant="tonal" :color="goal.in_context !== false ? 'info' : 'grey'" @click.stop="goal.in_context = !goal.in_context" :title="goal.in_context !== false ? 'In context — click to exclude' : 'Excluded from context — click to include'">
                            <v-icon size="14">{{ goal.in_context !== false ? 'mdi-brain' : 'mdi-brain-off' }}</v-icon>
                          </v-btn>
                          <v-btn icon size="x-small" variant="text" color="grey" @click.stop="removeGoal(gi)" title="Remove">
                            <v-icon size="14">mdi-close</v-icon>
                          </v-btn>
                        </div>
                      </div>
                    </v-card-text>
                  </v-card>
                </div>
              </template>
            </draggable>
          </template>
        </v-window-item>

        <!-- ══════════ TAB: Dreams ══════════ -->
        <v-window-item value="dreams">
          <!-- Empty State -->
          <div v-if="!form.dreams.length" class="empty-state">
            <div class="empty-state-icon purple">
              <v-icon size="48" color="deep-purple-lighten-2">mdi-creation</v-icon>
            </div>
            <div class="text-h6 mt-4">No dreams yet</div>
            <div class="text-body-2 text-medium-emphasis mt-1 mb-5">Describe your big-picture vision and aspirations</div>
            <v-btn color="deep-purple" variant="flat" @click="addDream" prepend-icon="mdi-plus">
              Add First Dream
            </v-btn>
          </div>

          <template v-else>
            <div class="d-flex justify-end mb-4">
              <v-btn variant="tonal" color="deep-purple" size="small" @click="addDream" prepend-icon="mdi-plus">
                Add Dream
              </v-btn>
            </div>

            <draggable
              v-model="form.dreams"
              item-key="id"
              handle=".drag-handle"
              animation="200"
              ghost-class="drag-ghost"
            >
              <template #item="{ element: dream, index: di }">
                <div class="mb-4">
                  <v-card variant="flat" class="section-card goal-card" :class="{ 'item-completed': dream.completed, 'item-no-context': dream.in_context === false }">
                    <div class="card-accent card-accent--purple" />
                    <v-card-text class="pa-5 pl-7">
                      <div class="d-flex align-start">
                        <v-checkbox
                          v-model="dream.completed"
                          density="compact"
                          hide-details
                          color="success"
                          class="mr-1 mt-1 flex-shrink-0"
                          title="Mark as completed"
                        />
                        <div class="drag-handle mr-2 mt-2" title="Drag to reorder">
                          <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
                        </div>
                        <div class="flex-grow-1">
                          <div class="d-flex align-center mb-2 ga-2">
                            <v-text-field
                              v-model="dream.title"
                              variant="plain"
                              density="compact"
                              hide-details
                              placeholder="Dream title..."
                              class="goal-title-field"
                            />
                            <v-chip
                              :color="priorityColor(dream.priority)"
                              size="x-small"
                              variant="tonal"
                              class="priority-chip"
                              @click="cyclePriority(dream)"
                            >
                              {{ priorityOptions.find(o => o.value === dream.priority)?.title || 'Medium' }}
                            </v-chip>
                          </div>
                          <v-textarea
                            v-model="dream.description"
                            variant="outlined"
                            density="compact"
                            rows="2"
                            auto-grow
                            hide-details
                            placeholder="Describe your dream..."
                          />
                        </div>
                        <div class="d-flex flex-column ml-3 ga-1 mt-1">
                          <v-btn icon size="x-small" variant="tonal" :color="dream.in_context !== false ? 'info' : 'grey'" @click="dream.in_context = !dream.in_context" :title="dream.in_context !== false ? 'In context — click to exclude' : 'Excluded from context — click to include'">
                            <v-icon size="14">{{ dream.in_context !== false ? 'mdi-brain' : 'mdi-brain-off' }}</v-icon>
                          </v-btn>
                          <v-btn icon size="x-small" variant="text" color="grey" @click="removeDream(di)">
                            <v-icon size="14">mdi-close</v-icon>
                          </v-btn>
                        </div>
                      </div>
                    </v-card-text>
                  </v-card>
                </div>
              </template>
            </draggable>
          </template>
        </v-window-item>

        <!-- ══════════ TAB: Cities ══════════ -->
        <v-window-item value="cities">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4">
            Cities you live in, visit frequently, or are interested in. Used by agents for weather forecasts, travel suggestions, and time zone awareness.
          </v-alert>

          <div class="d-flex justify-end mb-3">
            <v-btn color="light-blue" variant="flat" prepend-icon="mdi-plus" @click="addCity">
              Add City
            </v-btn>
          </div>

          <v-row>
            <v-col v-for="(city, idx) in form.cities" :key="city.id || idx" cols="12" sm="6" md="4" lg="3">
              <v-card variant="outlined" class="fill-height">
                <v-card-text class="pb-2">
                  <div class="d-flex align-center mb-2">
                    <v-icon size="20" class="mr-2" :color="cityTypeColor(city.type)">
                      {{ cityTypeIcon(city.type) }}
                    </v-icon>
                    <v-chip :color="cityTypeColor(city.type)" size="x-small" variant="tonal">{{ city.type }}</v-chip>
                    <v-spacer />
                    <v-btn icon size="x-small" variant="text" color="error" @click="form.cities.splice(idx, 1)">
                      <v-icon size="16">mdi-close</v-icon>
                    </v-btn>
                  </div>
                  <v-text-field
                    v-model="city.name"
                    label="City"
                    variant="outlined"
                    density="compact"
                    hide-details
                    placeholder="Berlin, New York..."
                    class="mb-2"
                  />
                  <v-text-field
                    v-model="city.country"
                    label="Country"
                    variant="outlined"
                    density="compact"
                    hide-details
                    placeholder="Germany, US..."
                    class="mb-2"
                  />
                  <v-select
                    v-model="city.type"
                    :items="cityTypes"
                    item-title="label"
                    item-value="value"
                    label="Type"
                    variant="outlined"
                    density="compact"
                    hide-details
                    class="mb-2"
                  />
                  <v-checkbox
                    v-model="city.in_context"
                    label="Include in agent context"
                    density="compact"
                    hide-details
                    color="primary"
                  />
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <div v-if="!form.cities.length" class="text-center py-8 text-medium-emphasis">
            <v-icon size="48" class="mb-2" color="grey">mdi-city-variant-outline</v-icon>
            <div>No cities added yet. Click "Add City" to get started.</div>
          </div>
        </v-window-item>

      </v-window>
    </v-form>

    <v-snackbar v-model="snackbar" :color="snackColor" timeout="3000">
      {{ snackText }}
    </v-snackbar>

    <!-- Goal Add/Edit Dialog -->
    <v-dialog v-model="goalDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2" color="amber">mdi-flag-variant</v-icon>
          {{ goalDialogIndex === null ? 'New Goal' : 'Edit Goal' }}
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4" style="max-height: 70vh; overflow-y: auto;">
          <v-text-field
            v-model="goalForm.title"
            label="Goal title"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-4"
            autofocus
          />
          <v-textarea
            v-model="goalForm.description"
            label="Description"
            variant="outlined"
            density="compact"
            rows="3"
            auto-grow
            hide-details
            class="mb-4"
          />
          <v-row dense class="mb-4">
            <v-col cols="4">
              <v-select
                v-model="goalForm.priority"
                :items="priorityOptions"
                item-title="title"
                item-value="value"
                label="Priority"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-select
                v-model="goalForm.scale"
                :items="scaleOptions"
                item-title="title"
                item-value="value"
                label="Scale"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-text-field
                v-model="goalForm.target_date"
                label="Target date"
                type="date"
                variant="outlined"
                density="compact"
                hide-details
              />
            </v-col>
          </v-row>

          <!-- Sub-goals -->
          <div class="d-flex align-center mb-3">
            <div class="text-subtitle-2 font-weight-medium">Sub-goals</div>
            <v-spacer />
            <v-btn variant="tonal" size="x-small" color="primary" prepend-icon="mdi-plus" @click="addSubGoalInDialog">Add Sub-goal</v-btn>
          </div>
          <draggable
            v-model="goalForm.children"
            item-key="id"
            handle=".drag-handle"
            animation="200"
            ghost-class="drag-ghost"
          >
            <template #item="{ element: sub, index: si }">
              <v-card variant="outlined" class="mb-3 sub-card">
                <v-card-text class="pa-3">
                  <div class="d-flex align-start">
                    <div class="drag-handle mr-1 mt-2" title="Drag to reorder" @click.stop>
                      <v-icon size="14" color="grey">mdi-drag-vertical</v-icon>
                    </div>
                    <v-icon size="14" color="grey" class="mt-2 mr-2">mdi-subdirectory-arrow-right</v-icon>
                    <div class="flex-grow-1">
                      <v-text-field
                        v-model="sub.title"
                        variant="outlined"
                        density="compact"
                        hide-details
                        placeholder="Sub-goal title..."
                        class="mb-2"
                      />
                      <v-textarea
                        v-model="sub.description"
                        variant="outlined"
                        density="compact"
                        rows="1"
                        auto-grow
                        hide-details
                        placeholder="Description..."
                        class="mb-2"
                      />
                      <v-row dense>
                        <v-col cols="4">
                          <v-select
                            v-model="sub.priority"
                            :items="priorityOptions"
                            item-title="title"
                            item-value="value"
                            label="Priority"
                            variant="outlined"
                            density="compact"
                            hide-details
                          />
                        </v-col>
                        <v-col cols="4">
                          <v-select
                            v-model="sub.scale"
                            :items="scaleOptions"
                            item-title="title"
                            item-value="value"
                            label="Scale"
                            variant="outlined"
                            density="compact"
                            hide-details
                          />
                        </v-col>
                        <v-col cols="4">
                          <v-text-field
                            v-model="sub.target_date"
                            type="date"
                            variant="outlined"
                            density="compact"
                            hide-details
                            label="Target date"
                          />
                        </v-col>
                      </v-row>
                    </div>
                    <v-btn icon size="x-small" variant="text" color="grey" class="ml-2 mt-1" @click="goalForm.children.splice(si, 1)">
                      <v-icon size="14">mdi-close</v-icon>
                    </v-btn>
                  </div>
                </v-card-text>
              </v-card>
            </template>
          </draggable>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="goalDialog = false">Cancel</v-btn>
          <v-btn color="amber-darken-2" variant="flat" @click="saveGoalDialog" :disabled="!goalForm.title?.trim()">
            {{ goalDialogIndex === null ? 'Add Goal' : 'Save' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import api from '../api'

const dataRefreshSignal = inject('dataRefreshSignal', reactive({ type: '', timestamp: 0 }))
watch(() => dataRefreshSignal.timestamp, () => {
  if (dataRefreshSignal.type === 'creator') load()
})

const route = useRoute()
const router = useRouter()

const tabFromRoute = () => {
  const path = route.path
  if (path.startsWith('/creator/goals')) return 'goals'
  if (path.startsWith('/creator/dreams')) return 'dreams'
  if (path.startsWith('/creator/cities')) return 'cities'
  return 'profile'
}

const tab = ref(tabFromRoute())
const loading = ref(false)
const saving = ref(false)
const snackbar = ref(false)
const snackColor = ref('success')
const snackText = ref('')

function uid() {
  return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)
}

const priorityOptions = [
  { value: 0, title: 'High', color: 'error' },
  { value: 1, title: 'Medium', color: 'warning' },
  { value: 2, title: 'Low', color: 'grey' },
]

const scaleOptions = [
  { value: 'big', title: 'Big', icon: 'mdi-arrow-up-bold-circle', color: 'deep-purple' },
  { value: 'medium', title: 'Medium', icon: 'mdi-circle-outline', color: 'blue' },
  { value: 'micro', title: 'Micro', icon: 'mdi-arrow-down-bold-circle', color: 'teal' },
]

function priorityColor(p) {
  return priorityOptions.find(o => o.value === p)?.color || 'warning'
}

function scaleColor(s) {
  return scaleOptions.find(o => o.value === s)?.color || 'blue'
}

function cycleScale(item) {
  const order = ['big', 'medium', 'micro']
  const idx = order.indexOf(item.scale || 'medium')
  item.scale = order[(idx + 1) % order.length]
}

const form = ref({
  name: '',
  who: '',
  goals: [],
  dreams: [],
  cities: [],
  skills_and_abilities: '',
  current_situation: '',
  principles: '',
  successes: '',
  failures: '',
  action_history: '',
})

const cityTypes = [
  { value: 'home', label: 'Home' },
  { value: 'frequent', label: 'Frequent' },
  { value: 'interest', label: 'Interest' },
]

function cityTypeColor(type) {
  return { home: 'green', frequent: 'blue', interest: 'amber' }[type] || 'grey'
}

function cityTypeIcon(type) {
  return { home: 'mdi-home-city', frequent: 'mdi-airplane', interest: 'mdi-map-marker-star' }[type] || 'mdi-city'
}

function addCity() {
  form.value.cities.push({ id: Date.now().toString(), name: '', country: '', type: 'interest', in_context: true })
}

const tabPaths = {
  profile: '/creator',
  goals: '/creator/goals',
  dreams: '/creator/dreams',
  cities: '/creator/cities',
}

function navigateTab(val) {
  const path = tabPaths[val]
  if (path && route.path !== path) router.push(path)
}

watch(() => route.path, () => {
  tab.value = tabFromRoute()
})

// ── Goal dialog ──
const goalDialog = ref(false)
const goalDialogIndex = ref(null)
const goalForm = ref({ id: '', title: '', description: '', target_date: null, priority: 1, scale: 'medium', children: [] })

function openGoalDialog(index = null) {
  if (index !== null && index !== undefined) {
    // Edit existing goal
    goalDialogIndex.value = index
    const g = form.value.goals[index]
    goalForm.value = JSON.parse(JSON.stringify({
      ...g,
      children: (g.children || []).map(c => ({
        ...c,
        priority: c.priority ?? 1,
        scale: c.scale || 'medium',
      })),
    }))
  } else {
    // New goal
    goalDialogIndex.value = null
    goalForm.value = { id: uid(), title: '', description: '', target_date: null, priority: 1, scale: 'medium', children: [] }
  }
  goalDialog.value = true
}

function addSubGoalInDialog() {
  if (!goalForm.value.children) goalForm.value.children = []
  goalForm.value.children.push({ id: uid(), title: '', description: '', target_date: null, priority: 1, scale: 'medium', children: [] })
}

function saveGoalDialog() {
  const data = JSON.parse(JSON.stringify(goalForm.value))
  if (goalDialogIndex.value !== null) {
    // Preserve completed / in_context state from original
    const orig = form.value.goals[goalDialogIndex.value]
    data.completed = orig.completed
    data.in_context = orig.in_context
    form.value.goals[goalDialogIndex.value] = data
  } else {
    data.completed = false
    data.in_context = true
    form.value.goals.push(data)
  }
  goalDialog.value = false
}

function addGoal() {
  openGoalDialog()
}
function removeGoal(i) {
  form.value.goals.splice(i, 1)
}
function addSubGoal(gi) {
  openGoalDialog(gi)
}
function removeSubGoal(gi, si) {
  form.value.goals[gi].children.splice(si, 1)
}

// ── Dream helpers ──
function addDream() {
  form.value.dreams.push({ id: uid(), title: '', description: '', priority: 1 })
}
function removeDream(i) {
  form.value.dreams.splice(i, 1)
}

// ── Priority helper ──
function cyclePriority(item) {
  item.priority = ((item.priority ?? 0) + 1) % 3
}

function showSnack(text, color = 'success') {
  snackText.value = text
  snackColor.value = color
  snackbar.value = true
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/creator')
    form.value.name = data.name || ''
    form.value.who = data.who || ''
    form.value.goals = Array.isArray(data.goals) ? data.goals : []
    form.value.dreams = Array.isArray(data.dreams) ? data.dreams : []
    form.value.cities = Array.isArray(data.cities) ? data.cities : []
    form.value.skills_and_abilities = data.skills_and_abilities || ''
    form.value.current_situation = data.current_situation || ''
    form.value.principles = data.principles || ''
    form.value.successes = data.successes || ''
    form.value.failures = data.failures || ''
    form.value.action_history = data.action_history || ''
    form.value.goals.forEach((g, i) => {
      if (!g.children) g.children = []
      if (g.priority == null) g.priority = 1
      if (!g.scale) g.scale = 'medium'
      g.children.forEach(c => {
        if (c.priority == null) c.priority = 1
        if (!c.scale) c.scale = 'medium'
        if (!c.children) c.children = []
      })
    })
    form.value.dreams.forEach((d, i) => { if (d.priority == null) d.priority = 1 })
    form.value.cities.forEach(c => { if (c.in_context == null) c.in_context = true })
  } catch (e) {
    console.error('Failed to load creator profile:', e)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await api.put('/creator', form.value)
    showSnack('Profile saved')
  } catch (e) {
    showSnack('Failed to save: ' + (e.response?.data?.detail || e.message), 'error')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.creator-page {
  max-width: 900px;
}

/* Section blocks */
.section-block {
  margin-bottom: 24px;
}

.section-label {
  display: flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(var(--v-theme-on-surface), 0.5);
  margin-bottom: 8px;
  padding-left: 4px;
}

.section-card {
  background: rgba(var(--v-theme-on-surface), 0.03) !important;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06) !important;
  border-radius: 12px !important;
}

/* Goal/Dream/Idea cards */
.goal-card {
  position: relative;
  overflow: hidden;
}

.card-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 3px 0 0 3px;
}

.card-accent--amber {
  background: rgb(var(--v-theme-warning));
}

.card-accent--purple {
  background: #b39ddb;
}

.card-accent--yellow {
  background: #ffd54f;
}

.card-accent--teal {
  background: #4db6ac;
}

.goal-title-field :deep(input) {
  font-size: 16px;
  font-weight: 600;
}

.sub-title-field :deep(input) {
  font-size: 14px;
  font-weight: 500;
}

.sub-card {
  border-radius: 8px !important;
  border-color: rgba(var(--v-theme-on-surface), 0.08) !important;
}

/* Empty states */
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
}

.empty-state-icon.amber {
  background: rgba(255, 179, 0, 0.1);
}

.empty-state-icon.purple {
  background: rgba(149, 117, 205, 0.1);
}

.empty-state-icon.yellow {
  background: rgba(255, 213, 79, 0.1);
}

.empty-state-icon.teal {
  background: rgba(77, 182, 172, 0.1);
}

/* Tabs styling */
.creator-tabs :deep(.v-tab) {
  text-transform: none;
  font-weight: 500;
  letter-spacing: 0;
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
}

.priority-chip {
  cursor: pointer;
  font-size: 10px !important;
  font-weight: 600;
  letter-spacing: 0.04em;
  min-width: 56px;
  justify-content: center;
  flex-shrink: 0;
}

/* Completed / Context states */
.item-completed {
  opacity: 0.5;
}

.item-completed .goal-title-field :deep(input) {
  text-decoration: line-through;
}

.item-no-context {
  border-left: 2px dashed rgba(var(--v-theme-on-surface), 0.15) !important;
}

.item-no-context .card-accent {
  opacity: 0.25;
}
</style>
