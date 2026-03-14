<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <v-icon size="32" color="blue-accent-2" class="mr-3">mdi-shield-search</v-icon>
      <div class="text-h4 font-weight-bold">DARPA Monitor</div>
      <v-spacer />
      <v-btn
        color="blue"
        variant="tonal"
        prepend-icon="mdi-refresh"
        @click="triggerScrape"
        :loading="scraping"
        class="mr-2"
      >
        Scrape Now
      </v-btn>
      <v-chip v-if="lastScrape" variant="tonal" color="grey" size="small">
        Last scrape: {{ formatDate(lastScrape) }}
      </v-chip>
    </div>

    <!-- Stats chips -->
    <div class="d-flex flex-wrap ga-2 mb-4" v-if="stats">
      <v-chip
        v-for="(s, cat) in stats"
        :key="cat"
        variant="tonal"
        :color="categoryColor(cat)"
        size="large"
      >
        <v-icon start size="16">{{ categoryIcon(cat) }}</v-icon>
        {{ categoryLabel(cat) }}: {{ s.total }}
        <v-badge v-if="s.new > 0" :content="s.new" color="red" floating inline />
      </v-chip>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="blue-accent-2" class="mb-4">
      <v-tab value="opportunities">
        <v-icon start size="18">mdi-file-document-outline</v-icon>
        Opportunities
        <v-badge v-if="newCount('opportunities') > 0" :content="newCount('opportunities')" color="red" floating inline />
      </v-tab>
      <v-tab value="programs">
        <v-icon start size="18">mdi-flask-outline</v-icon>
        Programs
        <v-badge v-if="newCount('programs') > 0" :content="newCount('programs')" color="red" floating inline />
      </v-tab>
      <v-tab value="news">
        <v-icon start size="18">mdi-newspaper-variant-outline</v-icon>
        News
        <v-badge v-if="newCount('news') > 0" :content="newCount('news')" color="red" floating inline />
      </v-tab>
      <v-tab value="events">
        <v-icon start size="18">mdi-calendar-star</v-icon>
        Events
        <v-badge v-if="newCount('events') > 0" :content="newCount('events')" color="red" floating inline />
      </v-tab>
      <v-tab value="settings">
        <v-icon start size="18">mdi-cog-outline</v-icon>
        Settings
      </v-tab>
    </v-tabs>

    <!-- Filters (for all data tabs) -->
    <div v-if="activeTab !== 'settings'" class="d-flex flex-wrap ga-2 mb-4 align-center">
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="outlined"
        prepend-inner-icon="mdi-magnify"
        placeholder="Search..."
        hide-details
        clearable
        style="max-width: 300px"
        @keydown.enter="loadItems"
        @click:clear="searchQuery = ''; loadItems()"
      />
      <v-select
        v-model="filterOffice"
        :items="offices"
        density="compact"
        variant="outlined"
        label="Office"
        hide-details
        clearable
        style="max-width: 250px"
      />
      <v-select
        v-model="filterTopic"
        :items="topics"
        density="compact"
        variant="outlined"
        label="Topic"
        hide-details
        clearable
        style="max-width: 250px"
      />
      <v-switch
        v-model="newOnly"
        label="New only"
        density="compact"
        hide-details
        color="red"
        class="ml-2"
      />
      <v-spacer />
      <v-btn-toggle v-model="viewMode" mandatory density="compact" variant="outlined" color="blue">
        <v-btn value="table" icon="mdi-format-list-bulleted" size="small" />
        <v-btn value="cards" icon="mdi-view-grid-outline" size="small" />
      </v-btn-toggle>
    </div>

    <!-- Content -->
    <v-window v-model="activeTab">
      <!-- Opportunities -->
      <v-window-item value="opportunities">
        <item-list
          :items="items"
          :loading="loading"
          :total="total"
          :view-mode="viewMode"
          category="opportunities"
          @load-more="loadMore"
          @open="openItem"
        />
      </v-window-item>

      <!-- Programs -->
      <v-window-item value="programs">
        <item-list
          :items="items"
          :loading="loading"
          :total="total"
          :view-mode="viewMode"
          category="programs"
          @load-more="loadMore"
          @open="openItem"
        />
      </v-window-item>

      <!-- News -->
      <v-window-item value="news">
        <item-list
          :items="items"
          :loading="loading"
          :total="total"
          :view-mode="viewMode"
          category="news"
          @load-more="loadMore"
          @open="openItem"
        />
      </v-window-item>

      <!-- Events -->
      <v-window-item value="events">
        <item-list
          :items="items"
          :loading="loading"
          :total="total"
          :view-mode="viewMode"
          category="events"
          @load-more="loadMore"
          @open="openItem"
        />
      </v-window-item>

      <!-- Settings -->
      <v-window-item value="settings">
        <v-card variant="outlined" class="pa-4" style="max-width: 600px">
          <div class="text-h6 mb-4">DARPA Monitor Settings</div>

          <v-select
            v-model="scrapeFrequency"
            :items="frequencyOptions"
            label="Scrape Frequency"
            variant="outlined"
            density="compact"
            hint="How often to automatically fetch new data from DARPA"
            persistent-hint
            class="mb-4"
            @update:model-value="saveSetting('darpa_scrape_frequency', $event)"
          />

          <v-card variant="tonal" class="pa-3 mb-4">
            <div class="text-subtitle-2 mb-2">Scrape Status</div>
            <div v-if="lastScrape">
              <div class="text-body-2">Last run: {{ formatDate(lastScrape) }}</div>
              <div v-if="scrapeStats" class="mt-2">
                <div v-for="(s, cat) in scrapeStats" :key="cat" class="text-body-2">
                  <v-icon size="14" :color="categoryColor(cat)" class="mr-1">{{ categoryIcon(cat) }}</v-icon>
                  {{ categoryLabel(cat) }}: {{ s.total }} items ({{ s.new }} new, {{ s.updated }} updated)
                  <span v-if="s.error" class="text-red"> — Error: {{ s.error }}</span>
                </div>
              </div>
            </div>
            <div v-else class="text-body-2 text-grey">
              No scrape has been run yet. Click "Scrape Now" to start.
            </div>
          </v-card>

          <v-btn
            color="blue"
            variant="tonal"
            prepend-icon="mdi-refresh"
            @click="triggerScrape"
            :loading="scraping"
            class="mr-2"
          >
            Run Scrape Now
          </v-btn>
          <v-btn
            color="red"
            variant="tonal"
            prepend-icon="mdi-delete-outline"
            @click="confirmClear = true"
          >
            Clear All Data
          </v-btn>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- Item detail dialog -->
    <v-dialog v-model="detailOpen" max-width="800" scrollable>
      <v-card v-if="detailItem">
        <v-card-title class="d-flex align-center">
          <v-icon :color="categoryColor(detailItem.category)" class="mr-2">{{ categoryIcon(detailItem.category) }}</v-icon>
          {{ detailItem.title }}
          <v-chip v-if="detailItem.is_new" color="red" size="x-small" class="ml-2">NEW</v-chip>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="detailOpen = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height: 70vh">
          <!-- Metadata chips -->
          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-chip v-if="detailItem.office" size="small" variant="tonal" color="blue">
              <v-icon start size="14">mdi-office-building</v-icon>
              {{ detailItem.office }}
            </v-chip>
            <v-chip v-if="detailItem.status" size="small" variant="tonal" color="purple">
              {{ detailItem.status }}
            </v-chip>
            <v-chip v-if="detailItem.opportunity_number" size="small" variant="tonal" color="orange">
              #{{ detailItem.opportunity_number }}
            </v-chip>
            <v-chip v-if="detailItem.program_manager" size="small" variant="tonal" color="teal">
              <v-icon start size="14">mdi-account</v-icon>
              {{ detailItem.program_manager }}
            </v-chip>
            <v-chip
              v-for="topic in (detailItem.topics || [])"
              :key="topic"
              size="small"
              variant="outlined"
            >
              {{ topic }}
            </v-chip>
          </div>

          <!-- Dates -->
          <div class="d-flex flex-wrap ga-4 mb-3 text-body-2 text-grey">
            <span v-if="detailItem.open_date">Opens: {{ formatDate(detailItem.open_date) }}</span>
            <span v-if="detailItem.close_date">Closes: {{ formatDate(detailItem.close_date) }}</span>
            <span v-if="detailItem.publish_date">Published: {{ formatDate(detailItem.publish_date) }}</span>
            <span v-if="detailItem.event_date">Event: {{ formatDate(detailItem.event_date) }}</span>
            <span v-if="detailItem.start_date">Started: {{ formatDate(detailItem.start_date) }}</span>
            <span v-if="detailItem.location">Location: {{ detailItem.location }}</span>
          </div>

          <!-- Body -->
          <div v-if="detailItem.body" class="darpa-body text-body-1" v-html="detailItem.body" />
          <div v-else-if="detailItem.summary" class="text-body-1">{{ detailItem.summary }}</div>
          <div v-else class="text-body-2 text-grey-darken-1">No description available.</div>

          <!-- Links -->
          <div v-if="detailItem.darpa_url || detailItem.external_url" class="mt-4">
            <v-btn
              v-if="detailItem.darpa_url"
              :href="detailItem.darpa_url"
              target="_blank"
              variant="tonal"
              color="blue"
              size="small"
              prepend-icon="mdi-open-in-new"
              class="mr-2"
            >
              View on DARPA
            </v-btn>
            <v-btn
              v-if="detailItem.external_url"
              :href="detailItem.external_url"
              target="_blank"
              variant="tonal"
              color="green"
              size="small"
              prepend-icon="mdi-open-in-new"
            >
              External Link
            </v-btn>
          </div>

          <!-- Meta -->
          <div class="text-caption text-grey mt-4">
            First seen: {{ formatDate(detailItem.first_seen_at) }} |
            Last seen: {{ formatDate(detailItem.last_seen_at) }} |
            Scraped {{ detailItem.scrape_count || 0 }} times
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Clear confirmation -->
    <v-dialog v-model="confirmClear" max-width="400">
      <v-card>
        <v-card-title>Clear All DARPA Data?</v-card-title>
        <v-card-text>
          This will delete all stored DARPA items. You can re-scrape at any time.
          <v-text-field
            v-model="deleteConfirmText"
            label="Type DELETE to confirm"
            variant="outlined"
            density="compact"
            class="mt-3"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmClear = false">Cancel</v-btn>
          <v-btn color="red" variant="tonal" :disabled="deleteConfirmText !== 'DELETE'" @click="clearAll">
            Clear All
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<script>
/* Sub-component for displaying items as table or cards */
const ItemList = {
  name: 'ItemList',
  props: {
    items: Array,
    loading: Boolean,
    total: Number,
    viewMode: String,
    category: String,
  },
  emits: ['loadMore', 'open'],
  template: `
    <div>
      <!-- Loading -->
      <v-progress-linear v-if="loading" indeterminate color="blue" class="mb-2" />

      <!-- Empty state -->
      <v-card v-if="!loading && items.length === 0" variant="tonal" class="pa-8 text-center">
        <v-icon size="48" color="grey">mdi-database-off-outline</v-icon>
        <div class="text-h6 mt-2 text-grey">No items found</div>
        <div class="text-body-2 text-grey">Try adjusting filters or run a scrape first.</div>
      </v-card>

      <!-- Table view -->
      <v-table v-if="viewMode === 'table' && items.length > 0" density="compact" hover>
        <thead>
          <tr>
            <th style="width: 30px"></th>
            <th>Title</th>
            <th v-if="category === 'opportunities'">Number</th>
            <th>Office</th>
            <th>Topics</th>
            <th v-if="category === 'opportunities'">Closes</th>
            <th v-if="category === 'programs'">Status</th>
            <th v-if="category === 'news'">Published</th>
            <th v-if="category === 'events'">Date</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.nid"
            style="cursor: pointer"
            @click="$emit('open', item)"
          >
            <td>
              <v-icon v-if="item.is_new" color="red" size="12">mdi-circle</v-icon>
            </td>
            <td class="font-weight-medium" style="max-width: 400px">
              <div class="text-truncate">{{ item.title }}</div>
            </td>
            <td v-if="category === 'opportunities'" class="text-caption">{{ item.opportunity_number }}</td>
            <td class="text-caption">{{ item.office }}</td>
            <td style="max-width: 200px">
              <div class="d-flex flex-wrap ga-1">
                <v-chip v-for="t in (item.topics || []).slice(0, 3)" :key="t" size="x-small" variant="outlined">{{ t }}</v-chip>
                <v-chip v-if="(item.topics || []).length > 3" size="x-small" variant="text">+{{ item.topics.length - 3 }}</v-chip>
              </div>
            </td>
            <td v-if="category === 'opportunities'" class="text-caption">{{ fmtDate(item.close_date) }}</td>
            <td v-if="category === 'programs'">
              <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">{{ item.status || 'Unknown' }}</v-chip>
            </td>
            <td v-if="category === 'news'" class="text-caption">{{ fmtDate(item.publish_date) }}</td>
            <td v-if="category === 'events'" class="text-caption">{{ fmtDate(item.event_date) }}</td>
          </tr>
        </tbody>
      </v-table>

      <!-- Card view -->
      <div v-if="viewMode === 'cards' && items.length > 0" class="d-flex flex-wrap ga-3">
        <v-card
          v-for="item in items"
          :key="item.nid"
          variant="outlined"
          width="350"
          hover
          @click="$emit('open', item)"
          style="cursor: pointer"
        >
          <v-card-title class="text-subtitle-1 d-flex align-center" style="line-height: 1.3">
            <v-icon v-if="item.is_new" color="red" size="10" class="mr-1">mdi-circle</v-icon>
            <span class="text-truncate">{{ item.title }}</span>
          </v-card-title>
          <v-card-text class="pt-0">
            <div class="text-caption text-grey mb-1" v-if="item.office">
              <v-icon size="12" class="mr-1">mdi-office-building</v-icon>
              {{ item.office }}
            </div>
            <div class="text-body-2 mb-2" v-if="item.summary || item.body">
              {{ (item.summary || item.body || '').substring(0, 150) }}{{ (item.summary || item.body || '').length > 150 ? '...' : '' }}
            </div>
            <div class="d-flex flex-wrap ga-1">
              <v-chip v-for="t in (item.topics || []).slice(0, 4)" :key="t" size="x-small" variant="outlined">{{ t }}</v-chip>
            </div>
            <div class="text-caption text-grey mt-2" v-if="category === 'opportunities' && item.close_date">
              Closes: {{ fmtDate(item.close_date) }}
            </div>
            <div class="text-caption text-grey mt-2" v-if="category === 'programs' && item.status">
              <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">{{ item.status }}</v-chip>
            </div>
            <div class="text-caption text-grey mt-2" v-if="category === 'news' && item.publish_date">
              {{ fmtDate(item.publish_date) }}
            </div>
            <div class="text-caption text-grey mt-2" v-if="category === 'events' && item.event_date">
              {{ fmtDate(item.event_date) }} {{ item.location ? '| ' + item.location : '' }}
            </div>
          </v-card-text>
        </v-card>
      </div>

      <!-- Load more -->
      <div v-if="items.length < total" class="text-center mt-4">
        <v-btn variant="text" color="blue" @click="$emit('loadMore')">
          Load more ({{ items.length }}/{{ total }})
        </v-btn>
      </div>
    </div>
  `,
  methods: {
    fmtDate(d) {
      if (!d) return ''
      try {
        return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
      } catch { return d }
    },
    statusColor(s) {
      if (!s) return 'grey'
      const sl = s.toLowerCase()
      if (sl.includes('active') || sl.includes('ongoing')) return 'green'
      if (sl.includes('completed') || sl.includes('closed')) return 'grey'
      if (sl.includes('new') || sl.includes('proposed')) return 'blue'
      return 'orange'
    },
  },
}

