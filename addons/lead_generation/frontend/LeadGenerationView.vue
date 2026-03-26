<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <v-icon size="32" color="cyan-accent-3" class="mr-3">mdi-account-search</v-icon>
      <div class="text-h4 font-weight-bold">Lead Generation</div>
      <v-spacer />
      <v-btn color="cyan" variant="tonal" prepend-icon="mdi-refresh" @click="refreshAll" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <!-- Stats -->
    <div class="d-flex flex-wrap ga-2 mb-4" v-if="stats">
      <v-chip variant="tonal" color="blue" size="large">
        <v-icon start size="16">mdi-account-group</v-icon>
        Clients: {{ stats.clients || 0 }}
      </v-chip>
      <v-chip variant="tonal" color="green" size="large" v-if="stats.clients_new">
        <v-icon start size="16">mdi-new-box</v-icon>
        New: {{ stats.clients_new }}
      </v-chip>
      <v-chip variant="tonal" color="amber" size="large" v-if="stats.clients_qualified">
        <v-icon start size="16">mdi-star</v-icon>
        Qualified: {{ stats.clients_qualified }}
      </v-chip>
      <v-chip variant="tonal" color="purple" size="large">
        <v-icon start size="16">mdi-briefcase-search</v-icon>
        Jobs: {{ stats.jobs || 0 }}
      </v-chip>
      <v-chip variant="tonal" color="teal" size="large">
        <v-icon start size="16">mdi-link-variant</v-icon>
        Connections: {{ stats.connections || 0 }}
      </v-chip>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="cyan-accent-3" class="mb-4" show-arrows>
      <v-tab value="clients">
        <v-icon start size="18">mdi-account-group</v-icon>
        Clients Search
      </v-tab>
      <v-tab value="jobs">
        <v-icon start size="18">mdi-briefcase-search</v-icon>
        Job Search
      </v-tab>
      <v-tab value="connections">
        <v-icon start size="18">mdi-link-variant</v-icon>
        Connection Search
      </v-tab>
      <v-tab value="map">
        <v-icon start size="18">mdi-graph-outline</v-icon>
        Connections Map
      </v-tab>
      <v-tab value="settings">
        <v-icon start size="18">mdi-cog-outline</v-icon>
        Settings
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">

      <!-- ═══════ CLIENTS SEARCH ═══════ -->
      <v-window-item value="clients">
        <v-row dense class="mb-3">
          <v-col cols="12" sm="4">
            <v-text-field v-model="clientSearch" label="Search clients..." variant="outlined" density="compact" prepend-inner-icon="mdi-magnify" clearable hide-details @keyup.enter="loadClients" />
          </v-col>
          <v-col cols="6" sm="2">
            <v-select v-model="clientStatusFilter" :items="clientStatuses" label="Status" variant="outlined" density="compact" clearable hide-details />
          </v-col>
          <v-col cols="6" sm="2">
            <v-text-field v-model="clientIndustryFilter" label="Industry" variant="outlined" density="compact" clearable hide-details />
          </v-col>
          <v-col cols="auto">
            <v-btn color="cyan" variant="tonal" @click="loadClients" class="mt-1">Search</v-btn>
          </v-col>
          <v-spacer />
          <v-col cols="auto" class="d-flex ga-1">
            <v-btn v-if="selectedClients.length" color="deep-purple" variant="tonal" size="small" prepend-icon="mdi-upload" @click="pushToAkm('leads')">
              Push {{ selectedClients.length }} to AKM
            </v-btn>
            <v-btn color="blue" variant="tonal" size="small" prepend-icon="mdi-plus" @click="showAddClient = true">Add Client</v-btn>
          </v-col>
        </v-row>

        <v-progress-linear v-if="loadingClients" indeterminate color="blue" class="mb-2" />

        <!-- Clients table -->
        <v-card variant="outlined" v-if="clients.length > 0">
          <v-table density="compact" hover>
            <thead>
              <tr>
                <th style="width:32px"><v-checkbox-btn v-model="selectAllClients" @update:model-value="toggleAllClients" hide-details density="compact" /></th>
                <th>Name</th>
                <th>Company</th>
                <th>Title</th>
                <th>Industry</th>
                <th>Status</th>
                <th>Source</th>
                <th style="width:80px">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in clients" :key="c._id">
                <td><v-checkbox-btn v-model="selectedClients" :value="c._id" hide-details density="compact" /></td>
                <td>
                  <div class="d-flex align-center">
                    <span class="font-weight-medium">{{ c.name }}</span>
                    <v-btn v-if="c.linkedin" :href="c.linkedin" target="_blank" icon="mdi-linkedin" size="x-small" variant="text" color="blue" class="ml-1" />
                  </div>
                  <div v-if="c.email" class="text-caption text-grey">{{ c.email }}</div>
                </td>
                <td class="text-body-2">{{ c.company }}</td>
                <td class="text-body-2">{{ c.title }}</td>
                <td class="text-body-2">{{ c.industry }}</td>
                <td>
                  <v-chip :color="clientStatusColor(c.status)" size="x-small" variant="tonal">{{ c.status }}</v-chip>
                </td>
                <td class="text-caption">{{ c.source }}</td>
                <td>
                  <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editClient(c)" />
                  <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="deleteClient(c._id)" />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card>

        <v-card v-else-if="!loadingClients" variant="tonal" class="pa-8 text-center">
          <v-icon size="48" color="grey">mdi-account-search-outline</v-icon>
          <div class="text-h6 mt-2 text-grey">No clients yet</div>
          <div class="text-body-2 text-grey mb-3">Add clients manually or let an agent search using the leadgen_search skill</div>
          <v-btn color="blue" variant="tonal" @click="showAddClient = true" prepend-icon="mdi-plus">Add First Client</v-btn>
        </v-card>

        <div v-if="clientsTotal > clients.length" class="text-center mt-3">
          <v-btn variant="text" @click="loadMoreClients">Load More ({{ clientsTotal - clients.length }} remaining)</v-btn>
        </div>
      </v-window-item>

      <!-- ═══════ JOB SEARCH (sub-tabs) ═══════ -->
      <v-window-item value="jobs">
        <v-tabs v-model="jobSubTab" color="purple-accent-2" class="mb-3" density="compact" show-arrows>
          <v-tab value="cv"><v-icon start size="16">mdi-file-document</v-icon>CV</v-tab>
          <v-tab value="criterias"><v-icon start size="16">mdi-filter-cog</v-icon>Job Criterias</v-tab>
          <v-tab value="parsed"><v-icon start size="16">mdi-text-search</v-icon>Parsed</v-tab>
          <v-tab value="sources"><v-icon start size="16">mdi-web</v-icon>Sources</v-tab>
        </v-tabs>

        <v-window v-model="jobSubTab">

          <!-- ─── CV ─── -->
          <v-window-item value="cv">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3">
              Upload your resumes here. Name each one clearly — agents can reference them when applying to jobs.
            </v-alert>

            <div class="d-flex justify-end mb-3">
              <v-btn color="purple" variant="tonal" size="small" prepend-icon="mdi-upload" @click="triggerCvUpload">Upload CV</v-btn>
              <input ref="cvFileInput" type="file" accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.md" style="display:none" @change="handleCvUpload" />
            </div>

            <v-progress-linear v-if="loadingCvs" indeterminate color="purple" class="mb-2" />

            <v-card v-if="cvs.length > 0" variant="outlined">
              <v-table density="compact" hover>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>File</th>
                    <th>Description</th>
                    <th>Date</th>
                    <th style="width:120px">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="cv in cvs" :key="cv._id">
                    <td>
                      <v-text-field v-if="editingCvId === cv._id" v-model="editCvTitle" variant="outlined" density="compact" hide-details style="max-width:200px" @keyup.enter="saveCvEdit(cv._id)" />
                      <span v-else class="font-weight-medium">{{ cv.title }}</span>
                    </td>
                    <td class="text-caption">
                      <v-chip size="x-small" variant="tonal" color="purple">{{ cv.ext?.toUpperCase() }}</v-chip>
                      {{ cv.original_name }}
                    </td>
                    <td class="text-body-2 text-grey" style="max-width:250px">
                      <v-text-field v-if="editingCvId === cv._id" v-model="editCvDesc" variant="outlined" density="compact" hide-details placeholder="Description..." />
                      <span v-else>{{ cv.description || '—' }}</span>
                    </td>
                    <td class="text-caption">{{ formatDate(cv.created_at) }}</td>
                    <td>
                      <template v-if="editingCvId === cv._id">
                        <v-btn icon="mdi-check" size="x-small" variant="text" color="green" @click="saveCvEdit(cv._id)" />
                        <v-btn icon="mdi-close" size="x-small" variant="text" @click="editingCvId = null" />
                      </template>
                      <template v-else>
                        <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="startEditCv(cv)" />
                        <v-btn icon="mdi-download" size="x-small" variant="text" color="blue" @click="downloadCv(cv._id)" />
                        <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="deleteCv(cv._id)" />
                      </template>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
            <v-card v-else-if="!loadingCvs" variant="tonal" class="pa-8 text-center">
              <v-icon size="48" color="grey">mdi-file-document-outline</v-icon>
              <div class="text-h6 mt-2 text-grey">No CVs uploaded yet</div>
            </v-card>
          </v-window-item>

          <!-- ─── JOB CRITERIAS ─── -->
          <v-window-item value="criterias">
            <v-card variant="outlined" class="pa-4" style="max-width:1500px">
              <div class="text-h6 mb-3">Job Search Criterias</div>

              <v-row dense>
                <v-col cols="12" md="6">
                  <v-combobox v-model="criterias.industries" label="Priority Industries" variant="outlined" density="compact" multiple chips closable-chips class="mb-3" placeholder="e.g. fintech, healthcare, AI..." hint="Press Enter to add" persistent-hint />
                </v-col>
              </v-row>

              <div class="text-subtitle-2 font-weight-bold mb-2">Desired Target Companies</div>
              <v-row dense>
                <v-col cols="12" md="4">
                  <v-textarea v-model="criterias.companies_dream" label="Dream Companies" variant="outlined" density="compact" rows="3" class="mb-3" placeholder="One per line..." hint="Top-choice employers" persistent-hint />
                </v-col>
                <v-col cols="12" md="4">
                  <v-textarea v-model="criterias.companies_good" label="Good Fit Companies" variant="outlined" density="compact" rows="3" class="mb-3" placeholder="One per line..." hint="Solid options you'd accept" persistent-hint />
                </v-col>
                <v-col cols="12" md="4">
                  <v-textarea v-model="criterias.companies_backup" label="Backup Companies" variant="outlined" density="compact" rows="3" class="mb-3" placeholder="One per line..." hint="Fallback / safety net" persistent-hint />
                </v-col>
              </v-row>

              <!-- Salary Section -->
              <v-card variant="tonal" class="pa-3 mb-4">
                <div class="text-subtitle-2 font-weight-bold mb-2"><v-icon size="16" class="mr-1">mdi-currency-usd</v-icon>Minimum Salary</div>
                <v-row dense class="mb-2">
                  <v-col cols="6" md="3">
                    <v-text-field v-model="criterias.salary_annual_min" label="Annual ($)" variant="outlined" density="compact" type="number" hide-details @input="syncFromAnnual" />
                  </v-col>
                  <v-col cols="6" md="3">
                    <v-text-field v-model="criterias.salary_monthly_min" label="Monthly ($)" variant="outlined" density="compact" type="number" hide-details @input="syncFromMonthly" />
                  </v-col>
                  <v-col cols="12" md="3">
                    <v-select v-model="criterias.tax_state" :items="taxStates" label="State (for tax estimate)" variant="outlined" density="compact" clearable hide-details />
                  </v-col>
                  <v-col cols="12" md="3">
                    <v-alert v-if="takeHomeEstimate" type="info" variant="tonal" density="compact" class="text-body-2 h-100 d-flex align-center">
                      <div>
                        <v-icon size="14" class="mr-1">mdi-calculator</v-icon>
                        <strong>~${{ takeHomeEstimate.monthly }}/mo</strong> after taxes
                        <span class="text-grey ml-1">(~{{ takeHomeEstimate.eff_rate }}%{{ criterias.tax_state ? ' ' + criterias.tax_state : '' }})</span>
                      </div>
                    </v-alert>
                  </v-col>
                </v-row>
              </v-card>

              <v-row dense>
                <v-col cols="12" md="6">
                  <v-combobox v-model="criterias.keywords" label="Keywords (title & description)" variant="outlined" density="compact" multiple chips closable-chips class="mb-3" placeholder="e.g. Python, engineer, remote, Kubernetes..." hint="Tags matched against job title and description" persistent-hint />
                </v-col>
                <v-col cols="12" md="6">
                  <v-select v-model="criterias.states" :items="taxStates" label="States" variant="outlined" density="compact" multiple chips closable-chips class="mb-3" hint="Select target states" persistent-hint />
                </v-col>
              </v-row>

              <v-row dense>
                <v-col cols="12">
                  <v-textarea v-model="criterias.notes" label="Notes" variant="outlined" density="compact" rows="2" class="mb-3" />
                </v-col>
              </v-row>

              <v-btn color="purple" variant="tonal" prepend-icon="mdi-content-save" @click="saveCriterias" :loading="savingCriterias">
                Save Criterias
              </v-btn>
            </v-card>
          </v-window-item>

          <!-- ─── PARSED JOBS ─── -->
          <v-window-item value="parsed">
            <v-row dense class="mb-3">
              <v-col cols="12" sm="4">
                <v-text-field v-model="parsedSearch" label="Search parsed jobs..." variant="outlined" density="compact" prepend-inner-icon="mdi-magnify" clearable hide-details @keyup.enter="loadParsedJobs" />
              </v-col>
              <v-col cols="6" sm="2">
                <v-select v-model="parsedSourceFilter" :items="sourceNames" label="Source" variant="outlined" density="compact" clearable hide-details />
              </v-col>
              <v-col cols="6" sm="3">
                <v-select v-model="parsedExcludeSourceFilter" :items="sourceNames" label="Exclude Sources" variant="outlined" density="compact" clearable hide-details multiple chips closable-chips />
              </v-col>
              <v-col cols="6" sm="2">
                <v-select v-model="parsedStatusFilter" :items="parsedStatuses" label="Status" variant="outlined" density="compact" clearable hide-details />
              </v-col>
              <v-col cols="auto">
                <v-btn color="cyan" variant="tonal" @click="loadParsedJobs" class="mt-1">Search</v-btn>
              </v-col>
            </v-row>

            <v-progress-linear v-if="loadingParsed" indeterminate color="purple" class="mb-2" />

            <v-card v-if="parsedJobs.length > 0" variant="outlined">
              <v-table density="compact" hover>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Location</th>
                    <th>Source</th>
                    <th>Matches</th>
                    <th>Status</th>
                    <th>Date</th>
                    <th style="width:120px">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="pj in parsedJobs" :key="pj._id">
                    <td>
                      <a v-if="pj.url" :href="pj.url" target="_blank" class="text-decoration-none font-weight-medium">{{ pj.title }}</a>
                      <span v-else class="font-weight-medium">{{ pj.title }}</span>
                      <div v-if="pj.tags && pj.tags.length" class="d-flex flex-wrap ga-1 mt-1">
                        <v-chip v-for="t in pj.tags" :key="t" size="x-small" variant="tonal" color="cyan">{{ t }}</v-chip>
                      </div>
                    </td>
                    <td class="text-body-2">{{ pj.location }}</td>
                    <td class="text-caption">{{ pj.source }}</td>
                    <td class="text-center">
                      <v-chip size="x-small" :color="pj.keyword_matches >= 3 ? 'green' : pj.keyword_matches >= 2 ? 'amber' : 'grey'" variant="tonal">{{ pj.keyword_matches || 0 }}</v-chip>
                    </td>
                    <td>
                      <v-chip :color="parsedStatusColor(pj.status)" size="x-small" variant="tonal">{{ pj.status }}</v-chip>
                    </td>
                    <td class="text-caption">{{ formatDate(pj.parsed_at) }}</td>
                    <td>
                      <v-btn v-if="pj.status !== 'saved'" icon="mdi-content-save" size="x-small" variant="text" color="green" title="Save as Job" @click="saveAsJob(pj._id)" />
                      <v-btn v-if="pj.url" :href="pj.url" target="_blank" icon="mdi-open-in-new" size="x-small" variant="text" />
                      <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="deleteParsedJob(pj._id)" />
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-card>
            <v-card v-else-if="!loadingParsed" variant="tonal" class="pa-8 text-center">
              <v-icon size="48" color="grey">mdi-text-search-variant</v-icon>
              <div class="text-h6 mt-2 text-grey">No parsed jobs yet</div>
              <div class="text-body-2 text-grey">Configure sources and trigger a scrape to populate this list</div>
            </v-card>

            <div v-if="parsedTotal > parsedJobs.length" class="text-center mt-3">
              <v-btn variant="text" @click="loadMoreParsed">Load More ({{ parsedTotal - parsedJobs.length }} remaining)</v-btn>
            </div>
          </v-window-item>

          <!-- ─── SOURCES ─── -->
          <v-window-item value="sources">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3">
              Configure job listing sources. Add keywords to filter results — only listings matching at least the minimum keyword count will be kept.
            </v-alert>

            <div class="d-flex justify-end mb-3">
              <v-btn color="purple" variant="tonal" size="small" prepend-icon="mdi-plus" @click="showAddSource = true">Add Source</v-btn>
            </div>

            <v-progress-linear v-if="loadingSources" indeterminate color="purple" class="mb-2" />

            <v-row v-if="jobSources.length > 0">
              <v-col v-for="src in jobSources" :key="src._id" cols="12" md="6">
                <v-card variant="outlined" class="pa-3 h-100">
                  <div class="d-flex align-center mb-2">
                    <v-icon :color="src.enabled ? 'green' : 'grey'" size="20" class="mr-2">
                      {{ sourceTypeIcon(src.source_type) }}
                    </v-icon>
                    <span class="text-subtitle-1 font-weight-bold">{{ src.name }}</span>
                    <v-spacer />
                    <v-switch v-model="src.enabled" hide-details density="compact" color="green" class="flex-grow-0" @update:model-value="toggleSource(src)" />
                  </div>

                  <div class="text-caption text-grey mb-1">{{ src.url || 'Default URL' }}</div>
                  <div class="text-caption mb-2">Type: <strong>{{ src.source_type }}</strong> &middot; Interval: {{ src.scrape_interval_hours }}h &middot; Max: {{ src.max_results }}</div>

                  <div v-if="src.keywords && src.keywords.length" class="mb-2">
                    <span class="text-caption text-grey">Keywords:</span>
                    <div class="d-flex flex-wrap ga-1 mt-1">
                      <v-chip v-for="kw in src.keywords" :key="kw" size="x-small" variant="tonal" color="cyan">{{ kw }}</v-chip>
                    </div>
                  </div>

                  <div v-if="src.exclude_keywords && src.exclude_keywords.length" class="mb-2">
                    <span class="text-caption text-grey">Exclude:</span>
                    <div class="d-flex flex-wrap ga-1 mt-1">
                      <v-chip v-for="kw in src.exclude_keywords" :key="kw" size="x-small" variant="tonal" color="red">{{ kw }}</v-chip>
                    </div>
                  </div>

                  <div class="text-caption mb-2">Min keyword matches: <strong>{{ src.min_keyword_matches }}</strong></div>

                  <div v-if="src.last_scraped" class="text-caption text-grey mb-2">Last scraped: {{ formatDate(src.last_scraped) }}</div>

                  <v-divider class="my-2" />
                  <div class="d-flex ga-1">
                    <v-btn size="small" variant="tonal" color="cyan" prepend-icon="mdi-play" @click="scrapeSource(src._id)" :loading="scrapingId === src._id" :disabled="!src.enabled">Scrape Now</v-btn>
                    <v-btn icon="mdi-pencil" size="small" variant="text" @click="editSource(src)" />
                    <v-btn icon="mdi-delete" size="small" variant="text" color="red" @click="deleteSource(src._id)" />
                  </div>
                </v-card>
              </v-col>
            </v-row>
            <v-card v-else-if="!loadingSources" variant="tonal" class="pa-8 text-center">
              <v-icon size="48" color="grey">mdi-web</v-icon>
              <div class="text-h6 mt-2 text-grey">No job sources configured</div>
              <v-btn color="purple" variant="tonal" class="mt-3" @click="showAddSource = true" prepend-icon="mdi-plus">Add Source</v-btn>
            </v-card>
          </v-window-item>

        </v-window>
      </v-window-item>

      <!-- ═══════ CONNECTION SEARCH ═══════ -->
      <v-window-item value="connections">
        <v-row dense class="mb-3">
          <v-col cols="12" sm="4">
            <v-text-field v-model="connSearch" label="Search connections..." variant="outlined" density="compact" prepend-inner-icon="mdi-magnify" clearable hide-details @keyup.enter="loadConnections" />
          </v-col>
          <v-col cols="6" sm="2">
            <v-select v-model="connRelFilter" :items="relationshipTypes" label="Relationship" variant="outlined" density="compact" clearable hide-details />
          </v-col>
          <v-col cols="auto">
            <v-btn color="cyan" variant="tonal" @click="loadConnections" class="mt-1">Search</v-btn>
          </v-col>
          <v-spacer />
          <v-col cols="auto">
            <v-btn color="teal" variant="tonal" size="small" prepend-icon="mdi-plus" @click="showAddConn = true">Add Connection</v-btn>
          </v-col>
        </v-row>

        <v-progress-linear v-if="loadingConns" indeterminate color="teal" class="mb-2" />

        <v-row v-if="connections.length > 0">
          <v-col v-for="c in connections" :key="c._id" cols="12" sm="6" md="4" lg="3">
            <v-card variant="outlined" class="pa-3 h-100">
              <div class="d-flex align-center mb-2">
                <v-avatar size="32" :color="strengthColor(c.strength)" class="mr-2">
                  <span class="text-caption font-weight-bold">{{ (c.name || '?')[0].toUpperCase() }}</span>
                </v-avatar>
                <div>
                  <div class="text-subtitle-2 font-weight-bold">{{ c.name }}</div>
                  <div class="text-caption text-grey">{{ c.title }}<span v-if="c.company"> @ {{ c.company }}</span></div>
                </div>
                <v-spacer />
                <v-btn v-if="c.linkedin" :href="c.linkedin" target="_blank" icon="mdi-linkedin" size="x-small" variant="text" color="blue" />
              </div>
              <div class="d-flex flex-wrap ga-1 mb-2">
                <v-chip v-if="c.relationship" size="x-small" variant="tonal" color="teal">{{ c.relationship }}</v-chip>
                <v-chip v-if="c.met_through" size="x-small" variant="outlined">via {{ c.met_through }}</v-chip>
                <v-rating v-model="c.strength" :length="5" size="x-small" density="compact" color="amber" active-color="amber" half-increments readonly class="ml-auto" />
              </div>
              <div v-if="c.tags && c.tags.length" class="d-flex flex-wrap ga-1 mb-2">
                <v-chip v-for="t in c.tags" :key="t" size="x-small" variant="tonal" color="cyan">{{ t }}</v-chip>
              </div>
              <div v-if="c.email" class="text-caption text-grey"><v-icon size="12" class="mr-1">mdi-email</v-icon>{{ c.email }}</div>
              <div v-if="c.phone" class="text-caption text-grey"><v-icon size="12" class="mr-1">mdi-phone</v-icon>{{ c.phone }}</div>
              <div v-if="c.notes" class="text-caption text-grey mt-1 text-truncate-2">{{ c.notes }}</div>
              <div class="d-flex mt-2">
                <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="editConnection(c)" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="deleteConnection(c._id)" />
              </div>
            </v-card>
          </v-col>
        </v-row>

        <v-card v-else-if="!loadingConns" variant="tonal" class="pa-8 text-center">
          <v-icon size="48" color="grey">mdi-account-multiple-plus-outline</v-icon>
          <div class="text-h6 mt-2 text-grey">No connections yet</div>
          <v-btn color="teal" variant="tonal" class="mt-3" @click="showAddConn = true" prepend-icon="mdi-plus">Add Connection</v-btn>
        </v-card>
      </v-window-item>

      <!-- ═══════ CONNECTIONS MAP ═══════ -->
      <v-window-item value="map">
        <v-card variant="outlined" class="pa-4">
          <div class="d-flex align-center mb-3">
            <v-icon class="mr-2" color="teal">mdi-graph-outline</v-icon>
            <span class="text-h6">Connections Map</span>
            <v-spacer />
            <v-btn variant="tonal" color="teal" size="small" prepend-icon="mdi-refresh" @click="loadMap" :loading="loadingMap">Refresh</v-btn>
          </div>

          <v-progress-linear v-if="loadingMap" indeterminate color="teal" class="mb-3" />

          <div v-if="mapData && mapData.nodes && mapData.nodes.length > 1" ref="mapContainer" class="map-container" :style="{ height: mapHeight + 'px' }">
            <!-- SVG-based force graph -->
            <svg ref="mapSvg" width="100%" :height="mapHeight" class="connections-svg">
              <!-- Links -->
              <line v-for="(link, i) in renderedLinks" :key="'l'+i"
                :x1="link.x1" :y1="link.y1" :x2="link.x2" :y2="link.y2"
                :stroke="link.type === 'works_at' ? 'rgba(0,188,212,0.3)' : 'rgba(255,255,255,0.15)'"
                stroke-width="1" />
              <!-- Nodes -->
              <g v-for="node in renderedNodes" :key="node.id"
                :transform="`translate(${node.x}, ${node.y})`"
                class="map-node"
                @mouseenter="hoveredNode = node"
                @mouseleave="hoveredNode = null"
                style="cursor:pointer">
                <circle :r="node.size / 2"
                  :fill="node.type === 'center' ? '#00e5ff' : node.type === 'company' ? '#7c4dff' : '#26a69a'"
                  :stroke="hoveredNode?.id === node.id ? '#fff' : 'transparent'"
                  stroke-width="2" opacity="0.85" />
                <text dy="0.35em" text-anchor="middle" fill="#fff" :font-size="node.type === 'center' ? 11 : node.type === 'company' ? 9 : 8" font-weight="bold">
                  {{ node.name.length > 12 ? node.name.slice(0, 11) + '…' : node.name }}
                </text>
              </g>
            </svg>

            <!-- Tooltip -->
            <v-card v-if="hoveredNode && hoveredNode.type !== 'center'" class="map-tooltip" variant="tonal" density="compact">
              <div class="pa-2">
                <div class="font-weight-bold">{{ hoveredNode.name }}</div>
                <div v-if="hoveredNode.title" class="text-caption">{{ hoveredNode.title }}</div>
                <div v-if="hoveredNode.company && hoveredNode.type === 'person'" class="text-caption text-grey">{{ hoveredNode.company }}</div>
                <div v-if="hoveredNode.relationship" class="text-caption">
                  <v-chip size="x-small" variant="tonal" color="teal">{{ hoveredNode.relationship }}</v-chip>
                </div>
              </div>
            </v-card>
          </div>

          <div v-else-if="!loadingMap" class="text-center pa-8">
            <v-icon size="48" color="grey">mdi-graph-outline</v-icon>
            <div class="text-h6 mt-2 text-grey">No connections to map</div>
            <div class="text-body-2 text-grey">Add connections first, then view the map</div>
          </div>
        </v-card>
      </v-window-item>

      <!-- ═══════ SETTINGS ═══════ -->
      <v-window-item value="settings">
        <v-card variant="outlined" class="pa-4" style="max-width:700px">
          <div class="text-h6 mb-4">AKM-Advisor Integration</div>

          <v-text-field
            v-model="settAkmKey"
            label="AKM-Advisor API Key"
            variant="outlined"
            density="compact"
            :type="showAkmKey ? 'text' : 'password'"
            :append-inner-icon="showAkmKey ? 'mdi-eye-off' : 'mdi-eye'"
            @click:append-inner="showAkmKey = !showAkmKey"
            class="mb-3"
            @blur="saveSetting('leadgen_akm_api_key', settAkmKey)"
          />

          <v-text-field
            v-model="settAkmBaseUrl"
            label="AKM-Advisor Base URL"
            variant="outlined"
            density="compact"
            class="mb-3"
            @blur="saveSetting('leadgen_akm_base_url', settAkmBaseUrl)"
          />

          <v-row dense class="mb-3">
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="settLeadBoardId"
                label="Lead Board (Pipeline) ID"
                variant="outlined"
                density="compact"
                hint="Select from list or type ID"
                persistent-hint
                @blur="saveSetting('leadgen_akm_lead_board_id', settLeadBoardId)"
              >
                <template #append>
                  <v-btn icon="mdi-refresh" size="x-small" variant="text" @click="fetchAkmBoards('leads')" :loading="loadingLeadBoards" />
                </template>
              </v-text-field>
              <v-list v-if="akmLeadBoards.length" density="compact" class="mt-1" style="max-height:160px;overflow-y:auto">
                <v-list-item v-for="b in akmLeadBoards" :key="b.id || b._id" @click="settLeadBoardId = b.id || b._id; saveSetting('leadgen_akm_lead_board_id', settLeadBoardId)">
                  <v-list-item-title class="text-body-2">{{ b.name || b.title }}</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="settDealBoardId"
                label="Deal Board (Pipeline) ID"
                variant="outlined"
                density="compact"
                hint="Select from list or type ID"
                persistent-hint
                @blur="saveSetting('leadgen_akm_deal_board_id', settDealBoardId)"
              >
                <template #append>
                  <v-btn icon="mdi-refresh" size="x-small" variant="text" @click="fetchAkmBoards('deals')" :loading="loadingDealBoards" />
                </template>
              </v-text-field>
              <v-list v-if="akmDealBoards.length" density="compact" class="mt-1" style="max-height:160px;overflow-y:auto">
                <v-list-item v-for="b in akmDealBoards" :key="b.id || b._id" @click="settDealBoardId = b.id || b._id; saveSetting('leadgen_akm_deal_board_id', settDealBoardId)">
                  <v-list-item-title class="text-body-2">{{ b.name || b.title }}</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-col>
          </v-row>

          <v-select
            v-model="settPushMode"
            :items="pushModeOptions"
            label="Push Mode"
            variant="outlined"
            density="compact"
            class="mb-3"
            @update:model-value="saveSetting('leadgen_akm_push_mode', $event)"
          />

          <v-divider class="my-4" />
          <div class="text-h6 mb-4">Search Settings</div>

          <v-text-field
            v-model="settPlatforms"
            label="Default Search Platforms (comma-separated)"
            variant="outlined"
            density="compact"
            hint="e.g.: linkedin, google, crunchbase, indeed, glassdoor"
            persistent-hint
            class="mb-3"
            @blur="saveSetting('leadgen_default_search_platforms', settPlatforms)"
          />

          <v-select
            v-model="settSearchLimit"
            :items="['25','50','100','200']"
            label="Max Results per Search"
            variant="outlined"
            density="compact"
            class="mb-3"
            @update:model-value="saveSetting('leadgen_search_limit', $event)"
          />

          <v-divider class="my-4" />

          <div class="d-flex ga-2">
            <v-btn color="red" variant="tonal" prepend-icon="mdi-delete-outline" @click="confirmClear = true">Clear All Data</v-btn>
          </div>
        </v-card>

        <v-card variant="outlined" class="pa-4 mt-4" style="max-width:700px">
          <div class="text-h6 mb-4">Available Skills</div>
          <v-card variant="tonal" class="pa-3 mb-3">
            <div class="d-flex align-center mb-2">
              <v-icon color="cyan" size="20" class="mr-2">mdi-magnify</v-icon>
              <span class="text-subtitle-1 font-weight-bold">leadgen_search</span>
            </div>
            <div class="text-body-2">Search for potential clients, job opportunities, and connections across configured platforms.</div>
          </v-card>
          <v-card variant="tonal" class="pa-3 mb-3">
            <div class="d-flex align-center mb-2">
              <v-icon color="cyan" size="20" class="mr-2">mdi-contacts</v-icon>
              <span class="text-subtitle-1 font-weight-bold">leadgen_contacts</span>
            </div>
            <div class="text-body-2">Retrieve existing contacts from the lead generation database — filter by status, industry, relationship.</div>
          </v-card>
          <v-alert type="info" variant="tonal" density="compact">
            Add <strong>leadgen_search</strong> and <strong>leadgen_contacts</strong> to an agent's skill list to enable AI-driven lead generation.
          </v-alert>
        </v-card>
      </v-window-item>

    </v-window>

    <!-- ═══════ ADD CLIENT DIALOG ═══════ -->
    <v-dialog v-model="showAddClient" max-width="550">
      <v-card class="pa-4">
        <v-card-title>{{ editingClient ? 'Edit Client' : 'Add Client' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="clientForm.name" label="Full Name *" variant="outlined" density="compact" class="mb-2" />
          <v-row dense class="mb-2">
            <v-col><v-text-field v-model="clientForm.company" label="Company" variant="outlined" density="compact" /></v-col>
            <v-col><v-text-field v-model="clientForm.title" label="Title" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-row dense class="mb-2">
            <v-col><v-text-field v-model="clientForm.email" label="Email" variant="outlined" density="compact" type="email" /></v-col>
            <v-col><v-text-field v-model="clientForm.phone" label="Phone" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-text-field v-model="clientForm.linkedin" label="LinkedIn URL" variant="outlined" density="compact" class="mb-2" />
          <v-row dense class="mb-2">
            <v-col><v-text-field v-model="clientForm.industry" label="Industry" variant="outlined" density="compact" /></v-col>
            <v-col><v-text-field v-model="clientForm.location" label="Location" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-select v-model="clientForm.status" :items="clientStatuses" label="Status" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model="clientForm.source" label="Source" variant="outlined" density="compact" class="mb-2" />
          <v-combobox v-model="clientForm.tags" label="Tags" variant="outlined" density="compact" multiple chips closable-chips class="mb-2" />
          <v-textarea v-model="clientForm.notes" label="Notes" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeClientDialog">Cancel</v-btn>
          <v-btn color="cyan" variant="tonal" @click="saveClient" :disabled="!clientForm.name">{{ editingClient ? 'Save' : 'Add' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ ADD JOB DIALOG ═══════ -->
    <v-dialog v-model="showAddJob" max-width="550">
      <v-card class="pa-4">
        <v-card-title>Add Job</v-card-title>
        <v-card-text>
          <v-text-field v-model="jobForm.title" label="Job Title *" variant="outlined" density="compact" class="mb-2" />
          <v-row dense class="mb-2">
            <v-col><v-text-field v-model="jobForm.company" label="Company" variant="outlined" density="compact" /></v-col>
            <v-col><v-text-field v-model="jobForm.location" label="Location" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-text-field v-model="jobForm.url" label="Job URL" variant="outlined" density="compact" class="mb-2" />
          <v-row dense class="mb-2">
            <v-col><v-text-field v-model="jobForm.salary_range" label="Salary Range" variant="outlined" density="compact" /></v-col>
            <v-col><v-select v-model="jobForm.job_type" :items="jobTypes" label="Type" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-select v-model="jobForm.remote" :items="remoteOptions" label="Remote" variant="outlined" density="compact" class="mb-2" />
          <v-select v-model="jobForm.status" :items="jobStatuses" label="Status" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model="jobForm.source" label="Source" variant="outlined" density="compact" class="mb-2" />
          <v-combobox v-model="jobForm.tags" label="Tags" variant="outlined" density="compact" multiple chips closable-chips class="mb-2" />
          <v-textarea v-model="jobForm.description" label="Description" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showAddJob = false">Cancel</v-btn>
          <v-btn color="purple" variant="tonal" @click="saveJob" :disabled="!jobForm.title">Add</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ ADD CONNECTION DIALOG ═══════ -->
    <v-dialog v-model="showAddConn" max-width="550">
      <v-card class="pa-4">
        <v-card-title>{{ editingConn ? 'Edit Connection' : 'Add Connection' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="connForm.name" label="Full Name *" variant="outlined" density="compact" class="mb-2" />
          <v-row dense class="mb-2">
            <v-col><v-text-field v-model="connForm.company" label="Company" variant="outlined" density="compact" /></v-col>
            <v-col><v-text-field v-model="connForm.title" label="Title" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-row dense class="mb-2">
            <v-col><v-text-field v-model="connForm.email" label="Email" variant="outlined" density="compact" /></v-col>
            <v-col><v-text-field v-model="connForm.phone" label="Phone" variant="outlined" density="compact" /></v-col>
          </v-row>
          <v-text-field v-model="connForm.linkedin" label="LinkedIn URL" variant="outlined" density="compact" class="mb-2" />
          <v-row dense class="mb-2">
            <v-col><v-select v-model="connForm.relationship" :items="relationshipTypes" label="Relationship" variant="outlined" density="compact" /></v-col>
            <v-col><v-text-field v-model="connForm.met_through" label="Met Through" variant="outlined" density="compact" /></v-col>
          </v-row>
          <div class="d-flex align-center mb-2">
            <span class="text-body-2 mr-3">Connection Strength:</span>
            <v-rating v-model="connForm.strength" :length="5" size="small" color="amber" active-color="amber" />
          </div>
          <v-combobox v-model="connForm.tags" label="Tags" variant="outlined" density="compact" multiple chips closable-chips class="mb-2" />
          <v-textarea v-model="connForm.notes" label="Notes" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeConnDialog">Cancel</v-btn>
          <v-btn color="teal" variant="tonal" @click="saveConnection" :disabled="!connForm.name">{{ editingConn ? 'Save' : 'Add' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ CONFIRM CLEAR ═══════ -->
    <v-dialog v-model="confirmClear" max-width="420">
      <v-card class="pa-4">
        <v-card-title class="text-red">Clear All Lead Generation Data?</v-card-title>
        <v-card-text>
          This will delete all clients, jobs, connections, CVs, parsed jobs, and sources. Type <strong>DELETE</strong> to confirm.
          <v-text-field v-model="clearConfirmText" label="Type DELETE" variant="outlined" density="compact" class="mt-3" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmClear = false; clearConfirmText = ''">Cancel</v-btn>
          <v-btn color="red" variant="tonal" :disabled="clearConfirmText !== 'DELETE'" @click="clearAll">Delete All</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ ADD/EDIT JOB SOURCE DIALOG ═══════ -->
    <v-dialog v-model="showAddSource" max-width="600">
      <v-card class="pa-4">
        <v-card-title>{{ editingSource ? 'Edit Source' : 'Add Job Source' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="sourceForm.name" label="Source Name *" variant="outlined" density="compact" class="mb-2" placeholder="e.g. Craigslist SF Bay" />
          <v-select v-model="sourceForm.source_type" :items="sourceTypes" label="Source Type" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model="sourceForm.url" label="Base URL" variant="outlined" density="compact" class="mb-2" :placeholder="sourceForm.source_type === 'craigslist' ? 'https://sfbay.craigslist.org' : 'https://...'" hint="Leave empty for default" persistent-hint />
          <v-combobox v-model="sourceForm.keywords" label="Keywords (required)" variant="outlined" density="compact" multiple chips closable-chips class="mb-2" placeholder="e.g. python, developer, remote..." hint="Press Enter to add. Listings matching these keywords will be collected." persistent-hint />
          <v-combobox v-model="sourceForm.exclude_keywords" label="Exclude Keywords" variant="outlined" density="compact" multiple chips closable-chips class="mb-2" placeholder="e.g. senior, manager..." hint="Listings matching these will be excluded" persistent-hint />
          <v-row dense class="mb-2">
            <v-col cols="4">
              <v-text-field v-model.number="sourceForm.min_keyword_matches" label="Min Keyword Matches" variant="outlined" density="compact" type="number" :min="1" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model.number="sourceForm.max_results" label="Max Results" variant="outlined" density="compact" type="number" :min="10" hide-details />
            </v-col>
            <v-col cols="4">
              <v-select v-model="sourceForm.scrape_interval_hours" :items="[6, 12, 24, 48]" label="Interval (h)" variant="outlined" density="compact" hide-details />
            </v-col>
          </v-row>
          <v-textarea v-model="sourceForm.notes" label="Notes" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeSourceDialog">Cancel</v-btn>
          <v-btn color="purple" variant="tonal" @click="saveSource" :disabled="!sourceForm.name || !sourceForm.keywords.length">{{ editingSource ? 'Save' : 'Add' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ CV UPLOAD DIALOG (title/desc before upload) ═══════ -->
    <v-dialog v-model="showCvDialog" max-width="420">
      <v-card class="pa-4">
        <v-card-title>Upload CV</v-card-title>
        <v-card-text>
          <v-text-field v-model="cvUploadTitle" label="Resume Title" variant="outlined" density="compact" class="mb-2" placeholder="e.g. Full Stack Developer Resume 2026" />
          <v-textarea v-model="cvUploadDesc" label="Description" variant="outlined" density="compact" rows="2" placeholder="What does this resume highlight?" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showCvDialog = false">Cancel</v-btn>
          <v-btn color="purple" variant="tonal" @click="doCvUpload" :loading="uploadingCv">Upload</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack" :color="snackColor" :timeout="3000" location="bottom right">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useSettingsStore } from '@src/stores/settings'
import api from '@src/api'

const API = '/addons/lead-generation'
const settingsStore = useSettingsStore()

// ── State ──
const loading = ref(false)
const stats = ref(null)
const activeTab = ref(localStorage.getItem('leadgen_tab') || 'clients')

// Clients
const clients = ref([])
const clientsTotal = ref(0)
const loadingClients = ref(false)
const clientSearch = ref('')
const clientStatusFilter = ref(null)
const clientIndustryFilter = ref('')
const selectedClients = ref([])
const selectAllClients = ref(false)
const showAddClient = ref(false)
const editingClient = ref(null)
const clientForm = ref(emptyClientForm())

// Jobs
const jobs = ref([])
const loadingJobs = ref(false)
const jobSearch = ref('')
const jobStatusFilter = ref(null)
const jobTypeFilter = ref(null)
const jobRemoteFilter = ref(null)
const showAddJob = ref(false)
const jobForm = ref(emptyJobForm())
const jobSubTab = ref(localStorage.getItem('leadgen_job_subtab') || 'cv')

// CVs
const cvs = ref([])
const loadingCvs = ref(false)
const cvFileInput = ref(null)
const cvPendingFile = ref(null)
const showCvDialog = ref(false)
const cvUploadTitle = ref('')
const cvUploadDesc = ref('')
const uploadingCv = ref(false)
const editingCvId = ref(null)
const editCvTitle = ref('')
const editCvDesc = ref('')

// Job Criterias
const criterias = ref({ industries: [], companies_dream: '', companies_good: '', companies_backup: '', salary_annual_min: '', salary_monthly_min: '', tax_state: '', keywords: [], states: [], notes: '' })
const savingCriterias = ref(false)

// Parsed Jobs
const parsedJobs = ref([])
const parsedTotal = ref(0)
const loadingParsed = ref(false)
const parsedSearch = ref('')
const parsedSourceFilter = ref(null)
const parsedExcludeSourceFilter = ref([])
const parsedStatusFilter = ref(null)

// Job Sources
const jobSources = ref([])
const loadingSources = ref(false)
const showAddSource = ref(false)
const editingSource = ref(null)
const sourceForm = ref(emptySourceForm())
const scrapingId = ref(null)

// Connections
const connections = ref([])
const loadingConns = ref(false)
const connSearch = ref('')
const connRelFilter = ref(null)
const showAddConn = ref(false)
const editingConn = ref(null)
const connForm = ref(emptyConnForm())

// Map
const mapData = ref(null)
const loadingMap = ref(false)
const hoveredNode = ref(null)
const renderedNodes = ref([])
const renderedLinks = ref([])
const mapHeight = 500
const mapContainer = ref(null)
const mapSvg = ref(null)

// Settings
const settAkmKey = ref('')
const settAkmBaseUrl = ref('https://app.akm-advisor.com/api/v1')
const settLeadBoardId = ref('')
const settDealBoardId = ref('')
const settPushMode = ref('manual')
const settPlatforms = ref('linkedin,google,crunchbase')
const settSearchLimit = ref('50')
const showAkmKey = ref(false)
const akmLeadBoards = ref([])
const akmDealBoards = ref([])
const loadingLeadBoards = ref(false)
const loadingDealBoards = ref(false)

// Misc
const snack = ref(false)
const snackText = ref('')
const snackColor = ref('success')
const confirmClear = ref(false)
const clearConfirmText = ref('')

// ── Constants ──
const clientStatuses = ['new', 'contacted', 'qualified', 'converted', 'lost']
const jobStatuses = ['new', 'saved', 'applied', 'interview', 'offer', 'rejected']
const jobTypes = ['full-time', 'part-time', 'contract', 'freelance']
const remoteOptions = [
  { title: 'Any', value: 'any' },
  { title: 'Remote', value: 'remote' },
  { title: 'Hybrid', value: 'hybrid' },
  { title: 'Onsite', value: 'onsite' },
]
const relationshipTypes = ['colleague', 'friend', 'mentor', 'client', 'vendor', 'partner', 'recruiter', 'other']
const sourceTypes = ['craigslist', 'indeed', 'linkedin', 'other']
const parsedStatuses = ['new', 'reviewed', 'saved', 'rejected']
const taxStates = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware',
  'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky',
  'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
  'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico',
  'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania',
  'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont',
  'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming',
]
// Approximate state income tax rates (top marginal) for take-home estimation
const stateTaxRates = {
  'Alabama': 5, 'Alaska': 0, 'Arizona': 2.5, 'Arkansas': 4.4, 'California': 13.3, 'Colorado': 4.4,
  'Connecticut': 6.99, 'Delaware': 6.6, 'Florida': 0, 'Georgia': 5.49, 'Hawaii': 11, 'Idaho': 5.8,
  'Illinois': 4.95, 'Indiana': 3.05, 'Iowa': 5.7, 'Kansas': 5.7, 'Kentucky': 4.5, 'Louisiana': 4.25,
  'Maine': 7.15, 'Maryland': 5.75, 'Massachusetts': 9, 'Michigan': 4.25, 'Minnesota': 9.85,
  'Mississippi': 5, 'Missouri': 4.8, 'Montana': 6.75, 'Nebraska': 5.84, 'Nevada': 0,
  'New Hampshire': 0, 'New Jersey': 10.75, 'New Mexico': 5.9, 'New York': 10.9,
  'North Carolina': 4.5, 'North Dakota': 2.5, 'Ohio': 3.5, 'Oklahoma': 4.75, 'Oregon': 9.9,
  'Pennsylvania': 3.07, 'Rhode Island': 5.99, 'South Carolina': 6.4, 'South Dakota': 0,
  'Tennessee': 0, 'Texas': 0, 'Utah': 4.65, 'Vermont': 8.75, 'Virginia': 5.75,
  'Washington': 0, 'West Virginia': 5.12, 'Wisconsin': 7.65, 'Wyoming': 0,
}
const pushModeOptions = [
  { title: 'Manual only', value: 'manual' },
  { title: 'Auto-push as Leads', value: 'auto_leads' },
  { title: 'Auto-push as Deals', value: 'auto_deals' },
  { title: 'Auto-push Both', value: 'auto_both' },
]

// ── Computed ──
const sourceNames = computed(() => jobSources.value.map(s => s.name))

const takeHomeEstimate = computed(() => {
  const annual = parseFloat(criterias.value.salary_annual_min) || 0
  if (!annual) return null
  const st = criterias.value.tax_state
  const stateRate = st && stateTaxRates[st] !== undefined ? stateTaxRates[st] : 0
  // Federal effective rate approximation (progressive brackets simplified)
  function fedRate(a) {
    if (a <= 0) return 0
    if (a <= 11600) return 10
    if (a <= 47150) return 12
    if (a <= 100525) return 18
    if (a <= 191950) return 22
    if (a <= 243725) return 26
    if (a <= 609350) return 30
    return 35
  }
  // FICA: 7.65% up to ~168k SS + 1.45% Medicare above
  function ficaRate(a) {
    if (a <= 0) return 0
    if (a <= 168600) return 7.65
    return 6.2 * (168600 / a) + 1.45
  }
  const totalRate = fedRate(annual) + stateRate + ficaRate(annual)
  const takeHome = annual * (1 - totalRate / 100) / 12
  return {
    monthly: Math.round(takeHome).toLocaleString(),
    eff_rate: Math.round(totalRate),
  }
})

// ── Form helpers ──
function emptyClientForm() {
  return { name: '', company: '', title: '', email: '', phone: '', linkedin: '', website: '', industry: '', location: '', source: '', notes: '', tags: [], status: 'new' }
}
function emptyJobForm() {
  return { title: '', company: '', location: '', url: '', salary_range: '', job_type: '', remote: 'any', description: '', requirements: '', source: '', status: 'new', tags: [] }
}
function emptyConnForm() {
  return { name: '', company: '', title: '', email: '', phone: '', linkedin: '', relationship: '', met_through: '', notes: '', tags: [], strength: 3 }
}
function emptySourceForm() {
  return { name: '', source_type: 'craigslist', url: '', keywords: [], exclude_keywords: [], min_keyword_matches: 1, max_results: 100, scrape_interval_hours: 24, notes: '' }
}

// ── Salary sync helpers ──
function syncFromAnnual() {
  const annual = parseFloat(criterias.value.salary_annual_min) || 0
  criterias.value.salary_monthly_min = annual > 0 ? String(Math.round(annual / 12)) : ''
}
function syncFromMonthly() {
  const monthly = parseFloat(criterias.value.salary_monthly_min) || 0
  criterias.value.salary_annual_min = monthly > 0 ? String(Math.round(monthly * 12)) : ''
}

// ── Color helpers ──
function clientStatusColor(s) {
  const map = { new: 'blue', contacted: 'orange', qualified: 'amber', converted: 'green', lost: 'red' }
  return map[s] || 'grey'
}
function jobStatusColor(s) {
  const map = { new: 'blue', saved: 'cyan', applied: 'orange', interview: 'amber', offer: 'green', rejected: 'red' }
  return map[s] || 'grey'
}
function strengthColor(s) {
  if (s >= 5) return 'green'
  if (s >= 4) return 'teal'
  if (s >= 3) return 'blue'
  if (s >= 2) return 'orange'
  return 'grey'
}
function parsedStatusColor(s) {
  const map = { new: 'blue', reviewed: 'orange', saved: 'green', rejected: 'red' }
  return map[s] || 'grey'
}
function sourceTypeIcon(t) {
  const map = { craigslist: 'mdi-newspaper-variant-outline', indeed: 'mdi-briefcase-search', linkedin: 'mdi-linkedin', other: 'mdi-web' }
  return map[t] || 'mdi-web'
}
function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
function cvFileExt(filename) {
  if (!filename) return '?'
  return filename.split('.').pop().toUpperCase()
}

// ── Notify ──
function notify(text, color = 'success') {
  snackText.value = text
  snackColor.value = color
  snack.value = true
}

// ── Tab watcher ──
watch(activeTab, (val) => {
  localStorage.setItem('leadgen_tab', val)
  loadTabData(val)
})

watch(jobSubTab, (val) => {
  localStorage.setItem('leadgen_job_subtab', val)
  loadJobSubTabData(val)
})

// ── Load helpers ──
function loadTabData(tab) {
  switch (tab) {
    case 'clients': loadClients(); break
    case 'jobs': loadJobs(); loadJobSubTabData(jobSubTab.value); break
    case 'connections': loadConnections(); break
    case 'map': loadMap(); break
  }
}

function loadJobSubTabData(sub) {
  switch (sub) {
    case 'cv': loadCvs(); break
    case 'criterias': loadCriterias(); break
    case 'parsed': loadParsedJobs(); break
    case 'sources': loadJobSources(); break
  }
}

async function refreshAll() {
  loading.value = true
  await Promise.all([loadStats(), loadTabData(activeTab.value)])
  loading.value = false
}

async function loadStats() {
  try { const { data } = await api.get(`${API}/stats`); stats.value = data } catch {}
}

// ── Clients ──
async function loadClients() {
  loadingClients.value = true
  try {
    const params = { limit: 200, offset: 0 }
    if (clientSearch.value) params.search = clientSearch.value
    if (clientStatusFilter.value) params.status = clientStatusFilter.value
    if (clientIndustryFilter.value) params.industry = clientIndustryFilter.value
    const { data } = await api.get(`${API}/clients`, { params })
    clients.value = data.items || []
    clientsTotal.value = data.total || 0
  } catch (e) { notify('Failed to load clients', 'error') }
  loadingClients.value = false
}

async function loadMoreClients() {
  const params = { limit: 200, offset: clients.value.length }
  if (clientSearch.value) params.search = clientSearch.value
  if (clientStatusFilter.value) params.status = clientStatusFilter.value
  const { data } = await api.get(`${API}/clients`, { params })
  clients.value.push(...(data.items || []))
}

function toggleAllClients(val) {
  selectedClients.value = val ? clients.value.map(c => c._id) : []
}

function editClient(c) {
  editingClient.value = c._id
  clientForm.value = { ...c }
  showAddClient.value = true
}

function closeClientDialog() {
  showAddClient.value = false
  editingClient.value = null
  clientForm.value = emptyClientForm()
}

async function saveClient() {
  try {
    if (editingClient.value) {
      const { _id, created_at, updated_at, ...body } = clientForm.value
      await api.patch(`${API}/clients/${editingClient.value}`, body)
      notify('Client updated')
    } else {
      await api.post(`${API}/clients`, clientForm.value)
      notify('Client added')
    }
    closeClientDialog()
    loadClients()
    loadStats()
  } catch (e) { notify('Failed to save client', 'error') }
}

async function deleteClient(id) {
  try {
    await api.delete(`${API}/clients/${id}`)
    clients.value = clients.value.filter(c => c._id !== id)
    selectedClients.value = selectedClients.value.filter(i => i !== id)
    loadStats()
  } catch { notify('Failed to delete', 'error') }
}

// ── Jobs ──
async function loadJobs() {
  loadingJobs.value = true
  try {
    const params = { limit: 200 }
    if (jobSearch.value) params.search = jobSearch.value
    if (jobStatusFilter.value) params.status = jobStatusFilter.value
    if (jobTypeFilter.value) params.job_type = jobTypeFilter.value
    if (jobRemoteFilter.value) params.remote = jobRemoteFilter.value
    const { data } = await api.get(`${API}/jobs`, { params })
    jobs.value = data.items || []
  } catch { notify('Failed to load jobs', 'error') }
  loadingJobs.value = false
}

async function saveJob() {
  try {
    await api.post(`${API}/jobs`, jobForm.value)
    notify('Job added')
    showAddJob.value = false
    jobForm.value = emptyJobForm()
    loadJobs()
    loadStats()
  } catch { notify('Failed to add job', 'error') }
}

async function updateJobStatus(id, status) {
  try {
    await api.patch(`${API}/jobs/${id}`, { status })
    const j = jobs.value.find(x => x._id === id)
    if (j) j.status = status
    loadStats()
  } catch { notify('Failed to update', 'error') }
}

async function deleteJob(id) {
  try {
    await api.delete(`${API}/jobs/${id}`)
    jobs.value = jobs.value.filter(j => j._id !== id)
    loadStats()
  } catch { notify('Failed to delete', 'error') }
}

// ── CVs ──
async function loadCvs() {
  loadingCvs.value = true
  try {
    const { data } = await api.get(`${API}/cvs`)
    cvs.value = data.items || data || []
  } catch { notify('Failed to load CVs', 'error') }
  loadingCvs.value = false
}

function triggerCvUpload() {
  cvFileInput.value?.click()
}

function handleCvUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  cvPendingFile.value = file
  cvUploadTitle.value = file.name.replace(/\.[^.]+$/, '')
  cvUploadDesc.value = ''
  showCvDialog.value = true
}

async function doCvUpload() {
  if (!cvPendingFile.value) return
  uploadingCv.value = true
  try {
    const fd = new FormData()
    fd.append('file', cvPendingFile.value)
    fd.append('title', cvUploadTitle.value || cvPendingFile.value.name)
    fd.append('description', cvUploadDesc.value)
    await api.post(`${API}/cvs/upload`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    notify('CV uploaded')
    showCvDialog.value = false
    cvPendingFile.value = null
    if (cvFileInput.value) cvFileInput.value.value = ''
    loadCvs()
    loadStats()
  } catch { notify('Failed to upload CV', 'error') }
  uploadingCv.value = false
}

async function downloadCv(id) {
  try {
    const cv = cvs.value.find(c => c._id === id)
    const { data } = await api.get(`${API}/cvs/${id}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = cv?.original_name || 'cv'
    a.click()
    URL.revokeObjectURL(url)
  } catch { notify('Failed to download', 'error') }
}

async function deleteCv(id) {
  try {
    await api.delete(`${API}/cvs/${id}`)
    cvs.value = cvs.value.filter(c => c._id !== id)
    loadStats()
  } catch { notify('Failed to delete', 'error') }
}

function startEditCv(cv) {
  editingCvId.value = cv._id
  editCvTitle.value = cv.title || ''
  editCvDesc.value = cv.description || ''
}

async function saveCvEdit(id) {
  try {
    await api.patch(`${API}/cvs/${id}`, { title: editCvTitle.value, description: editCvDesc.value })
    const cv = cvs.value.find(c => c._id === id)
    if (cv) { cv.title = editCvTitle.value; cv.description = editCvDesc.value }
    editingCvId.value = null
    notify('CV updated')
  } catch { notify('Failed to update', 'error') }
}

// ── Job Criterias ──
async function loadCriterias() {
  try {
    const { data } = await api.get(`${API}/job-criterias`)
    if (data) {
      criterias.value = {
        industries: data.industries || [],
        companies_dream: data.companies_dream || '',
        companies_good: data.companies_good || '',
        companies_backup: data.companies_backup || '',
        salary_annual_min: data.salary_annual_min || '',
        salary_monthly_min: data.salary_monthly_min || '',
        tax_state: data.tax_state || '',
        keywords: data.keywords || [],
        states: data.states || [],
        notes: data.notes || '',
      }
    }
  } catch {}
}

async function saveCriterias() {
  savingCriterias.value = true
  try {
    await api.put(`${API}/job-criterias`, criterias.value)
    notify('Job criterias saved')
  } catch { notify('Failed to save criterias', 'error') }
  savingCriterias.value = false
}

// ── Parsed Jobs ──
async function loadParsedJobs() {
  loadingParsed.value = true
  try {
    const params = { limit: 100, offset: 0 }
    if (parsedSearch.value) params.search = parsedSearch.value
    if (parsedSourceFilter.value) params.source = parsedSourceFilter.value
    if (parsedExcludeSourceFilter.value && parsedExcludeSourceFilter.value.length) params.exclude_source = parsedExcludeSourceFilter.value.join(',')
    if (parsedStatusFilter.value) params.status = parsedStatusFilter.value
    const { data } = await api.get(`${API}/parsed-jobs`, { params })
    parsedJobs.value = data.items || []
    parsedTotal.value = data.total || 0
  } catch { notify('Failed to load parsed jobs', 'error') }
  loadingParsed.value = false
}

async function loadMoreParsed() {
  try {
    const params = { limit: 100, offset: parsedJobs.value.length }
    if (parsedSearch.value) params.search = parsedSearch.value
    if (parsedSourceFilter.value) params.source = parsedSourceFilter.value
    if (parsedExcludeSourceFilter.value && parsedExcludeSourceFilter.value.length) params.exclude_source = parsedExcludeSourceFilter.value.join(',')
    if (parsedStatusFilter.value) params.status = parsedStatusFilter.value
    const { data } = await api.get(`${API}/parsed-jobs`, { params })
    parsedJobs.value.push(...(data.items || []))
  } catch { notify('Failed to load more', 'error') }
}

async function deleteParsedJob(id) {
  try {
    await api.delete(`${API}/parsed-jobs/${id}`)
    parsedJobs.value = parsedJobs.value.filter(j => j._id !== id)
    parsedTotal.value = Math.max(0, parsedTotal.value - 1)
    loadStats()
  } catch { notify('Failed to delete', 'error') }
}

async function saveAsJob(id) {
  try {
    await api.post(`${API}/parsed-jobs/${id}/save-as-job`)
    const pj = parsedJobs.value.find(j => j._id === id)
    if (pj) pj.status = 'saved'
    notify('Saved as job listing')
    loadStats()
  } catch { notify('Failed to save as job', 'error') }
}

// ── Job Sources ──
async function loadJobSources() {
  loadingSources.value = true
  try {
    const { data } = await api.get(`${API}/job-sources`)
    jobSources.value = data.items || data || []
  } catch { notify('Failed to load sources', 'error') }
  loadingSources.value = false
}

function editSource(src) {
  editingSource.value = src._id
  sourceForm.value = { ...src }
  showAddSource.value = true
}

function closeSourceDialog() {
  showAddSource.value = false
  editingSource.value = null
  sourceForm.value = emptySourceForm()
}

async function saveSource() {
  try {
    if (editingSource.value) {
      const { _id, created_at, updated_at, last_scraped, ...body } = sourceForm.value
      await api.patch(`${API}/job-sources/${editingSource.value}`, body)
      notify('Source updated')
    } else {
      await api.post(`${API}/job-sources`, sourceForm.value)
      notify('Source added')
    }
    closeSourceDialog()
    loadJobSources()
  } catch { notify('Failed to save source', 'error') }
}

async function deleteSource(id) {
  try {
    await api.delete(`${API}/job-sources/${id}`)
    jobSources.value = jobSources.value.filter(s => s._id !== id)
  } catch { notify('Failed to delete', 'error') }
}

async function toggleSource(src) {
  try {
    await api.patch(`${API}/job-sources/${src._id}`, { enabled: src.enabled })
  } catch {
    src.enabled = !src.enabled
    notify('Failed to toggle', 'error')
  }
}

async function scrapeSource(id) {
  scrapingId.value = id
  try {
    const { data } = await api.post(`${API}/job-sources/${id}/scrape`)
    notify(`Scraped: ${data.new_jobs || 0} new, ${data.duplicates || 0} duplicates`)
    const src = jobSources.value.find(s => s._id === id)
    if (src) src.last_scraped = new Date().toISOString()
    loadParsedJobs()
    loadStats()
  } catch (e) {
    notify(e.response?.data?.detail || 'Scrape failed', 'error')
  }
  scrapingId.value = null
}

// ── Connections ──
async function loadConnections() {
  loadingConns.value = true
  try {
    const params = { limit: 500 }
    if (connSearch.value) params.search = connSearch.value
    if (connRelFilter.value) params.relationship = connRelFilter.value
    const { data } = await api.get(`${API}/connections`, { params })
    connections.value = data.items || []
  } catch { notify('Failed to load connections', 'error') }
  loadingConns.value = false
}

function editConnection(c) {
  editingConn.value = c._id
  connForm.value = { ...c }
  showAddConn.value = true
}

function closeConnDialog() {
  showAddConn.value = false
  editingConn.value = null
  connForm.value = emptyConnForm()
}

async function saveConnection() {
  try {
    if (editingConn.value) {
      const { _id, created_at, updated_at, ...body } = connForm.value
      await api.patch(`${API}/connections/${editingConn.value}`, body)
      notify('Connection updated')
    } else {
      await api.post(`${API}/connections`, connForm.value)
      notify('Connection added')
    }
    closeConnDialog()
    loadConnections()
    loadStats()
  } catch { notify('Failed to save connection', 'error') }
}

async function deleteConnection(id) {
  try {
    await api.delete(`${API}/connections/${id}`)
    connections.value = connections.value.filter(c => c._id !== id)
    loadStats()
  } catch { notify('Failed to delete', 'error') }
}

// ── Connections Map ──
async function loadMap() {
  loadingMap.value = true
  try {
    const { data } = await api.get(`${API}/connections-map`)
    mapData.value = data
    await nextTick()
    layoutMap()
  } catch { notify('Failed to load map', 'error') }
  loadingMap.value = false
}

function layoutMap() {
  if (!mapData.value || !mapData.value.nodes || mapData.value.nodes.length < 2) return

  const svgEl = mapSvg.value
  if (!svgEl) return
  const W = svgEl.clientWidth || 800
  const H = mapHeight
  const cx = W / 2
  const cy = H / 2

  const nodes = mapData.value.nodes
  const links = mapData.value.links
  const nodeMap = {}

  // Position center
  nodes.forEach((n, i) => {
    if (n.type === 'center') {
      n.x = cx; n.y = cy
    } else if (n.type === 'company') {
      const angle = (i / nodes.length) * Math.PI * 2
      const radius = Math.min(W, H) * 0.32
      n.x = cx + Math.cos(angle) * radius
      n.y = cy + Math.sin(angle) * radius
    } else {
      const angle = (i / nodes.length) * Math.PI * 2 + 0.3
      const radius = Math.min(W, H) * 0.42
      n.x = cx + Math.cos(angle) * radius
      n.y = cy + Math.sin(angle) * radius
    }
    nodeMap[n.id] = n
  })

  // Render
  renderedNodes.value = nodes
  renderedLinks.value = links.map(l => ({
    x1: nodeMap[l.source]?.x || 0,
    y1: nodeMap[l.source]?.y || 0,
    x2: nodeMap[l.target]?.x || 0,
    y2: nodeMap[l.target]?.y || 0,
    type: l.type,
  }))
}

// ── AKM Push ──
async function pushToAkm(target) {
  if (!selectedClients.value.length) return
  try {
    const { data } = await api.post(`${API}/push-to-akm`, {
      item_ids: selectedClients.value,
      target,
    })
    notify(`Pushed ${data.pushed} to AKM-Advisor as ${target}`)
    if (data.errors && data.errors.length) {
      notify(`${data.errors.length} failed`, 'warning')
    }
    selectedClients.value = []
    loadClients()
    loadStats()
  } catch (e) {
    const msg = e.response?.data?.detail || 'Push failed'
    notify(msg, 'error')
  }
}

// ── AKM Boards ──
async function fetchAkmBoards(target) {
  if (target === 'leads') {
    loadingLeadBoards.value = true
    try {
      const { data } = await api.get(`${API}/akm-boards`, { params: { target: 'leads' } })
      akmLeadBoards.value = data.items || data || []
    } catch (e) {
      notify(e.response?.data?.detail || 'Failed to fetch boards', 'error')
    }
    loadingLeadBoards.value = false
  } else {
    loadingDealBoards.value = true
    try {
      const { data } = await api.get(`${API}/akm-boards`, { params: { target: 'deals' } })
      akmDealBoards.value = data.items || data || []
    } catch (e) {
      notify(e.response?.data?.detail || 'Failed to fetch boards', 'error')
    }
    loadingDealBoards.value = false
  }
}

// ── Settings ──
function loadSettings() {
  const s = settingsStore.systemSettings || {}
  settAkmKey.value = s.leadgen_akm_api_key || ''
  settAkmBaseUrl.value = s.leadgen_akm_base_url || 'https://app.akm-advisor.com/api/v1'
  settLeadBoardId.value = s.leadgen_akm_lead_board_id || ''
  settDealBoardId.value = s.leadgen_akm_deal_board_id || ''
  settPushMode.value = s.leadgen_akm_push_mode || 'manual'
  settPlatforms.value = s.leadgen_default_search_platforms || 'linkedin,google,crunchbase'
  settSearchLimit.value = s.leadgen_search_limit || '50'
}

async function saveSetting(key, value) {
  try { await settingsStore.updateSystemSetting(key, value) }
  catch { notify('Failed to save setting', 'error') }
}

// ── Clear all ──
async function clearAll() {
  try {
    await api.post(`${API}/clear-all`)
    notify('All data cleared')
    confirmClear.value = false
    clearConfirmText.value = ''
    clients.value = []
    jobs.value = []
    connections.value = []
    cvs.value = []
    parsedJobs.value = []
    parsedTotal.value = 0
    jobSources.value = []
    criterias.value = { industries: [], companies_dream: '', companies_good: '', companies_backup: '', salary_annual_min: '', salary_monthly_min: '', tax_state: '', keywords: [], states: [], notes: '' }
    mapData.value = null
    renderedNodes.value = []
    renderedLinks.value = []
    loadStats()
  } catch { notify('Failed to clear', 'error') }
}

// ── Mount ──
onMounted(() => {
  loadSettings()
  loadStats()
  loadTabData(activeTab.value)
})
</script>

<style scoped>
.map-container {
  position: relative;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.3);
}
.connections-svg {
  display: block;
}
.map-node:hover circle {
  filter: brightness(1.3);
}
.map-tooltip {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
  min-width: 160px;
}
.text-truncate-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
