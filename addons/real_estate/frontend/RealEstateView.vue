<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <v-icon size="32" color="brown-lighten-1" class="mr-3">mdi-terrain</v-icon>
      <div class="text-h4 font-weight-bold">Real Estate</div>
    </div>

    <!-- Top-level tabs -->
    <v-tabs v-model="mainTab" color="brown-lighten-1" class="mb-4" density="comfortable">
      <v-tab value="land">
        <v-icon start size="20">mdi-terrain</v-icon>
        Affordable Land
      </v-tab>
      <v-tab value="auctions">
        <v-icon start size="20">mdi-gavel</v-icon>
        Auction Houses
      </v-tab>
    </v-tabs>

    <v-window v-model="mainTab" :transition="false" :reverse-transition="false">

    <!-- ═══════════════════════════════════════════════════════════ -->
    <!-- MAIN TAB 1: AFFORDABLE LAND                                -->
    <!-- ═══════════════════════════════════════════════════════════ -->
    <v-window-item value="land" eager>

    <!-- Scrape buttons -->
    <div class="d-flex align-center mb-3">
      <v-btn-group variant="tonal" density="comfortable" class="mr-2" divided>
        <v-btn
          color="brown"
          prepend-icon="mdi-refresh"
          @click="scrapeMode('full')"
          :loading="scraping"
          size="small"
        >
          Update All
        </v-btn>
        <v-btn
          color="teal"
          prepend-icon="mdi-magnify-plus-outline"
          @click="scrapeMode('new_only')"
          :loading="scraping"
          size="small"
        >
          Find New
        </v-btn>
        <v-btn
          color="red"
          prepend-icon="mdi-heart-pulse"
          @click="scrapeMode('favorites')"
          :loading="scraping"
          size="small"
        >
          Update Favorites
        </v-btn>
      </v-btn-group>
      <v-chip v-if="lastScrape" variant="tonal" color="grey" size="small">
        Last: {{ fmtDate(lastScrape) }}
      </v-chip>
    </div>

    <!-- Scrape progress banner -->
    <v-alert v-if="scrapeProgress && scrapeProgress.running" type="info" variant="tonal" density="compact" class="mb-3">
      <div class="d-flex align-center">
        <v-progress-circular indeterminate size="18" width="2" class="mr-2" />
        <v-chip v-if="scrapeProgress.mode" size="x-small" variant="flat" :color="scrapeProgress.mode === 'favorites' ? 'red' : scrapeProgress.mode === 'new_only' ? 'teal' : 'brown'" class="mr-2">
          {{ {full: 'Update All', new_only: 'Find New', favorites: 'Favorites'}[scrapeProgress.mode] || scrapeProgress.mode }}
        </v-chip>
        <span v-if="scrapeProgress.source === 'details'">
          Scraping details <strong>{{ scrapeProgress.states_done }}/{{ scrapeProgress.states_total }}</strong> listings
          <span v-if="scrapeProgress.errors"> ({{ scrapeProgress.errors }} errors)</span>
        </span>
        <span v-else>
          <span v-if="scrapeProgress.sources_total" class="text-medium-emphasis mr-1">[{{ scrapeProgress.source_index || 0 }}/{{ scrapeProgress.sources_total }}]</span>
          Scraping <strong>{{ scrapeProgress.source || '...' }}</strong>
          — {{ scrapeProgress.states_done }}/{{ scrapeProgress.states_total }} states,
          {{ scrapeProgress.listings_found }} listings found
          <span :class="scrapeProgress.new_count ? 'text-success font-weight-bold' : 'text-medium-emphasis'">({{ scrapeProgress.new_count || 0 }} new)</span>
          <span v-if="scrapeProgress.errors"> ({{ scrapeProgress.errors }} errors)</span>
        </span>
        <v-spacer />
        <v-btn
          variant="text"
          size="x-small"
          color="red"
          icon="mdi-stop-circle-outline"
          :loading="stoppingParserScrape"
          @click="stopScrape"
        />
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
      <v-chip variant="tonal" color="cyan" size="large">
        <v-icon start size="16">mdi-binoculars</v-icon>
        Watched: {{ stats.watched || 0 }}
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
      <v-tab value="watched">
        <v-icon start size="18">mdi-binoculars</v-icon>
        Watched
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

    <v-window v-model="activeTab" :transition="false" :reverse-transition="false">

      <!-- ═══════════════════════════════════════ -->
      <!-- 1. AFFORDABLE LAND LISTINGS -->
      <!-- ═══════════════════════════════════════ -->
      <v-window-item value="listings">

        <!-- Filter panel -->
        <v-card variant="flat" class="filter-panel mb-4 pa-4">
          <!-- Row 1: Main property filters -->
          <div class="d-flex align-center mb-3">
            <v-icon size="18" color="brown-lighten-1" class="mr-2">mdi-filter-variant</v-icon>
            <span class="text-subtitle-2 font-weight-medium text-medium-emphasis">Filters</span>
            <v-spacer />
            <v-btn
              variant="text"
              size="x-small"
              color="grey"
              prepend-icon="mdi-filter-remove"
              @click="clearFilters"
              class="text-none"
            >
              Clear all
            </v-btn>
          </div>

          <v-row dense class="mb-1">
            <v-col cols="12" sm="6" md="3" lg="2">
              <v-select
                v-model="filterSource"
                :items="sourceOptions"
                label="Source"
                variant="solo-filled"
                density="compact"
                flat
                clearable
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6" md="4" lg="3">
              <v-select
                v-model="filterState"
                :items="stateOptions"
                label="States"
                variant="solo-filled"
                density="compact"
                flat
                clearable
                multiple
                chips
                closable-chips
                hide-details
              />
            </v-col>
            <v-col cols="6" sm="4" md="2">
              <v-text-field
                v-model.number="filterMaxPrice"
                label="Max Price"
                variant="solo-filled"
                density="compact"
                flat
                type="number"
                prefix="$"
                clearable
                hide-details
              />
            </v-col>
            <v-col cols="6" sm="4" md="2">
              <v-text-field
                v-model.number="filterMinAcreage"
                label="Min Acres"
                variant="solo-filled"
                density="compact"
                flat
                type="number"
                clearable
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="4" md="3" lg="3">
              <v-select
                v-model="filterZoning"
                :items="zoningOptions"
                label="Zoning"
                variant="solo-filled"
                density="compact"
                flat
                clearable
                multiple
                chips
                closable-chips
                hide-details
              />
            </v-col>
          </v-row>

          <!-- Row 2: Extra filters + comment search + sort + actions -->
          <v-row dense align="center">
            <v-col cols="6" sm="3" md="2">
              <v-select
                v-model="filterHoa"
                :items="hoaOptions"
                label="HOA"
                variant="solo-filled"
                density="compact"
                flat
                clearable
                hide-details
              />
            </v-col>
            <v-col cols="6" sm="3" md="2">
              <v-checkbox
                v-model="filterHasComment"
                label="With comments"
                density="compact"
                hide-details
                color="brown"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-text-field
                v-model="filterSearchComment"
                label="Search comments"
                variant="solo-filled"
                density="compact"
                flat
                clearable
                prepend-inner-icon="mdi-comment-search-outline"
                hide-details
              />
            </v-col>
            <v-col cols="6" sm="4" md="2">
              <v-select
                v-model="sortBy"
                :items="sortOptions"
                label="Sort by"
                variant="solo-filled"
                density="compact"
                flat
                hide-details
              />
            </v-col>
            <v-col cols="auto">
              <v-btn-toggle v-model="sortDir" mandatory density="compact" variant="outlined" color="brown" rounded="lg">
                <v-btn value="asc" size="small"><v-icon size="18">mdi-sort-ascending</v-icon></v-btn>
                <v-btn value="desc" size="small"><v-icon size="18">mdi-sort-descending</v-icon></v-btn>
              </v-btn-toggle>
            </v-col>
            <v-col cols="auto" class="d-flex ga-2">
              <v-btn
                color="brown"
                variant="flat"
                size="small"
                prepend-icon="mdi-magnify"
                @click="loadListings"
                :loading="loadingListings"
                rounded="lg"
                class="text-none"
              >
                Apply
              </v-btn>
              <v-btn
                color="brown"
                variant="tonal"
                size="small"
                icon="mdi-content-save-outline"
                @click="openSavePreset"
                rounded="lg"
              >
                <v-icon size="18">mdi-content-save-outline</v-icon>
                <v-tooltip activator="parent" location="top">Save filter preset</v-tooltip>
              </v-btn>
            </v-col>
          </v-row>

          <!-- Saved presets row -->
          <div v-if="filterPresets.length > 0" class="d-flex flex-wrap align-center ga-2 mt-3 pt-3" style="border-top: 1px solid rgba(255,255,255,0.06)">
            <v-icon size="14" color="brown-lighten-2" class="mr-1">mdi-bookmark-multiple-outline</v-icon>
            <span class="text-caption text-medium-emphasis mr-1">Presets:</span>
            <v-chip
              v-for="preset in filterPresets"
              :key="preset._id"
              color="brown"
              variant="tonal"
              size="small"
              closable
              @click="applyPreset(preset)"
              @click:close="deletePreset(preset._id)"
              rounded="lg"
            >
              {{ preset.name }}
            </v-chip>
          </div>
        </v-card>

        <v-progress-linear v-if="loadingListings" indeterminate color="brown" class="mb-2" />

        <!-- View toggle -->
        <div class="d-flex align-center mb-3">
          <v-btn-toggle v-model="viewMode" mandatory density="compact" variant="outlined" color="brown" rounded="lg" class="mr-3">
            <v-btn value="cards" size="small"><v-icon size="18">mdi-view-grid</v-icon></v-btn>
            <v-btn value="table" size="small"><v-icon size="18">mdi-view-list</v-icon></v-btn>
          </v-btn-toggle>
          <span class="text-body-2 text-medium-emphasis">
            {{ (currentPage - 1) * perPage + 1 }}–{{ Math.min(currentPage * perPage, listingsTotal) }} of {{ listingsTotal }} listings
            <span v-if="hiddenCount > 0" class="text-grey"> ({{ hiddenCount }} hidden)</span>
          </span>
          <v-spacer />
          <v-btn
            v-if="hiddenCount > 0"
            variant="text"
            size="small"
            :prepend-icon="showHidden ? 'mdi-eye-off' : 'mdi-eye'"
            @click="showHidden = !showHidden"
            class="mr-2"
          >
            {{ showHidden ? 'Hide dismissed' : 'Show dismissed' }}
          </v-btn>

        </div>

        <!-- CARD view -->
        <v-row v-if="viewMode === 'cards' && visibleListings.length > 0">
          <v-col
            v-for="item in visibleListings"
            :key="item.hash"
            cols="12"
            sm="6"
            md="4"
            lg="3"
          >
            <v-card
              variant="outlined"
              class="h-100 d-flex flex-column"
              :class="{ 're-seen': seenHashes[item.hash] && !item.is_hidden }"
              :style="item.is_hidden ? 'opacity: 0.45; text-decoration: line-through' : ''"
            >
              <!-- Image -->
              <v-img
                v-if="item.image_url"
                :src="item.image_url"
                height="160"
                cover
                loading="lazy"
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
                <div class="text-subtitle-1 font-weight-bold text-truncate mb-1">{{ item.name }}</div>

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
                <div class="mt-1" v-if="item.hoa">
                  <v-chip size="x-small" :color="item.hoa === 'yes' ? 'red' : 'green'" variant="tonal">
                    <v-icon start size="10">{{ item.hoa === 'yes' ? 'mdi-alert' : 'mdi-check-circle' }}</v-icon>
                    HOA: {{ item.hoa === 'yes' ? (item.hoa_dues || 'Yes') : 'None' }}
                  </v-chip>
                </div>
                <div class="mt-1" v-if="item.zoning || item.zoning_code">
                  <v-chip size="x-small" color="purple" variant="tonal" class="mr-1" v-if="item.zoning">
                    <v-icon start size="10">mdi-gavel</v-icon>{{ item.zoning }}
                  </v-chip>
                  <v-chip size="x-small" color="deep-purple" variant="tonal" v-if="item.zoning_code">
                    {{ item.zoning_code }}
                  </v-chip>
                </div>
                <div class="mt-2" @click.stop>
                  <v-text-field
                    :model-value="item.user_comment || ''"
                    @update:model-value="item.user_comment = $event"
                    @blur="saveComment(item)"
                    @keydown.enter="$event.target.blur()"
                    variant="outlined"
                    density="compact"
                    placeholder="Add comment..."
                    hide-details
                    prepend-inner-icon="mdi-comment-outline"
                    class="comment-card-field"
                  />
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
                  @click="markSeen(item); scrapeDetail(item)"
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
                  @click="markSeen(item)"
                >
                  Visit
                </v-btn>
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  @click.stop="toggleFavorite(item)"
                  :color="item.is_favorite ? 'red' : 'grey'"
                >
                  <v-icon>{{ item.is_favorite ? 'mdi-heart' : 'mdi-heart-outline' }}</v-icon>
                </v-btn>
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  @click.stop="toggleWatched(item)"
                  :color="item.is_watched ? 'cyan' : 'grey'"
                >
                  <v-icon>{{ item.is_watched ? 'mdi-binoculars' : 'mdi-eye-outline' }}</v-icon>
                </v-btn>
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  @click.stop="toggleHidden(item)"
                  :color="item.is_hidden ? 'orange' : 'grey'"
                >
                  <v-icon>{{ item.is_hidden ? 'mdi-eye-off' : 'mdi-eye-off-outline' }}</v-icon>
                </v-btn>
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  @click.stop="deleteListing(item)"
                  color="red-darken-2"
                >
                  <v-icon>mdi-delete-outline</v-icon>
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>

        <!-- TABLE view -->
        <v-table v-if="viewMode === 'table' && visibleListings.length > 0" density="compact" hover>
          <thead>
            <tr>
              <th>Name</th>
              <th>State</th>
              <th>County</th>
              <th>Acres</th>
              <th>Price</th>
              <th>Down</th>
              <th>Monthly</th>
              <th>Source</th>
              <th>HOA</th>
              <th>Zoning</th>
              <th style="min-width: 180px">Comment</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in visibleListings"
              :key="item.hash"
              :class="{ 're-seen-row': seenHashes[item.hash] && !item.is_hidden }"
              :style="[
                item.is_hidden ? 'opacity: 0.45; text-decoration: line-through' : '',
                lastClickedHash === item.hash ? 'background: rgba(255, 183, 77, 0.15); box-shadow: inset 3px 0 0 #FFB74D' : '',
              ]"
            >
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
                <v-chip v-if="item.hoa" size="x-small" :color="item.hoa === 'yes' ? 'red' : 'green'" variant="tonal">
                  {{ item.hoa === 'yes' ? (item.hoa_dues || 'Yes') : 'None' }}
                </v-chip>
                <span v-else class="text-grey">—</span>
              </td>
              <td>
                <v-chip v-if="item.zoning" size="x-small" color="purple" variant="tonal">{{ item.zoning }}</v-chip>
                <span v-else class="text-grey">—</span>
              </td>
              <td @click.stop>
                <v-text-field
                  :model-value="item.user_comment || ''"
                  @update:model-value="item.user_comment = $event"
                  @blur="saveComment(item)"
                  @keydown.enter="$event.target.blur()"
                  variant="plain"
                  density="compact"
                  placeholder="Add comment..."
                  hide-details
                  single-line
                  class="comment-field"
                />
              </td>
              <td style="white-space: nowrap">
                <v-btn size="x-small" variant="text" icon @click="markSeen(item); scrapeDetail(item)" :loading="item._loadingDetail">
                  <v-icon size="16">mdi-information-outline</v-icon>
                </v-btn>
                <v-btn size="x-small" variant="text" icon :href="item.url" target="_blank" @click="markSeen(item); lastClickedHash = item.hash">
                  <v-icon size="16">mdi-open-in-new</v-icon>
                </v-btn>
                <v-btn size="x-small" variant="text" icon @click="toggleFavorite(item)" :color="item.is_favorite ? 'red' : 'grey'">
                  <v-icon size="16">{{ item.is_favorite ? 'mdi-heart' : 'mdi-heart-outline' }}</v-icon>
                </v-btn>
                <v-btn size="x-small" variant="text" icon @click="toggleWatched(item)" :color="item.is_watched ? 'cyan' : 'grey'">
                  <v-icon size="16">{{ item.is_watched ? 'mdi-binoculars' : 'mdi-eye-outline' }}</v-icon>
                  <v-tooltip activator="parent" location="top">{{ item.is_watched ? 'Unwatch' : 'Watch' }}</v-tooltip>
                </v-btn>
                <v-btn size="x-small" variant="text" icon @click="toggleHidden(item)" :color="item.is_hidden ? 'orange' : 'grey'">
                  <v-icon size="16">{{ item.is_hidden ? 'mdi-eye-off' : 'mdi-eye-off-outline' }}</v-icon>
                  <v-tooltip activator="parent" location="top">{{ item.is_hidden ? 'Restore' : 'Dismiss' }}</v-tooltip>
                </v-btn>
                <v-btn size="x-small" variant="text" icon @click="deleteListing(item)" color="red-darken-2">
                  <v-icon size="16">mdi-delete-outline</v-icon>
                  <v-tooltip activator="parent" location="top">Delete permanently</v-tooltip>
                </v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>

        <!-- Pagination -->
        <div v-if="totalPages > 1 && listings.length > 0" class="d-flex justify-center align-center mt-4 mb-2">
          <v-pagination
            v-model="currentPage"
            :length="totalPages"
            :total-visible="7"
            density="comfortable"
            rounded="lg"
            color="brown"
            @update:modelValue="goToPage"
          />
        </div>

        <!-- Empty state -->
        <v-alert v-if="!loadingListings && listings.length === 0" type="info" variant="tonal" class="mt-3">
          No listings found. Click <strong>Scrape All</strong> to fetch land listings, or adjust your filters.
        </v-alert>
        <v-alert v-else-if="!loadingListings && visibleListings.length === 0" type="info" variant="tonal" class="mt-3">
          All listings are dismissed. Click <strong>Show dismissed</strong> to see them.
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
      <!-- WATCHED -->
      <!-- ═══════════════════════════════════════ -->
      <v-window-item value="watched">
        <v-progress-linear v-if="loadingWatched" indeterminate color="cyan" class="mb-2" />

        <v-row v-if="watchedItems.length > 0">
          <v-col
            v-for="item in watchedItems"
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
                    icon variant="text" size="x-small" color="cyan"
                    @click="toggleWatched(item)"
                  >
                    <v-icon>mdi-binoculars</v-icon>
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

        <v-alert v-if="!loadingWatched && watchedItems.length === 0" type="info" variant="tonal" class="mt-3">
          No watched items yet. Click the <v-icon size="16">mdi-eye-outline</v-icon> icon on any listing to track it here.
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

    </v-window-item>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <!-- MAIN TAB 2: AUCTION HOUSES                                 -->
    <!-- ═══════════════════════════════════════════════════════════ -->
    <v-window-item value="auctions" eager>

      <!-- Auction scrape buttons -->
      <div class="d-flex align-center mb-3">
        <v-btn-group variant="tonal" density="comfortable" class="mr-2" divided>
          <v-btn color="deep-purple" prepend-icon="mdi-refresh" size="small" disabled>
            Update All
          </v-btn>
          <v-btn color="teal" prepend-icon="mdi-magnify-plus-outline" size="small" disabled>
            Find New
          </v-btn>
          <v-btn color="red" prepend-icon="mdi-heart-pulse" size="small" disabled>
            Update Favorites
          </v-btn>
        </v-btn-group>
        <v-chip variant="tonal" color="grey" size="small">Coming soon</v-chip>
      </div>

      <!-- Auction stats chips -->
      <div class="d-flex flex-wrap ga-2 mb-4">
        <v-chip variant="tonal" color="deep-purple" size="large">
          <v-icon start size="16">mdi-gavel</v-icon>
          Auction Listings: 0
        </v-chip>
        <v-chip variant="tonal" color="red" size="large">
          <v-icon start size="16">mdi-heart</v-icon>
          Favorites: 0
        </v-chip>
        <v-chip variant="tonal" color="blue" size="large">
          <v-icon start size="16">mdi-web</v-icon>
          Sources: 0
        </v-chip>
      </div>

      <!-- Auction sub-tabs -->
      <v-tabs v-model="auctionTab" color="deep-purple-lighten-1" class="mb-4" show-arrows>
        <v-tab value="auction_listings">
          <v-icon start size="18">mdi-gavel</v-icon>
          Auction Listings
        </v-tab>
        <v-tab value="auction_favorites">
          <v-icon start size="18">mdi-heart-outline</v-icon>
          Favorites
        </v-tab>
        <v-tab value="auction_sources">
          <v-icon start size="18">mdi-web</v-icon>
          Sources
        </v-tab>
        <v-tab value="auction_settings">
          <v-icon start size="18">mdi-cog-outline</v-icon>
          Settings
        </v-tab>
      </v-tabs>

      <v-window v-model="auctionTab" :transition="false" :reverse-transition="false">
        <!-- Auction listings -->
        <v-window-item value="auction_listings">
          <!-- Filters -->
          <v-card variant="tonal" class="mb-4 pa-3">
            <v-row dense align="center">
              <v-col cols="12" sm="6" md="2">
                <v-select
                  v-model="auctionFilterState"
                  :items="stateOptions"
                  label="State"
                  density="compact"
                  clearable
                  multiple
                  chips
                  closable-chips
                  variant="outlined"
                  hide-details
                />
              </v-col>
              <v-col cols="6" sm="3" md="2">
                <v-text-field
                  v-model.number="auctionFilterMaxPrice"
                  label="Max Price"
                  type="number"
                  density="compact"
                  prefix="$"
                  variant="outlined"
                  hide-details
                  clearable
                />
              </v-col>
              <v-col cols="6" sm="3" md="2">
                <v-text-field
                  v-model.number="auctionFilterMinBeds"
                  label="Min Beds"
                  type="number"
                  density="compact"
                  variant="outlined"
                  hide-details
                  clearable
                />
              </v-col>
              <v-col cols="6" sm="3" md="2">
                <v-text-field
                  v-model.number="auctionFilterMinBath"
                  label="Min Bath"
                  type="number"
                  density="compact"
                  variant="outlined"
                  hide-details
                  clearable
                />
              </v-col>
              <v-col cols="6" sm="3" md="2">
                <v-select
                  v-model="auctionFilterType"
                  :items="auctionTypeOptions"
                  label="Property Type"
                  density="compact"
                  clearable
                  variant="outlined"
                  hide-details
                />
              </v-col>
              <v-col cols="auto">
                <v-btn color="deep-purple" variant="flat" size="small" rounded="lg" class="text-none" disabled>
                  Apply
                </v-btn>
              </v-col>
            </v-row>
          </v-card>

          <!-- View mode toggle -->
          <div class="d-flex align-center mb-3">
            <v-btn-toggle v-model="auctionViewMode" mandatory density="compact" variant="outlined" color="deep-purple" rounded="lg" class="mr-3">
              <v-btn value="cards" size="small"><v-icon size="18">mdi-view-grid</v-icon></v-btn>
              <v-btn value="table" size="small"><v-icon size="18">mdi-view-list</v-icon></v-btn>
            </v-btn-toggle>
            <span class="text-body-2 text-medium-emphasis">0 auction listings</span>
          </div>

          <!-- Empty state -->
          <v-alert type="info" variant="tonal" class="mt-3">
            <v-icon start>mdi-gavel</v-icon>
            <strong>Auction Houses</strong> — scrape homes from foreclosure auctions, online auction platforms (Auction.com, Hubzu, Xome, etc.), and sheriff sales.
            <br><span class="text-caption text-medium-emphasis mt-1 d-block">This feature is under development. Sources and scrapers will be added soon.</span>
          </v-alert>

          <!-- Placeholder table -->
          <v-table v-if="auctionViewMode === 'table'" density="compact" hover class="mt-3">
            <thead>
              <tr>
                <th>Address</th>
                <th>City</th>
                <th>State</th>
                <th>Beds</th>
                <th>Bath</th>
                <th>Sq Ft</th>
                <th>Price</th>
                <th>Auction Date</th>
                <th>Source</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colspan="10" class="text-center text-medium-emphasis pa-6">No auction listings yet</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>

        <!-- Auction favorites -->
        <v-window-item value="auction_favorites">
          <v-alert type="info" variant="tonal">
            <v-icon start>mdi-heart-outline</v-icon>
            No auction favorites yet. Favorite auction listings will appear here.
          </v-alert>
        </v-window-item>

        <!-- Auction sources -->
        <v-window-item value="auction_sources">
          <v-card variant="outlined" class="pa-4 mb-3">
            <div class="d-flex align-center mb-3">
              <div class="text-h6">Auction Sources</div>
              <v-spacer />
              <v-btn color="deep-purple" variant="tonal" size="small" prepend-icon="mdi-plus" disabled>
                Add Source
              </v-btn>
            </div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>URL</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Auction.com</td>
                  <td>Online Auction</td>
                  <td class="text-caption">https://www.auction.com</td>
                  <td><v-chip size="x-small" color="grey" variant="tonal">Planned</v-chip></td>
                </tr>
                <tr>
                  <td>Hubzu</td>
                  <td>Online Auction</td>
                  <td class="text-caption">https://www.hubzu.com</td>
                  <td><v-chip size="x-small" color="grey" variant="tonal">Planned</v-chip></td>
                </tr>
                <tr>
                  <td>Xome</td>
                  <td>Online Auction</td>
                  <td class="text-caption">https://www.xome.com</td>
                  <td><v-chip size="x-small" color="grey" variant="tonal">Planned</v-chip></td>
                </tr>
                <tr>
                  <td>Foreclosure.com</td>
                  <td>Foreclosure</td>
                  <td class="text-caption">https://www.foreclosure.com</td>
                  <td><v-chip size="x-small" color="grey" variant="tonal">Planned</v-chip></td>
                </tr>
                <tr>
                  <td>RealtyTrac</td>
                  <td>Foreclosure</td>
                  <td class="text-caption">https://www.realtytrac.com</td>
                  <td><v-chip size="x-small" color="grey" variant="tonal">Planned</v-chip></td>
                </tr>
                <tr>
                  <td>Sheriff Sales</td>
                  <td>Government</td>
                  <td class="text-caption">Various county sites</td>
                  <td><v-chip size="x-small" color="grey" variant="tonal">Planned</v-chip></td>
                </tr>
              </tbody>
            </v-table>
          </v-card>
        </v-window-item>

        <!-- Auction settings -->
        <v-window-item value="auction_settings">
          <v-card variant="outlined" class="pa-4">
            <div class="text-h6 mb-3">Auction Scraping Settings</div>
            <v-row dense>
              <v-col cols="12" md="6">
                <v-text-field label="Max Total Price ($)" model-value="200000" variant="outlined" density="compact" disabled />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field label="States (comma-separated)" model-value="" variant="outlined" density="compact" placeholder="e.g. Washington, Oregon" disabled />
              </v-col>
              <v-col cols="12" md="6">
                <v-select label="Property Types" :items="['Single Family', 'Condo', 'Townhouse', 'Multi-Family']" variant="outlined" density="compact" multiple chips disabled />
              </v-col>
              <v-col cols="12" md="6">
                <v-select label="Scrape Interval (hours)" :items="['6', '12', '24', '48']" model-value="24" variant="outlined" density="compact" disabled />
              </v-col>
            </v-row>
            <v-alert type="info" variant="tonal" density="compact" class="mt-3">
              <v-icon start size="16">mdi-information</v-icon>
              Auction settings will be enabled once auction scrapers are implemented.
            </v-alert>
          </v-card>
        </v-window-item>
      </v-window>

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

          <!-- HOA info -->
          <div v-if="detailItem.hoa" class="mt-3">
            <div class="text-subtitle-2 mb-1"><v-icon size="16" class="mr-1">mdi-home-group</v-icon>HOA</div>
            <div class="d-flex flex-wrap ga-2">
              <v-chip size="small" :color="detailItem.hoa === 'yes' ? 'red' : 'green'" variant="tonal">
                {{ detailItem.hoa === 'yes' ? 'Has HOA' : 'No HOA' }}
              </v-chip>
              <v-chip v-if="detailItem.hoa_dues" size="small" color="orange" variant="tonal">
                Dues: {{ detailItem.hoa_dues }}
              </v-chip>
              <v-chip v-if="detailItem.annual_taxes" size="small" color="amber" variant="tonal">
                Taxes: {{ detailItem.annual_taxes }}
              </v-chip>
            </div>
            <div v-if="detailItem.hoa_name" class="text-body-2 mt-1 text-medium-emphasis">{{ detailItem.hoa_name }}</div>
            <div v-if="detailItem.hoa_info" class="text-body-2 mt-1 pa-2 bg-grey-darken-3 rounded" style="font-size: 0.85em">{{ detailItem.hoa_info }}</div>
          </div>

          <!-- Zoning info -->
          <div v-if="detailItem.zoning || detailItem.zoning_code" class="mt-3">
            <div class="text-subtitle-2 mb-1"><v-icon size="16" class="mr-1">mdi-gavel</v-icon>Zoning</div>
            <div class="d-flex flex-wrap ga-2 mb-2">
              <v-chip v-if="detailItem.zoning" size="small" color="purple" variant="tonal">{{ detailItem.zoning }}</v-chip>
              <v-chip v-if="detailItem.zoning_code" size="small" color="deep-purple" variant="tonal">{{ detailItem.zoning_code }}</v-chip>
            </div>
            <div v-if="detailItem.zoning_definition" class="text-body-2 pa-3 bg-grey-darken-3 rounded" style="max-height: 200px; overflow-y: auto; font-size: 0.85em">
              {{ detailItem.zoning_definition }}
            </div>
          </div>

          <!-- Extra details -->
          <v-list v-if="detailItem.road_access || detailItem.slope || detailItem.usage_potential" density="compact" class="bg-transparent mt-2">
            <v-list-item v-if="detailItem.road_access">
              <template #prepend><v-icon size="18" class="mr-2">mdi-road</v-icon></template>
              <v-list-item-title>Road: {{ detailItem.road_access }}</v-list-item-title>
            </v-list-item>
            <v-list-item v-if="detailItem.slope">
              <template #prepend><v-icon size="18" class="mr-2">mdi-image-filter-hdr</v-icon></template>
              <v-list-item-title>Slope: {{ detailItem.slope }}</v-list-item-title>
            </v-list-item>
            <v-list-item v-if="detailItem.usage_potential">
              <template #prepend><v-icon size="18" class="mr-2">mdi-land-plots</v-icon></template>
              <v-list-item-title>Usage: {{ detailItem.usage_potential }}</v-list-item-title>
            </v-list-item>
          </v-list>

          <div v-if="detailItem.description" class="text-body-2 mt-3 pa-3 bg-grey-darken-3 rounded">
            {{ detailItem.description }}
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="detailDialog = false">Close</v-btn>
          <v-btn color="brown" variant="tonal" :href="detailItem.url" target="_blank" append-icon="mdi-open-in-new" @click="markSeen(detailItem)">
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

    <!-- Save filter preset dialog -->
    <v-dialog v-model="showSavePreset" max-width="400">
      <v-card>
        <v-card-title>Save Filter Preset</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="presetName"
            label="Preset name"
            variant="outlined"
            density="compact"
            placeholder="e.g. Cheap Texas land"
            autofocus
            @keydown.enter="savePreset"
          />
          <div class="text-caption text-medium-emphasis mt-2">
            Saves current filters: source, states, max price, min acreage, zoning, HOA, sort.
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showSavePreset = false">Cancel</v-btn>
          <v-btn color="brown" variant="tonal" :disabled="!presetName.trim()" @click="savePreset">Save</v-btn>
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
      mainTab: localStorage.getItem('re_mainTab') || 'land',
      activeTab: localStorage.getItem('re_tab') || 'listings',

      // Auction Houses tab
      auctionTab: 'auction_listings',
      auctionViewMode: 'table',
      auctionFilterState: [],
      auctionFilterMaxPrice: null,
      auctionFilterMinBeds: null,
      auctionFilterMinBath: null,
      auctionFilterType: null,
      auctionTypeOptions: ['Single Family', 'Condo', 'Townhouse', 'Multi-Family', 'Commercial'],

      // Stats
      stats: null,
      lastScrape: null,
      scraping: false,
      stoppingParserScrape: false,
      scrapeStatusData: null,
      scrapeProgress: null,
      _pollTimer: null,

      // Listings tab
      listings: [],
      listingsTotal: 0,
      loadingListings: false,
      currentPage: 1,
      perPage: 50,
      viewMode: localStorage.getItem('re_view') || 'cards',
      lastClickedHash: null,
      hiddenCount: 0,
      seenHashes: (() => { try { const arr = JSON.parse(localStorage.getItem('re_seen') || '[]'); const obj = {}; arr.forEach(h => obj[h] = true); return obj } catch { return {} } })(),
      showHidden: localStorage.getItem('re_showHidden') === 'true',
      filterSource: (() => { try { return JSON.parse(localStorage.getItem('re_filterSource')) } catch { return null } })(),
      filterState: (() => { try { const v = JSON.parse(localStorage.getItem('re_filterState')); return Array.isArray(v) ? v : [] } catch { return [] } })(),
      filterMaxPrice: (() => { try { return JSON.parse(localStorage.getItem('re_filterMaxPrice')) } catch { return null } })(),
      filterMinAcreage: (() => { try { return JSON.parse(localStorage.getItem('re_filterMinAcreage')) } catch { return null } })(),
      filterZoning: (() => { try { const v = JSON.parse(localStorage.getItem('re_filterZoning')); return Array.isArray(v) ? v : [] } catch { return [] } })(),
      zoningOptions: [],
      filterHoa: (() => { try { return JSON.parse(localStorage.getItem('re_filterHoa')) } catch { return null } })(),
      filterHasComment: false,
      filterSearchComment: '',
      hoaOptions: [
        { title: 'No HOA', value: 'no' },
        { title: 'Has HOA', value: 'yes' },
      ],
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

      // Watched tab
      watchedItems: [],
      loadingWatched: false,

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

      // Filter presets
      filterPresets: [],
      showSavePreset: false,
      presetName: '',

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
    mainTab(tab) {
      localStorage.setItem('re_mainTab', tab)
    },
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
    filterZoning(v) {
      localStorage.setItem('re_filterZoning', JSON.stringify(v || []))
    },
    filterHoa(v) {
      localStorage.setItem('re_filterHoa', JSON.stringify(v))
    },
    sortBy(v) {
      localStorage.setItem('re_sortBy', v)
    },
    sortDir(v) {
      localStorage.setItem('re_sortDir', v)
    },
    showHidden(v) {
      localStorage.setItem('re_showHidden', String(v))
      this.loadListings()
    },
  },

  async mounted() {
    this.loadSettings()
    this.loadStats()
    this.loadScrapeStatus()
    this.loadZoningOptions()
    this.loadFilterPresets()
    this.loadHiddenCount()
    await this.loadSourceOptions()
    this.loadTabData(this.activeTab)
    // Migrate localStorage hidden hashes to server-side
    this._migrateHiddenHashes()
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

  computed: {
    visibleListings() {
      return this.listings
    },
    totalPages() {
      return Math.max(1, Math.ceil(this.listingsTotal / this.perPage))
    },
  },

  methods: {
    clearFilters() {
      this.filterSource = null
      this.filterState = []
      this.filterMaxPrice = null
      this.filterMinAcreage = null
      this.filterZoning = []
      this.filterHoa = null
      this.filterHasComment = false
      this.filterSearchComment = ''
      this.sortBy = 'price'
      this.sortDir = 'asc'
      this.loadListings()
    },
    async loadZoningOptions() {
      try {
        const { data } = await api.get(`${API}/zoning-values`)
        this.zoningOptions = data.values || []
      } catch {}
    },
    async toggleHidden(item) {
      try {
        const { data } = await api.patch(`${API}/listings/${item.hash}/hidden`)
        item.is_hidden = data.is_hidden
        if (data.is_hidden && !this.showHidden) {
          // Remove from current view when hiding and not showing hidden
          this.listings = this.listings.filter(l => l.hash !== item.hash)
          this.listingsTotal = Math.max(0, this.listingsTotal - 1)
        } else if (!data.is_hidden && this.showHidden) {
          // Unhiding while viewing hidden — just update the flag
        }
        this.loadHiddenCount()
      } catch (e) {
        this.notify('Failed to update hidden status', 'error')
      }
    },
    markSeen(item) {
      if (!item?.hash || this.seenHashes[item.hash]) return
      this.seenHashes[item.hash] = true
      this.seenHashes = { ...this.seenHashes }
      localStorage.setItem('re_seen', JSON.stringify(Object.keys(this.seenHashes)))
    },
    async deleteListing(item) {
      const name = item.name || 'this listing'
      if (!confirm(`Delete "${name}"?\n\nThis listing will be permanently hidden and will not reappear on future scrapes.`)) return
      try {
        await api.delete(`${API}/listings/${item.hash}`)
        this.listings = this.listings.filter(l => l.hash !== item.hash)
        this.listingsTotal = Math.max(0, this.listingsTotal - 1)
        this.notify('Listing deleted')
      } catch (e) {
        this.notify('Failed to delete listing', 'error')
      }
    },
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
      const palette = [
        'blue', 'green', 'orange', 'purple', 'teal', 'red', 'indigo',
        'cyan', 'pink', 'amber', 'deep-purple', 'light-blue', 'lime',
        'brown', 'blue-grey', 'deep-orange', 'light-green', 'yellow',
        'grey', 'grey-darken-1',
      ]
      const ids = this.sources.map(s => s.source_id)
      const idx = ids.indexOf(src)
      return idx >= 0 ? palette[idx % palette.length] : 'grey'
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
        case 'watched': this.loadWatched(); break
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

    // ---- Stop scrape ----
    async stopScrape() {
      this.stoppingParserScrape = true
      try {
        const { data } = await api.post(`${API}/scrape/stop`)
        this.notify(data.message || 'Stop requested', data.ok ? 'warning' : 'info')
      } catch (e) {
        this.notify('Failed to stop: ' + (e.response?.data?.detail || e.message), 'error')
      } finally {
        this.stoppingParserScrape = false
      }
    },

    // ---- Scrape with mode (background + polling) ----
    async scrapeMode(mode = 'full') {
      this.scraping = true
      this.scrapeProgress = null
      try {
        const params = new URLSearchParams({ mode })
        const { data } = await api.post(`${API}/scrape-all?${params.toString()}`)
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
    // Backwards compat
    async scrapeAll() {
      return this.scrapeMode('full')
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
    async _migrateHiddenHashes() {
      // One-time migration: move localStorage hidden hashes to server-side is_hidden
      try {
        const raw = localStorage.getItem('re_hidden')
        if (!raw) return
        const hashes = JSON.parse(raw)
        if (!Array.isArray(hashes) || hashes.length === 0) return
        await api.post(`${API}/listings/bulk-hide`, { hashes })
        localStorage.removeItem('re_hidden')
        this.loadHiddenCount()
        this.loadListings()
      } catch {}
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
          this.loadZoningOptions()
          this.loadTabData(this.activeTab)
        }
      } catch {
        // If progress endpoint fails, just keep polling
      }
    },

    // ---- Listings ----
    async loadListings(resetPage = true) {
      if (resetPage) this.currentPage = 1
      this.loadingListings = true
      try {
        const params = {
          sort_by: this.sortBy,
          sort_dir: this.sortDir,
          limit: this.perPage,
          offset: (this.currentPage - 1) * this.perPage,
          exclude_hidden: !this.showHidden,
        }
        if (this.filterSource) params.source = this.filterSource
        if (this.filterState && this.filterState.length) params.state = this.filterState.join(',')
        if (this.filterMaxPrice) params.max_price = this.filterMaxPrice
        if (this.filterMinAcreage) params.min_acreage = this.filterMinAcreage
        if (this.filterZoning && this.filterZoning.length) params.zoning = this.filterZoning.join(',')
        if (this.filterHoa) params.hoa = this.filterHoa
        if (this.filterHasComment) params.has_comment = true
        if (this.filterSearchComment) params.search_comment = this.filterSearchComment

        const { data } = await api.get(`${API}/listings`, { params })
        this.listings = (data.items || []).map(i => ({ ...i, _loadingDetail: false }))
        this.listingsTotal = data.total || 0
      } catch {} finally {
        this.loadingListings = false
      }
    },
    async loadHiddenCount() {
      try {
        const { data } = await api.get(`${API}/hidden-count`)
        this.hiddenCount = data.count || 0
      } catch {}
    },
    goToPage(page) {
      this.currentPage = page
      this.loadListings(false)
      this.$nextTick(() => {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      })
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

    // ---- Watched ----
    async loadWatched() {
      this.loadingWatched = true
      try {
        const { data } = await api.get(`${API}/listings`, { params: { watched_only: true, limit: 200 } })
        this.watchedItems = data.items || []
      } catch {} finally {
        this.loadingWatched = false
      }
    },
    async toggleWatched(item) {
      try {
        if (item.is_watched) {
          await api.delete(`${API}/watched/${item.hash}`)
          item.is_watched = false
          this.watchedItems = this.watchedItems.filter(w => w.hash !== item.hash)
        } else {
          await api.post(`${API}/watched/${item.hash}`)
          item.is_watched = true
        }
        this.loadStats()
      } catch (e) {
        this.notify('Failed to update watched status', 'error')
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

    // ---- Comment ----
    async saveComment(item) {
      const comment = (item.user_comment || '').trim()
      try {
        await api.patch(`${API}/listings/${item.hash}/comment`, { comment })
      } catch (e) {
        this.notify('Failed to save comment', 'error')
      }
    },

    // ---- Sources ----
    async loadSourceOptions() {
      try {
        const { data } = await api.get(`${API}/sources`)
        this.sources = data.items || []
        this.sourceOptions = [
          { title: 'All Sources', value: null },
          ...this.sources.map(s => ({ title: s.name, value: s.source_id })),
        ]
      } catch {}
    },
    async loadSources() {
      try {
        const { data } = await api.get(`${API}/sources`)
        this.sources = data.items || []
        this.sourceOptions = [
          { title: 'All Sources', value: null },
          ...this.sources.map(s => ({ title: s.name, value: s.source_id })),
        ]
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

    // ---- Filter presets ----
    async loadFilterPresets() {
      try {
        const { data } = await api.get(`${API}/filter-presets`)
        this.filterPresets = data.items || []
      } catch {}
    },
    openSavePreset() {
      this.presetName = ''
      this.showSavePreset = true
    },
    async savePreset() {
      const name = this.presetName.trim()
      if (!name) return
      try {
        const filters = {
          source: this.filterSource,
          state: this.filterState,
          maxPrice: this.filterMaxPrice,
          minAcreage: this.filterMinAcreage,
          zoning: this.filterZoning,
          hoa: this.filterHoa,
          sortBy: this.sortBy,
          sortDir: this.sortDir,
        }
        await api.post(`${API}/filter-presets`, { name, filters })
        this.showSavePreset = false
        this.notify('Preset saved')
        this.loadFilterPresets()
      } catch (e) {
        this.notify('Failed to save preset', 'error')
      }
    },
    applyPreset(preset) {
      const f = preset.filters || {}
      this.filterSource = f.source || null
      this.filterState = Array.isArray(f.state) ? f.state : []
      this.filterMaxPrice = f.maxPrice || null
      this.filterMinAcreage = f.minAcreage || null
      this.filterZoning = Array.isArray(f.zoning) ? f.zoning : []
      this.filterHoa = f.hoa || null
      this.sortBy = f.sortBy || 'price'
      this.sortDir = f.sortDir || 'asc'
      this.loadListings()
      this.notify(`Applied: ${preset.name}`)
    },
    async deletePreset(presetId) {
      if (!confirm('Delete this saved search?')) return
      try {
        await api.delete(`${API}/filter-presets/${presetId}`)
        this.filterPresets = this.filterPresets.filter(p => p._id !== presetId)
        this.notify('Preset deleted')
      } catch (e) {
        this.notify('Failed to delete preset', 'error')
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
.filter-panel {
  background: rgba(141, 110, 99, 0.06);
  border: 1px solid rgba(141, 110, 99, 0.12);
  border-radius: 12px;
}
.filter-panel :deep(.v-field--variant-solo-filled .v-field__overlay) {
  opacity: 0.04;
}
.comment-field :deep(.v-field__input) {
  font-size: 0.8rem;
  padding: 2px 4px;
  min-height: 28px;
}
.comment-field :deep(.v-field) {
  border-bottom: 1px dashed rgba(255, 255, 255, 0.15);
}
.comment-field :deep(.v-field:hover) {
  border-bottom-color: rgba(255, 255, 255, 0.4);
}
.comment-field :deep(.v-field--focused) {
  border-bottom-color: #8D6E63;
}
.comment-card-field :deep(.v-field__input) {
  font-size: 0.8rem;
  min-height: 32px;
}

/* Subtle "seen" indicator for viewed listings */
.re-seen {
  opacity: 0.72;
  border-color: rgba(255, 255, 255, 0.04) !important;
}
.re-seen:hover {
  opacity: 1;
}
.re-seen-row {
  opacity: 0.65;
}
.re-seen-row:hover {
  opacity: 1;
}
</style>
