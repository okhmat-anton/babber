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

      <!-- ═══════ JOB SEARCH ═══════ -->
      <v-window-item value="jobs">
        <v-row dense class="mb-3">
          <v-col cols="12" sm="4">
            <v-text-field v-model="jobSearch" label="Search jobs..." variant="outlined" density="compact" prepend-inner-icon="mdi-magnify" clearable hide-details @keyup.enter="loadJobs" />
          </v-col>
          <v-col cols="6" sm="2">
            <v-select v-model="jobStatusFilter" :items="jobStatuses" label="Status" variant="outlined" density="compact" clearable hide-details />
          </v-col>
          <v-col cols="6" sm="2">
            <v-select v-model="jobTypeFilter" :items="jobTypes" label="Type" variant="outlined" density="compact" clearable hide-details />
          </v-col>
          <v-col cols="6" sm="2">
            <v-select v-model="jobRemoteFilter" :items="remoteOptions" label="Remote" variant="outlined" density="compact" clearable hide-details />
          </v-col>
          <v-col cols="auto">
            <v-btn color="cyan" variant="tonal" @click="loadJobs" class="mt-1">Search</v-btn>
          </v-col>
          <v-spacer />
          <v-col cols="auto">
            <v-btn color="purple" variant="tonal" size="small" prepend-icon="mdi-plus" @click="showAddJob = true">Add Job</v-btn>
          </v-col>
        </v-row>

        <v-progress-linear v-if="loadingJobs" indeterminate color="purple" class="mb-2" />

        <v-row v-if="jobs.length > 0">
          <v-col v-for="j in jobs" :key="j._id" cols="12" sm="6" md="4" lg="3">
            <v-card variant="outlined" class="pa-3 h-100">
              <div class="d-flex align-center mb-2">
                <v-icon :color="jobStatusColor(j.status)" size="20" class="mr-2">mdi-briefcase</v-icon>
                <span class="text-subtitle-2 font-weight-bold text-truncate" style="max-width:200px">{{ j.title }}</span>
                <v-spacer />
                <v-btn v-if="j.url" :href="j.url" target="_blank" icon="mdi-open-in-new" size="x-small" variant="text" />
              </div>
              <div class="text-body-2 font-weight-medium mb-1">{{ j.company }}</div>
              <div class="text-caption text-grey mb-1" v-if="j.location">{{ j.location }}</div>
              <div class="d-flex flex-wrap ga-1 mb-2">
                <v-chip :color="jobStatusColor(j.status)" size="x-small" variant="tonal">{{ j.status }}</v-chip>
                <v-chip v-if="j.job_type" size="x-small" variant="outlined">{{ j.job_type }}</v-chip>
                <v-chip v-if="j.remote && j.remote !== 'any'" size="x-small" variant="tonal" color="teal">{{ j.remote }}</v-chip>
                <v-chip v-if="j.salary_range" size="x-small" variant="tonal" color="green">{{ j.salary_range }}</v-chip>
              </div>
              <div v-if="j.tags && j.tags.length" class="d-flex flex-wrap ga-1 mb-2">
                <v-chip v-for="t in j.tags" :key="t" size="x-small" variant="tonal" color="cyan">{{ t }}</v-chip>
              </div>
              <div class="d-flex mt-auto">
                <v-btn-group variant="text" density="compact">
                  <v-btn v-for="s in ['applied','interview','offer']" :key="s" size="x-small" @click="updateJobStatus(j._id, s)"
                    :color="j.status === s ? jobStatusColor(s) : 'grey'" :variant="j.status === s ? 'tonal' : 'text'">
                    {{ s }}
                  </v-btn>
                </v-btn-group>
                <v-spacer />
                <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="deleteJob(j._id)" />
              </div>
            </v-card>
          </v-col>
        </v-row>

        <v-card v-else-if="!loadingJobs" variant="tonal" class="pa-8 text-center">
          <v-icon size="48" color="grey">mdi-briefcase-search-outline</v-icon>
          <div class="text-h6 mt-2 text-grey">No jobs yet</div>
          <v-btn color="purple" variant="tonal" class="mt-3" @click="showAddJob = true" prepend-icon="mdi-plus">Add Job</v-btn>
        </v-card>
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
          This will delete all clients, jobs, and connections. Type <strong>DELETE</strong> to confirm.
          <v-text-field v-model="clearConfirmText" label="Type DELETE" variant="outlined" density="compact" class="mt-3" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmClear = false; clearConfirmText = ''">Cancel</v-btn>
          <v-btn color="red" variant="tonal" :disabled="clearConfirmText !== 'DELETE'" @click="clearAll">Delete All</v-btn>
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
import { ref, onMounted, watch, nextTick } from 'vue'
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
const pushModeOptions = [
  { title: 'Manual only', value: 'manual' },
  { title: 'Auto-push as Leads', value: 'auto_leads' },
  { title: 'Auto-push as Deals', value: 'auto_deals' },
  { title: 'Auto-push Both', value: 'auto_both' },
]

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

// ── Load helpers ──
function loadTabData(tab) {
  switch (tab) {
    case 'clients': loadClients(); break
    case 'jobs': loadJobs(); break
    case 'connections': loadConnections(); break
    case 'map': loadMap(); break
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