import api from '@src/api'
import { useSettingsStore } from '@src/stores/settings'

export default {
  name: 'DarpaMonitorView',
  components: { ItemList },
  data() {
    return {
      activeTab: 'opportunities',
      viewMode: localStorage.getItem('darpa_view_mode') || 'table',
      loading: false,
      scraping: false,
      items: [],
      total: 0,
      offset: 0,

      // Filters
      searchQuery: '',
      filterOffice: null,
      filterTopic: null,
      newOnly: false,

      // Filter options
      offices: [],
      topics: [],

      // Stats
      stats: null,
      lastScrape: null,
      scrapeStats: null,

      // Settings
      scrapeFrequency: 'daily',
      frequencyOptions: [
        { title: 'Every hour', value: 'hourly' },
        { title: 'Once a day', value: 'daily' },
        { title: 'Once a week', value: 'weekly' },
        { title: 'Manual only', value: 'manual' },
      ],

      // Detail dialog
      detailOpen: false,
      detailItem: null,

      // Clear confirmation
      confirmClear: false,
      deleteConfirmText: '',

      // Snackbar
      snack: false,
      snackText: '',
      snackColor: 'success',
    }
  },

  watch: {
    activeTab(val) {
      if (val !== 'settings') {
        this.offset = 0
        this.items = []
        this.loadItems()
      }
    },
    viewMode(val) {
      localStorage.setItem('darpa_view_mode', val)
    },
    filterOffice() { this.offset = 0; this.items = []; this.loadItems() },
    filterTopic() { this.offset = 0; this.items = []; this.loadItems() },
    newOnly() { this.offset = 0; this.items = []; this.loadItems() },
  },

  async mounted() {
    // Load persisted view mode
    const saved = localStorage.getItem('darpa_view_mode')
    if (saved) this.viewMode = saved

    // Load settings
    const settingsStore = useSettingsStore()
    await settingsStore.fetchSystemSettings()
    this.scrapeFrequency = settingsStore.systemSettings?.darpa_scrape_frequency || 'daily'

    await Promise.all([
      this.loadStats(),
      this.loadScrapeStatus(),
      this.loadFilterOptions(),
      this.loadItems(),
    ])
  },

  methods: {
    // ---------- Data loading ----------

    async loadItems() {
      if (this.activeTab === 'settings') return
      this.loading = true
      try {
        const params = {
          category: this.activeTab,
          limit: 50,
          offset: this.offset,
        }
        if (this.searchQuery) params.search = this.searchQuery
        if (this.filterOffice) params.office = this.filterOffice
        if (this.filterTopic) params.topic = this.filterTopic
        if (this.newOnly) params.new_only = true

        const { data } = await api.get('/addons/darpa_monitor/items', { params })
        if (this.offset === 0) {
          this.items = data.items
        } else {
          this.items.push(...data.items)
        }
        this.total = data.total
      } catch (e) {
        this.showSnack('Failed to load items: ' + (e.response?.data?.detail || e.message), 'error')
      } finally {
        this.loading = false
      }
    },

    loadMore() {
      this.offset += 50
      this.loadItems()
    },

    async loadStats() {
      try {
        const { data } = await api.get('/addons/darpa_monitor/stats')
        this.stats = data.categories
        this.lastScrape = data.last_scrape
      } catch (e) {
        // Stats may not exist yet if never scraped
      }
    },

    async loadScrapeStatus() {
      try {
        const { data } = await api.get('/addons/darpa_monitor/scrape/status')
        if (data.last_scrape) {
          this.lastScrape = data.last_scrape.timestamp
          this.scrapeStats = data.last_scrape.stats
        }
      } catch (e) {
        // May not exist yet
      }
    },

    async loadFilterOptions() {
      try {
        const [officesRes, topicsRes] = await Promise.all([
          api.get('/addons/darpa_monitor/offices'),
          api.get('/addons/darpa_monitor/topics'),
        ])
        this.offices = officesRes.data.offices || []
        this.topics = topicsRes.data.topics || []
      } catch (e) {
        // Filter options may not exist yet
      }
    },

    // ---------- Scrape ----------

    async triggerScrape() {
      this.scraping = true
      try {
        const { data } = await api.post('/addons/darpa_monitor/scrape')
        this.scrapeStats = data.stats

        // Compute totals
        let totalNew = 0, totalUpdated = 0
        for (const s of Object.values(data.stats)) {
          totalNew += s.new || 0
          totalUpdated += s.updated || 0
        }
        this.showSnack(`Scrape complete: ${totalNew} new, ${totalUpdated} updated`, 'success')

        // Refresh everything
        await Promise.all([
          this.loadStats(),
          this.loadScrapeStatus(),
          this.loadFilterOptions(),
        ])
        this.offset = 0
        this.items = []
        await this.loadItems()
      } catch (e) {
        this.showSnack('Scrape failed: ' + (e.response?.data?.detail || e.message), 'error')
      } finally {
        this.scraping = false
      }
    },

    // ---------- Settings ----------

    async saveSetting(key, value) {
      try {
        const settingsStore = useSettingsStore()
        await settingsStore.updateSystemSetting(key, value)
        this.showSnack('Setting saved', 'success')
      } catch (e) {
        this.showSnack('Failed to save setting', 'error')
      }
    },

    // ---------- Clear ----------

    async clearAll() {
      try {
        await api.delete('/addons/darpa_monitor/items')
        this.confirmClear = false
        this.deleteConfirmText = ''
        this.items = []
        this.total = 0
        this.stats = null
        this.showSnack('All DARPA data cleared', 'success')
      } catch (e) {
        this.showSnack('Clear failed: ' + (e.response?.data?.detail || e.message), 'error')
      }
    },

    // ---------- Detail ----------

    openItem(item) {
      this.detailItem = item
      this.detailOpen = true
    },

    // ---------- Formatting ----------

    formatDate(d) {
      if (!d) return ''
      try {
        return new Date(d).toLocaleString('en-US', {
          year: 'numeric', month: 'short', day: 'numeric',
          hour: '2-digit', minute: '2-digit',
        })
      } catch { return d }
    },

    categoryColor(cat) {
      const colors = {
        opportunities: 'orange',
        programs: 'blue',
        news: 'green',
        events: 'purple',
      }
      return colors[cat] || 'grey'
    },

    categoryIcon(cat) {
      const icons = {
        opportunities: 'mdi-file-document-outline',
        programs: 'mdi-flask-outline',
        news: 'mdi-newspaper-variant-outline',
        events: 'mdi-calendar-star',
      }
      return icons[cat] || 'mdi-information'
    },

    categoryLabel(cat) {
      const labels = {
        opportunities: 'Opportunities',
        programs: 'Programs',
        news: 'News',
        events: 'Events',
      }
      return labels[cat] || cat
    },

    newCount(cat) {
      return this.stats?.[cat]?.new || 0
    },

    showSnack(text, color = 'success') {
      this.snackText = text
      this.snackColor = color
      this.snack = true
    },
  },
}
</script>

<style scoped>
.darpa-body {
  line-height: 1.6;
}
.darpa-body h1, .darpa-body h2, .darpa-body h3, .darpa-body h4 {
  margin-top: 1em;
  margin-bottom: 0.5em;
}
.darpa-body p {
  margin-bottom: 0.8em;
}
.darpa-body ul, .darpa-body ol {
  padding-left: 1.5em;
  margin-bottom: 0.8em;
}
</style>
