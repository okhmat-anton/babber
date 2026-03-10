<template>
  <div>
    <div class="d-flex align-center mb-6">
      <v-btn icon="mdi-arrow-left" variant="text" @click="$router.back()" />
      <div class="text-h4 font-weight-bold ml-2">{{ isEdit ? 'Edit Task' : 'New Task' }}</div>
    </div>

    <v-card>
      <v-card-text>
        <v-form @submit.prevent="handleSubmit">
          <v-text-field v-model="form.title" label="Title" required />
          <v-textarea v-model="form.description" label="Description / Prompt" rows="4" />
          <v-row>
            <v-col cols="4">
              <v-select v-model="form.type" :items="['one_time','recurring','trigger']" label="Type" />
            </v-col>
            <v-col cols="4">
              <v-select v-model="form.priority" :items="['low','normal','high','critical']" label="Priority" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model.number="form.timeout" label="Timeout (sec)" type="number" />
            </v-col>
          </v-row>

          <v-switch
            v-model="form.is_user_task"
            label="User task (agents can read but not execute)"
            color="amber"
            hide-details
            class="mb-4"
          />

          <v-combobox
            v-model="form.tags"
            :items="existingTags"
            label="Tags"
            multiple
            chips
            closable-chips
            density="compact"
            hide-details
            class="mb-4"
          />

          <!-- Schedule builder -->
          <v-card v-if="form.type !== 'one_time'" variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 pb-0">
              <v-icon class="mr-2" size="small">mdi-clock-outline</v-icon>
              Schedule
            </v-card-title>
            <v-card-text>
              <v-row>
                <v-col cols="12" sm="4">
                  <v-select
                    v-model="sched.frequency"
                    :items="frequencyOptions"
                    label="Frequency"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>

                <!-- Every N minutes -->
                <v-col v-if="sched.frequency === 'every_n_min'" cols="12" sm="4">
                  <v-select
                    v-model="sched.interval"
                    :items="minuteIntervals"
                    label="Every"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>

                <!-- Every N hours -->
                <v-col v-if="sched.frequency === 'every_n_hour'" cols="12" sm="4">
                  <v-select
                    v-model="sched.hourInterval"
                    :items="hourIntervals"
                    label="Every"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col v-if="sched.frequency === 'every_n_hour'" cols="12" sm="4">
                  <v-select
                    v-model="sched.minute"
                    :items="minuteOptions"
                    label="At minute"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>

                <!-- Daily -->
                <v-col v-if="sched.frequency === 'daily'" cols="6" sm="4">
                  <v-select
                    v-model="sched.hour"
                    :items="hourOptions"
                    label="Hour"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col v-if="sched.frequency === 'daily'" cols="6" sm="4">
                  <v-select
                    v-model="sched.minute"
                    :items="minuteOptions"
                    label="Minute"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>

                <!-- Weekly -->
                <v-col v-if="sched.frequency === 'weekly'" cols="12" sm="4">
                  <v-select
                    v-model="sched.weekday"
                    :items="weekdayOptions"
                    label="Day of week"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col v-if="sched.frequency === 'weekly'" cols="6" sm="4">
                  <v-select
                    v-model="sched.hour"
                    :items="hourOptions"
                    label="Hour"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col v-if="sched.frequency === 'weekly'" cols="6" sm="4">
                  <v-select
                    v-model="sched.minute"
                    :items="minuteOptions"
                    label="Minute"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>

                <!-- Monthly -->
                <v-col v-if="sched.frequency === 'monthly'" cols="12" sm="3">
                  <v-select
                    v-model="sched.dayOfMonth"
                    :items="dayOfMonthOptions"
                    label="Day"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col v-if="sched.frequency === 'monthly'" cols="6" sm="3">
                  <v-select
                    v-model="sched.hour"
                    :items="hourOptions"
                    label="Hour"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col v-if="sched.frequency === 'monthly'" cols="6" sm="3">
                  <v-select
                    v-model="sched.minute"
                    :items="minuteOptions"
                    label="Minute"
                    item-title="text"
                    item-value="value"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
              </v-row>

              <!-- Preview -->
              <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                <strong>Cron:</strong> {{ form.schedule || '—' }}
                <span class="ml-3 text-caption">{{ scheduleDescription }}</span>
              </v-alert>
            </v-card-text>
          </v-card>

          <div class="d-flex mt-4">
            <v-btn type="submit" color="primary" :loading="saving">{{ isEdit ? 'Update' : 'Create' }}</v-btn>
            <v-btn class="ml-3" variant="outlined" @click="$router.back()">Cancel</v-btn>
          </div>
        </v-form>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTasksStore } from '../stores/tasks'
