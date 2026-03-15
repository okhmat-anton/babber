<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <div class="text-h4 font-weight-bold">Video Analysis</div>
      <v-spacer />
      <v-btn
        v-if="selectedItems.length && activeTab === 'videos'"
        color="deep-purple"
        variant="tonal"
        prepend-icon="mdi-forum"
        class="mr-3"
        @click="discussSelected"
      >
        Discuss ({{ selectedItems.length }})
      </v-btn>
      <v-btn v-if="activeTab === 'videos'" color="primary" prepend-icon="mdi-plus" @click="openAddDialog">
        Add Video
      </v-btn>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" class="mb-4" density="compact">
      <v-tab value="videos" prepend-icon="mdi-video-outline">Videos</v-tab>
      <v-tab value="logs" prepend-icon="mdi-text-box-search-outline">
        Transcript Logs
        <v-chip v-if="logErrorCount > 0" size="x-small" color="error" variant="flat" class="ml-2">{{ logErrorCount }}</v-chip>
      </v-tab>
      <v-tab value="skills" prepend-icon="mdi-puzzle-outline">Skills</v-tab>
    </v-tabs>

    <!-- Error alert -->
    <v-alert v-if="errorMsg" type="error" closable class="mb-4" @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <!-- ========== VIDEOS TAB ========== -->
    <div v-show="activeTab === 'videos'">

    <!-- Filters -->
    <div class="d-flex align-center ga-3 mb-4 flex-wrap">
      <v-chip-group v-model="filterPlatform" selected-class="text-primary" @update:model-value="loadHistory">
        <v-chip value="" variant="tonal" size="small">All</v-chip>
        <v-chip v-for="p in platforms" :key="p.value" :value="p.value" :color="p.color" variant="tonal" size="small">
          <v-icon start size="14">{{ p.icon }}</v-icon>
          {{ p.label }}
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
        @update:model-value="loadHistory"
      />
      <v-select
        v-model="selectedAgentId"
        :items="agents"
        item-title="name"
        item-value="id"
        label="Agent"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 220px;"
        prepend-inner-icon="mdi-robot"
      />
    </div>

    <!-- Videos grouped by category -->
    <div v-if="filterCategory === null && groupedHistory.length > 1">
      <div v-for="group in groupedHistory" :key="group.category" class="mb-6">
        <div class="text-subtitle-1 font-weight-bold mb-2 d-flex align-center">
          <v-icon size="18" class="mr-2">mdi-tag</v-icon>
          {{ group.category || 'Uncategorized' }}
          <v-chip size="x-small" variant="tonal" class="ml-2">{{ group.items.length }}</v-chip>
        </div>
        <v-card>
          <v-card-text class="pa-0">
            <v-data-table
              v-model="selectedItems"
              :headers="headers"
              :items="group.items"
              :loading="loadingHistory"
              show-select
              return-object
              hover
              density="compact"
              @click:row="(_, { item }) => openVideo(item)"
            >
              <template #item.platform="{ item }">
                <v-chip :color="platformColor(item.platform)" size="small" variant="tonal">
                  {{ item.platform }}
                </v-chip>
              </template>
              <template #item.url="{ item }">
                <div class="d-flex align-center">
                  <div>
                    <span class="font-weight-medium text-truncate d-block" style="max-width: 400px;">{{ item.url }}</span>
                    <div v-if="item.transcript" class="text-caption text-grey text-truncate" style="max-width: 400px;">
                      {{ item.transcript.substring(0, 80) }}…
                    </div>
                  </div>
                </div>
              </template>
              <template #item.status="{ item }">
                <v-chip :color="item.transcript ? 'success' : (item.error ? 'error' : 'warning')" size="small" variant="tonal">
                  {{ item.transcript ? 'ready' : (item.error ? 'error' : 'pending') }}
                </v-chip>
              </template>
              <template #item.category="{ item }">
                <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
              </template>
              <template #item.created_at="{ item }">
                {{ formatDate(item.created_at) }}
              </template>
              <template #item.actions="{ item }">
                <v-btn v-if="!item.transcript && !item.error" icon size="small" variant="text" color="primary" :loading="fetchingId === item.id" @click.stop="fetchTranscriptForItem(item)">
                  <v-icon>mdi-text-recognition</v-icon>
                </v-btn>
                <v-btn icon size="small" variant="text" color="error" @click.stop="confirmDeleteVideo(item.id)">
                  <v-icon>mdi-delete</v-icon>
                </v-btn>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </div>
    </div>

    <!-- Flat table when no grouping -->
    <v-card v-else>
      <v-card-text class="pa-0">
        <v-data-table
          v-model="selectedItems"
          :headers="headers"
          :items="filteredHistory"
          :loading="loadingHistory"
          show-select
          return-object
          hover
          @click:row="(_, { item }) => openVideo(item)"
        >
          <template #item.platform="{ item }">
            <v-chip :color="platformColor(item.platform)" size="small" variant="tonal">
              {{ item.platform }}
            </v-chip>
          </template>

          <template #item.url="{ item }">
            <div class="d-flex align-center">
              <div>
                <span class="font-weight-medium text-truncate d-block" style="max-width: 400px;">{{ item.url }}</span>
                <div v-if="item.transcript" class="text-caption text-grey text-truncate" style="max-width: 400px;">
                  {{ item.transcript.substring(0, 80) }}…
                </div>
              </div>
            </div>
          </template>

          <template #item.status="{ item }">
            <v-chip
              :color="item.transcript ? 'success' : (item.error ? 'error' : 'warning')"
              size="small"
              variant="tonal"
            >
              {{ item.transcript ? 'ready' : (item.error ? 'error' : 'pending') }}
            </v-chip>
          </template>

          <template #item.category="{ item }">
            <v-chip v-if="item.category" size="small" variant="tonal" color="indigo">{{ item.category }}</v-chip>
          </template>

          <template #item.created_at="{ item }">
            {{ formatDate(item.created_at) }}
          </template>

          <template #item.actions="{ item }">
            <v-btn
              v-if="!item.transcript && !item.error"
              icon
              size="small"
              variant="text"
              color="primary"
              :loading="fetchingId === item.id"
              @click.stop="fetchTranscriptForItem(item)"
            >
              <v-icon>mdi-text-recognition</v-icon>
              <v-tooltip activator="parent" location="top">Get Transcript</v-tooltip>
            </v-btn>
            <v-btn icon size="small" variant="text" color="error" @click.stop="confirmDeleteVideo(item.id)">
              <v-icon>mdi-delete</v-icon>
              <v-tooltip activator="parent" location="top">Delete</v-tooltip>
            </v-btn>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">Delete Video</v-card-title>
        <v-card-text>
          Are you sure you want to delete this video? This action cannot be undone.
          <v-text-field
            v-model="deleteConfirmText"
            label="Type DELETE to confirm"
            variant="outlined"
            density="compact"
            class="mt-4"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :disabled="deleteConfirmText !== 'DELETE'" @click="doDeleteVideo">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add Video Dialog -->
    <v-dialog v-model="addDialog" max-width="550">
      <v-card>
        <v-card-title class="text-h6">Add Video</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="addUrl"
            label="Video URL"
            placeholder="Paste YouTube, TikTok, Instagram, etc. URL..."
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-link"
            class="mb-3"
            autofocus
            @keydown.enter="addVideo"
          />
          <v-combobox
            v-model="addCategory"
            :items="categoryOptions"
            label="Category"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            prepend-inner-icon="mdi-tag-outline"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="addDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="adding" :disabled="!addUrl?.trim()" @click="addVideo">Add</v-btn>
          <v-btn color="teal" variant="tonal" :loading="addingWithTranscript" :disabled="!addUrl?.trim()" prepend-icon="mdi-text-recognition" @click="addVideoWithTranscript">
            Add & Transcript
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Video Detail Dialog -->
    <v-dialog v-model="detailDialog" max-width="900" scrollable>
      <v-card v-if="currentVideo">
        <v-card-title class="d-flex align-center pa-4">
          <v-chip :color="platformColor(currentVideo.platform)" size="small" class="mr-3">
            {{ currentVideo.platform }}
          </v-chip>
          <span class="text-body-1 text-truncate flex-grow-1" style="max-width: 600px;">{{ currentVideo.url }}</span>
          <v-spacer />
          <v-btn
            v-if="!transcript"
            color="primary"
            size="small"
            variant="tonal"
            :loading="fetching"
            prepend-icon="mdi-text-recognition"
            class="mr-2"
            @click="fetchTranscriptForCurrent"
          >
            Get Transcript
          </v-btn>
          <v-btn
            v-if="transcript"
            color="amber-darken-2"
            size="small"
            variant="tonal"
            :loading="fetching"
            prepend-icon="mdi-refresh"
            class="mr-2"
            @click="regenerateTranscript"
          >
            Regenerate
          </v-btn>
          <v-chip v-if="currentVideo.language" size="x-small" variant="tonal" class="mr-2">{{ currentVideo.language }}</v-chip>
          <v-btn icon size="small" variant="text" color="error" class="mr-1" @click="confirmDeleteFromDetail">
            <v-icon>mdi-delete</v-icon>
            <v-tooltip activator="parent" location="top">Delete Video</v-tooltip>
          </v-btn>
          <v-btn icon size="small" variant="text" @click="detailDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-divider />

        <!-- Category -->
        <div class="d-flex align-center ga-2 px-4 py-2" style="background: rgba(255,255,255,0.02);">
          <v-combobox
            :model-value="currentVideo.category"
            :items="categoryOptions"
            label="Category"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="max-width: 250px;"
            prepend-inner-icon="mdi-tag-outline"
            @update:model-value="updateVideoCategory($event)"
          />
          <v-spacer />
        </div>

        <!-- Action toolbar (only when transcript is available) -->
        <div v-if="transcript" class="d-flex align-center flex-wrap ga-2 px-4 py-2" style="background: rgba(255,255,255,0.02);">
          <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-chat-plus-outline" @click="startChatWithTranscript">
            Start Chat
          </v-btn>
          <v-btn variant="tonal" color="orange" size="small" prepend-icon="mdi-lightbulb-on-outline" :loading="extractingFacts" :disabled="!selectedAgentId" @click="extractFacts">
            Extract Facts
          </v-btn>
          <v-btn variant="tonal" color="teal" size="small" prepend-icon="mdi-text-box-check-outline" :loading="summarizing" @click="getSummary">
            Summary
          </v-btn>
          <v-btn variant="tonal" color="deep-purple" size="small" prepend-icon="mdi-brain" :loading="savingMemory" :disabled="!selectedAgentId" @click="saveToMemory">
            Save to Memory
          </v-btn>
        </div>

        <v-divider v-if="transcript" />

        <v-card-text style="max-height: 65vh; overflow-y: auto;">
          <!-- Summary result -->
          <v-alert v-if="summaryText" type="info" variant="tonal" class="mb-3" closable @click:close="summaryText = null">
            <div class="text-subtitle-2 mb-1 font-weight-bold">Summary</div>
            <div style="white-space: pre-wrap;">{{ summaryText }}</div>
          </v-alert>

          <!-- Facts result -->
          <v-alert v-if="factsResult" type="success" variant="tonal" class="mb-3" closable @click:close="factsResult = null">
            <div class="text-subtitle-2 mb-1 font-weight-bold">Extracted Facts</div>
            <div style="white-space: pre-wrap;">{{ factsResult }}</div>
          </v-alert>

          <!-- Memory result -->
          <v-alert v-if="memoryResult" color="deep-purple" variant="tonal" class="mb-3" closable @click:close="memoryResult = null">
            <v-icon class="mr-1">mdi-brain</v-icon>
            {{ memoryResult }}
          </v-alert>

          <!-- Linked Entities -->
          <div v-if="currentVideo && (currentVideo.linked_fact_ids?.length || currentVideo.linked_analysis_ids?.length || currentVideo.linked_idea_ids?.length || currentVideo.linked_chat_session_ids?.length)" class="mb-4">
            <div class="text-subtitle-2 font-weight-bold mb-2">
              <v-icon size="18" class="mr-1">mdi-link-variant</v-icon>
              Linked Entities
            </div>
            <div class="d-flex flex-wrap ga-2">
              <v-chip v-for="fid in (currentVideo.linked_fact_ids || [])" :key="'f-'+fid" size="small" variant="tonal" color="teal" closable @click:close="unlinkFromVideo('fact', fid)">
                <v-icon start size="14">mdi-check-decagram</v-icon>
                Fact
              </v-chip>
              <v-chip v-for="aid in (currentVideo.linked_analysis_ids || [])" :key="'a-'+aid" size="small" variant="tonal" color="blue" closable @click:close="unlinkFromVideo('analysis', aid)">
                <v-icon start size="14">mdi-chart-line</v-icon>
                Analysis
              </v-chip>
              <v-chip v-for="iid in (currentVideo.linked_idea_ids || [])" :key="'i-'+iid" size="small" variant="tonal" color="amber" closable @click:close="unlinkFromVideo('idea', iid)">
                <v-icon start size="14">mdi-lightbulb-on-outline</v-icon>
                Idea
              </v-chip>
              <v-chip v-for="cid in (currentVideo.linked_chat_session_ids || [])" :key="'c-'+cid" size="small" variant="tonal" color="purple" @click="openLinkedChat(cid)">
                <v-icon start size="14">mdi-chat-outline</v-icon>
                Chat
              </v-chip>
            </div>
          </div>

          <!-- Transcript text -->
          <div v-if="transcript" ref="transcriptContainerRef" class="transcript-box pa-4 rounded-lg" style="
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            white-space: pre-wrap;
            font-size: 13px;
            line-height: 1.7;
          ">{{ transcript }}</div>

          <div v-else-if="!fetching" class="text-center text-grey py-8">
            <v-icon size="48" class="mb-2" color="grey-darken-1">mdi-text-recognition</v-icon>
            <div>No transcript yet. Click <strong>Get Transcript</strong> to fetch it via ScrapeCreators API.</div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
    </div>

    <!-- ========== TRANSCRIPT LOGS TAB ========== -->
    <div v-show="activeTab === 'logs'">
      <div class="d-flex align-center ga-3 mb-4">
        <v-btn-toggle v-model="logLevelFilter" density="compact" variant="outlined" @update:model-value="loadLogs">
          <v-btn value="" size="small">All</v-btn>
          <v-btn value="error" size="small" color="error">
            <v-icon size="16" class="mr-1">mdi-alert-circle</v-icon> Errors
          </v-btn>
          <v-btn value="warning" size="small" color="orange">
            <v-icon size="16" class="mr-1">mdi-alert</v-icon> Warnings
          </v-btn>
          <v-btn value="success" size="small" color="success">
            <v-icon size="16" class="mr-1">mdi-check-circle</v-icon> Success
          </v-btn>
          <v-btn value="info" size="small">
            <v-icon size="16" class="mr-1">mdi-information</v-icon> Info
          </v-btn>
        </v-btn-toggle>
        <v-spacer />
        <v-btn size="small" variant="tonal" prepend-icon="mdi-refresh" @click="loadLogs" :loading="loadingLogs">Refresh</v-btn>
        <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-sweep" @click="clearLogs" :loading="clearingLogs" :disabled="!logs.length">Clear All</v-btn>
      </div>

      <v-card v-if="logs.length" variant="outlined">
        <v-table density="compact" hover>
          <thead>
            <tr>
              <th style="width: 50px">Level</th>
              <th style="width: 170px">Time</th>
              <th style="width: 100px">Platform</th>
              <th>Message</th>
              <th>URL</th>
              <th style="width: 60px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>
                <v-icon
                  :color="logLevelColor(log.level)"
                  size="20"
                >{{ logLevelIcon(log.level) }}</v-icon>
              </td>
              <td class="text-caption">{{ formatLogDate(log.created_at) }}</td>
              <td>
                <v-chip v-if="log.platform" :color="platformColor(log.platform)" size="x-small" variant="tonal">{{ log.platform }}</v-chip>
              </td>
              <td class="font-weight-medium">{{ log.message }}</td>
              <td class="text-caption text-truncate" style="max-width: 300px;">{{ log.url }}</td>
              <td>
                <v-btn v-if="log.details" icon size="x-small" variant="text" @click="expandedLog = expandedLog === log.id ? null : log.id">
                  <v-icon>{{ expandedLog === log.id ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
                </v-btn>
              </td>
            </tr>
            <tr v-if="expandedLog" v-for="log in logs.filter(l => l.id === expandedLog)" :key="'d-' + log.id">
              <td colspan="6" class="pa-0">
                <pre class="pa-3 text-caption" style="background: rgba(255,255,255,0.03); white-space: pre-wrap; max-height: 300px; overflow-y: auto; border-top: 1px solid rgba(255,255,255,0.08);">{{ log.details }}</pre>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card>

      <div v-else-if="!loadingLogs" class="text-center text-medium-emphasis py-12">
        <v-icon size="64" class="mb-3">mdi-text-box-check-outline</v-icon>
        <div class="text-h6 mb-2">No transcript logs</div>
        <div>Logs will appear here when you fetch video transcripts.</div>
      </div>

      <v-progress-linear v-if="loadingLogs" indeterminate color="primary" class="mt-4" />
    </div>

    <!-- ========== SKILLS TAB ========== -->
    <div v-show="activeTab === 'skills'">
      <v-alert type="info" variant="tonal" class="mb-4" density="compact">
        These skills are available to agents when working with video content. Agents can call them automatically during conversations.
      </v-alert>

      <v-row>
        <v-col v-for="skill in videoSkills" :key="skill.name" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="fill-height">
            <v-card-title class="d-flex align-center text-subtitle-1">
              <v-icon :color="skill.color" size="22" class="mr-2">{{ skill.icon }}</v-icon>
              {{ skill.displayName }}
            </v-card-title>
            <v-card-subtitle class="pb-0">
              <v-chip size="x-small" variant="tonal" :color="skill.catColor">{{ skill.category }}</v-chip>
            </v-card-subtitle>
            <v-card-text class="text-body-2">
              {{ skill.description }}
              <div v-if="skill.params.length" class="mt-3">
                <div class="text-caption text-medium-emphasis font-weight-bold mb-1">Parameters</div>
                <div v-for="p in skill.params" :key="p.name" class="d-flex align-start ga-2 mb-1">
                  <code class="text-caption" style="white-space: nowrap;">{{ p.name }}</code>
                  <span class="text-caption text-medium-emphasis">{{ p.desc }}</span>
                </div>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import api from '../api'
import { useChatStore } from '../stores/chat'
import { useAgentsStore } from '../stores/agents'

const showSnackbar = inject('showSnackbar')
const chatStore = useChatStore()
const agentsStore = useAgentsStore()

// State
const videoUrl = ref('')
const adding = ref(false)
const fetching = ref(false)
const fetchingId = ref(null)
const currentVideo = ref(null)
const transcript = ref('')
const errorMsg = ref(null)
const detailDialog = ref(false)
const filterPlatform = ref('')

const selectedAgentId = ref(null)
const extractingFacts = ref(false)
const summarizing = ref(false)
const savingMemory = ref(false)
const summaryText = ref(null)
const factsResult = ref(null)
const memoryResult = ref(null)

const history = ref([])
const loadingHistory = ref(false)
const agents = ref([])
const deleteDialog = ref(false)
const deleteVideoId = ref(null)
const deleteConfirmText = ref('')
const filterCategory = ref(null)
const selectedItems = ref([])

// Add video dialog
const addDialog = ref(false)
const addUrl = ref('')
const addCategory = ref(null)
const addingWithTranscript = ref(false)
const transcriptContainerRef = ref(null)

// Tabs
const activeTab = ref('videos')

// Video-related skills
const videoSkills = [
  {
    name: 'video_watch',
    displayName: 'Video Watch',
    description: 'Fetch video transcript or post content from YouTube (incl. Shorts), TikTok, Instagram, Facebook, Twitter/X, Threads, LinkedIn, Reddit, Twitch, or Kick via ScrapeCreators API. Results are cached in the watched videos database.',
    icon: 'mdi-video-outline',
    color: 'red',
    category: 'web',
    catColor: 'blue',
    params: [
      { name: 'url', desc: 'Full video/post URL (required)' },
      { name: 'language', desc: '2-letter language code, e.g. en, es, ru (optional)' },
    ],
  },
  {
    name: 'study_material',
    displayName: 'Study Material',
    description: 'Study and deeply learn material from text, file, or topic. Creates a summary, extracts key topics, writes detailed notes with source references, and links everything in the knowledge graph.',
    icon: 'mdi-book-open-page-variant',
    color: 'purple',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'topic', desc: 'Subject to study (optional)' },
      { name: 'text', desc: 'Direct text to study (optional)' },
      { name: 'file_path', desc: 'Path to file in agent data/ folder (optional)' },
      { name: 'depth', desc: 'quick, normal, or deep (default: normal)' },
    ],
  },
  {
    name: 'recall_knowledge',
    displayName: 'Recall Knowledge',
    description: 'Search and aggregate previously studied knowledge from memory. Provides structured answers based on what the agent has learned before.',
    icon: 'mdi-brain',
    color: 'deep-purple',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'query', desc: 'What to recall/remember (required)' },
      { name: 'depth', desc: 'quick or detailed (default: quick)' },
      { name: 'tags', desc: 'Filter by specific tags (optional)' },
    ],
  },
  {
    name: 'memory_store',
    displayName: 'Memory Store',
    description: 'Save information to the agent\'s long-term vector memory. Used to persist key facts, summaries, and insights from video analysis.',
    icon: 'mdi-database-plus',
    color: 'teal',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'title', desc: 'Memory entry title' },
      { name: 'content', desc: 'Content to memorize' },
      { name: 'type', desc: 'Entry type (fact, note, summary, etc.)' },
      { name: 'importance', desc: 'Importance score 0-1' },
      { name: 'tags', desc: 'Tags for categorization' },
    ],
  },
  {
    name: 'text_summarize',
    displayName: 'Text Summarize',
    description: 'Summarize text using LLM. Useful for creating concise summaries of long video transcripts.',
    icon: 'mdi-text-box-check',
    color: 'blue',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'text', desc: 'Text to summarize' },
      { name: 'max_length', desc: 'Max summary length (default: 200)' },
    ],
  },
  {
    name: 'speech_recognize',
    displayName: 'Speech Recognize (STT)',
    description: 'Transcribe audio to text using OpenAI Whisper. Use for audio files that need transcription (not needed for videos — video_watch handles that).',
    icon: 'mdi-microphone',
    color: 'orange',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'audio_url', desc: 'URL or path to audio file (required)' },
      { name: 'language', desc: 'Language code for accuracy (optional)' },
    ],
  },
  {
    name: 'humanize_text',
    displayName: 'Humanize Text',
    description: 'Rewrite AI-sounding text to sound natural and human. Checks for 24 common AI patterns (significance inflation, AI vocabulary, em dash overuse, sycophantic tone, etc.) and rewrites the text.',
    icon: 'mdi-account-edit',
    color: 'pink',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'text', desc: 'Text to humanize (required)' },
      { name: 'tone', desc: 'neutral, casual, or formal (default: neutral)' },
    ],
  },
]

