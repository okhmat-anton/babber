<template>
  <div>
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <v-icon size="32" color="deep-purple-accent-2" class="mr-3">mdi-chart-timeline-variant</v-icon>
      <div class="text-h4 font-weight-bold">Polymarket</div>
      <v-spacer />
      <v-chip v-if="stats" variant="tonal" color="green" class="mr-2">
        <v-icon start size="14">mdi-trophy</v-icon>
        {{ stats.won }} W
      </v-chip>
      <v-chip v-if="stats" variant="tonal" color="red" class="mr-2">
        <v-icon start size="14">mdi-close-circle</v-icon>
        {{ stats.lost }} L
      </v-chip>
      <v-chip v-if="stats" variant="tonal" :color="stats.total_profit >= 0 ? 'green' : 'red'" class="mr-4">
        {{ stats.total_profit >= 0 ? '+' : '' }}{{ stats.total_profit }} USDC
      </v-chip>
      <v-btn color="deep-purple-accent-2" variant="tonal" prepend-icon="mdi-refresh" class="mr-2" @click="refreshAll" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <!-- No agent with Gambling Addict protocol -->
    <v-alert v-if="!hasProtocolAgent && !loading" type="error" variant="tonal" class="mb-4">
      <div class="d-flex align-center">
        <div class="flex-grow-1">
          <strong>No agent with the Gambling Addict protocol.</strong>
          Create an agent and assign the <strong>Gambling Addict</strong> protocol so it can autonomously analyze markets and place bets.
        </div>
        <v-btn color="error" variant="flat" size="small" prepend-icon="mdi-plus" class="ml-4" :to="{ path: '/agents/new', query: { protocol: 'Gambling Addict' } }">
          Create Agent
        </v-btn>
      </div>
    </v-alert>

    <!-- Not configured -->
    <v-alert v-if="!configured && !loading" type="info" variant="tonal" class="mb-6">
      <div class="d-flex align-center">
        <div>
          <strong>Polymarket API not configured.</strong>
          You can browse events without an API key. To place bets, configure your credentials in the
          <a href="#" @click.prevent="activeTab = 'settings'" class="text-decoration-underline">Settings</a> tab.
        </div>
      </div>
    </v-alert>

    <!-- Error -->
    <v-alert v-if="errorMsg" type="error" closable class="mb-4" @click:close="errorMsg = null">
      {{ errorMsg }}
    </v-alert>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="deep-purple-accent-2" class="mb-4">
      <v-tab value="events">
        <v-icon start>mdi-earth</v-icon>
        Events
      </v-tab>
      <v-tab value="positions" :disabled="!configured">
        <v-icon start>mdi-wallet</v-icon>
        Positions
      </v-tab>
      <v-tab value="history">
        <v-icon start>mdi-history</v-icon>
        History
      </v-tab>
      <v-tab value="ai_betting">
        <v-icon start>mdi-robot</v-icon>
        AI Betting
      </v-tab>
      <v-tab value="skills">
        <v-icon start>mdi-puzzle</v-icon>
        Skills
      </v-tab>
      <v-tab value="protocols">
        <v-icon start>mdi-head-cog</v-icon>
        Protocols
      </v-tab>
      <v-tab value="settings">
        <v-icon start>mdi-cog</v-icon>
        Settings
      </v-tab>
    </v-tabs>

    <!-- Events Tab -->
    <div v-if="activeTab === 'events'">
      <div class="d-flex align-center ga-3 mb-4">
        <v-text-field
          v-model="searchQuery"
          placeholder="Search events..."
          variant="outlined"
          density="compact"
          hide-details
          clearable
          prepend-inner-icon="mdi-magnify"
          style="max-width: 400px;"
          @keyup.enter="loadEvents"
          @click:clear="searchQuery = ''; loadEvents()"
        />
        <v-switch
          v-model="showClosed"
          label="Show Closed"
          hide-details
          color="deep-purple-accent-2"
          density="compact"
        />
        <v-spacer />
        <v-btn-toggle v-model="eventsViewMode" mandatory density="compact" variant="outlined" divided class="mr-2">
          <v-btn value="cards" icon="mdi-view-grid" size="small" />
          <v-btn value="table" icon="mdi-table" size="small" />
        </v-btn-toggle>
        <v-btn variant="text" size="small" prepend-icon="mdi-refresh" @click="loadEvents" :loading="eventsLoading">
          Reload
        </v-btn>
      </div>

      <v-progress-linear v-if="eventsLoading" indeterminate color="deep-purple-accent-2" class="mb-4" />

      <!-- Cards View -->
      <v-row v-if="eventsViewMode === 'cards'">
        <v-col v-for="ev in events" :key="ev.id || ev.slug" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="h-100" hover @click="openEventDetail(ev)">
            <v-card-title class="text-body-1 font-weight-bold">
              {{ ev.title }}
            </v-card-title>
            <v-card-text>
              <div v-if="ev.description" class="text-body-2 text-medium-emphasis mb-3" style="max-height: 60px; overflow: hidden;">
                {{ ev.description }}
              </div>
              <div class="d-flex ga-2 flex-wrap mb-2">
                <v-chip size="x-small" variant="tonal" color="green">
                  Vol: ${{ formatNumber(ev.volume) }}
                </v-chip>
                <v-chip size="x-small" variant="tonal" color="blue">
                  Liq: ${{ formatNumber(ev.liquidity) }}
                </v-chip>
                <v-chip size="x-small" variant="tonal">
                  {{ ev.markets_count }} markets
                </v-chip>
              </div>
              <!-- Top markets -->
              <div v-for="m in (ev.markets || []).slice(0, 3)" :key="m.id" class="d-flex align-center py-1" style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                <div class="text-body-2 flex-grow-1 text-truncate" style="max-width: 60%;">{{ m.question }}</div>
                <v-spacer />
                <v-chip size="x-small" color="green" variant="flat" class="mr-1">
                  Y {{ formatPercent(m.outcome_yes) }}
                </v-chip>
                <v-chip size="x-small" color="red" variant="flat">
                  N {{ formatPercent(m.outcome_no) }}
                </v-chip>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <!-- Table View -->
      <v-table v-if="eventsViewMode === 'table' && events.length" density="compact" hover class="polymarket-events-table">
        <thead>
          <tr>
            <th style="min-width: 260px;">Event</th>
            <th class="text-right" style="min-width: 80px;">Volume</th>
            <th class="text-right" style="min-width: 80px;">Liquidity</th>
            <th style="min-width: 220px;">Market</th>
            <th class="text-center" style="min-width: 70px;">Yes</th>
            <th class="text-center" style="min-width: 70px;">No</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="ev in events" :key="'tbl-' + (ev.id || ev.slug)">
            <!-- First market row (with event info) -->
            <tr
              style="cursor: pointer;"
              @click="openEventDetail(ev)"
              :class="{ 'event-first-row': (ev.markets || []).length > 1 }"
            >
              <td
                class="text-body-2 font-weight-medium"
                :rowspan="Math.max((ev.markets || []).length, 1)"
                style="vertical-align: top; padding-top: 10px; max-width: 300px; border-right: 1px solid rgba(255,255,255,0.04);"
              >
                <div class="text-truncate mb-1">{{ ev.title }}</div>
                <div class="d-flex ga-1 flex-wrap">
                  <v-chip size="x-small" variant="tonal" :color="ev.active ? 'green' : 'grey'">
                    {{ ev.active ? 'Active' : 'Closed' }}
                  </v-chip>
                  <v-chip size="x-small" variant="tonal">
                    {{ ev.markets_count }} {{ ev.markets_count === 1 ? 'market' : 'markets' }}
                  </v-chip>
                </div>
              </td>
              <td
                class="text-right text-body-2"
                :rowspan="Math.max((ev.markets || []).length, 1)"
                style="vertical-align: top; padding-top: 10px; border-right: 1px solid rgba(255,255,255,0.04);"
              >
                ${{ formatNumber(ev.volume) }}
              </td>
              <td
                class="text-right text-body-2"
                :rowspan="Math.max((ev.markets || []).length, 1)"
                style="vertical-align: top; padding-top: 10px; border-right: 1px solid rgba(255,255,255,0.04);"
              >
                ${{ formatNumber(ev.liquidity) }}
              </td>
              <!-- First market -->
              <template v-if="ev.markets && ev.markets.length">
                <td class="text-body-2" style="max-width: 250px;">
                  <div class="text-truncate">{{ ev.markets[0].question }}</div>
                </td>
                <td class="text-center">
                  <v-chip color="green" size="x-small" variant="flat" class="font-weight-bold">
                    {{ formatPercent(ev.markets[0].outcome_yes) }}
                  </v-chip>
                </td>
                <td class="text-center">
                  <v-chip color="red" size="x-small" variant="flat" class="font-weight-bold">
                    {{ formatPercent(ev.markets[0].outcome_no) }}
                  </v-chip>
                </td>
              </template>
              <template v-else>
                <td class="text-body-2 text-medium-emphasis">—</td>
                <td></td>
                <td></td>
              </template>
            </tr>
            <!-- Additional market rows -->
            <tr
              v-for="(m, mi) in (ev.markets || []).slice(1)"
              :key="'tbl-m-' + (m.id || mi)"
              style="cursor: pointer;"
              @click="openEventDetail(ev)"
              class="market-sub-row"
            >
              <td class="text-body-2" style="max-width: 250px;">
                <div class="text-truncate">{{ m.question }}</div>
              </td>
              <td class="text-center">
                <v-chip color="green" size="x-small" variant="flat" class="font-weight-bold">
                  {{ formatPercent(m.outcome_yes) }}
                </v-chip>
              </td>
              <td class="text-center">
                <v-chip color="red" size="x-small" variant="flat" class="font-weight-bold">
                  {{ formatPercent(m.outcome_no) }}
                </v-chip>
              </td>
            </tr>
          </template>
        </tbody>
      </v-table>

      <div v-if="!eventsLoading && events.length === 0" class="text-center text-medium-emphasis py-12">
        <v-icon size="64" class="mb-4">mdi-earth-off</v-icon>
        <div>No events found</div>
      </div>
    </div>

    <!-- Positions Tab -->
    <div v-if="activeTab === 'positions'">
      <v-progress-linear v-if="positionsLoading" indeterminate color="deep-purple-accent-2" class="mb-4" />
      <v-alert v-if="balance !== null" type="info" variant="tonal" class="mb-4">
        <strong>Balance:</strong> {{ balance }} USDC
      </v-alert>
      <v-table v-if="positions.length" density="compact">
        <thead>
          <tr>
            <th>Token ID</th>
            <th>Size</th>
            <th>Avg Price</th>
            <th>Current Value</th>
            <th>P&L</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in positions" :key="p.token_id || p.asset">
            <td class="text-body-2 font-weight-medium" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">
              {{ p.token_id || p.asset || 'N/A' }}
            </td>
            <td>{{ p.size || p.balance || 0 }}</td>
            <td>{{ p.avg_price || 'N/A' }}</td>
            <td>{{ p.current_value || 'N/A' }}</td>
            <td :class="(p.pnl || 0) >= 0 ? 'text-green' : 'text-red'">
              {{ (p.pnl || 0) >= 0 ? '+' : '' }}{{ p.pnl || 0 }}
            </td>
          </tr>
        </tbody>
      </v-table>
      <div v-if="!positionsLoading && positions.length === 0" class="text-center text-medium-emphasis py-12">
        <v-icon size="64" class="mb-4">mdi-wallet-outline</v-icon>
        <div>No open positions</div>
      </div>
    </div>

    <!-- History Tab -->
    <div v-if="activeTab === 'history'">
      <!-- Stats cards -->
      <v-row v-if="stats" class="mb-4">
        <v-col cols="6" sm="3">
          <v-card variant="tonal" color="blue">
            <v-card-text class="text-center">
              <div class="text-h5 font-weight-bold">{{ stats.total_bets }}</div>
              <div class="text-caption">Total Bets</div>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="6" sm="3">
          <v-card variant="tonal" color="green">
            <v-card-text class="text-center">
              <div class="text-h5 font-weight-bold">{{ stats.win_rate }}%</div>
              <div class="text-caption">Win Rate</div>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="6" sm="3">
          <v-card variant="tonal" :color="stats.total_profit >= 0 ? 'green' : 'red'">
            <v-card-text class="text-center">
              <div class="text-h5 font-weight-bold">{{ stats.total_profit >= 0 ? '+' : '' }}{{ stats.total_profit }}</div>
              <div class="text-caption">Total P&L (USDC)</div>
            </v-card-text>
          </v-card>
        </v-col>
        <v-col cols="6" sm="3">
          <v-card variant="tonal" color="orange">
            <v-card-text class="text-center">
              <div class="text-h5 font-weight-bold">{{ stats.pending }}</div>
              <div class="text-caption">Pending</div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-progress-linear v-if="historyLoading" indeterminate color="deep-purple-accent-2" class="mb-4" />

      <v-table v-if="betHistory.length" density="compact">
        <thead>
          <tr>
            <th>Date</th>
            <th>Token</th>
            <th>Side</th>
            <th>Price</th>
            <th>Size</th>
            <th>Result</th>
            <th>Profit</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="bet in betHistory" :key="bet.id">
            <td class="text-body-2">{{ formatDate(bet.created_at) }}</td>
            <td class="text-body-2" style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">{{ bet.token_id }}</td>
            <td>
              <v-chip :color="bet.side === 'BUY' ? 'green' : 'red'" size="x-small" variant="flat">{{ bet.side }}</v-chip>
            </td>
            <td>{{ bet.price }}</td>
            <td>{{ bet.size }} USDC</td>
            <td>
              <v-chip
                :color="bet.result === 'won' ? 'green' : bet.result === 'lost' ? 'red' : 'grey'"
                size="x-small"
                variant="flat"
              >
                {{ bet.result || 'pending' }}
              </v-chip>
            </td>
            <td :class="(bet.profit || 0) >= 0 ? 'text-green' : 'text-red'">
              {{ (bet.profit || 0) >= 0 ? '+' : '' }}{{ bet.profit || 0 }}
            </td>
            <td>
              <v-btn
                v-if="!bet.result || bet.result === 'pending'"
                size="x-small"
                color="green"
                variant="text"
                icon="mdi-check"
                @click="recordResult(bet, 'won')"
              />
              <v-btn
                v-if="!bet.result || bet.result === 'pending'"
                size="x-small"
                color="red"
                variant="text"
                icon="mdi-close"
                @click="recordResult(bet, 'lost')"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
      <div v-if="!historyLoading && betHistory.length === 0" class="text-center text-medium-emphasis py-12">
        <v-icon size="64" class="mb-4">mdi-history</v-icon>
        <div>No betting history yet</div>
      </div>
    </div>

    <!-- Event Detail Dialog -->
    <v-dialog v-model="eventDialog" max-width="800" scrollable>
      <v-card v-if="selectedEvent">
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2" color="deep-purple-accent-2">mdi-earth</v-icon>
          {{ selectedEvent.title }}
        </v-card-title>
        <v-card-text>
          <div v-if="selectedEvent.description" class="text-body-2 mb-4">{{ selectedEvent.description }}</div>
          <div class="d-flex ga-2 mb-4">
            <v-chip variant="tonal" color="green" size="small">Vol: ${{ formatNumber(selectedEvent.volume) }}</v-chip>
            <v-chip variant="tonal" color="blue" size="small">Liq: ${{ formatNumber(selectedEvent.liquidity) }}</v-chip>
          </div>
          <div class="text-subtitle-2 mb-2">Markets:</div>
          <v-card v-for="m in (selectedEvent.markets || [])" :key="m.id" variant="outlined" class="mb-2 pa-3">
            <div class="text-body-1 font-weight-medium mb-2">{{ m.question }}</div>
            <div class="d-flex align-center ga-3">
              <v-chip color="green" variant="flat" size="small">
                YES {{ formatPercent(m.outcome_yes) }}
              </v-chip>
              <v-chip color="red" variant="flat" size="small">
                NO {{ formatPercent(m.outcome_no) }}
              </v-chip>
              <v-chip variant="tonal" size="small">Vol: ${{ formatNumber(m.volume) }}</v-chip>
              <v-spacer />
              <v-btn
                v-if="configured"
                size="small"
                color="green"
                variant="tonal"
                prepend-icon="mdi-arrow-up-bold"
                @click="openBetDialog(m, 'YES')"
              >
                Buy Yes
              </v-btn>
              <v-btn
                v-if="configured"
                size="small"
                color="red"
                variant="tonal"
                prepend-icon="mdi-arrow-down-bold"
                @click="openBetDialog(m, 'NO')"
              >
                Buy No
              </v-btn>
            </div>
          </v-card>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="eventDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Place Bet Dialog -->
    <v-dialog v-model="betDialog" max-width="500">
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon class="mr-2" :color="betSide === 'YES' ? 'green' : 'red'">mdi-cash</v-icon>
          Place Bet — {{ betSide }}
        </v-card-title>
        <v-card-text>
          <div class="text-body-2 mb-3">
            <strong>Market:</strong> {{ betMarket?.question }}
          </div>
          <div class="text-body-2 mb-4">
            Current price: <v-chip :color="betSide === 'YES' ? 'green' : 'red'" size="x-small" variant="flat">
              {{ betSide === 'YES' ? formatPercent(betMarket?.outcome_yes) : formatPercent(betMarket?.outcome_no) }}
            </v-chip>
          </div>
          <v-text-field
            v-model.number="betPrice"
            label="Price (0.01 - 0.99)"
            type="number"
            step="0.01"
            min="0.01"
            max="0.99"
            variant="outlined"
            density="compact"
            class="mb-3"
            hint="The probability/price you want to buy at"
            persistent-hint
          />
          <v-text-field
            v-model.number="betSize"
            label="Size (USDC)"
            type="number"
            step="1"
            min="1"
            variant="outlined"
            density="compact"
            class="mb-3"
            hint="Amount in USDC to bet"
            persistent-hint
          />
          <v-alert v-if="betPrice && betSize" type="info" variant="tonal" density="compact" class="mb-2">
            <div>Potential payout: <strong>{{ (betSize / betPrice).toFixed(2) }} USDC</strong></div>
            <div>Potential profit: <strong>{{ ((betSize / betPrice) - betSize).toFixed(2) }} USDC</strong></div>
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="betDialog = false">Cancel</v-btn>
          <v-btn
            :color="betSide === 'YES' ? 'green' : 'red'"
            :loading="betLoading"
            :disabled="!betPrice || !betSize || betPrice < 0.01 || betPrice > 0.99 || betSize <= 0"
            @click="submitBet"
          >
            Place Bet
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Record Result Dialog -->
    <v-dialog v-model="resultDialog" max-width="400">
      <v-card>
        <v-card-title>Record Result</v-card-title>
        <v-card-text>
          <div class="text-body-2 mb-3">Mark this bet as {{ resultType }}?</div>
          <v-text-field
            v-model.number="resultProfit"
            label="Profit/Loss (USDC)"
            type="number"
            variant="outlined"
            density="compact"
            :hint="resultType === 'won' ? 'Enter profit amount' : 'Enter loss as negative'"
            persistent-hint
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="resultDialog = false">Cancel</v-btn>
          <v-btn :color="resultType === 'won' ? 'green' : 'red'" @click="submitResult" :loading="resultLoading">
            Confirm
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- AI Betting Tab -->
    <AiBettingTab v-if="activeTab === 'ai_betting'" :configured="configured" />

    <!-- Skills Tab -->
    <div v-if="activeTab === 'skills'">
      <v-progress-linear v-if="skillsLoading" indeterminate color="deep-purple-accent-2" class="mb-4" />
      <v-row v-if="addonSkills.length">
        <v-col v-for="skill in addonSkills" :key="skill.id" cols="12" md="6" lg="4">
          <v-card variant="outlined" rounded="lg">
            <v-card-item>
              <template #prepend>
                <v-avatar color="info" size="36" rounded="lg">
                  <v-icon size="20">mdi-puzzle</v-icon>
                </v-avatar>
              </template>
              <v-card-title class="text-body-1 font-weight-bold">{{ skill.display_name || skill.name }}</v-card-title>
              <v-card-subtitle class="text-caption">{{ skill.category || 'general' }}</v-card-subtitle>
            </v-card-item>
            <v-card-text class="pt-0">
              <p class="text-body-2 text-medium-emphasis mb-3">{{ skill.description || 'No description' }}</p>
              <div v-if="skill.description_for_agent" class="text-caption text-medium-emphasis mb-3" style="max-height: 60px; overflow: hidden;">
                <strong>Agent hint:</strong> {{ skill.description_for_agent }}
              </div>
              <div class="d-flex ga-2 flex-wrap">
                <v-chip size="x-small" variant="tonal" :color="skill.enabled ? 'success' : 'grey'">
                  {{ skill.enabled ? 'Enabled' : 'Disabled' }}
                </v-chip>
                <v-chip v-if="skill.is_system" size="x-small" variant="tonal" color="info">System</v-chip>
                <v-chip v-if="skill.version" size="x-small" variant="tonal">v{{ skill.version }}</v-chip>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
      <div v-if="!skillsLoading && !addonSkills.length" class="text-center text-medium-emphasis py-12">
        <v-icon size="64" class="mb-4">mdi-puzzle-outline</v-icon>
        <div>No addon skills found</div>
      </div>
    </div>

    <!-- Protocols Tab -->
    <div v-if="activeTab === 'protocols'">
      <v-progress-linear v-if="protocolsLoading" indeterminate color="deep-purple-accent-2" class="mb-4" />
      <v-row v-if="addonProtocols.length">
        <v-col v-for="proto in addonProtocols" :key="proto.id" cols="12" md="6">
          <v-card variant="outlined" rounded="lg">
            <v-card-item>
              <template #prepend>
                <v-avatar color="purple" size="36" rounded="lg">
                  <v-icon size="20">mdi-head-cog</v-icon>
                </v-avatar>
              </template>
              <v-card-title class="text-body-1 font-weight-bold">{{ proto.name }}</v-card-title>
              <v-card-subtitle class="text-caption">{{ proto.type || 'standard' }}</v-card-subtitle>
              <template #append>
                <v-btn icon="mdi-pencil" size="small" variant="text" @click="editProtocol(proto)" />
              </template>
            </v-card-item>
            <v-card-text class="pt-0">
              <p v-if="proto.description" class="text-body-2 text-medium-emphasis mb-3">{{ proto.description }}</p>
              <div v-if="proto.response_style" class="mb-3">
                <v-chip size="x-small" variant="tonal" color="warning" prepend-icon="mdi-format-paint">
                  Style: {{ proto.response_style.name || proto.response_style.preset || 'custom' }}
                </v-chip>
              </div>
              <div v-if="(proto.steps || []).length" class="mt-2">
                <div class="text-subtitle-2 mb-2">Steps ({{ proto.steps.length }}):</div>
                <div v-for="(step, idx) in proto.steps" :key="idx" class="d-flex align-start mb-2 pa-2 rounded" style="background: rgba(255,255,255,0.03);">
                  <v-chip size="x-small" variant="flat" color="deep-purple-accent-2" class="mr-2 mt-1" style="min-width: 24px;">{{ idx + 1 }}</v-chip>
                  <div class="flex-grow-1">
                    <div class="text-body-2 font-weight-medium">{{ step.name }}</div>
                    <div v-if="step.instruction" class="text-caption text-medium-emphasis mt-1" style="max-height: 40px; overflow: hidden;">
                      {{ step.instruction }}
                    </div>
                    <div class="d-flex ga-1 mt-1 flex-wrap">
                      <v-chip v-if="step.type" size="x-small" variant="tonal">{{ step.type }}</v-chip>
                      <v-chip v-if="step.skill" size="x-small" variant="tonal" color="info" prepend-icon="mdi-puzzle">{{ step.skill }}</v-chip>
                    </div>
                  </div>
                </div>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
      <div v-if="!protocolsLoading && !addonProtocols.length" class="text-center text-medium-emphasis py-12">
        <v-icon size="64" class="mb-4">mdi-head-cog-outline</v-icon>
        <div>No addon protocols found</div>
      </div>
    </div>

    <!-- Settings Tab -->
    <div v-if="activeTab === 'settings'">
      <v-card variant="outlined" max-width="600">
        <v-card-title class="text-body-1 font-weight-bold">
          <v-icon class="mr-2" size="20">mdi-key-variant</v-icon>
          API Credentials
        </v-card-title>
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Enter your Polymarket CLOB API credentials to enable trading, positions and balance features.
          </p>
          <v-text-field
            v-model="settingsForm.polymarket_api_key"
            label="API Key"
            variant="outlined"
            density="compact"
            class="mb-3"
            :append-inner-icon="showApiKey ? 'mdi-eye-off' : 'mdi-eye'"
            :type="showApiKey ? 'text' : 'password'"
            @click:append-inner="showApiKey = !showApiKey"
            placeholder="Enter Polymarket API key"
          />
          <v-text-field
            v-model="settingsForm.polymarket_api_secret"
            label="API Secret"
            variant="outlined"
            density="compact"
            class="mb-3"
            :append-inner-icon="showApiSecret ? 'mdi-eye-off' : 'mdi-eye'"
            :type="showApiSecret ? 'text' : 'password'"
            @click:append-inner="showApiSecret = !showApiSecret"
            placeholder="Enter Polymarket API secret"
          />
          <v-text-field
            v-model="settingsForm.polymarket_passphrase"
            label="Passphrase"
            variant="outlined"
            density="compact"
            class="mb-4"
            :append-inner-icon="showPassphrase ? 'mdi-eye-off' : 'mdi-eye'"
            :type="showPassphrase ? 'text' : 'password'"
            @click:append-inner="showPassphrase = !showPassphrase"
            placeholder="Enter Polymarket passphrase"
          />
          <v-btn color="primary" :loading="settingsSaving" @click="saveSettings" prepend-icon="mdi-content-save">
            Save Settings
          </v-btn>
          <v-alert v-if="settingsSaved" type="success" variant="tonal" density="compact" class="mt-4">
            Settings saved successfully
          </v-alert>
        </v-card-text>
      </v-card>

      <!-- VPN Proxy Settings -->
      <v-card variant="outlined" max-width="800" class="mt-6">
        <v-card-title class="text-body-1 font-weight-bold d-flex align-center">
          <v-icon class="mr-2" size="20">mdi-vpn</v-icon>
          VPN Proxy
          <v-spacer />
          <v-chip v-if="activeVpn" color="success" size="small" variant="tonal" class="mr-2">
            <v-icon start size="14">mdi-shield-check</v-icon>
            {{ activeVpn.name }}
          </v-chip>
          <v-chip v-else color="warning" size="small" variant="tonal" class="mr-2">
            <v-icon start size="14">mdi-shield-off-outline</v-icon>
            No VPN
          </v-chip>
          <v-btn size="small" variant="tonal" color="primary" @click="openVpnDialog()" prepend-icon="mdi-plus">
            Add VPN
          </v-btn>
        </v-card-title>
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Configure VPN/proxy connections to route Polymarket API calls through. Only one VPN can be active at a time.
          </p>

          <v-progress-linear v-if="vpnsLoading" indeterminate color="primary" class="mb-4" />

          <div v-if="!vpnsLoading && !vpns.length" class="text-center text-medium-emphasis py-6">
            <v-icon size="48" class="mb-2">mdi-vpn</v-icon>
            <div>No VPN proxies configured</div>
          </div>

          <v-list v-if="vpns.length" density="compact" class="bg-transparent">
            <v-list-item
              v-for="vpn in vpns"
              :key="vpn.id"
              :class="vpn.is_active ? 'border-s-4 border-success' : ''"
              rounded="lg"
              class="mb-2"
            >
              <template #prepend>
                <v-icon :color="vpn.is_active ? 'success' : 'grey'" class="mr-3">
                  {{ vpn.is_active ? 'mdi-shield-check' : 'mdi-shield-outline' }}
                </v-icon>
              </template>

              <v-list-item-title class="font-weight-medium">
                {{ vpn.name }}
                <v-chip size="x-small" variant="outlined" class="ml-2">{{ vpn.protocol }}</v-chip>
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ vpn.host }}:{{ vpn.port }}
                <span v-if="vpn.username"> &middot; user: {{ vpn.username }}</span>
                <span v-if="vpn.password_set"> &middot; <v-icon size="12">mdi-lock</v-icon></span>
              </v-list-item-subtitle>

              <template #append>
                <div class="d-flex align-center ga-1">
                  <v-btn
                    v-if="!vpn.is_active"
                    size="x-small"
                    variant="tonal"
                    color="success"
                    @click="activateVpn(vpn.id)"
                    :loading="vpnActivating === vpn.id"
                    title="Activate"
                  >
                    <v-icon>mdi-power</v-icon>
                  </v-btn>
                  <v-btn
                    v-else
                    size="x-small"
                    variant="tonal"
                    color="warning"
                    @click="deactivateVpn()"
                    :loading="vpnActivating === vpn.id"
                    title="Deactivate"
                  >
                    <v-icon>mdi-power-off</v-icon>
                  </v-btn>
                  <v-btn
                    size="x-small"
                    variant="tonal"
                    @click="testVpn(vpn.id)"
                    :loading="vpnTesting === vpn.id"
                    title="Test connection"
                  >
                    <v-icon>mdi-connection</v-icon>
                  </v-btn>
                  <v-btn
                    size="x-small"
                    variant="tonal"
                    @click="openVpnDialog(vpn)"
                    title="Edit"
                  >
                    <v-icon>mdi-pencil</v-icon>
                  </v-btn>
                  <v-btn
                    size="x-small"
                    variant="tonal"
                    color="error"
                    @click="deleteVpn(vpn)"
                    :loading="vpnDeleting === vpn.id"
                    title="Delete"
                  >
                    <v-icon>mdi-delete</v-icon>
                  </v-btn>
                </div>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
      </v-card>

      <!-- VPN Add/Edit Dialog -->
      <v-dialog v-model="vpnDialog" max-width="500" persistent>
        <v-card>
          <v-card-title>{{ vpnEditing ? 'Edit VPN' : 'Add VPN' }}</v-card-title>
          <v-card-text>
            <v-text-field
              v-model="vpnForm.name"
              label="Name"
              variant="outlined"
              density="compact"
              class="mb-3"
              placeholder="e.g. US Proxy, EU SOCKS"
            />
            <v-select
              v-model="vpnForm.protocol"
              :items="['socks5', 'socks5h', 'http', 'https']"
              label="Protocol"
              variant="outlined"
              density="compact"
              class="mb-3"
            />
            <v-row dense class="mb-3">
              <v-col cols="8">
                <v-text-field
                  v-model="vpnForm.host"
                  label="Host"
                  variant="outlined"
                  density="compact"
                  placeholder="proxy.example.com"
                />
              </v-col>
              <v-col cols="4">
                <v-text-field
                  v-model.number="vpnForm.port"
                  label="Port"
                  variant="outlined"
                  density="compact"
                  type="number"
                  placeholder="1080"
                />
              </v-col>
            </v-row>
            <v-text-field
              v-model="vpnForm.username"
              label="Username (optional)"
              variant="outlined"
              density="compact"
              class="mb-3"
              autocomplete="off"
            />
            <v-text-field
              v-model="vpnForm.password"
              label="Password (optional)"
              variant="outlined"
              density="compact"
              :append-inner-icon="showVpnPassword ? 'mdi-eye-off' : 'mdi-eye'"
              :type="showVpnPassword ? 'text' : 'password'"
              @click:append-inner="showVpnPassword = !showVpnPassword"
              autocomplete="off"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="vpnDialog = false">Cancel</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              :loading="vpnSaving"
              :disabled="!vpnForm.name || !vpnForm.host || !vpnForm.port"
              @click="saveVpn"
            >
              {{ vpnEditing ? 'Update' : 'Create' }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@src/api'
import { useSettingsStore } from '@src/stores/settings'
import AiBettingTab from './AiBettingTab.vue'

const showSnackbar = inject('showSnackbar')
const settingsStore = useSettingsStore()
const router = useRouter()

// State
const loading = ref(false)
const errorMsg = ref(null)
const activeTab = ref(localStorage.getItem('polymarket_active_tab') || 'events')

// Events
const events = ref([])
const eventsLoading = ref(false)
const searchQuery = ref('')
const showClosed = ref(false)
const eventsViewMode = ref(localStorage.getItem('polymarket_view_mode') || 'cards')

// Positions
const positions = ref([])
const positionsLoading = ref(false)
const balance = ref(null)

// History
const betHistory = ref([])
const historyLoading = ref(false)
const stats = ref(null)

// Skills & Protocols
const addonSkills = ref([])
const skillsLoading = ref(false)
const addonProtocols = ref([])
const protocolsLoading = ref(false)
const ADDON_SKILL_NAMES = ['polymarket_events', 'polymarket_event_odds', 'polymarket_place_bet', 'polymarket_positions', 'polymarket_history', 'polymarket_balance']
const ADDON_PROTOCOL_NAMES = ['Gambling Addict']

// Agents check
const allAgents = ref([])

// Dialogs
const eventDialog = ref(false)
const selectedEvent = ref(null)
const betDialog = ref(false)
const betMarket = ref(null)
const betSide = ref('YES')
const betPrice = ref(0.5)
const betSize = ref(10)
const betLoading = ref(false)
const resultDialog = ref(false)
const resultBet = ref(null)
const resultType = ref('won')
const resultProfit = ref(0)
const resultLoading = ref(false)

// Settings
const settingsSaving = ref(false)
const settingsSaved = ref(false)
const showApiKey = ref(false)
const showApiSecret = ref(false)
const showPassphrase = ref(false)
const settingsForm = ref({
  polymarket_api_key: '',
  polymarket_api_secret: '',
  polymarket_passphrase: '',
})

// VPN
const vpns = ref([])
const vpnsLoading = ref(false)
const vpnDialog = ref(false)
const vpnEditing = ref(null) // vpn id if editing, null if creating
const vpnForm = ref({ name: '', protocol: 'socks5', host: '', port: 1080, username: '', password: '' })
const vpnSaving = ref(false)
const vpnTesting = ref(null) // vpn id being tested
const vpnActivating = ref(null) // vpn id being activated
const vpnDeleting = ref(null) // vpn id being deleted
const showVpnPassword = ref(false)

const activeVpn = computed(() => vpns.value.find(v => v.is_active))

// Computed
const configured = computed(() => {
  const s = settingsStore.systemSettings
  return !!(s.polymarket_api_key?.value)
})

const hasProtocolAgent = computed(() => {
  return allAgents.value.some(a =>
    (a.protocols || []).some(p => ADDON_PROTOCOL_NAMES.includes(p.name))
  )
})

// Watch view mode to persist
watch(eventsViewMode, (v) => localStorage.setItem('polymarket_view_mode', v))
watch(activeTab, (tab) => {
  localStorage.setItem('polymarket_active_tab', tab)
  if (tab === 'settings') {
    const s = settingsStore.systemSettings
    settingsForm.value = {
      polymarket_api_key: s.polymarket_api_key?.value || '',
      polymarket_api_secret: s.polymarket_api_secret?.value || '',
      polymarket_passphrase: s.polymarket_passphrase?.value || '',
    }
    settingsSaved.value = false
    loadVpns()
  }
})

// Methods
function formatNumber(n) {
  if (!n) return '0'
  n = parseFloat(n)
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return n.toFixed(0)
}

function formatPercent(p) {
  if (!p) return '—'
  return (parseFloat(p) * 100).toFixed(0) + '%'
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadEvents() {
  eventsLoading.value = true
  try {
    const params = { limit: 30, active: !showClosed.value, closed: showClosed.value }
    if (searchQuery.value) params.search = searchQuery.value
    const { data } = await api.get('/addons/polymarket/events', { params })
    events.value = data.items || []
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to load events'
  } finally {
    eventsLoading.value = false
  }
}

async function loadPositions() {
  if (!configured.value) return
  positionsLoading.value = true
  try {
    const [posRes, balRes] = await Promise.all([
      api.get('/addons/polymarket/positions').catch(() => ({ data: [] })),
      api.get('/addons/polymarket/balance').catch(() => ({ data: {} })),
    ])
    const posData = posRes.data
    positions.value = Array.isArray(posData) ? posData : posData.positions || []
    balance.value = balRes.data?.balance ?? balRes.data?.available ?? null
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to load positions'
  } finally {
    positionsLoading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const [histRes, statsRes] = await Promise.all([
      api.get('/addons/polymarket/history', { params: { limit: 100 } }),
      api.get('/addons/polymarket/history/stats'),
    ])
    betHistory.value = histRes.data.items || []
    stats.value = statsRes.data
  } catch (e) {
    // History might not have entries yet — that's fine
    betHistory.value = []
    stats.value = { total_bets: 0, won: 0, lost: 0, pending: 0, total_profit: 0, win_rate: 0 }
  } finally {
    historyLoading.value = false
  }
}

async function loadSkills() {
  skillsLoading.value = true
  try {
    const { data } = await api.get('/skills')
    addonSkills.value = data.filter(s => ADDON_SKILL_NAMES.includes(s.name))
  } catch (e) {
    addonSkills.value = []
  } finally {
    skillsLoading.value = false
  }
}

async function loadProtocols() {
  protocolsLoading.value = true
  try {
    const { data } = await api.get('/protocols')
    addonProtocols.value = data.filter(p => ADDON_PROTOCOL_NAMES.includes(p.name))
  } catch (e) {
    addonProtocols.value = []
  } finally {
    protocolsLoading.value = false
  }
}

async function loadAgents() {
  try {
    const { data } = await api.get('/agents')
    allAgents.value = data
  } catch (e) {
    allAgents.value = []
  }
}

async function refreshAll() {
  loading.value = true
  await Promise.all([loadEvents(), loadHistory(), loadPositions(), loadSkills(), loadProtocols(), loadAgents()])
  loading.value = false
}

function openEventDetail(ev) {
  selectedEvent.value = ev
  eventDialog.value = true
}

function openBetDialog(market, side) {
  betMarket.value = market
  betSide.value = side
  const tokenKey = side === 'YES' ? 'token_id_yes' : 'token_id_no'
  betPrice.value = parseFloat(side === 'YES' ? market.outcome_yes : market.outcome_no) || 0.5
  betSize.value = 10
  betDialog.value = true
}

async function submitBet() {
  betLoading.value = true
  try {
    const tokenKey = betSide.value === 'YES' ? 'token_id_yes' : 'token_id_no'
    const tokenId = betMarket.value?.[tokenKey]
    if (!tokenId) {
      errorMsg.value = 'Token ID not available for this market'
      return
    }
    await api.post('/addons/polymarket/bet', {
      token_id: tokenId,
      side: 'BUY',
      price: betPrice.value,
      size: betSize.value,
    })
    showSnackbar('Bet placed successfully!', 'success')
    betDialog.value = false
    await loadHistory()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to place bet'
  } finally {
    betLoading.value = false
  }
}

function recordResult(bet, type) {
  resultBet.value = bet
  resultType.value = type
  resultProfit.value = type === 'won' ? (bet.size / bet.price - bet.size) : -bet.size
  resultDialog.value = true
}

async function submitResult() {
  resultLoading.value = true
  try {
    await api.patch(`/addons/polymarket/history/${resultBet.value.id}`, {
      result: resultType.value,
      profit: resultProfit.value,
    })
    showSnackbar(`Bet marked as ${resultType.value}`, 'success')
    resultDialog.value = false
    await loadHistory()
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Failed to record result'
  } finally {
    resultLoading.value = false
  }
}

async function saveSettings() {
  settingsSaving.value = true
  settingsSaved.value = false
  try {
    const keys = ['polymarket_api_key', 'polymarket_api_secret', 'polymarket_passphrase']
    for (const key of keys) {
      await settingsStore.updateSystemSetting(key, settingsForm.value[key])
    }
    settingsSaved.value = true
    await settingsStore.fetchSystemSettings()
  } catch (e) {
    errorMsg.value = 'Failed to save settings'
  } finally {
    settingsSaving.value = false
  }
}

// VPN Methods
async function loadVpns() {
  vpnsLoading.value = true
  try {
    const { data } = await api.get('/addons/polymarket/vpns')
    vpns.value = data.items || []
  } catch (e) {
    console.error('Failed to load VPNs:', e)
  } finally {
    vpnsLoading.value = false
  }
}

function openVpnDialog(vpn = null) {
  if (vpn) {
    vpnEditing.value = vpn.id
    vpnForm.value = {
      name: vpn.name,
      protocol: vpn.protocol,
      host: vpn.host,
      port: vpn.port,
      username: vpn.username || '',
      password: vpn.password || '',
    }
  } else {
    vpnEditing.value = null
    vpnForm.value = { name: '', protocol: 'socks5', host: '', port: 1080, username: '', password: '' }
  }
  showVpnPassword.value = false
  vpnDialog.value = true
}

async function saveVpn() {
  vpnSaving.value = true
  try {
    if (vpnEditing.value) {
      await api.patch(`/addons/polymarket/vpns/${vpnEditing.value}`, vpnForm.value)
      showSnackbar('VPN updated', 'success')
    } else {
      await api.post('/addons/polymarket/vpns', vpnForm.value)
      showSnackbar('VPN created', 'success')
    }
    vpnDialog.value = false
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to save VPN', 'error')
  } finally {
    vpnSaving.value = false
  }
}

async function deleteVpn(vpn) {
  if (!confirm(`Delete VPN "${vpn.name}"?`)) return
  vpnDeleting.value = vpn.id
  try {
    await api.delete(`/addons/polymarket/vpns/${vpn.id}`)
    showSnackbar('VPN deleted', 'success')
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to delete VPN', 'error')
  } finally {
    vpnDeleting.value = null
  }
}

async function activateVpn(vpnId) {
  vpnActivating.value = vpnId
  try {
    await api.post(`/addons/polymarket/vpns/${vpnId}/activate`)
    showSnackbar('VPN activated', 'success')
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to activate VPN', 'error')
  } finally {
    vpnActivating.value = null
  }
}

async function deactivateVpn() {
  vpnActivating.value = activeVpn.value?.id
  try {
    await api.post('/addons/polymarket/vpns/none/activate')
    showSnackbar('VPN deactivated', 'success')
    await loadVpns()
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'Failed to deactivate VPN', 'error')
  } finally {
    vpnActivating.value = null
  }
}

async function testVpn(vpnId) {
  vpnTesting.value = vpnId
  try {
    const { data } = await api.post(`/addons/polymarket/vpns/${vpnId}/test`)
    if (data.success) {
      showSnackbar(`VPN working! IP: ${data.ip}`, 'success')
    } else {
      showSnackbar(`VPN test failed: ${data.error}`, 'error')
    }
  } catch (e) {
    showSnackbar(e.response?.data?.detail || 'VPN test failed', 'error')
  } finally {
    vpnTesting.value = null
  }
}

function editProtocol(proto) {
  router.push({ path: '/settings/protocols', query: { edit: proto.id } })
}

onMounted(async () => {
  await Promise.all([
    settingsStore.fetchSystemSettings(),
    refreshAll(),
    loadVpns(),
  ])
})
</script>

<style scoped>
.polymarket-events-table :deep(tr.market-sub-row td) {
  border-top: 1px solid rgba(255, 255, 255, 0.03) !important;
}
.polymarket-events-table :deep(tr.event-first-row td) {
  border-bottom: none !important;
}
.polymarket-events-table :deep(tbody tr:hover) {
  background: rgba(255, 255, 255, 0.03) !important;
}
</style>