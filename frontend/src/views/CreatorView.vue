<template>
  <div>
    <div class="d-flex align-center mb-6">
      <v-icon size="32" class="mr-3" color="primary">mdi-account-heart</v-icon>
      <div>
        <div class="text-h4 font-weight-bold">Creator Profile</div>
        <div class="text-body-2 text-medium-emphasis">
          Information about you — the person who manages the bots. Agents use this context to personalize responses.
        </div>
      </div>
    </div>

    <v-card :loading="loading">
      <v-card-text>
        <v-form @submit.prevent="save">
          <v-row>
            <!-- Name -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="form.name"
                label="Name"
                prepend-inner-icon="mdi-account"
                hint="How should agents refer to you?"
                persistent-hint
              />
            </v-col>

            <!-- Who -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="form.who"
                label="Who you are"
                prepend-inner-icon="mdi-card-account-details"
                hint="Brief description: profession, role, identity"
                persistent-hint
              />
            </v-col>

            <!-- Goals -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.goals"
                label="Goals"
                prepend-inner-icon="mdi-target"
                rows="3"
                auto-grow
                hint="What are your current goals?"
                persistent-hint
              />
            </v-col>

            <!-- Dreams -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.dreams"
                label="Dreams"
                prepend-inner-icon="mdi-weather-night"
                rows="3"
                auto-grow
                hint="What do you dream about?"
                persistent-hint
              />
            </v-col>

            <!-- Skills -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.skills_and_abilities"
                label="Skills & Abilities"
                prepend-inner-icon="mdi-hammer-wrench"
                rows="3"
                auto-grow
                hint="What are your skills and expertise?"
                persistent-hint
              />
            </v-col>

            <!-- Current situation -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.current_situation"
                label="Current Situation"
                prepend-inner-icon="mdi-map-marker"
                rows="3"
                auto-grow
                hint="What's going on in your life right now?"
                persistent-hint
              />
            </v-col>

            <!-- Principles -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.principles"
                label="Principles"
                prepend-inner-icon="mdi-shield-star"
                rows="3"
                auto-grow
                hint="Your core principles and values"
                persistent-hint
              />
            </v-col>

            <!-- Successes -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.successes"
                label="Successes"
                prepend-inner-icon="mdi-trophy"
                rows="3"
                auto-grow
                hint="What have you achieved?"
                persistent-hint
              />
            </v-col>

            <!-- Failures -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.failures"
                label="Failures"
                prepend-inner-icon="mdi-alert-decagram"
                rows="3"
                auto-grow
                hint="What didn't work? Lessons learned."
                persistent-hint
              />
            </v-col>

            <!-- Action history -->
            <v-col cols="12" md="6">
              <v-textarea
                v-model="form.action_history"
                label="Action History"
                prepend-inner-icon="mdi-history"
                rows="3"
                auto-grow
                hint="History of your attempts and actions"
                persistent-hint
              />
            </v-col>

            <!-- Ideas -->
            <v-col cols="12">
              <v-textarea
                v-model="form.ideas"
                label="Ideas"
                prepend-inner-icon="mdi-lightbulb"
                rows="4"
                auto-grow
                hint="Your ideas, plans, thoughts"
                persistent-hint
              />
            </v-col>
          </v-row>

          <div class="d-flex justify-end mt-4 ga-3">
            <v-btn variant="text" @click="load" :disabled="saving">
              <v-icon start>mdi-refresh</v-icon>
              Reset
            </v-btn>
            <v-btn type="submit" color="primary" :loading="saving" size="large">
              <v-icon start>mdi-content-save</v-icon>
              Save
            </v-btn>
          </div>
        </v-form>
      </v-card-text>
    </v-card>

    <v-snackbar v-model="snackbar" :color="snackColor" timeout="3000">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'

const loading = ref(false)
const saving = ref(false)
const snackbar = ref(false)
const snackColor = ref('success')
const snackText = ref('')

const form = ref({
  name: '',
  who: '',
  goals: '',
  dreams: '',
  skills_and_abilities: '',
  current_situation: '',
  principles: '',
  successes: '',
  failures: '',
  action_history: '',
  ideas: '',
})

function showSnack(text, color = 'success') {
  snackText.value = text
  snackColor.value = color
  snackbar.value = true
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/creator')
    Object.keys(form.value).forEach(key => {
      form.value[key] = data[key] || ''
    })
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