// Transcript logs
const logs = ref([])
const loadingLogs = ref(false)
const clearingLogs = ref(false)
const logLevelFilter = ref('')
const expandedLog = ref(null)
const logErrorCount = ref(0)

const platforms = [
  { value: 'youtube', label: 'YouTube', color: 'red', icon: 'mdi-youtube' },
  { value: 'tiktok', label: 'TikTok', color: 'pink', icon: 'mdi-music-note' },
  { value: 'instagram', label: 'Instagram', color: 'purple', icon: 'mdi-instagram' },
  { value: 'facebook', label: 'Facebook', color: 'blue', icon: 'mdi-facebook' },
  { value: 'twitter', label: 'X/Twitter', color: 'cyan', icon: 'mdi-twitter' },
]

const headers = [
  { title: 'Platform', key: 'platform', width: 120 },
  { title: 'URL', key: 'url' },
  { title: 'Category', key: 'category', width: 140 },
  { title: 'Status', key: 'status', width: 100 },
  { title: 'Added', key: 'created_at', width: 140 },
  { title: 'Actions', key: 'actions', sortable: false, width: 120 },
]

const filteredHistory = computed(() => {
  if (!filterPlatform.value) return history.value
  return history.value.filter(v => v.platform === filterPlatform.value)
})

const categoryOptions = computed(() => {
  const cats = [...new Set(history.value.map(v => v.category).filter(Boolean))]
  return cats.sort()
})