import api from '../api'

const route = useRoute()
const router = useRouter()
const store = useTasksStore()
const saving = ref(false)
const isEdit = computed(() => !!route.params.id)
const agentId = computed(() => route.query.agent_id || null)

const form = ref({
  title: '', description: '', type: 'one_time', priority: 'normal', schedule: null, max_retries: 3, timeout: 300, is_user_task: false, tags: [],
})

const existingTags = computed(() => {
  const tags = new Set()
  store.tasks.forEach(t => (t.tags || []).forEach(tag => tags.add(tag)))
  return [...tags].sort()
})

// ── Schedule builder ──────────────────────────────
const sched = ref({
  frequency: 'every_n_min',
  interval: 5,
  hourInterval: 2,
  minute: 0,
  hour: 9,
  weekday: 1,
  dayOfMonth: 1,
})

const frequencyOptions = [
  { text: 'Every N minutes', value: 'every_n_min' },
  { text: 'Every N hours', value: 'every_n_hour' },
  { text: 'Daily', value: 'daily' },
  { text: 'Weekly', value: 'weekly' },
  { text: 'Monthly', value: 'monthly' },
]

const minuteIntervals = [
  { text: 'Every 1 minute',  value: 1 },
  { text: 'Every 2 minutes', value: 2 },
  { text: 'Every 5 minutes', value: 5 },
  { text: 'Every 10 minutes', value: 10 },
  { text: 'Every 15 minutes', value: 15 },
  { text: 'Every 20 minutes', value: 20 },
  { text: 'Every 30 minutes', value: 30 },
]

const hourIntervals = [
  { text: 'Every 1 hour',  value: 1 },
  { text: 'Every 2 hours', value: 2 },
  { text: 'Every 3 hours', value: 3 },
  { text: 'Every 4 hours', value: 4 },
  { text: 'Every 6 hours', value: 6 },
  { text: 'Every 8 hours', value: 8 },
  { text: 'Every 12 hours', value: 12 },
]

const minuteOptions = Array.from({ length: 60 }, (_, i) => ({
  text: String(i).padStart(2, '0'), value: i,
}))

const hourOptions = Array.from({ length: 24 }, (_, i) => ({
  text: String(i).padStart(2, '0') + ':00', value: i,
}))

const weekdayOptions = [
  { text: 'Monday', value: 1 },
  { text: 'Tuesday', value: 2 },
  { text: 'Wednesday', value: 3 },
  { text: 'Thursday', value: 4 },
  { text: 'Friday', value: 5 },
  { text: 'Saturday', value: 6 },
  { text: 'Sunday', value: 0 },
]

const dayOfMonthOptions = Array.from({ length: 31 }, (_, i) => ({
  text: `${i + 1}`, value: i + 1,
}))

// Build cron from selects
const buildCron = () => {
  const s = sched.value
  switch (s.frequency) {
    case 'every_n_min':
      return s.interval === 1 ? '* * * * *' : `*/${s.interval} * * * *`
    case 'every_n_hour':
      return s.hourInterval === 1
        ? `${s.minute} * * * *`
        : `${s.minute} */${s.hourInterval} * * *`
    case 'daily':
      return `${s.minute} ${s.hour} * * *`
    case 'weekly':
      return `${s.minute} ${s.hour} * * ${s.weekday}`
    case 'monthly':
      return `${s.minute} ${s.hour} ${s.dayOfMonth} * *`
    default:
      return '* * * * *'
  }
}

