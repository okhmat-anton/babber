<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div class="text-h4 font-weight-bold">Research Resources</div>
      <v-spacer />
      <v-text-field
        v-if="activeTab === 'resources'"
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
      <v-btn v-if="activeTab === 'resources'" color="primary" prepend-icon="mdi-plus" @click="openCreate">New Resource</v-btn>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" class="mb-4" density="compact">
      <v-tab value="resources" prepend-icon="mdi-earth">Resources</v-tab>
      <v-tab value="skills" prepend-icon="mdi-puzzle-outline">Skills</v-tab>
    </v-tabs>

    <!-- ========== RESOURCES TAB ========== -->
    <div v-show="activeTab === 'resources'">

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

    <!-- Tag filter -->
    <div v-if="allTags.length" class="d-flex align-center ga-1 mb-3 flex-wrap">
      <v-icon size="18" class="mr-1 text-grey">mdi-tag-multiple</v-icon>
      <v-chip
        v-for="tag in allTags" :key="tag"
        :color="selectedTags.includes(tag) ? 'cyan' : 'default'"
        :variant="selectedTags.includes(tag) ? 'flat' : 'outlined'"
        size="small" @click="toggleTag(tag)"
      >{{ tag }}</v-chip>
      <v-btn v-if="selectedTags.length" variant="text" size="x-small" color="grey" @click="selectedTags = []">Clear</v-btn>
    </div>

    <!-- Resources Table -->
    <v-card>
      <v-card-text class="pa-0">
        <v-data-table
          :headers="headers"
          :items="tagFilteredResources"
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

          <template #item.tags="{ item }">
            <div class="d-flex ga-1 flex-wrap">
              <v-chip v-for="t in (item.tags || [])" :key="t" size="x-small" variant="tonal" color="cyan">{{ t }}</v-chip>
              <v-chip v-if="(item.rss_feeds || []).length" size="x-small" variant="tonal" color="orange">
                <v-icon start size="10">mdi-rss</v-icon>
                {{ item.rss_feeds.length }} feed{{ item.rss_feeds.length > 1 ? 's' : '' }}
              </v-chip>
            </div>
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

              <!-- RSS Feeds -->
              <v-col cols="12">
                <div class="d-flex align-center mb-2">
                  <v-icon size="18" class="mr-2" color="orange">mdi-rss</v-icon>
                  <span class="text-subtitle-2 font-weight-medium">RSS Feeds</span>
                  <v-spacer />
                  <v-btn size="small" variant="tonal" color="orange" prepend-icon="mdi-plus" @click="addFeed">
                    Add Feed
                  </v-btn>
                </div>
                <div v-for="(feed, idx) in form.rss_feeds" :key="idx" class="d-flex align-center ga-2 mb-2">
                  <v-text-field
                    v-model="feed.url"
                    label="Feed URL"
                    variant="outlined"
                    density="compact"
                    hide-details
                    placeholder="https://example.com/rss"
                    style="flex: 2"
                  />
                  <v-text-field
                    v-model="feed.title"
                    label="Title"
                    variant="outlined"
                    density="compact"
                    hide-details
                    placeholder="Blog, News..."
                    style="flex: 1"
                  />
                  <v-select
                    v-model="feed.category"
                    :items="feedCategories"
                    variant="outlined"
                    density="compact"
                    hide-details
                    style="flex: 0.7"
                  />
                  <v-btn icon size="small" variant="text" color="error" @click="form.rss_feeds.splice(idx, 1)">
                    <v-icon>mdi-close</v-icon>
                  </v-btn>
                </div>
                <div v-if="!form.rss_feeds.length" class="text-caption text-grey ml-7">No RSS feeds added yet</div>
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

    <!-- ========== SKILLS TAB ========== -->
    <div v-show="activeTab === 'skills'">
      <v-alert type="info" variant="tonal" class="mb-4" density="compact">
        These skills allow agents to discover, fetch, and learn from research resources during conversations.
      </v-alert>

      <v-row>
        <v-col v-for="skill in researchSkills" :key="skill.name" cols="12" md="6" lg="4">
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
import { ref, computed, onMounted } from 'vue'
import { useResearchResourcesStore } from '../stores/researchResources'

const store = useResearchResourcesStore()

const selectedTags = ref([])
const activeTab = ref('resources')