const groupedHistory = computed(() => {
  const items = filteredHistory.value
  const groups = {}
  for (const v of items) {
    const cat = v.category || ''
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(v)
  }
  return Object.entries(groups)
    .sort(([a], [b]) => {
      if (!a) return 1
      if (!b) return -1
      return a.localeCompare(b)
    })
    .map(([cat, items]) => ({ category: cat, items }))
})

onMounted(async () => {
  await Promise.all([loadHistory(), loadAgents(), loadLogErrorCount()])
})

watch(activeTab, (val) => {
  if (val === 'logs') loadLogs()
})

async function loadAgents() {
  try {
    await agentsStore.fetchAgents()
    agents.value = agentsStore.agents
    if (agents.value.length && !selectedAgentId.value) {
      selectedAgentId.value = agents.value[0].id
    }
  } catch (e) {
    console.error('Failed to load agents:', e)
  }
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const params = { limit: 200 }
    if (filterPlatform.value) params.platform = filterPlatform.value
    if (filterCategory.value) params.category = filterCategory.value
    const { data } = await api.get('/watched-videos', { params })
    history.value = data.items || []
  } catch (e) {
    console.error('Failed to load history:', e)
  } finally {
    loadingHistory.value = false
  }
}

// ── Transcript Logs ──

async function loadLogErrorCount() {
  try {
    const { data } = await api.get('/watched-videos/logs/transcript', { params: { level: 'error', limit: 500 } })
    logErrorCount.value = (data.items || []).length
  } catch { /* ignore */ }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const params = { limit: 200 }
    if (logLevelFilter.value) params.level = logLevelFilter.value
    const { data } = await api.get('/watched-videos/logs/transcript', { params })
    logs.value = data.items || []
  } catch (e) {
    console.error('Failed to load transcript logs:', e)
  } finally {
    loadingLogs.value = false
  }
}

