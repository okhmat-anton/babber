<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <v-icon size="32" color="brown-lighten-1" class="mr-3">mdi-terrain</v-icon>
      <div class="text-h4 font-weight-bold">Real Estate — Affordable Land</div>
      <v-spacer />
      <v-btn
        color="brown"
        variant="tonal"
        prepend-icon="mdi-refresh"
        @click="scrapeAll"
        :loading="scraping"
        class="mr-2"
      >
        Scrape All
      </v-btn>
      <v-chip v-if="lastScrape" variant="tonal" color="grey" size="small">
        Last: {{ fmtDate(lastScrape) }}
      </v-chip>
    </div>

    <!-- Scrape progress banner -->
    <v-alert v-if="scrapeProgress && scrapeProgress.running" type="info" variant="tonal" density="compact" class="mb-3">
      <div class="d-flex align-center">
        <v-progress-circular indeterminate size="18" width="2" class="mr-2" />
        <span>
          Scraping <strong>{{ scrapeProgress.source || '...' }}</strong>
          — {{ scrapeProgress.states_done }}/{{ scrapeProgress.states_total }} states,
          {{ scrapeProgress.listings_found }} listings found
          <span v-if="scrapeProgress.errors"> ({{ scrapeProgress.errors }} errors)</span>
        </span>
      </div>
    </v-alert>

    <!-- Stats chips -->
    <div class="d-flex flex-wrap ga-2 mb-4" v-if="stats">
      <v-chip variant="tonal" color="brown" size="large">
        <v-icon start size="16">mdi-map-marker-multiple</v-icon>
        Listings: {{ stats.listings || 0 }}
      </v-chip>
      <v-chip variant="tonal" color="red" size="large">
        <v-icon start size="16">mdi-heart</v-icon>
        Favorites: {{ stats.favorites || 0 }}
      </v-chip>
      <v-chip variant="tonal" color="blue" size="large">
        <v-icon start size="16">mdi-web</v-icon>
        Sources: {{ stats.sources || 0 }}
      </v-chip>
      <v-chip v-if="stats.avg_price" variant="tonal" color="green" size="large">
        <v-icon start size="16">mdi-currency-usd</v-icon>
        Avg: ${{ fmtNum(stats.avg_price) }}
      </v-chip>
      <v-chip v-if="stats.min_price" variant="tonal" color="teal" size="large">
        Range: ${{ fmtNum(stats.min_price) }} — ${{ fmtNum(stats.max_price) }}
      </v-chip>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="brown-lighten-1" class="mb-4" show-arrows>
      <v-tab value="listings">
        <v-icon start size="18">mdi-terrain</v-icon>
        Affordable Land
      </v-tab>
      <v-tab value="favorites">
        <v-icon start size="18">mdi-heart-outline</v-icon>
        Favorites
      </v-tab>
      <v-tab value="sources">
        <v-icon start size="18">mdi-web</v-icon>
        Sources
      </v-tab>
      <v-tab value="settings">
        <v-icon start size="18">mdi-cog-outline</v-icon>
        Settings
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">

      <!-- ═══════════════════════════════════════ -->
      <!-- 1. AFFORDABLE LAND LISTINGS -->
      <!-- ═══════════════════════════════════════ -->
      <v-window-item value="listings">
        <!-- Filters row -->
        <div class="d-flex flex-wrap align-center ga-2 mb-3">
          <v-select
            v-model="filterSource"
            :items="sourceOptions"
            label="Source"
            variant="outlined"
            density="compact"
            clearable
            style="max-width: 200px"
          />
          <v-select
            v-model="filterState"
            :items="stateOptions"
            label="States"
            variant="outlined"
            density="compact"
            clearable
            multiple
            chips
            closable-chips
            style="min-width: 200px; max-width: 400px"
          />
          <v-text-field
            v-model.number="filterMaxPrice"
            label="Max Price"
            variant="outlined"
            density="compact"
            type="number"
            prefix="$"
            clearable
            style="max-width: 160px"
          />
          <v-text-field
            v-model.number="filterMinAcreage"
            label="Min Acres"
            variant="outlined"
            density="compact"
            type="number"
            clearable
            style="max-width: 140px"
          />
          <v-select
            v-model="sortBy"
            :items="sortOptions"
            label="Sort"
            variant="outlined"
            density="compact"
            style="max-width: 160px"
          />
          <v-btn-toggle v-model="sortDir" mandatory density="compact" variant="outlined" color="brown">
            <v-btn value="asc" size="small"><v-icon>mdi-sort-ascending</v-icon></v-btn>
            <v-btn value="desc" size="small"><v-icon>mdi-sort-descending</v-icon></v-btn>
          </v-btn-toggle>
          <v-btn
            color="brown"
            variant="tonal"
            size="small"
            prepend-icon="mdi-magnify"
            @click="loadListings"
            :loading="loadingListings"
          >
            Apply
          </v-btn>
        </div>

        <v-progress-linear v-if="loadingListings" indeterminate color="brown" class="mb-2" />

        <!-- View toggle -->
        <div class="d-flex align-center mb-3">
          <v-btn-toggle v-model="viewMode" mandatory density="compact" variant="outlined" color="brown" class="mr-3">
            <v-btn value="cards" size="small"><v-icon>mdi-view-grid</v-icon></v-btn>
            <v-btn value="table" size="small"><v-icon>mdi-view-list</v-icon></v-btn>
          </v-btn-toggle>
          <span class="text-body-2 text-medium-emphasis">
            {{ listings.length }} of {{ listingsTotal }} listings
          </span>
          <v-spacer />
          <v-btn
            v-if="listingsTotal > listings.length"
            variant="text"
            size="small"
            @click="loadMore"
            :loading="loadingMore"
          >
            Load More
          </v-btn>
        </div>

        <!-- CARD view -->
        <v-row v-if="viewMode === 'cards' && listings.length > 0">
          <v-col
            v-for="item in listings"
            :key="item.hash"
            cols="12"
            sm="6"
            md="4"
            lg="3"
          >
            <v-card variant="outlined" class="h-100 d-flex flex-column">
              <!-- Image -->
              <v-img
                v-if="item.image_url"
                :src="item.image_url"
                height="160"
                cover
                class="bg-grey-darken-3"
              >
                <template #error>
                  <div class="d-flex align-center justify-center fill-height bg-grey-darken-3">
                    <v-icon size="48" color="grey">mdi-image-off</v-icon>
                  </div>
                </template>
              </v-img>
              <div v-else class="d-flex align-center justify-center bg-grey-darken-3" style="height: 120px">
                <v-icon size="48" color="grey-darken-1">mdi-terrain</v-icon>
              </div>

              <v-card-text class="flex-grow-1">
                <div class="d-flex align-center mb-1">
                  <div class="text-subtitle-1 font-weight-bold text-truncate flex-grow-1">{{ item.name }}</div>
                  <v-btn
                    icon
                    variant="text"
                    size="x-small"
                    @click.stop="toggleFavorite(item)"
                    :color="item.is_favorite ? 'red' : 'grey'"
                  >
                    <v-icon>{{ item.is_favorite ? 'mdi-heart' : 'mdi-heart-outline' }}</v-icon>
                  </v-btn>
                </div>

                <div class="mb-1">
                  <v-chip size="x-small" color="green" variant="tonal" class="mr-1" v-if="item.price">
                    ${{ fmtNum(item.price) }}
                  </v-chip>
                  <v-chip size="x-small" color="brown" variant="tonal" class="mr-1" v-if="item.acreage">
                    {{ item.acreage }} ac
                  </v-chip>
                  <v-chip size="x-small" color="orange" variant="tonal" v-if="item.is_foreclosure">
                    Foreclosure
                  </v-chip>
                </div>

                <div class="text-caption text-medium-emphasis">
                  <span v-if="item.county">{{ item.county }} County, </span>
                  {{ item.state }}
                </div>

                <div class="text-caption text-medium-emphasis mt-1" v-if="item.down_payment || item.monthly_payment">
                  <span v-if="item.down_payment">${{ fmtNum(item.down_payment) }} down</span>
                  <span v-if="item.down_payment && item.monthly_payment"> · </span>
                  <span v-if="item.monthly_payment">${{ fmtNum(item.monthly_payment) }}/mo</span>
                </div>

                <div class="text-caption text-grey mt-1" v-if="item.tracts_available">
                  {{ item.tracts_available }} tracts available
                </div>
              </v-card-text>

              <v-card-actions class="px-3 pb-3">
                <v-chip size="x-small" :color="sourceColor(item.source)" variant="tonal">
                  {{ item.source_name }}
                </v-chip>
                <v-spacer />
                <v-btn
                  size="small"
                  variant="tonal"
                  color="brown"
                  prepend-icon="mdi-information-outline"
                  @click="scrapeDetail(item)"
                  :loading="item._loadingDetail"
                >
                  Details
                </v-btn>
                <v-btn
                  size="small"
                  variant="text"
                  :href="item.url"
                  target="_blank"
                  append-icon="mdi-open-in-new"
                >
                  Visit
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>

        <!-- TABLE view -->
        <v-table v-if="viewMode === 'table' && listings.length > 0" density="compact" hover>
          <thead>
            <tr>
              <th style="width: 30px"></th>
              <th>Name</th>
              <th>State</th>
              <th>County</th>
              <th>Acres</th>
              <th>Price</th>
              <th>Down</th>
              <th>Monthly</th>
              <th>Source</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in listings" :key="item.hash">
              <td>
                <v-btn
                  icon
                  variant="text"
                  size="x-small"
                  @click="toggleFavorite(item)"
                  :color="item.is_favorite ? 'red' : 'grey'"
                >
                  <v-icon size="16">{{ item.is_favorite ? 'mdi-heart' : 'mdi-heart-outline' }}</v-icon>
                </v-btn>
              </td>
              <td class="font-weight-medium">{{ item.name }}</td>
              <td>{{ item.state }}</td>
              <td>{{ item.county }}</td>
              <td>{{ item.acreage || '—' }}</td>
              <td>
                <span v-if="item.price" class="text-green">${{ fmtNum(item.price) }}</span>
                <span v-else>—</span>
              </td>
              <td>
                <span v-if="item.down_payment">${{ fmtNum(item.down_payment) }}</span>
                <span v-else>—</span>
              </td>
              <td>
                <span v-if="item.monthly_payment">${{ fmtNum(item.monthly_payment) }}</span>
                <span v-else>—</span>
              </td>
              <td>
                <v-chip size="x-small" :color="sourceColor(item.source)" variant="tonal">
                  {{ item.source_name }}
                </v-chip>
              </td>
              <td>
                <v-btn size="x-small" variant="text" icon @click="scrapeDetail(item)" :loading="item._loadingDetail">
                  <v-icon size="16">mdi-information-outline</v-icon>
                </v-btn>
                <v-btn size="x-small" variant="text" icon :href="item.url" target="_blank">
                  <v-icon size="16">mdi-open-in-new</v-icon>
                </v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>

        <!-- Empty state -->
        <v-alert v-if="!loadingListings && listings.length === 0" type="info" variant="tonal" class="mt-3">
          No listings found. Click <strong>Scrape All</strong> to fetch land listings, or adjust your filters.
        </v-alert>
      </v-window-item>

      <!-- ═══════════════════════════════════════ -->
      <!-- 2. FAVORITES -->
      <!-- ═══════════════════════════════════════ -->
      <v-window-item value="favorites">
        <v-progress-linear v-if="loadingFavorites" indeterminate color="red" class="mb-2" />

        <v-row v-if="favoriteItems.length > 0">
          <v-col
            v-for="item in favoriteItems"
            :key="item.hash"
            cols="12"
            sm="6"
            md="4"
            lg="3"
          >
            <v-card variant="outlined" class="h-100 d-flex flex-column">
              <v-img
                v-if="item.image_url"
                :src="item.image_url"
                height="140"
                cover
                class="bg-grey-darken-3"
              />
              <v-card-text class="flex-grow-1">
                <div class="d-flex align-center mb-1">
                  <div class="text-subtitle-1 font-weight-bold text-truncate flex-grow-1">{{ item.name }}</div>
                  <v-btn
                    icon variant="text" size="x-small" color="red"
                    @click="toggleFavorite(item)"
                  >
                    <v-icon>mdi-heart</v-icon>
                  </v-btn>
                </div>
                <div class="mb-1">
                  <v-chip size="x-small" color="green" variant="tonal" class="mr-1" v-if="item.price">
                    ${{ fmtNum(item.price) }}
                  </v-chip>
                  <v-chip size="x-small" color="brown" variant="tonal" v-if="item.acreage">
                    {{ item.acreage }} ac
                  </v-chip>
                </div>
                <div class="text-caption text-medium-emphasis">
                  <span v-if="item.county">{{ item.county }} County, </span>{{ item.state }}
                </div>
                <div class="text-caption text-medium-emphasis mt-1" v-if="item.down_payment || item.monthly_payment">
                  <span v-if="item.down_payment">${{ fmtNum(item.down_payment) }} down</span>
                  <span v-if="item.down_payment && item.monthly_payment"> · </span>
                  <span v-if="item.monthly_payment">${{ fmtNum(item.monthly_payment) }}/mo</span>
                </div>
              </v-card-text>
              <v-card-actions>
                <v-chip size="x-small" :color="sourceColor(item.source)" variant="tonal">{{ item.source_name }}</v-chip>
                <v-spacer />
                <v-btn size="small" variant="text" :href="item.url" target="_blank" append-icon="mdi-open-in-new">Visit</v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>

        <v-alert v-if="!loadingFavorites && favoriteItems.length === 0" type="info" variant="tonal" class="mt-3">
          No favorites yet. Click the <v-icon size="16">mdi-heart-outline</v-icon> icon on any listing to save it here.
        </v-alert>
      </v-window-item>

      <!-- ═══════════════════════════════════════ -->
      <!-- 3. SOURCES -->
      <!-- ═══════════════════════════════════════ -->
      <v-window-item value="sources">
        <div class="d-flex align-center mb-3">
          <div class="text-subtitle-1 font-weight-bold">Scraping Sources</div>
          <v-spacer />
          <v-btn
            color="brown"
            variant="tonal"
            size="small"
            prepend-icon="mdi-plus"
            @click="showAddSource = true"
          >
            Add Source
          </v-btn>
        </div>

        <v-row>
          <v-col v-for="src in sources" :key="src.source_id" cols="12" sm="6" md="4">
            <v-card variant="outlined" class="pa-4">
              <div class="d-flex align-center mb-2">
                <v-icon :color="src.enabled ? 'green' : 'grey'" class="mr-2">
                  {{ src.enabled ? 'mdi-check-circle' : 'mdi-close-circle' }}
                </v-icon>
                <div class="text-subtitle-1 font-weight-bold">{{ src.name }}</div>
                <v-spacer />
                <v-switch
                  :model-value="src.enabled"
                  @update:model-value="toggleSource(src, $event)"
                  color="green"
                  density="compact"
                  hide-details
                />
              </div>

              <div class="text-caption text-medium-emphasis mb-2">{{ src.base_url }}</div>
              <div class="text-body-2 mb-3" v-if="src.description">{{ src.description }}</div>

              <div class="text-caption text-medium-emphasis mb-2" v-if="scrapeStatusData && scrapeStatusData[src.source_id]">
                Last scrape: {{ fmtDate(scrapeStatusData[src.source_id].last_scrape) }}
                · {{ scrapeStatusData[src.source_id].count || 0 }} items
              </div>

              <div class="d-flex ga-2">
                <v-btn
                  color="blue"
                  variant="tonal"
                  size="small"
                  prepend-icon="mdi-download"
                  @click="scrapeSourceFromTab(src.source_id)"
                  :loading="scrapingSource === src.source_id"
                  :disabled="!src.enabled"
                >
                  Scrape
                </v-btn>
                <v-btn
                  color="red"
                  variant="tonal"
                  size="small"
                  prepend-icon="mdi-delete-outline"
                  @click="confirmDeleteSource(src)"
                  v-if="!['landcentral', 'classiccountryland'].includes(src.source_id)"
                >
                  Delete
                </v-btn>
              </div>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>

      <!-- ═══════════════════════════════════════ -->
      <!-- 4. SETTINGS -->
      <!-- ═══════════════════════════════════════ -->
      <v-window-item value="settings">
        <v-card variant="outlined" class="pa-4" style="max-width: 700px">
          <div class="text-h6 mb-4">Real Estate Settings</div>

          <!-- Budget -->
          <div class="text-subtitle-2 text-medium-emphasis mb-2">Budget Limits</div>
          <v-row dense class="mb-3">
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="settMaxPrice"
                label="Max Price"
                variant="outlined"
                density="compact"
                type="number"
                prefix="$"
                @blur="saveSetting('re_max_price', settMaxPrice)"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="settMaxDown"
                label="Max Down Payment"
                variant="outlined"
                density="compact"
                type="number"
                prefix="$"
                @blur="saveSetting('re_max_down_payment', settMaxDown)"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="settMaxMonthly"
                label="Max Monthly Payment"
                variant="outlined"
                density="compact"
                type="number"
                prefix="$"
                @blur="saveSetting('re_max_monthly_payment', settMaxMonthly)"
              />
            </v-col>
          </v-row>

          <!-- Location -->
          <div class="text-subtitle-2 text-medium-emphasis mb-2">Location Filters</div>
          <v-text-field
            v-model="settStates"
            label="States (comma-separated)"
            variant="outlined"
            density="compact"
            hint="e.g. Texas, Florida, Arizona — leave empty for all states"
            persistent-hint
            class="mb-3"
            @blur="saveSetting('re_states', settStates)"
          />
          <v-row dense class="mb-3">
            <v-col cols="12" sm="8">
              <v-text-field
                v-model="settZipCodes"
                label="ZIP Codes (comma-separated)"
                variant="outlined"
                density="compact"
                hint="e.g. 75001, 85001 — optional proximity filter"
                persistent-hint
                @blur="saveSetting('re_zip_codes', settZipCodes)"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="settZipRadius"
                label="Radius (miles)"
                variant="outlined"
                density="compact"
                type="number"
                @blur="saveSetting('re_zip_radius_miles', settZipRadius)"
              />
            </v-col>
          </v-row>

          <!-- Land requirements -->
          <div class="text-subtitle-2 text-medium-emphasis mb-2">Land Requirements</div>
          <v-row dense class="mb-3">
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="settMinAcreage"
                label="Min Acreage"
                variant="outlined"
                density="compact"
                type="number"
                @blur="saveSetting('re_min_acreage', settMinAcreage)"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="settMaxAcreage"
                label="Max Acreage"
                variant="outlined"
                density="compact"
                type="number"
                @blur="saveSetting('re_max_acreage', settMaxAcreage)"
              />
            </v-col>
          </v-row>

          <v-text-field
            v-model="settLandTypes"
            label="Land Types (comma-separated)"
            variant="outlined"
            density="compact"
            hint="e.g. vacant, agricultural, residential, recreational"
            persistent-hint
            class="mb-3"
            @blur="saveSetting('re_land_types', settLandTypes)"
          />

          <v-row dense class="mb-3">
            <v-col cols="12" sm="4">
              <v-select
                v-model="settBuildPermit"
                :items="yesNoOptions"
                label="Building Permit"
                variant="outlined"
                density="compact"
                @update:model-value="saveSetting('re_require_building_permit', $event)"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-select
                v-model="settCamping"
                :items="yesNoOptions"
                label="Camping / RV"
                variant="outlined"
                density="compact"
                @update:model-value="saveSetting('re_require_camping', $event)"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-select
                v-model="settSeptic"
                :items="yesNoOptions"
                label="Septic / Sewer"
                variant="outlined"
                density="compact"
                @update:model-value="saveSetting('re_require_septic', $event)"
              />
            </v-col>
          </v-row>

          <v-select
            v-model="settScrapeInterval"
            :items="intervalOptions"
            label="Auto-Scrape Interval"
            variant="outlined"
            density="compact"
            class="mb-4"
            @update:model-value="saveSetting('re_scrape_interval_hours', $event)"
          />

          <!-- Scrape status -->
          <v-card variant="tonal" class="pa-3 mb-4">
            <div class="text-subtitle-2 mb-2">Scrape Status</div>
            <div v-if="scrapeStatusData && Object.keys(scrapeStatusData).length > 0">
              <div v-for="(info, key) in scrapeStatusData" :key="key" class="text-body-2 mb-1">
                <strong>{{ key }}:</strong>
                {{ info.last_scrape ? fmtDate(info.last_scrape) : 'Never' }}
                ({{ info.count || 0 }} items)
              </div>
            </div>
            <div v-else class="text-body-2 text-grey">No scrape data yet.</div>
          </v-card>

          <div class="d-flex ga-2">
            <v-btn
              color="brown"
              variant="tonal"
              prepend-icon="mdi-refresh"
              @click="scrapeAll"
              :loading="scraping"
            >
              Scrape All Now
            </v-btn>
            <v-btn
              color="red"
              variant="tonal"
              prepend-icon="mdi-delete-outline"
              @click="confirmClear = true"
            >
              Clear All Data
            </v-btn>
          </div>
        </v-card>

        <!-- Skill info -->
        <v-card variant="outlined" class="pa-4 mt-4" style="max-width: 700px">
          <div class="text-subtitle-1 font-weight-bold mb-2">
            <v-icon start size="18" color="brown">mdi-puzzle-outline</v-icon>
            Skill: real_estate_search
          </div>
          <p class="text-body-2 mb-2">
            Allows AI agents to search land listings from all scraped sources. Add <strong>real_estate_search</strong> to an agent's skill list to enable.
          </p>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Type</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr><td><code>query</code></td><td>string</td><td>Search text across listings (name, state, county)</td></tr>
              <tr><td><code>state</code></td><td>string</td><td>Filter by state</td></tr>
              <tr><td><code>max_price</code></td><td>number</td><td>Maximum price filter</td></tr>
              <tr><td><code>min_acreage</code></td><td>number</td><td>Minimum acreage filter</td></tr>
              <tr><td><code>limit</code></td><td>integer</td><td>Max results (default: 20)</td></tr>
            </tbody>
          </v-table>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- Detail dialog -->
    <v-dialog v-model="detailDialog" max-width="600">
      <v-card v-if="detailItem">
        <v-img v-if="detailItem.image_url" :src="detailItem.image_url" height="250" cover class="bg-grey-darken-3" />
        <v-card-title>{{ detailItem.name }}</v-card-title>
        <v-card-text>
          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-chip v-if="detailItem.price" color="green" variant="tonal">${{ fmtNum(detailItem.price) }}</v-chip>
            <v-chip v-if="detailItem.original_price && detailItem.original_price !== detailItem.price" color="grey" variant="tonal">
              <s>${{ fmtNum(detailItem.original_price) }}</s>
            </v-chip>
            <v-chip v-if="detailItem.acreage" color="brown" variant="tonal">{{ detailItem.acreage }} acres</v-chip>
            <v-chip v-if="detailItem.down_payment" color="blue" variant="tonal">${{ fmtNum(detailItem.down_payment) }} down</v-chip>
            <v-chip v-if="detailItem.monthly_payment" color="teal" variant="tonal">${{ fmtNum(detailItem.monthly_payment) }}/mo</v-chip>
            <v-chip v-if="detailItem.is_foreclosure" color="orange" variant="tonal">Foreclosure</v-chip>
          </div>

          <v-list density="compact" class="bg-transparent">
            <v-list-item v-if="detailItem.state">
              <template #prepend><v-icon size="18" class="mr-2">mdi-map-marker</v-icon></template>
              <v-list-item-title>{{ detailItem.county ? detailItem.county + ' County, ' : '' }}{{ detailItem.state }}</v-list-item-title>
            </v-list-item>
            <v-list-item v-if="detailItem.property_id">
              <template #prepend><v-icon size="18" class="mr-2">mdi-identifier</v-icon></template>
              <v-list-item-title>Property #{{ detailItem.property_id }}</v-list-item-title>
            </v-list-item>
            <v-list-item v-if="detailItem.tracts_available">
              <template #prepend><v-icon size="18" class="mr-2">mdi-layers</v-icon></template>
              <v-list-item-title>{{ detailItem.tracts_available }} tracts available</v-list-item-title>
            </v-list-item>
            <v-list-item>
              <template #prepend><v-icon size="18" class="mr-2">mdi-web</v-icon></template>
              <v-list-item-title>Source: {{ detailItem.source_name }}</v-list-item-title>
            </v-list-item>
          </v-list>

          <div v-if="detailItem.building_permitted || detailItem.camping_allowed || detailItem.septic_allowed" class="d-flex flex-wrap ga-2 mt-3">
            <v-chip v-if="detailItem.building_permitted" size="small" color="green" variant="tonal" prepend-icon="mdi-home">Building OK</v-chip>
            <v-chip v-if="detailItem.camping_allowed" size="small" color="teal" variant="tonal" prepend-icon="mdi-tent">Camping OK</v-chip>
            <v-chip v-if="detailItem.septic_allowed" size="small" color="blue" variant="tonal" prepend-icon="mdi-pipe">Septic</v-chip>
          </div>

          <div v-if="detailItem.description" class="text-body-2 mt-3 pa-3 bg-grey-darken-3 rounded">
            {{ detailItem.description }}
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="detailDialog = false">Close</v-btn>
          <v-btn color="brown" variant="tonal" :href="detailItem.url" target="_blank" append-icon="mdi-open-in-new">
            View on Site
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add Source dialog -->
    <v-dialog v-model="showAddSource" max-width="450">
      <v-card>
        <v-card-title>Add Scraping Source</v-card-title>
        <v-card-text>
          <v-text-field v-model="newSource.name" label="Name" variant="outlined" density="compact" class="mb-3" />
          <v-text-field v-model="newSource.base_url" label="Base URL" variant="outlined" density="compact" class="mb-3" placeholder="https://example.com" />
          <v-textarea v-model="newSource.description" label="Description" variant="outlined" density="compact" rows="2" class="mb-3" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showAddSource = false">Cancel</v-btn>
          <v-btn color="brown" variant="tonal" @click="addSource" :disabled="!newSource.name || !newSource.base_url">Add</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete source confirmation -->
    <v-dialog v-model="showDeleteSource" max-width="400">
      <v-card>
        <v-card-title>Delete Source?</v-card-title>
        <v-card-text>
          This will delete <strong>{{ deleteSourceItem?.name }}</strong> and all its listings.
          <v-text-field
            v-model="deleteSourceConfirm"
            label="Type DELETE to confirm"
            variant="outlined"
            density="compact"
            class="mt-3"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showDeleteSource = false">Cancel</v-btn>
          <v-btn color="red" variant="tonal" :disabled="deleteSourceConfirm !== 'DELETE'" @click="deleteSource">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Clear all confirmation -->
    <v-dialog v-model="confirmClear" max-width="400">
      <v-card>
        <v-card-title>Clear All Data?</v-card-title>
        <v-card-text>
          This deletes all scraped listings. You can re-scrape at any time.
          <v-text-field
            v-model="clearConfirmText"
            label="Type DELETE to confirm"
            variant="outlined"
            density="compact"
            class="mt-3"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmClear = false">Cancel</v-btn>
          <v-btn color="red" variant="tonal" :disabled="clearConfirmText !== 'DELETE'" @click="clearAllData">Clear All</v-btn>
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
import api from '@src/api'
import { useSettingsStore } from '@src/stores/settings'