// Research-related skills
const researchSkills = [
  {
    name: 'web_search',
    displayName: 'Web Search',
    description: 'Search the internet via DuckDuckGo. Returns search results with titles, URLs, and snippets. The starting point for most research tasks.',
    icon: 'mdi-magnify',
    color: 'amber',
    category: 'web',
    catColor: 'blue',
    params: [
      { name: 'query', desc: 'Search query (required)' },
      { name: 'limit', desc: 'Max results (default: 10)' },
      { name: 'region', desc: 'Region code, e.g. us-en, ru-ru (optional)' },
    ],
  },
  {
    name: 'web_fetch',
    displayName: 'Web Fetch',
    description: 'HTTP GET/POST requests to any URL. Fetches the raw content of a page. Used to retrieve articles, documentation, and data from research resources.',
    icon: 'mdi-download',
    color: 'blue',
    category: 'web',
    catColor: 'blue',
    params: [
      { name: 'url', desc: 'URL to fetch (required)' },
      { name: 'method', desc: 'HTTP method: GET or POST (default: GET)' },
    ],
  },
  {
    name: 'web_scrape',
    displayName: 'Web Scrape',
    description: 'Parse and extract specific data from HTML pages using BeautifulSoup CSS selectors. Useful for structured extraction from research sites.',
    icon: 'mdi-code-tags',
    color: 'green',
    category: 'web',
    catColor: 'blue',
    params: [
      { name: 'url', desc: 'URL to scrape (required)' },
      { name: 'selector', desc: 'CSS selector to extract' },
    ],
  },
  {
    name: 'rss_read',
    displayName: 'RSS Read',
    description: 'Parse RSS/Atom feeds and return latest entries. Monitors news, blog posts, releases, and updates from research resources with RSS feeds.',
    icon: 'mdi-rss',
    color: 'orange',
    category: 'web',
    catColor: 'blue',
    params: [
      { name: 'url', desc: 'RSS/Atom feed URL (required)' },
      { name: 'limit', desc: 'Max entries to return (default: 20)' },
    ],
  },
  {
    name: 'weather_check',
    displayName: 'Weather Check',
    description: 'Check current weather and 3-day forecast for any city. Uses Open-Meteo API (free, no API key). Integrates with creator cities of interest.',
    icon: 'mdi-weather-partly-cloudy',
    color: 'light-blue',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'location', desc: 'City name, optionally with country (required)' },
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
      { name: 'file_path', desc: 'Path to file in agent data/ (optional)' },
      { name: 'depth', desc: 'quick, normal, or deep (default: normal)' },
    ],
  },
  {
    name: 'recall_knowledge',
    displayName: 'Recall Knowledge',
    description: 'Search and aggregate previously studied knowledge from memory. Provides structured answers based on what the agent has learned from past research.',
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
    description: 'Save information to the agent\'s long-term vector memory. Used to persist key facts, findings, and insights from research sessions.',
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
    name: 'memory_search',
    displayName: 'Memory Search',
    description: 'Semantic search through the agent\'s memory. Finds previously stored research findings, facts, and notes by meaning, not just keywords.',
    icon: 'mdi-database-search',
    color: 'cyan',
    category: 'general',
    catColor: 'deep-purple',
    params: [
      { name: 'query', desc: 'Semantic search query (required)' },
      { name: 'limit', desc: 'Max results (default: 5)' },
    ],
  },
  {
    name: 'text_summarize',
    displayName: 'Text Summarize',
    description: 'Summarize text using LLM. Condense long articles, papers, or documentation into concise summaries.',
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
    name: 'humanize_text',
    displayName: 'Humanize Text',
    description: 'Rewrite AI-sounding text to sound natural and human. Removes 24 common AI patterns from research summaries and articles.',
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

// ── Table config ──
const headers = [
  { title: 'Resource', key: 'name', sortable: true },
  { title: 'Trust', key: 'trust_level', width: 110, sortable: true },
  { title: 'Tags', key: 'tags', width: 160, sortable: false },
  { title: 'User Rating', key: 'user_rating', width: 150, sortable: true },
  { title: 'Agent Rating', key: 'agent_rating', width: 100, sortable: true },
  { title: 'Active', key: 'is_active', width: 80 },
  { title: 'Uses', key: 'use_count', width: 70, sortable: true },
  { title: 'Added by', key: 'added_by', width: 100 },
  { title: '', key: 'actions', width: 100, sortable: false },
]

const allTags = computed(() => {
  const tags = new Set()
  store.resources.forEach(i => (i.tags || []).forEach(t => tags.add(t)))
  return [...tags].sort()
})

const tagFilteredResources = computed(() => {
  if (!selectedTags.value.length) return store.resources
  return store.resources.filter(i => (i.tags || []).some(t => selectedTags.value.includes(t)))
})

function toggleTag(tag) {
  const idx = selectedTags.value.indexOf(tag)
  if (idx >= 0) selectedTags.value.splice(idx, 1)
  else selectedTags.value.push(tag)
}

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

const feedCategories = ['general', 'news', 'blog', 'releases', 'updates', 'discussions']

function addFeed() {
  form.value.rss_feeds.push({ url: '', title: '', category: 'general', is_active: true })
}

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
    rss_feeds: [],
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
    rss_feeds: (item.rss_feeds || []).map(f => ({ url: f.url, title: f.title, category: f.category || 'general', is_active: f.is_active !== false })),
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