async function clearLogs() {
  if (!confirm('Clear all transcript logs?')) return
  clearingLogs.value = true
  try {
    await api.delete('/watched-videos/logs/transcript')
    logs.value = []
    logErrorCount.value = 0
    showSnackbar?.('Logs cleared', 'success')
  } catch (e) {
    showSnackbar?.('Failed to clear logs', 'error')
  } finally {
    clearingLogs.value = false
  }
}

function logLevelColor(level) {
  return { error: 'error', warning: 'orange', success: 'success', info: 'blue-grey' }[level] || 'grey'
}

function logLevelIcon(level) {
  return {
    error: 'mdi-alert-circle',
    warning: 'mdi-alert',
    success: 'mdi-check-circle',
    info: 'mdi-information-outline',
  }[level] || 'mdi-circle-small'
}

function formatLogDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function addVideo() {
  if (!addUrl.value?.trim()) return
  adding.value = true
  errorMsg.value = null
  try {
    const payload = { url: addUrl.value.trim() }
    if (addCategory.value) payload.category = addCategory.value
    const { data } = await api.post('/watched-videos', payload)
    addUrl.value = ''
    addCategory.value = null
    addDialog.value = false
    await loadHistory()
    openVideo(data)
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to add video'
  } finally {
    adding.value = false
  }
}

