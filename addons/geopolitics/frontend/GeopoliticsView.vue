<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <v-row class="mb-4" align="center">
      <v-col>
        <div class="d-flex align-center ga-3">
          <v-icon size="32" color="red-darken-2">mdi-earth</v-icon>
          <div>
            <h1 class="text-h4 font-weight-bold">Geopolitics Monitor</h1>
            <p class="text-subtitle-2 text-medium-emphasis mb-0">
              Track global news, Pentagon open sources &amp; geopolitical intelligence
            </p>
          </div>
        </div>
      </v-col>
      <v-col cols="auto" class="d-flex ga-2 align-center">
        <v-select
          v-model="summaryLang"
          :items="summaryLangs"
          item-title="label"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          style="max-width: 140px"
        />
        <v-btn color="amber-darken-3" variant="flat" :loading="summarizing" @click="summarizeDay" size="small">
          <v-icon start>mdi-text-box-search-outline</v-icon> Summarize Today
        </v-btn>
        <v-btn color="deep-purple" variant="flat" :loading="summarizingMonth" @click="summarizeMonth" size="small">
          <v-icon start>mdi-calendar-month</v-icon> Monthly
        </v-btn>
        <v-chip variant="tonal" color="red-darken-2">
          <v-icon start>mdi-newspaper</v-icon>
          {{ stats.news_articles || 0 }} articles
        </v-chip>
        <v-chip variant="tonal" color="blue-grey">
          <v-icon start>mdi-shield-star</v-icon>
          {{ stats.pentagon_items || 0 }} DoD items
        </v-chip>
      </v-col>
    </v-row>

    <!-- Tabs -->
    <v-tabs v-model="tab" color="red-darken-2" class="mb-4">
      <v-tab value="summaries">
        <v-icon start>mdi-text-box-multiple-outline</v-icon> Summaries
        <v-badge v-if="summaries.length" :content="summaries.length" color="amber-darken-3" inline class="ml-1" />
      </v-tab>
      <v-tab value="news">
        <v-icon start>mdi-newspaper-variant-outline</v-icon> News Feed
      </v-tab>
      <v-tab value="pentagon">
        <v-icon start>mdi-shield-star-outline</v-icon> Pentagon
      </v-tab>
      <v-tab value="sources">
        <v-icon start>mdi-rss</v-icon> Sources
      </v-tab>
      <v-tab value="bookmarks">
        <v-icon start>mdi-bookmark-outline</v-icon> Bookmarks
      </v-tab>
      <v-tab value="settings">
        <v-icon start>mdi-cog</v-icon> Settings
      </v-tab>
    </v-tabs>

    <!-- ========== News Feed Tab ========== -->
    <div v-if="tab === 'news'">
      <v-row class="mb-4" align="center">
        <v-col cols="12" md="4">
          <v-text-field
            v-model="newsSearch"
            label="Search news..."
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-magnify"
            clearable
            hide-details
          />
        </v-col>
        <v-col cols="auto">
          <v-select
            v-model="newsCategory"
            :items="['all', 'wire', 'analysis', 'defense', 'think_tank', 'general']"
            label="Category"
            variant="outlined"
            density="compact"
            hide-details
            style="min-width: 150px"
          />
        </v-col>
        <v-col cols="auto">
          <v-btn color="red-darken-2" variant="flat" :loading="scraping" @click="scrapeNews">
            <v-icon start>mdi-refresh</v-icon> Scrape News
          </v-btn>
        </v-col>
        <v-col cols="auto">
          <v-btn variant="tonal" @click="addNewsDialog = true">
            <v-icon start>mdi-plus</v-icon> Add Manually
          </v-btn>
        </v-col>
      </v-row>

      <v-card v-if="filteredNews.length === 0" variant="outlined" class="text-center pa-8">
        <v-icon size="64" color="grey">mdi-newspaper-variant-outline</v-icon>
        <p class="text-h6 mt-4">No news articles yet</p>
        <p class="text-medium-emphasis">Click "Scrape News" to fetch from configured sources, or add articles manually.</p>
      </v-card>

      <div v-else>
        <v-card
          v-for="article in filteredNews"
          :key="article._id"
          variant="outlined"
          class="mb-3"
        >
          <v-card-text class="d-flex align-start ga-3">
            <div class="flex-grow-1">
              <div class="d-flex align-center ga-2 mb-1">
                <v-chip :color="categoryColor(article.category)" size="x-small" variant="flat">
                  {{ article.category }}
                </v-chip>
                <v-chip size="x-small" variant="tonal" color="blue-grey">
                  {{ article.source_name }}
                </v-chip>
                <v-chip
                  v-if="article.importance === 'high'"
                  size="x-small"
                  variant="flat"
                  color="red"
                >HIGH</v-chip>
                <v-spacer />
                <span class="text-caption text-medium-emphasis">
                  {{ formatDate(article.published_at) }}
                </span>
              </div>
              <h3 class="text-subtitle-1 font-weight-medium mb-1">
                <a v-if="article.url" :href="article.url" target="_blank" class="text-decoration-none" style="color: inherit">
                  {{ article.title }}
                  <v-icon size="x-small" class="ml-1">mdi-open-in-new</v-icon>
                </a>
                <span v-else>{{ article.title }}</span>
              </h3>
              <p v-if="article.summary" class="text-body-2 text-medium-emphasis mb-1">
                {{ article.summary.substring(0, 300) }}{{ article.summary.length > 300 ? '...' : '' }}
              </p>
              <div v-if="article.tags?.length" class="d-flex ga-1 flex-wrap">
                <v-chip v-for="t in article.tags" :key="t" size="x-small" variant="tonal">{{ t }}</v-chip>
              </div>
            </div>
            <div class="d-flex flex-column ga-1">
              <v-btn icon size="x-small" variant="text" @click="toggleBookmark(article._id)">
                <v-icon :color="isBookmarked(article._id) ? 'amber' : 'grey'">
                  {{ isBookmarked(article._id) ? 'mdi-bookmark' : 'mdi-bookmark-outline' }}
                </v-icon>
              </v-btn>
              <v-btn icon size="x-small" variant="text" color="red" @click="deleteArticle(article._id)">
                <v-icon>mdi-delete-outline</v-icon>
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </div>

      <!-- Add News Dialog -->
      <v-dialog v-model="addNewsDialog" max-width="600">
        <v-card>
          <v-card-title>Add News Article</v-card-title>
          <v-card-text>
            <v-text-field v-model="newArticle.title" label="Title" variant="outlined" class="mb-3" />
            <v-text-field v-model="newArticle.url" label="URL" variant="outlined" class="mb-3" />
            <v-row>
              <v-col cols="6">
                <v-text-field v-model="newArticle.source_name" label="Source" variant="outlined" />
              </v-col>
              <v-col cols="6">
                <v-select
                  v-model="newArticle.category"
                  :items="['wire', 'analysis', 'defense', 'think_tank', 'general']"
                  label="Category"
                  variant="outlined"
                />
              </v-col>
            </v-row>
            <v-textarea v-model="newArticle.summary" label="Summary" variant="outlined" rows="3" class="mb-3" />
            <v-select
              v-model="newArticle.importance"
              :items="['low', 'medium', 'high']"
              label="Importance"
              variant="outlined"
              class="mb-3"
            />
            <v-combobox v-model="newArticle.tags" label="Tags" variant="outlined" multiple chips closable-chips />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn @click="addNewsDialog = false">Cancel</v-btn>
            <v-btn color="red-darken-2" variant="flat" @click="createArticle">Add</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>

    <!-- ========== Pentagon Tab ========== -->
    <div v-if="tab === 'pentagon'">
      <v-row class="mb-4" align="center">
        <v-col cols="12" md="4">
          <v-text-field
            v-model="pentagonSearch"
            label="Search Pentagon sources..."
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-magnify"
            clearable
            hide-details
          />
        </v-col>
        <v-col cols="auto">
          <v-select
            v-model="pentagonType"
            :items="['all', 'news', 'releases', 'transcripts', 'contracts', 'advisories', 'centcom', 'eucom', 'indopacom', 'crs_reports', 'sipri']"
            label="Source Type"
            variant="outlined"
            density="compact"
            hide-details
            style="min-width: 170px"
          />
        </v-col>
        <v-col cols="auto">
          <v-btn color="blue-grey" variant="flat" :loading="scrapingPentagon" @click="scrapePentagon">
            <v-icon start>mdi-refresh</v-icon> Scrape Pentagon
          </v-btn>
        </v-col>
      </v-row>

      <!-- Pentagon official sources -->
      <v-expansion-panels variant="accordion" class="mb-4">
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon start color="blue-grey">mdi-shield-star</v-icon>
            <strong>Pentagon Open Sources ({{ pentagonSources.length }})</strong>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-table density="compact">
              <thead>
                <tr><th>Source</th><th>Type</th><th>URL</th></tr>
              </thead>
              <tbody>
                <tr v-for="s in pentagonSources" :key="s.name">
                  <td class="font-weight-medium">{{ s.name }}</td>
                  <td><v-chip size="x-small" variant="tonal">{{ s.type }}</v-chip></td>
                  <td><a :href="s.url" target="_blank" class="text-caption">{{ s.url }}</a></td>
                </tr>
              </tbody>
            </v-table>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <v-card v-if="filteredPentagon.length === 0" variant="outlined" class="text-center pa-8">
        <v-icon size="64" color="grey">mdi-shield-off-outline</v-icon>
        <p class="text-h6 mt-4">No Pentagon data yet</p>
        <p class="text-medium-emphasis">Click "Scrape Pentagon" to fetch from open DoD sources.</p>
      </v-card>

      <v-card
        v-for="item in filteredPentagon"
        :key="item._id"
        variant="outlined"
        class="mb-3"
      >
        <v-card-text class="d-flex align-start ga-3 py-3">
          <v-icon size="small" color="blue-grey" class="mt-1">mdi-shield-star</v-icon>
          <div class="flex-grow-1">
            <div class="d-flex align-center ga-2 mb-1">
              <v-chip size="x-small" variant="tonal" color="blue-grey">{{ item.source_type }}</v-chip>
              <v-chip size="x-small" variant="tonal">{{ item.source_name }}</v-chip>
              <v-spacer />
              <span class="text-caption text-medium-emphasis">{{ formatDate(item.published_at) }}</span>
            </div>
            <a v-if="item.url" :href="item.url" target="_blank" class="text-subtitle-2 font-weight-medium text-decoration-none" style="color: inherit">
              {{ decodeHtml(item.title) }}
              <v-icon size="x-small" class="ml-1">mdi-open-in-new</v-icon>
            </a>
            <span v-else class="text-subtitle-2 font-weight-medium">{{ decodeHtml(item.title) }}</span>
            <p v-if="item.summary" class="text-body-2 text-medium-emphasis mt-1 mb-1">
              {{ decodeHtml(item.summary).substring(0, 400) }}{{ item.summary.length > 400 ? '...' : '' }}
            </p>
            <div v-if="item.tags?.length" class="d-flex ga-1 flex-wrap mt-1">
              <v-chip v-for="t in item.tags" :key="t" size="x-small" variant="tonal">{{ t }}</v-chip>
            </div>
          </div>
          <v-btn icon size="x-small" variant="text" color="red" @click="deletePentagonItem(item._id)">
            <v-icon size="small">mdi-delete-outline</v-icon>
          </v-btn>
        </v-card-text>
      </v-card>
    </div>

    <!-- ========== Sources Tab ========== -->
    <div v-if="tab === 'sources'">
      <v-row class="mb-4">
        <v-col>
          <v-btn color="red-darken-2" variant="flat" @click="addSourceDialog = true" class="mr-2">
            <v-icon start>mdi-plus</v-icon> Add Source
          </v-btn>
          <v-btn variant="tonal" @click="seedSources">
            <v-icon start>mdi-database-refresh</v-icon> Seed Defaults
          </v-btn>
        </v-col>
      </v-row>

      <v-table density="compact">
        <thead>
          <tr>
            <th>Name</th>
            <th>Category</th>
            <th>URL</th>
            <th>RSS</th>
            <th>Enabled</th>
            <th width="50"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sources" :key="s._id">
            <td class="font-weight-medium">{{ s.name }}</td>
            <td><v-chip :color="categoryColor(s.category)" size="x-small" variant="tonal">{{ s.category }}</v-chip></td>
            <td class="text-caption"><a :href="s.url" target="_blank">{{ s.url }}</a></td>
            <td class="text-caption">
              <v-icon v-if="s.rss" size="small" color="green">mdi-check-circle</v-icon>
              <v-icon v-else size="small" color="grey">mdi-minus-circle-outline</v-icon>
            </td>
            <td>
              <v-switch
                :model-value="s.enabled"
                density="compact"
                hide-details
                color="green"
                @update:model-value="toggleSource(s._id, $event)"
              />
            </td>
            <td>
              <v-btn icon size="x-small" variant="text" color="red" @click="deleteSource(s._id)">
                <v-icon size="small">mdi-delete</v-icon>
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>

      <!-- Add Source Dialog -->
      <v-dialog v-model="addSourceDialog" max-width="500">
        <v-card>
          <v-card-title>Add News Source</v-card-title>
          <v-card-text>
            <v-text-field v-model="newSource.name" label="Name" variant="outlined" class="mb-3" />
            <v-text-field v-model="newSource.url" label="Website URL" variant="outlined" class="mb-3" />
            <v-text-field v-model="newSource.rss" label="RSS Feed URL (optional)" variant="outlined" class="mb-3" />
            <v-select
              v-model="newSource.category"
              :items="['wire', 'analysis', 'defense', 'think_tank', 'general']"
              label="Category"
              variant="outlined"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn @click="addSourceDialog = false">Cancel</v-btn>
            <v-btn color="red-darken-2" variant="flat" @click="createSource">Add</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>

    <!-- ========== Bookmarks Tab ========== -->
    <div v-if="tab === 'bookmarks'">
      <v-card v-if="bookmarkedArticles.length === 0" variant="outlined" class="text-center pa-8">
        <v-icon size="64" color="grey">mdi-bookmark-off-outline</v-icon>
        <p class="text-h6 mt-4">No bookmarks yet</p>
        <p class="text-medium-emphasis">Bookmark articles from the News Feed tab to save them here.</p>
      </v-card>

      <v-card
        v-for="article in bookmarkedArticles"
        :key="article._id"
        variant="outlined"
        class="mb-3"
      >
        <v-card-text>
          <div class="d-flex align-center ga-2 mb-1">
            <v-icon size="small" color="amber">mdi-bookmark</v-icon>
            <v-chip :color="categoryColor(article.category)" size="x-small" variant="flat">{{ article.category }}</v-chip>
            <v-chip size="x-small" variant="tonal">{{ article.source_name }}</v-chip>
            <v-spacer />
            <span class="text-caption text-medium-emphasis">{{ formatDate(article.published_at) }}</span>
          </div>
          <h3 class="text-subtitle-1 font-weight-medium">
            <a v-if="article.url" :href="article.url" target="_blank" class="text-decoration-none" style="color: inherit">
              {{ decodeHtml(article.title) }} <v-icon size="x-small">mdi-open-in-new</v-icon>
            </a>
            <span v-else>{{ decodeHtml(article.title) }}</span>
          </h3>
          <p v-if="article.summary" class="text-body-2 text-medium-emphasis mt-1">{{ decodeHtml(article.summary).substring(0, 200) }}</p>
        </v-card-text>
      </v-card>
    </div>

    <!-- ========== Summaries History Tab ========== -->
    <div v-if="tab === 'summaries'">
      <v-row class="mb-4" align="center">
        <v-col>
          <span class="text-subtitle-2 text-medium-emphasis">{{ summaries.length }} saved briefing{{ summaries.length !== 1 ? 's' : '' }}</span>
        </v-col>
        <v-col cols="auto" class="d-flex ga-2 align-center">
          <v-btn color="amber-darken-3" variant="flat" size="small" :loading="summarizing" @click="summarizeDay">
            <v-icon start>mdi-plus</v-icon> Daily
          </v-btn>
          <v-btn color="deep-purple" variant="flat" size="small" :loading="summarizingMonth" @click="summarizeMonth">
            <v-icon start>mdi-calendar-month</v-icon> Monthly
          </v-btn>
          <v-btn v-if="summaries.length" color="red" variant="outlined" size="small" @click="clearSummaries">
            <v-icon start>mdi-delete-forever</v-icon> Clear All
          </v-btn>
        </v-col>
      </v-row>

      <v-card v-if="summaries.length === 0" variant="outlined" class="text-center pa-8">
        <v-icon size="64" color="grey">mdi-text-box-remove-outline</v-icon>
        <p class="text-h6 mt-4">No summaries yet</p>
        <p class="text-medium-emphasis">Click "Summarize Today" to generate your first daily intelligence briefing.</p>
      </v-card>

      <v-card
        v-for="s in summaries"
        :key="s._id"
        variant="outlined"
        class="mb-3"
      >
        <v-card-title class="d-flex align-center ga-2" style="cursor: pointer" @click="s._expanded = !s._expanded">
          <v-icon :color="s._expanded ? 'amber-darken-3' : 'grey'">{{ s._expanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
          <v-icon size="small" color="amber-darken-3">mdi-text-box-search-outline</v-icon>
          <span class="text-subtitle-1 font-weight-medium">{{ formatDate(s.created_at) }}</span>
          <v-spacer />
          <v-chip size="x-small" variant="tonal" v-if="s.model">{{ s.model }}</v-chip>
          <v-chip size="x-small" variant="tonal" color="blue">{{ s.news_count || 0 }} news</v-chip>
          <v-chip size="x-small" variant="tonal" color="blue-grey">{{ s.pentagon_count || 0 }} DoD</v-chip>
          <v-chip v-if="s.language" size="x-small" variant="tonal" color="purple">{{ s.language }}</v-chip>
          <v-chip size="x-small" variant="flat" :color="s.scope === 'monthly' ? 'deep-purple' : 'amber-darken-3'">{{ s.scope === 'monthly' ? 'Monthly' : 'Daily' }}</v-chip>
          <v-btn icon size="x-small" variant="text" color="red" @click.stop="deleteSummary(s._id)">
            <v-icon size="small">mdi-delete</v-icon>
          </v-btn>
        </v-card-title>
        <v-expand-transition>
          <div v-if="s._expanded">
            <v-divider />
            <v-card-text style="max-height: 60vh; overflow-y: auto;">
              <div v-html="renderMarkdown(s.summary)" class="summary-content" />
            </v-card-text>
          </div>
        </v-expand-transition>
      </v-card>
    </div>

    <!-- ========== Settings Tab ========== -->
    <div v-if="tab === 'settings'">
      <v-row>
        <v-col cols="12" md="8">
          <v-card variant="outlined">
            <v-card-title>
              <v-icon start>mdi-cog</v-icon> Geopolitics Settings
            </v-card-title>
            <v-card-text>
              <v-select
                v-model="settingsForm.geopolitics_scrape_interval"
                :items="[{title: '15 min', value: '15'}, {title: '30 min', value: '30'}, {title: '1 hour', value: '60'}, {title: '2 hours', value: '120'}, {title: '6 hours', value: '360'}, {title: '12 hours', value: '720'}, {title: '24 hours', value: '1440'}]"
                label="Scraping Interval"
                variant="outlined"
                class="mb-3"
              />
              <v-textarea
                v-model="settingsForm.geopolitics_news_sources"
                label="News Sources (comma-separated URLs)"
                variant="outlined"
                rows="2"
                class="mb-3"
                hint="Additional source URLs to monitor"
                persistent-hint
              />
              <v-textarea
                v-model="settingsForm.geopolitics_keywords"
                label="Keywords Filter (comma-separated)"
                variant="outlined"
                rows="2"
                class="mb-3"
                hint="Only articles matching these keywords will be saved. Leave empty for all."
                persistent-hint
              />
              <v-select
                v-model="settingsForm.geopolitics_pentagon_enabled"
                :items="[{title: 'Enabled', value: 'true'}, {title: 'Disabled', value: 'false'}]"
                label="Pentagon Source Monitoring"
                variant="outlined"
                class="mb-3"
              />
              <v-select
                v-model="settingsForm.geopolitics_max_articles"
                :items="['10', '25', '50', '100']"
                label="Max Articles per Source"
                variant="outlined"
                class="mb-3"
              />
              <v-btn color="red-darken-2" variant="flat" @click="saveSettings">
                <v-icon start>mdi-content-save</v-icon> Save Settings
              </v-btn>
            </v-card-text>
          </v-card>

          <!-- Stats -->
          <v-card variant="outlined" class="mt-4">
            <v-card-title>
              <v-icon start>mdi-chart-bar</v-icon> Statistics
            </v-card-title>
            <v-card-text>
              <v-list density="compact">
                <v-list-item>
                  <v-list-item-title>News Articles</v-list-item-title>
                  <template #append><strong>{{ stats.news_articles || 0 }}</strong></template>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Pentagon Items</v-list-item-title>
                  <template #append><strong>{{ stats.pentagon_items || 0 }}</strong></template>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Configured Sources</v-list-item-title>
                  <template #append><strong>{{ stats.sources || 0 }}</strong></template>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Bookmarks</v-list-item-title>
                  <template #append><strong>{{ stats.bookmarks || 0 }}</strong></template>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Last News Scrape</v-list-item-title>
                  <template #append>
                    <span class="text-caption">{{ stats.last_scrape ? new Date(stats.last_scrape).toLocaleString() : 'Never' }}</span>
                  </template>
                </v-list-item>
                <v-list-item>
                  <v-list-item-title>Last Pentagon Scrape</v-list-item-title>
                  <template #append>
                    <span class="text-caption">{{ stats.last_pentagon_scrape ? new Date(stats.last_pentagon_scrape).toLocaleString() : 'Never' }}</span>
                  </template>
                </v-list-item>
              </v-list>
            </v-card-text>
          </v-card>

          <!-- Danger -->
          <v-card variant="outlined" class="mt-4">
            <v-card-title class="text-red">
              <v-icon start color="red">mdi-alert</v-icon> Danger Zone
            </v-card-title>
            <v-card-text>
              <div class="d-flex ga-2 flex-wrap">
                <v-btn color="orange" variant="outlined" size="small" @click="clearNews">
                  <v-icon start>mdi-delete</v-icon> Clear News
                </v-btn>
                <v-btn color="orange" variant="outlined" size="small" @click="clearPentagon">
                  <v-icon start>mdi-delete</v-icon> Clear Pentagon
                </v-btn>
                <v-btn color="red" variant="outlined" size="small" @click="clearAll">
                  <v-icon start>mdi-delete-forever</v-icon> Clear All Data
                </v-btn>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </div>

    <!-- Summary Dialog -->
    <v-dialog v-model="summaryDialog" max-width="900" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center ga-2">
          <v-icon color="amber-darken-3">mdi-text-box-search-outline</v-icon>
          Daily Intelligence Briefing
          <v-spacer />
          <v-chip v-if="summaryMeta.model" size="small" variant="tonal">{{ summaryMeta.model }}</v-chip>
          <v-chip size="small" variant="tonal" color="blue">{{ summaryMeta.news_count || 0 }} news</v-chip>
          <v-chip size="small" variant="tonal" color="blue-grey">{{ summaryMeta.pentagon_count || 0 }} DoD</v-chip>
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height: 70vh; overflow-y: auto;">
          <div v-if="summaryText" v-html="renderMarkdown(summaryText)" class="summary-content" />
          <div v-else class="text-center pa-8 text-medium-emphasis">No summary generated yet.</div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="summaryDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </v-container>
</template>

<script>
import api from '@src/api'
import { useSettingsStore } from '@src/stores/settings'

const API = '/addons/geopolitics'

export default {
  name: 'GeopoliticsView',

  data() {
    return {
      tab: localStorage.getItem('geopolitics_tab') || 'news',
      news: [],
      pentagonItems: [],
      pentagonSources: [],
      sources: [],
      summaries: [],
      bookmarkIds: new Set(),
      stats: {},

      // Filters
      newsSearch: '',
      newsCategory: 'all',
      pentagonSearch: '',
      pentagonType: 'all',

      // Summary language
      summaryLang: localStorage.getItem('geopolitics_summary_lang') || 'English',
      summaryLangs: [
        { label: '🇺🇸 English', value: 'English' },
        { label: '🇺🇦 Ukrainian-Russian', value: 'Russian' },
        { label: '🇺🇦 Ukrainian', value: 'Ukrainian' },
        { label: '🇨🇳 Chinese', value: 'Chinese' },
        { label: '🇪🇸 Spanish', value: 'Spanish' },
        { label: '🇫🇷 French', value: 'French' },
        { label: '🇩🇪 German', value: 'German' },
        { label: '🇯🇵 Japanese', value: 'Japanese' },
        { label: '🇰🇷 Korean', value: 'Korean' },
        { label: '🇸🇦 Arabic', value: 'Arabic' },
      ],

      // Loading
      scraping: false,
      scrapingPentagon: false,
      summarizing: false,
      summarizingMonth: false,

      // Dialogs
      addNewsDialog: false,
      addSourceDialog: false,
      summaryDialog: false,
      summaryText: '',
      summaryMeta: {},

      // Forms
      newArticle: { title: '', url: '', source_name: '', category: 'general', summary: '', importance: 'medium', tags: [] },
      newSource: { name: '', url: '', rss: '', category: 'general' },

      // Settings
      settingsForm: {
        geopolitics_scrape_interval: '60',
        geopolitics_news_sources: 'https://www.reuters.com,https://apnews.com,https://www.bbc.com/news',
        geopolitics_keywords: 'geopolitics,sanctions,military,nato,defense,conflict,treaty,diplomacy',
        geopolitics_pentagon_enabled: 'true',
        geopolitics_max_articles: '25',
      },

      snackbar: { show: false, text: '', color: 'success' },
    }
  },

  computed: {
    filteredNews() {
      let items = this.news
      if (this.newsCategory !== 'all') {
        items = items.filter(a => a.category === this.newsCategory)
      }
      if (this.newsSearch) {
        const q = this.newsSearch.toLowerCase()
        items = items.filter(a =>
          (a.title || '').toLowerCase().includes(q) ||
          (a.summary || '').toLowerCase().includes(q) ||
          (a.source_name || '').toLowerCase().includes(q)
        )
      }
      return items
    },

    filteredPentagon() {
      let items = this.pentagonItems
      if (this.pentagonType !== 'all') {
        items = items.filter(i => i.source_type === this.pentagonType)
      }
      if (this.pentagonSearch) {
        const q = this.pentagonSearch.toLowerCase()
        items = items.filter(i =>
          (i.title || '').toLowerCase().includes(q) ||
          (i.source_name || '').toLowerCase().includes(q)
        )
      }
      return items
    },

    bookmarkedArticles() {
      return this.news.filter(a => this.bookmarkIds.has(a._id))
    },
  },

  watch: {
    tab(v) { localStorage.setItem('geopolitics_tab', v) },
    summaryLang(v) { localStorage.setItem('geopolitics_summary_lang', v) },
  },

  async mounted() {
    await Promise.all([
      this.loadNews(),
      this.loadPentagon(),
      this.loadSources(),
      this.loadBookmarks(),
      this.loadPentagonSources(),
      this.loadSummaries(),
      this.loadStats(),
    ])
    this.loadSettings()
  },

  methods: {
    notify(text, color = 'success') {
      this.snackbar = { show: true, text, color }
    },

    decodeHtml(text) {
      if (!text) return ''
      const el = document.createElement('textarea')
      el.innerHTML = text
      return el.value
    },

    formatDate(d) {
      if (!d) return ''
      try { return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) }
      catch { return d }
    },

    categoryColor(cat) {
      return { wire: 'blue', analysis: 'deep-purple', defense: 'red-darken-2', think_tank: 'teal', general: 'grey' }[cat] || 'grey'
    },

    isBookmarked(id) { return this.bookmarkIds.has(id) },

    // News
    async loadNews() {
      try {
        const { data } = await api.get(`${API}/news?limit=100`)
        this.news = data.items || []
      } catch (e) { console.error(e) }
    },

    async createArticle() {
      try {
        await api.post(`${API}/news`, this.newArticle)
        this.addNewsDialog = false
        this.newArticle = { title: '', url: '', source_name: '', category: 'general', summary: '', importance: 'medium', tags: [] }
        this.notify('Article added')
        await this.loadNews()
      } catch (e) { this.notify(e.response?.data?.detail || 'Failed', 'error') }
    },

    async deleteArticle(id) {
      try {
        await api.delete(`${API}/news/${id}`)
        this.news = this.news.filter(a => a._id !== id)
        await this.loadStats()
      } catch (e) { this.notify('Delete failed', 'error') }
    },

    async scrapeNews() {
      this.scraping = true
      try {
        const { data } = await api.post(`${API}/scrape`)
        this.notify(`Scraped ${data.scraped} articles from ${data.sources_checked} sources`)
        await Promise.all([this.loadNews(), this.loadStats()])
      } catch (e) {
        this.notify(e.response?.data?.detail || 'Scrape failed', 'error')
      } finally { this.scraping = false }
    },

    // Pentagon
    async loadPentagon() {
      try {
        const { data } = await api.get(`${API}/pentagon?limit=100`)
        this.pentagonItems = data.items || []
      } catch (e) { console.error(e) }
    },

    async loadPentagonSources() {
      try {
        const { data } = await api.get(`${API}/pentagon/sources`)
        this.pentagonSources = data.items || []
      } catch (e) { console.error(e) }
    },

    async scrapePentagon() {
      this.scrapingPentagon = true
      try {
        const { data } = await api.post(`${API}/scrape-pentagon`)
        this.notify(`Scraped ${data.scraped} items from ${data.sources_checked} Pentagon sources`)
        await Promise.all([this.loadPentagon(), this.loadStats()])
      } catch (e) {
        this.notify(e.response?.data?.detail || 'Pentagon scrape failed', 'error')
      } finally { this.scrapingPentagon = false }
    },

    async deletePentagonItem(id) {
      try {
        await api.delete(`${API}/pentagon/${id}`)
        this.pentagonItems = this.pentagonItems.filter(i => i._id !== id)
        await this.loadStats()
      } catch (e) { this.notify('Delete failed', 'error') }
    },

    // Summarize
    async summarizeDay() {
      this.summarizing = true
      try {
        const { data } = await api.post(`${API}/summarize-day`, { language: this.summaryLang })
        await this.loadSummaries()
        this.tab = 'summaries'
        if (this.summaries.length > 0) {
          this.summaries[0]._expanded = true
        }
        this.notify('Daily briefing generated', 'success')
      } catch (e) {
        this.notify(e.response?.data?.detail || 'Summarization failed', 'error')
      } finally { this.summarizing = false }
    },

    async summarizeMonth() {
      this.summarizingMonth = true
      try {
        const { data } = await api.post(`${API}/summarize-month`, { language: this.summaryLang })
        await this.loadSummaries()
        this.tab = 'summaries'
        if (this.summaries.length > 0) {
          this.summaries[0]._expanded = true
        }
        this.notify('Monthly briefing generated', 'success')
      } catch (e) {
        this.notify(e.response?.data?.detail || 'Monthly summarization failed', 'error')
      } finally { this.summarizingMonth = false }
    },

    renderMarkdown(text) {
      if (!text) return ''
      // Simple markdown to HTML: bold, headers, bullets, line breaks
      return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^### (.+)$/gm, '<h4 class="mt-3 mb-1">$1</h4>')
        .replace(/^## (.+)$/gm, '<h3 class="mt-4 mb-2">$1</h3>')
        .replace(/^# (.+)$/gm, '<h2 class="mt-4 mb-2">$1</h2>')
        .replace(/^\- (.+)$/gm, '<li>$1</li>')
        .replace(/^\* (.+)$/gm, '<li>$1</li>')
        .replace(/^(\d+)\. (.+)$/gm, '<li><strong>$1.</strong> $2</li>')
        .replace(/(<li>.*<\/li>)/gs, '<ul style="margin-left:16px">$1</ul>')
        .replace(/<\/ul>\s*<ul[^>]*>/g, '')
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>')
    },

    // Sources
    async loadSources() {
      try {
        const { data } = await api.get(`${API}/sources`)
        this.sources = data.items || []
      } catch (e) { console.error(e) }
    },

    async createSource() {
      try {
        await api.post(`${API}/sources`, this.newSource)
        this.addSourceDialog = false
        this.newSource = { name: '', url: '', rss: '', category: 'general' }
        this.notify('Source added')
        await this.loadSources()
      } catch (e) { this.notify(e.response?.data?.detail || 'Failed', 'error') }
    },

    async toggleSource(id, enabled) {
      try {
        await api.patch(`${API}/sources/${id}`, { enabled })
        const s = this.sources.find(s => s._id === id)
        if (s) s.enabled = enabled
      } catch (e) { this.notify('Update failed', 'error') }
    },

    async deleteSource(id) {
      try {
        await api.delete(`${API}/sources/${id}`)
        this.notify('Source deleted')
        await this.loadSources()
      } catch (e) { this.notify('Delete failed', 'error') }
    },

    async seedSources() {
      try {
        const { data } = await api.post(`${API}/sources/seed`)
        this.notify(`Seeded ${data.added} new sources`)
        await this.loadSources()
      } catch (e) { this.notify('Seed failed', 'error') }
    },

    // Bookmarks
    async loadBookmarks() {
      try {
        const { data } = await api.get(`${API}/bookmarks`)
        this.bookmarkIds = new Set((data.items || []).map(b => b.article_id))
      } catch (e) { console.error(e) }
    },

    async toggleBookmark(articleId) {
      try {
        const { data } = await api.post(`${API}/bookmarks/${articleId}`)
        if (data.bookmarked) {
          this.bookmarkIds.add(articleId)
        } else {
          this.bookmarkIds.delete(articleId)
        }
        // Force reactivity
        this.bookmarkIds = new Set(this.bookmarkIds)
      } catch (e) { this.notify('Bookmark failed', 'error') }
    },

    // Summaries history
    async loadSummaries() {
      try {
        const { data } = await api.get(`${API}/summaries`)
        this.summaries = (data.items || []).map(s => ({ ...s, _expanded: false }))
      } catch (e) { console.error(e) }
    },

    async deleteSummary(id) {
      if (!confirm('Delete this summary?')) return
      try {
        await api.delete(`${API}/summaries/${id}`)
        this.summaries = this.summaries.filter(s => s._id !== id)
        this.notify('Summary deleted')
      } catch (e) { this.notify('Delete failed', 'error') }
    },

    async clearSummaries() {
      if (!confirm('Delete ALL saved summaries?')) return
      try {
        await api.delete(`${API}/clear-summaries`)
        this.summaries = []
        this.notify('Summaries cleared')
      } catch (e) { this.notify('Clear failed', 'error') }
    },

    // Stats
    async loadStats() {
      try {
        const { data } = await api.get(`${API}/stats`)
        this.stats = data
      } catch (e) { console.error(e) }
    },

    // Settings
    loadSettings() {
      const s = useSettingsStore()
      this.settingsForm.geopolitics_scrape_interval = s.systemSettings?.geopolitics_scrape_interval || '60'
      this.settingsForm.geopolitics_news_sources = s.systemSettings?.geopolitics_news_sources || 'https://www.reuters.com,https://apnews.com,https://www.bbc.com/news'
      this.settingsForm.geopolitics_keywords = s.systemSettings?.geopolitics_keywords || 'geopolitics,sanctions,military,nato,defense,conflict,treaty,diplomacy'
      this.settingsForm.geopolitics_pentagon_enabled = s.systemSettings?.geopolitics_pentagon_enabled || 'true'
      this.settingsForm.geopolitics_max_articles = s.systemSettings?.geopolitics_max_articles || '25'
    },

    async saveSettings() {
      const s = useSettingsStore()
      try {
        for (const [key, value] of Object.entries(this.settingsForm)) {
          await s.updateSystemSetting(key, value)
        }
        this.notify('Settings saved')
      } catch (e) { this.notify('Failed to save settings', 'error') }
    },

    // Clear
    async clearNews() {
      if (!confirm('Delete all news articles?')) return
      try {
        await api.delete(`${API}/clear-news`)
        this.notify('News cleared')
        await Promise.all([this.loadNews(), this.loadStats()])
      } catch (e) { this.notify('Clear failed', 'error') }
    },

    async clearPentagon() {
      if (!confirm('Delete all Pentagon data?')) return
      try {
        await api.delete(`${API}/clear-pentagon`)
        this.notify('Pentagon data cleared')
        await Promise.all([this.loadPentagon(), this.loadStats()])
      } catch (e) { this.notify('Clear failed', 'error') }
    },

    async clearAll() {
      if (!confirm('Delete ALL geopolitics data?')) return
      try {
        await api.delete(`${API}/clear`)
        this.notify('All data cleared')
        await Promise.all([this.loadNews(), this.loadPentagon(), this.loadBookmarks(), this.loadSummaries(), this.loadStats()])
      } catch (e) { this.notify('Clear failed', 'error') }
    },
  },
}
</script>