const API = '/addons/real_estate'

export default {
  name: 'RealEstateView',

  data() {
    return {
      activeTab: localStorage.getItem('re_tab') || 'listings',

      // Stats
      stats: null,
      lastScrape: null,
      scraping: false,
      scrapeStatusData: null,
      scrapeProgress: null,
      _pollTimer: null,

      // Listings tab
      listings: [],
      listingsTotal: 0,
      loadingListings: false,
      loadingMore: false,
      viewMode: localStorage.getItem('re_view') || 'cards',
      filterSource: (() => { try { return JSON.parse(localStorage.getItem('re_filterSource')) } catch { return null } })(),
      filterState: (() => { try { const v = JSON.parse(localStorage.getItem('re_filterState')); return Array.isArray(v) ? v : [] } catch { return [] } })(),
      filterMaxPrice: (() => { try { return JSON.parse(localStorage.getItem('re_filterMaxPrice')) } catch { return null } })(),
      filterMinAcreage: (() => { try { return JSON.parse(localStorage.getItem('re_filterMinAcreage')) } catch { return null } })(),
      sortBy: localStorage.getItem('re_sortBy') || 'price',
      sortDir: localStorage.getItem('re_sortDir') || 'asc',
      sortOptions: [
        { title: 'Price', value: 'price' },
        { title: 'Acreage', value: 'acreage' },
        { title: 'State', value: 'state' },
        { title: 'Date Scraped', value: 'scraped_at' },
        { title: 'Name', value: 'name' },
      ],
      sourceOptions: [
        { title: 'All Sources', value: null },
        { title: 'LandCentral', value: 'landcentral' },
        { title: 'Classic Country Land', value: 'classiccountryland' },
      ],
      stateOptions: [
        'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
        'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
        'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
        'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
        'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
        'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
        'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
        'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
        'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
        'West Virginia', 'Wisconsin', 'Wyoming',
      ],

      // Favorites tab
      favoriteItems: [],
      loadingFavorites: false,

      // Sources tab
      sources: [],
      showAddSource: false,
      newSource: { name: '', base_url: '', description: '' },
      scrapingSource: null,
      showDeleteSource: false,
      deleteSourceItem: null,
      deleteSourceConfirm: '',

      // Detail dialog
      detailDialog: false,
      detailItem: null,

      // Settings
      settMaxPrice: '',
      settMaxDown: '',
      settMaxMonthly: '',
      settStates: '',
      settZipCodes: '',
      settZipRadius: '50',
      settMinAcreage: '',
      settMaxAcreage: '',
      settLandTypes: '',
      settBuildPermit: 'any',
      settCamping: 'any',
      settSeptic: 'any',
      settScrapeInterval: '24',

      yesNoOptions: [
        { title: 'Any', value: 'any' },
        { title: 'Yes (required)', value: 'yes' },
        { title: 'No (not required)', value: 'no' },
      ],
      intervalOptions: [
        { title: 'Every 6 hours', value: '6' },
        { title: 'Every 12 hours', value: '12' },
        { title: 'Every 24 hours', value: '24' },
        { title: 'Every 48 hours', value: '48' },
        { title: 'Manual only', value: '0' },
      ],

      // Clear confirmation
      confirmClear: false,
      clearConfirmText: '',

      // Snackbar
      snack: false,
      snackText: '',
      snackColor: 'success',
    }
  },

  watch: {
    activeTab(tab) {
      localStorage.setItem('re_tab', tab)
      this.loadTabData(tab)
    },
    viewMode(v) {
      localStorage.setItem('re_view', v)
    },
    filterSource(v) {
      localStorage.setItem('re_filterSource', JSON.stringify(v))
    },
    filterState(v) {
      localStorage.setItem('re_filterState', JSON.stringify(v || []))
    },
    filterMaxPrice(v) {
      localStorage.setItem('re_filterMaxPrice', JSON.stringify(v))
    },
    filterMinAcreage(v) {
      localStorage.setItem('re_filterMinAcreage', JSON.stringify(v))
    },
    sortBy(v) {
      localStorage.setItem('re_sortBy', v)
    },
    sortDir(v) {
      localStorage.setItem('re_sortDir', v)
    },
  },

  async mounted() {
    this.loadSettings()
    this.loadStats()
    this.loadScrapeStatus()
    this.loadTabData(this.activeTab)
    // Check if scrape is already running (e.g. page refresh during scrape)
    try {
      const { data } = await api.get(`${API}/scrape/progress`)
      if (data && data.running) {
        this.scraping = true
        this.scrapeProgress = data
        this._startPolling()
      }
    } catch {}
  },
  beforeUnmount() {
    this._stopPolling()
  },

  methods: {
    // ---- Formatting ----
    fmtDate(d) {
      if (!d) return '—'
      return new Date(d).toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    },
    fmtNum(n) {
      if (n == null) return '0'
      return Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 })
    },
    sourceColor(src) {
      const colors = {
        landcentral: 'blue',
        classiccountryland: 'green',
      }
      return colors[src] || 'grey'
    },
    notify(text, color = 'success') {
      this.snackText = text
      this.snackColor = color
      this.snack = true
    },

    // ---- Tab data loading ----
    loadTabData(tab) {
      switch (tab) {
        case 'listings': this.loadListings(); break
        case 'favorites': this.loadFavorites(); break
        case 'sources': this.loadSources(); break
        case 'settings': this.loadScrapeStatus(); break
      }
    },

    // ---- Settings ----
    loadSettings() {
      const ss = useSettingsStore()
      const s = ss.systemSettings || {}
      this.settMaxPrice = s.re_max_price || ''
      this.settMaxDown = s.re_max_down_payment || ''
      this.settMaxMonthly = s.re_max_monthly_payment || ''
      this.settStates = s.re_states || ''
      this.settZipCodes = s.re_zip_codes || ''
      this.settZipRadius = s.re_zip_radius_miles || '50'
      this.settMinAcreage = s.re_min_acreage || ''
      this.settMaxAcreage = s.re_max_acreage || ''
      this.settLandTypes = s.re_land_types || ''
      this.settBuildPermit = s.re_require_building_permit || 'any'
      this.settCamping = s.re_require_camping || 'any'
      this.settSeptic = s.re_require_septic || 'any'
      this.settScrapeInterval = s.re_scrape_interval_hours || '24'
    },
    async saveSetting(key, value) {
      try {
        const ss = useSettingsStore()
        await ss.updateSystemSetting(key, value)
      } catch (e) {
        this.notify('Failed to save setting', 'error')
      }
    },

    // ---- Stats ----
    async loadStats() {
      try {
        const { data } = await api.get(`${API}/stats`)
        this.stats = data
      } catch {}
    },
    async loadScrapeStatus() {
      try {
        const { data } = await api.get(`${API}/scrape/status`)
        this.scrapeStatusData = data
        let latest = null
        for (const v of Object.values(data)) {
          if (v.last_scrape && (!latest || v.last_scrape > latest)) latest = v.last_scrape
        }
        this.lastScrape = latest
      } catch {}
    },

    // ---- Scrape All (background + polling) ----
    async scrapeAll() {
      this.scraping = true
      this.scrapeProgress = null
      try {
        const { data } = await api.post(`${API}/scrape-all`)
        if (data.ok) {
          this.notify(data.message || 'Scraping started...')
          this._startPolling()
        } else {
          this.notify(data.message || 'Scrape already running', 'warning')
          if (data.progress?.running) {
            this.scrapeProgress = data.progress
            this._startPolling()
          }
        }
      } catch (e) {
        this.notify('Scrape failed: ' + (e.response?.data?.detail || e.message), 'error')
        this.scraping = false
      }
    },
    async scrapeSource(sourceId) {
      this.scraping = true
      this.scrapeProgress = null
      try {
        const { data } = await api.post(`${API}/scrape/${sourceId}`)
        if (data.ok) {
          this.notify(data.message || `Scraping ${sourceId}...`)
          this._startPolling()
        } else {
          this.notify(data.message || 'Scrape already running', 'warning')
          if (data.progress?.running) {
            this.scrapeProgress = data.progress
            this._startPolling()
          }
        }
      } catch (e) {
        this.notify('Scrape failed: ' + (e.response?.data?.detail || e.message), 'error')
        this.scraping = false
      }
    },
    _startPolling() {
      this._stopPolling()
      this._pollTimer = setInterval(() => this._pollProgress(), 2000)
    },
    _stopPolling() {
      if (this._pollTimer) {
        clearInterval(this._pollTimer)
        this._pollTimer = null
      }
    },
    async _pollProgress() {
      try {
        const { data } = await api.get(`${API}/scrape/progress`)
        this.scrapeProgress = data
        if (!data.running) {
          this._stopPolling()
          this.scraping = false
          const msg = data.error_msg
            ? `Scrape finished with errors: ${data.error_msg}`
            : `Scrape complete — ${data.listings_found || 0} listings found`
          this.notify(msg, data.error_msg ? 'warning' : 'success')
          this.scrapeProgress = null
          this.loadStats()
          this.loadScrapeStatus()
          this.loadTabData(this.activeTab)
        }
      } catch {
        // If progress endpoint fails, just keep polling
      }
    },

    // ---- Listings ----
    async loadListings() {
      this.loadingListings = true
      try {
        const params = {
          sort_by: this.sortBy,
          sort_dir: this.sortDir,
          limit: 100,
          offset: 0,
        }
        if (this.filterSource) params.source = this.filterSource
        if (this.filterState && this.filterState.length) params.state = this.filterState.join(',')
        if (this.filterMaxPrice) params.max_price = this.filterMaxPrice
        if (this.filterMinAcreage) params.min_acreage = this.filterMinAcreage

        const { data } = await api.get(`${API}/listings`, { params })
        this.listings = (data.items || []).map(i => ({ ...i, _loadingDetail: false }))
        this.listingsTotal = data.total || 0
      } catch {} finally {
        this.loadingListings = false
      }
    },
    async loadMore() {
      this.loadingMore = true
      try {
        const params = {
          sort_by: this.sortBy,
          sort_dir: this.sortDir,
          limit: 100,
          offset: this.listings.length,
        }
        if (this.filterSource) params.source = this.filterSource
        if (this.filterState && this.filterState.length) params.state = this.filterState.join(',')
        if (this.filterMaxPrice) params.max_price = this.filterMaxPrice
        if (this.filterMinAcreage) params.min_acreage = this.filterMinAcreage

        const { data } = await api.get(`${API}/listings`, { params })
        const newItems = (data.items || []).map(i => ({ ...i, _loadingDetail: false }))
        this.listings.push(...newItems)
      } catch {} finally {
        this.loadingMore = false
      }
    },

    // ---- Favorites ----
    async loadFavorites() {
      this.loadingFavorites = true
      try {
        const { data } = await api.get(`${API}/listings`, { params: { favorites_only: true, limit: 200 } })
        this.favoriteItems = data.items || []
      } catch {} finally {
        this.loadingFavorites = false
      }
    },
    async toggleFavorite(item) {
      try {
        if (item.is_favorite) {
          await api.delete(`${API}/favorites/${item.hash}`)
          item.is_favorite = false
          this.favoriteItems = this.favoriteItems.filter(f => f.hash !== item.hash)
        } else {
          await api.post(`${API}/favorites/${item.hash}`)
          item.is_favorite = true
        }
        this.loadStats()
      } catch (e) {
        this.notify('Failed to update favorite', 'error')
      }
    },

    // ---- Detail scrape ----
    async scrapeDetail(item) {
      item._loadingDetail = true
      try {
        const { data } = await api.post(`${API}/listings/${item.hash}/scrape-detail`)
        // Update the item in-place
        Object.assign(item, data)
        item._loadingDetail = false
        this.detailItem = item
        this.detailDialog = true
      } catch (e) {
        this.notify('Failed to load details', 'error')
        item._loadingDetail = false
      }
    },

    // ---- Sources ----
    async loadSources() {
      try {
        const { data } = await api.get(`${API}/sources`)
        this.sources = data.items || []
      } catch {}
    },
    async toggleSource(src, enabled) {
      try {
        await api.patch(`${API}/sources/${src.source_id}`, { enabled })
        src.enabled = enabled
      } catch (e) {
        this.notify('Failed to update source', 'error')
      }
    },
    async scrapeSourceFromTab(sourceId) {
      this.scrapingSource = sourceId
      await this.scrapeSource(sourceId)
      this.scrapingSource = null
    },
    async addSource() {
      try {
        await api.post(`${API}/sources`, this.newSource)
        this.showAddSource = false
        this.newSource = { name: '', base_url: '', description: '' }
        this.loadSources()
        this.notify('Source added')
      } catch (e) {
        this.notify('Failed to add source', 'error')
      }
    },
    confirmDeleteSource(src) {
      this.deleteSourceItem = src
      this.deleteSourceConfirm = ''
      this.showDeleteSource = true
    },
    async deleteSource() {
      if (!this.deleteSourceItem) return
      try {
        await api.delete(`${API}/sources/${this.deleteSourceItem.source_id}`)
        this.showDeleteSource = false
        this.loadSources()
        this.loadStats()
        this.notify('Source deleted')
      } catch (e) {
        this.notify('Failed to delete source', 'error')
      }
    },

    // ---- Clear ----
    async clearAllData() {
      try {
        await api.delete(`${API}/clear`)
        this.notify('All data cleared')
        this.confirmClear = false
        this.clearConfirmText = ''
        this.loadStats()
        this.loadTabData(this.activeTab)
      } catch (e) {
        this.notify('Clear failed', 'error')
      }
    },
  },
}
</script>

<style scoped>
</style>