async function addVideoWithTranscript() {
  if (!addUrl.value?.trim()) return
  addingWithTranscript.value = true
  errorMsg.value = null
  try {
    const payload = { url: addUrl.value.trim() }
    if (addCategory.value) payload.category = addCategory.value
    const { data } = await api.post('/watched-videos', payload)
    // Trigger background transcript fetch (fire & forget)
    api.post(`/watched-videos/${data.id}/fetch-background`).then(() => {
      showSnackbar?.('Transcript is being fetched in background...', 'info')
    }).catch(() => {})
    addUrl.value = ''
    addCategory.value = null
    addDialog.value = false
    await loadHistory()
    showSnackbar?.('Video added. Transcript fetching in background.', 'success')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to add video'
  } finally {
    addingWithTranscript.value = false
  }
}

function openAddDialog() {
  addUrl.value = ''
  addCategory.value = null
  addDialog.value = true
}

function openVideo(item) {
  currentVideo.value = item
  summaryText.value = null
  factsResult.value = null
  memoryResult.value = null
  errorMsg.value = null
  if (item.transcript) {
    loadFullTranscript(item)
  } else {
    transcript.value = ''
  }
  detailDialog.value = true
}

async function loadFullTranscript(item) {
  try {
    const { data } = await api.get(`/watched-videos/${item.id}/full-transcript`)
    transcript.value = data.transcript || item.transcript || ''
  } catch {
    transcript.value = item.transcript || ''
  }
}

