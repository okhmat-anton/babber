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
      <v-tab value="ideas" rounded="lg" @click="navigateTab('ideas')">
        <v-icon start size="18" color="amber-lighten-1">mdi-lightbulb-on</v-icon>
        Ideas
        <v-badge v-if="form.ideas.length" :content="form.ideas.length" color="amber-darken-2" inline class="ml-1" />
      </v-tab>
      <v-tab value="notes" rounded="lg" @click="navigateTab('notes')">
        <v-icon start size="18" color="teal">mdi-note-text</v-icon>
        Notes
        <v-badge v-if="form.notes.length" :content="form.notes.length" color="teal" inline class="ml-1" />
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
            <v-btn color="amber-darken-2" variant="flat" @click="addGoal" prepend-icon="mdi-plus">
              Add First Goal
            </v-btn>
          </div>

          <!-- Goals List -->
          <template v-else>
            <div class="d-flex justify-end mb-4">
              <v-btn variant="tonal" color="amber-darken-2" size="small" @click="addGoal" prepend-icon="mdi-plus">
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
                  <v-card variant="flat" class="section-card goal-card" :class="{ 'item-completed': goal.completed, 'item-no-context': goal.in_context === false }">
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
                        />
                        <div class="drag-handle mr-2 mt-2" title="Drag to reorder">
                          <v-icon size="18" color="grey">mdi-drag-vertical</v-icon>
                        </div>
                        <div class="flex-grow-1">
                          <div class="d-flex align-center mb-2 ga-2">
                            <v-text-field
                              v-model="goal.title"
                              variant="plain"
                              density="compact"
                              hide-details
                              placeholder="Goal title..."
                              class="goal-title-field"
                            />
                            <v-chip
                              :color="priorityColor(goal.priority)"
                              size="x-small"
                              variant="tonal"
                              class="priority-chip"
                              @click="cyclePriority(goal)"
                            >
                              {{ priorityOptions.find(o => o.value === goal.priority)?.title || 'Medium' }}
                            </v-chip>
                          </div>
                          <v-row dense>
                            <v-col cols="12" sm="8">
                              <v-textarea
                                v-model="goal.description"
                                variant="outlined"
                                density="compact"
                                rows="2"
                                auto-grow
                                hide-details
                                placeholder="Description..."
                              />
                            </v-col>
                            <v-col cols="12" sm="4">
                              <v-text-field
                                v-model="goal.target_date"
                                label="Target date"
                                type="date"
                                variant="outlined"
                                density="compact"
                                hide-details
                              />
                            </v-col>
                          </v-row>
                        </div>
                        <div class="d-flex flex-column ml-3 ga-1 mt-1">
                          <v-btn icon size="x-small" variant="tonal" :color="goal.in_context !== false ? 'info' : 'grey'" @click="goal.in_context = !goal.in_context" :title="goal.in_context !== false ? 'In context — click to exclude' : 'Excluded from context — click to include'">
                            <v-icon size="14">{{ goal.in_context !== false ? 'mdi-brain' : 'mdi-brain-off' }}</v-icon>
                          </v-btn>
                          <v-btn icon size="x-small" variant="tonal" color="primary" @click="addSubGoal(gi)" title="Add sub-goal">
                            <v-icon size="14">mdi-plus</v-icon>
                          </v-btn>
                          <v-btn icon size="x-small" variant="text" color="grey" @click="removeGoal(gi)" title="Remove">
                            <v-icon size="14">mdi-close</v-icon>
                          </v-btn>
                        </div>
                      </div>

                      <!-- Sub-goals -->
                      <div v-if="goal.children && goal.children.length" class="mt-4 ml-6">
                        <draggable
                          v-model="goal.children"
                          item-key="id"
                          handle=".drag-handle"
                          animation="200"
                          ghost-class="drag-ghost"
                        >
                          <template #item="{ element: sub, index: si }">
                            <div class="mb-3">
                              <v-card variant="outlined" class="sub-card">
                                <v-card-text class="pa-3">
                                  <div class="d-flex align-start">
                                    <div class="drag-handle mr-1 mt-2" title="Drag to reorder">
                                      <v-icon size="14" color="grey">mdi-drag-vertical</v-icon>
                                    </div>
                                    <v-icon size="14" color="grey" class="mt-2 mr-2">mdi-subdirectory-arrow-right</v-icon>
                                    <div class="flex-grow-1">
                                      <v-text-field
                                        v-model="sub.title"
                                        variant="plain"
                                        density="compact"
                                        hide-details
                                        placeholder="Sub-goal..."
                                        class="sub-title-field mb-1"
                                      />
                                      <v-row dense>
                                        <v-col cols="12" sm="8">
                                          <v-textarea
                                            v-model="sub.description"
                                            variant="outlined"
                                            density="compact"
                                            rows="1"
                                            auto-grow
                                            hide-details
                                            placeholder="Description..."
                                          />
                                        </v-col>
                                        <v-col cols="12" sm="4">
                                          <v-text-field
                                            v-model="sub.target_date"
                                            type="date"
                                            variant="outlined"
                                            density="compact"
                                            hide-details
                                          />
                                        </v-col>
                                      </v-row>
                                    </div>
                                    <v-btn icon size="x-small" variant="text" color="grey" class="ml-2" @click="removeSubGoal(gi, si)">
                                      <v-icon size="14">mdi-close</v-icon>
                                    </v-btn>
                                  </div>
                                </v-card-text>
                              </v-card>
                            </div>
                          </template>
                        </draggable>
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

        <!-- ══════════ TAB: Ideas ══════════ -->
        <v-window-item value="ideas">
          <!-- Empty State -->
          <div v-if="!form.ideas.length" class="empty-state">
            <div class="empty-state-icon yellow">
              <v-icon size="48" color="amber-lighten-1">mdi-lightbulb-on</v-icon>
            </div>
            <div class="text-h6 mt-4">No ideas yet</div>
            <div class="text-body-2 text-medium-emphasis mt-1 mb-5">Capture your ideas so agents can help you develop them</div>
            <v-btn color="amber-darken-2" variant="flat" @click="addIdea" prepend-icon="mdi-plus">
              Add First Idea
            </v-btn>
          </div>

          <template v-else>
            <div class="d-flex justify-end mb-4">
              <v-btn variant="tonal" color="amber-darken-2" size="small" @click="addIdea" prepend-icon="mdi-plus">
                Add Idea
              </v-btn>
            </div>

            <draggable
              v-model="form.ideas"
              item-key="id"
              handle=".drag-handle"
              animation="200"
              ghost-class="drag-ghost"
            >
              <template #item="{ element: idea, index: ii }">
                <div class="mb-4">
                  <v-card variant="flat" class="section-card goal-card" :class="{ 'item-completed': idea.completed, 'item-no-context': idea.in_context === false }">
                    <div class="card-accent card-accent--yellow" />
                    <v-card-text class="pa-5 pl-7">
                      <div class="d-flex align-start">
                        <v-checkbox
                          v-model="idea.completed"
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
                              v-model="idea.title"
                              variant="plain"
                              density="compact"
                              hide-details
                              placeholder="Idea title..."
                              class="goal-title-field"
                            />
                            <v-chip
                              :color="priorityColor(idea.priority)"
                              size="x-small"
                              variant="tonal"
                              class="priority-chip"
                              @click="cyclePriority(idea)"
                            >
                              {{ priorityOptions.find(o => o.value === idea.priority)?.title || 'Medium' }}
                            </v-chip>
                          </div>
                          <v-textarea
                            v-model="idea.description"
                            variant="outlined"
                            density="compact"
                            rows="2"
                            auto-grow
                            hide-details
                            placeholder="Describe your idea..."
                          />
                        </div>
                        <div class="d-flex flex-column ml-3 ga-1 mt-1">
                          <v-btn icon size="x-small" variant="tonal" :color="idea.in_context !== false ? 'info' : 'grey'" @click="idea.in_context = !idea.in_context" :title="idea.in_context !== false ? 'In context — click to exclude' : 'Excluded from context — click to include'">
                            <v-icon size="14">{{ idea.in_context !== false ? 'mdi-brain' : 'mdi-brain-off' }}</v-icon>
                          </v-btn>
                          <v-btn icon size="x-small" variant="text" color="grey" @click="removeIdea(ii)">
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

        <!-- ══════════ TAB: Notes ══════════ -->
        <v-window-item value="notes">
          <!-- Empty State -->
          <div v-if="!form.notes.length" class="empty-state">
            <div class="empty-state-icon teal">
              <v-icon size="48" color="teal">mdi-note-text</v-icon>
            </div>
            <div class="text-h6 mt-4">No notes yet</div>
            <div class="text-body-2 text-medium-emphasis mt-1 mb-5">Write down thoughts, reminders, or context for your agents</div>
            <v-btn color="teal" variant="flat" @click="addNote" prepend-icon="mdi-plus">
              Add First Note
            </v-btn>
          </div>

          <template v-else>
            <div class="d-flex justify-end mb-4">
              <v-btn variant="tonal" color="teal" size="small" @click="addNote" prepend-icon="mdi-plus">
                Add Note
              </v-btn>
            </div>

            <div v-for="(note, ni) in form.notes" :key="note.id" class="mb-4">
              <v-card variant="flat" class="section-card goal-card" :class="{ 'item-completed': note.completed, 'item-no-context': note.in_context === false }">
                <div class="card-accent card-accent--teal" />
                <v-card-text class="pa-5 pl-7">
                  <div class="d-flex align-start">
                    <v-checkbox
                      v-model="note.completed"
                      density="compact"
                      hide-details
                      color="success"
                      class="mr-1 mt-1 flex-shrink-0"
                      title="Mark as completed"
                    />
                    <div class="flex-grow-1">
                      <v-text-field
                        v-model="note.title"
                        variant="plain"
                        density="compact"
                        hide-details
                        placeholder="Note title..."
                        class="goal-title-field mb-2"
                      />
                      <v-textarea
                        v-model="note.content"
                        variant="outlined"
                        density="compact"
                        rows="3"
                        auto-grow
                        hide-details
                        placeholder="Write your note..."
                      />
                    </div>
                    <div class="d-flex flex-column ml-3 ga-1 mt-1">
                      <v-btn icon size="x-small" variant="tonal" :color="note.in_context !== false ? 'info' : 'grey'" @click="note.in_context = !note.in_context" :title="note.in_context !== false ? 'In context — click to exclude' : 'Excluded from context — click to include'">
                        <v-icon size="14">{{ note.in_context !== false ? 'mdi-brain' : 'mdi-brain-off' }}</v-icon>
                      </v-btn>
                      <v-btn icon size="x-small" variant="text" color="grey" @click="removeNote(ni)" title="Remove">
                        <v-icon size="14">mdi-close</v-icon>
                      </v-btn>
                    </div>
                  </div>
                </v-card-text>
              </v-card>
            </div>
          </template>
        </v-window-item>

      </v-window>
    </v-form>

    <v-snackbar v-model="snackbar" :color="snackColor" timeout="3000">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import api from '../api'