const scheduleDescription = computed(() => {
  const s = sched.value
  const pad = (n) => String(n).padStart(2, '0')
  switch (s.frequency) {
    case 'every_n_min':
      return s.interval === 1 ? 'Every minute' : `Every ${s.interval} minutes`
    case 'every_n_hour':
      return s.hourInterval === 1
        ? `Every hour at :${pad(s.minute)}`
        : `Every ${s.hourInterval} hours at :${pad(s.minute)}`
    case 'daily':
      return `Daily at ${pad(s.hour)}:${pad(s.minute)}`
    case 'weekly': {
      const day = weekdayOptions.find(d => d.value === s.weekday)?.text || ''
      return `Every ${day} at ${pad(s.hour)}:${pad(s.minute)}`
    }
    case 'monthly':
      return `Monthly on day ${s.dayOfMonth} at ${pad(s.hour)}:${pad(s.minute)}`
    default:
      return ''
  }
})

// Parse existing cron string back to sched selects
const parseCron = (cron) => {
  if (!cron) return
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return
  const [min, hour, dom, , dow] = parts

  // Every N minutes: */N * * * *
  if (hour === '*' && dom === '*' && dow === '*') {
    if (min === '*') {
      sched.value = { ...sched.value, frequency: 'every_n_min', interval: 1 }
    } else if (min.startsWith('*/')) {
      sched.value = { ...sched.value, frequency: 'every_n_min', interval: parseInt(min.slice(2)) }
    } else {
      // N * * * * → every hour at minute N
      sched.value = { ...sched.value, frequency: 'every_n_hour', hourInterval: 1, minute: parseInt(min) }
    }
    return
  }

  // Every N hours: M */N * * *
  if (hour.startsWith('*/') && dom === '*' && dow === '*') {
    sched.value = { ...sched.value, frequency: 'every_n_hour', hourInterval: parseInt(hour.slice(2)), minute: parseInt(min) }
    return
  }

  // Weekly: M H * * D
  if (dom === '*' && dow !== '*' && !hour.includes('*')) {
    sched.value = { ...sched.value, frequency: 'weekly', weekday: parseInt(dow), hour: parseInt(hour), minute: parseInt(min) }
    return
  }

  // Monthly: M H D * *
  if (dom !== '*' && dow === '*' && !hour.includes('*')) {
    sched.value = { ...sched.value, frequency: 'monthly', dayOfMonth: parseInt(dom), hour: parseInt(hour), minute: parseInt(min) }
    return
  }

  // Daily: M H * * *
  if (dom === '*' && dow === '*' && !hour.includes('*')) {
    sched.value = { ...sched.value, frequency: 'daily', hour: parseInt(hour), minute: parseInt(min) }
    return
  }
}

// Sync sched → form.schedule
watch(sched, () => {
  if (form.value.type !== 'one_time') {
    form.value.schedule = buildCron()
  }
}, { deep: true })

// Also rebuild when type changes
watch(() => form.value.type, (t) => {
  if (t !== 'one_time') {
    form.value.schedule = buildCron()
  } else {
    form.value.schedule = null
  }
})

onMounted(async () => {
  if (isEdit.value) {
    const { data } = await api.get(`/tasks/${route.params.id}`)
    Object.keys(form.value).forEach((k) => { if (data[k] !== undefined) form.value[k] = data[k] })
    // Parse existing cron into selects
    if (data.schedule) parseCron(data.schedule)
  }
})

const handleSubmit = async () => {
  saving.value = true
  try {
    if (isEdit.value) {
      await store.updateTask(route.params.id, form.value)
    } else {
      await store.createTask(form.value, agentId.value)
    }
    router.back()
  } finally {
    saving.value = false
  }
}
</script>