async function fetchTranscriptForCurrent() {
  if (!currentVideo.value) return
  fetching.value = true
  errorMsg.value = null
  try {
    const { data } = await api.post('/watched-videos/fetch', { video_id: currentVideo.value.id })
    currentVideo.value = { ...currentVideo.value, ...data }
    if (data.id) {
      try {
        const { data: full } = await api.get(`/watched-videos/${data.id}/full-transcript`)
        transcript.value = full.transcript || data.transcript || ''
      } catch {
        transcript.value = data.transcript || ''
      }
    } else {
      transcript.value = data.transcript || ''
    }
    await loadHistory()
    loadLogErrorCount()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to fetch transcript'
    loadLogErrorCount()
  } finally {
    fetching.value = false
  }
}

async function fetchTranscriptForItem(item) {
  fetchingId.value = item.id
  errorMsg.value = null
  try {
    const { data } = await api.post('/watched-videos/fetch', { video_id: item.id })
    const idx = history.value.findIndex(v => v.id === item.id)
    if (idx !== -1) {
      history.value[idx] = { ...history.value[idx], transcript: data.transcript, language: data.language }
    }
    if (currentVideo.value?.id === item.id) {
      currentVideo.value = { ...currentVideo.value, ...data }
      try {
        const { data: full } = await api.get(`/watched-videos/${data.id}/full-transcript`)
        transcript.value = full.transcript || data.transcript || ''
      } catch {
        transcript.value = data.transcript || ''
      }
    }
    showSnackbar?.('Transcript fetched', 'success')
    loadLogErrorCount()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to fetch transcript'
    loadLogErrorCount()
  } finally {
    fetchingId.value = null
  }
}