const route = useRoute()
const router = useRouter()

const tabFromRoute = () => {
  const path = route.path
  if (path.startsWith('/creator/goals')) return 'goals'
  if (path.startsWith('/creator/dreams')) return 'dreams'
  if (path.startsWith('/creator/ideas')) return 'ideas'
  if (path.startsWith('/creator/notes')) return 'notes'
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

function priorityColor(p) {
  return priorityOptions.find(o => o.value === p)?.color || 'warning'
}

const form = ref({
  name: '',
  who: '',
  goals: [],
  dreams: [],
  skills_and_abilities: '',
  current_situation: '',
  principles: '',
  successes: '',
  failures: '',
  action_history: '',
  ideas: [],
  notes: [],
})

const tabPaths = {
  profile: '/creator',
  goals: '/creator/goals',
  dreams: '/creator/dreams',
  ideas: '/creator/ideas',
  notes: '/creator/notes',
}

function navigateTab(val) {
  const path = tabPaths[val]
  if (path && route.path !== path) router.push(path)
}

watch(() => route.path, () => {
  tab.value = tabFromRoute()
})

// ── Goal helpers ──
function addGoal() {
  form.value.goals.push({ id: uid(), title: '', description: '', target_date: null, priority: 1, children: [] })
}
function removeGoal(i) {
  form.value.goals.splice(i, 1)
}
function addSubGoal(gi) {
  if (!form.value.goals[gi].children) form.value.goals[gi].children = []
  form.value.goals[gi].children.push({ id: uid(), title: '', description: '', target_date: null, children: [] })
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

// ── Idea helpers ──
function addIdea() {
  form.value.ideas.push({ id: uid(), title: '', description: '', priority: 1 })
}
function removeIdea(i) {
  form.value.ideas.splice(i, 1)
}

// ── Priority helper ──
function cyclePriority(item) {
  item.priority = ((item.priority ?? 0) + 1) % 3
}

// ── Note helpers ──
function addNote() {
  form.value.notes.push({ id: uid(), title: '', content: '', created_at: new Date().toISOString() })
}
function removeNote(i) {
  form.value.notes.splice(i, 1)
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
    form.value.skills_and_abilities = data.skills_and_abilities || ''
    form.value.current_situation = data.current_situation || ''
    form.value.principles = data.principles || ''
    form.value.successes = data.successes || ''
    form.value.failures = data.failures || ''
    form.value.action_history = data.action_history || ''
    form.value.ideas = Array.isArray(data.ideas) ? data.ideas : []
    form.value.notes = Array.isArray(data.notes) ? data.notes : []
    form.value.goals.forEach((g, i) => { if (!g.children) g.children = []; if (g.priority == null) g.priority = 1 })
    form.value.dreams.forEach((d, i) => { if (d.priority == null) d.priority = 1 })
    form.value.ideas.forEach((d, i) => { if (d.priority == null) d.priority = 1 })
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