function startChatWithTranscript() {
  if (!transcript.value) return
  const videoTitle = currentVideo.value?.title || currentVideo.value?.url || 'video'
  
  // Create a NEW chat session linked to this video
  chatStore.createSession({
    title: `Video: ${videoTitle.substring(0, 60)}`,
    chat_type: 'user',
    video_id: currentVideo.value?.id || null,
  }).then(session => {
    if (session) {
      // Link chat session to video
      if (currentVideo.value?.id) {
        api.post(`/watched-videos/${currentVideo.value.id}/link`, {
          target_type: 'chat_session',
          target_id: session.id,
        }).then(() => {
          // Update local linked_chat_session_ids
          if (!currentVideo.value.linked_chat_session_ids) currentVideo.value.linked_chat_session_ids = []
          currentVideo.value.linked_chat_session_ids.push(session.id)
        }).catch(() => {})
      }
      // Set pending input with transcript
      const prefix = `Video transcript from ${currentVideo.value?.url || 'video'}:\n\n`
      chatStore.pendingInput = prefix + transcript.value
      chatStore.openPanel()
      detailDialog.value = false
    }
  }).catch(e => {
    errorMsg.value = 'Failed to create chat session'
  })
}

async function extractFacts() {
  if (!transcript.value || !selectedAgentId.value) return
  extractingFacts.value = true
  factsResult.value = null
  try {
    // Use LLM to extract individual facts from transcript
    const { data: session } = await api.post('/chat/sessions', {
      title: `Extract facts: ${currentVideo.value?.url?.substring(0, 50) || 'video'}`,
      chat_type: 'user',
    })
    const { data } = await api.post(`/chat/sessions/${session.id}/messages`, {
      content: `Extract all key facts from the following video transcript. Return ONLY a JSON array of strings, each being a concise factual statement. No explanations, just the JSON array.\n\n---\n\n${transcript.value.substring(0, 12000)}`,
    }, { timeout: 300000 })
    const assistantMsg = data.find?.(m => m.role === 'assistant') || data
    const responseText = assistantMsg.content || assistantMsg.text || ''
    
    // Parse JSON array from response
    let facts = []
    try {
      const jsonMatch = responseText.match(/\[[\s\S]*\]/)
      if (jsonMatch) {
        facts = JSON.parse(jsonMatch[0])
      }
    } catch {
      // Fallback: split by newlines and filter
      facts = responseText.split('\n').map(l => l.replace(/^[-*•\d.]+\s*/, '').trim()).filter(l => l.length > 10)
    }
    
    if (!facts.length) {
      factsResult.value = 'No facts extracted from transcript.'
      return
    }
    
    // Save each fact linked to this video
    let savedCount = 0
    for (const factText of facts) {
      if (typeof factText !== 'string' || factText.length < 5) continue
      try {
        const { data: newFact } = await api.post(`/agents/${selectedAgentId.value}/facts`, {
          type: 'fact',
          content: factText,
          source: 'video',
          verified: false,
          confidence: 0.7,
          tags: ['video', currentVideo.value?.platform || 'unknown'],
        })
        // Link fact to video bidirectionally
        if (currentVideo.value?.id && newFact?.id) {
          await api.post(`/watched-videos/${currentVideo.value.id}/link`, {
            target_type: 'fact', target_id: newFact.id,
          }).catch(() => {})
          await api.post(`/facts/${newFact.id}/link`, {
            target_type: 'video', target_id: currentVideo.value.id,
          }).catch(() => {})
        }
        savedCount++
      } catch (e) {
        console.error('Failed to save fact:', factText, e)
      }
    }
    
    factsResult.value = `Extracted and saved ${savedCount} facts from transcript.`
    showSnackbar?.(`${savedCount} facts extracted and saved`, 'success')
    // Reload video to get updated linked_fact_ids
    if (currentVideo.value?.id) {
      try {
        const { data: updated } = await api.get(`/watched-videos/${currentVideo.value.id}`)
        currentVideo.value = { ...currentVideo.value, ...updated }
      } catch {}
    }
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to extract facts'
  } finally {
    extractingFacts.value = false
  }
}

async function getSummary() {
  if (!transcript.value) return
  summarizing.value = true
  summaryText.value = null
  try {
    const { data: session } = await api.post('/chat/sessions', {
      title: `Summary: ${currentVideo.value?.url?.substring(0, 60) || 'video'}`,
      chat_type: 'user',
    })
    const { data } = await api.post(`/chat/sessions/${session.id}/messages`, {
      content: `Please provide a concise summary of the following video transcript. Focus on the key points, main topics, and conclusions.\n\n---\n\n${transcript.value.substring(0, 12000)}`,
    }, { timeout: 300000 })
    const assistantMsg = data.find?.(m => m.role === 'assistant') || data
    summaryText.value = assistantMsg.content || assistantMsg.text || JSON.stringify(assistantMsg)
    showSnackbar?.('Summary generated', 'success')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to generate summary'
  } finally {
    summarizing.value = false
  }
}

async function saveToMemory() {
  if (!transcript.value || !selectedAgentId.value) return
  savingMemory.value = true
  memoryResult.value = null
  try {
    const { data } = await api.post(`/agents/${selectedAgentId.value}/memory`, {
      title: `Video transcript: ${currentVideo.value?.url?.substring(0, 80) || 'video'}`,
      content: transcript.value.substring(0, 50000),
      type: 'fact',
      importance: 0.7,
      tags: ['video', currentVideo.value?.platform || 'unknown'],
      category: 'knowledge',
    })
    memoryResult.value = `Saved to ChromaDB memory (id: ${data.id})`
    showSnackbar?.('Saved to memory', 'success')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to save to memory'
  } finally {
    savingMemory.value = false
  }
}

function confirmDeleteVideo(id) {
  deleteVideoId.value = id
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

function confirmDeleteFromDetail() {
  if (!currentVideo.value) return
  deleteVideoId.value = currentVideo.value.id
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

async function regenerateTranscript() {
  if (!currentVideo.value) return
  fetching.value = true
  errorMsg.value = null
  try {
    const { data } = await api.post('/watched-videos/fetch', { video_id: currentVideo.value.id, force: true })
    currentVideo.value = { ...currentVideo.value, ...data }
    if (data.id) {
      try {
        const { data: full } = await api.get(`/watched-videos/${data.id}/full-transcript`)
        transcript.value = full.transcript || data.transcript || ''
      } catch {
        transcript.value = data.transcript || ''
      }
    } else {
      transcript.value = data.transcript || ''
    }
    await loadHistory()
    showSnackbar?.('Transcript regenerated', 'success')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to regenerate transcript'
  } finally {
    fetching.value = false
  }
}

async function updateVideoCategory(val) {
  if (!currentVideo.value) return
  const category = val || null
  try {
    await api.patch(`/watched-videos/${currentVideo.value.id}`, { category })
    currentVideo.value = { ...currentVideo.value, category }
    const idx = history.value.findIndex(v => v.id === currentVideo.value.id)
    if (idx !== -1) history.value[idx] = { ...history.value[idx], category }
    showSnackbar?.('Category updated', 'success')
  } catch (e) {
    showSnackbar?.('Failed to update category', 'error')
  }
}

async function doDeleteVideo() {
  const id = deleteVideoId.value
  deleteDialog.value = false
  try {
    await api.delete(`/watched-videos/${id}`)
    history.value = history.value.filter(v => v.id !== id)
    if (currentVideo.value?.id === id) {
      currentVideo.value = null
      transcript.value = ''
      detailDialog.value = false
    }
    showSnackbar?.('Video deleted', 'success')
  } catch (e) {
    showSnackbar?.('Failed to delete', 'error')
  }
}

function platformColor(p) {
  return { youtube: 'red', tiktok: 'pink', instagram: 'purple', facebook: 'blue', twitter: 'cyan', threads: 'grey', linkedin: 'indigo', reddit: 'deep-orange', twitch: 'purple', kick: 'green' }[p] || 'grey'
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function discussSelected() {
  if (!selectedItems.value.length) return
  try {
    const lines = selectedItems.value.map(v => {
      const label = v.url || v.platform || 'Video'
      const snippet = v.transcript ? v.transcript.substring(0, 500) : '(no transcript)'
      return `### ${label}\n${snippet}`
    }).join('\n\n')
    const session = await chatStore.createSession({ title: `Discuss ${selectedItems.value.length} video(s)` })
    chatStore.openPanel()
    await chatStore.sendMessage(`Please analyze and discuss these videos:\n\n${lines}`)
    selectedItems.value = []
    showSnackbar?.('Chat session created', 'success')
  } catch (e) {
    showSnackbar?.('Failed to create discussion', 'error')
  }
}

async function unlinkFromVideo(targetType, targetId) {
  if (!currentVideo.value?.id) return
  try {
    const { data } = await api.post(`/watched-videos/${currentVideo.value.id}/unlink`, {
      target_type: targetType,
      target_id: targetId,
    })
    currentVideo.value = { ...currentVideo.value, ...data }
    showSnackbar?.('Unlinked', 'success')
  } catch (e) {
    showSnackbar?.('Failed to unlink', 'error')
  }
}

function openLinkedChat(sessionId) {
  chatStore.loadSession(sessionId)
  chatStore.openPanel()
  detailDialog.value = false
}
</script>
