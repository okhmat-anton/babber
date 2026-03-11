<template>
  <div>
    <!-- Strategy sub-tabs -->
    <v-tabs v-model="activeStrategy" color="deep-purple-accent-2" density="compact" class="mb-4">
      <v-tab value="rare_events_micro">
        <v-icon start size="18">mdi-dice-multiple</v-icon>
        Micro Bets: Rare Events
      </v-tab>
    </v-tabs>

    <!-- No active session — setup view -->
    <div v-if="!currentSession">
      <v-card variant="outlined" class="mb-4">
        <v-card-text>
          <v-row align="center">
            <v-col cols="12" md="4">
              <v-select
                v-model="selectedAgentId"
                :items="agentItems"
                item-title="name"
                item-value="id"
                label="Select Agent"
                density="compact"
                variant="outlined"
                hide-details
                clearable
                prepend-inner-icon="mdi-robot"
                :loading="agentsLoading"
                no-data-text="No agents found"
              />
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model.number="defaultAmount"
                label="Default bet"
                type="number"
                min="0.1"
                step="0.5"
                density="compact"
                variant="outlined"
                hide-details
                prefix="$"
              />
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model.number="maxOdds"
                label="Max odds"
                type="number"
                min="0.01"
                max="0.99"
                step="0.05"
                density="compact"
                variant="outlined"
                hide-details
                hint="0.35 = 35%"
              />
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model.number="minMultiplier"
                label="Min multiplier"
                type="number"
                min="1.1"
                step="0.5"
                density="compact"
                variant="outlined"
                hide-details
                prefix="x"
              />
            </v-col>
            <v-col cols="auto">
              <v-btn
                color="deep-purple-accent-2"
                :loading="analyzing"
                prepend-icon="mdi-magnify-scan"
                @click="analyzeMarkets"
              >
                Analyze Markets
              </v-btn>
            </v-col>
          </v-row>
          <p class="text-caption text-medium-emphasis mt-3 mb-0">
            Scans all active Polymarket events, filters for rare events (elections, crypto crashes,
            geopolitical crises), picks outcomes with low probability (&le; {{ (maxOdds * 100).toFixed(0) }}%)
            and creates a betting session with micro-bet opportunities.
          </p>
        </v-card-text>
      </v-card>

      <!-- Past sessions table -->
      <div v-if="pastSessions.length" class="mt-4">
        <div class="d-flex align-center mb-2">
          <div class="text-subtitle-2 text-medium-emphasis">Past Sessions</div>
          <v-spacer />
          <v-btn variant="text" size="x-small" prepend-icon="mdi-refresh" @click="loadSessions" :loading="sessionsLoading">
            Reload
          </v-btn>
        </div>
        <v-table density="compact" hover>
          <thead>
            <tr>
              <th>Date</th>
              <th>Strategy</th>
              <th class="text-center">Bets</th>
              <th>Status</th>
              <th style="width: 80px;"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in pastSessions" :key="s.id" class="session-row" @click="openSession(s.id)">
              <td class="text-body-2">{{ formatDate(s.created_at) }}</td>
              <td class="text-body-2">{{ strategyLabel(s.strategy) }}</td>
              <td class="text-center text-body-2">{{ s.bets_count || s.total_bets }}</td>
              <td>
                <v-chip
                  :color="statusColor(s.status)"
                  size="x-small"
                  variant="tonal"
                >
                  {{ s.status }}
                </v-chip>
              </td>
              <td>
                <v-btn size="x-small" variant="text" icon="mdi-delete" color="red" @click.stop="requestDelete(s.id)" />
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>

      <div v-if="!pastSessions.length && !analyzing" class="text-center text-medium-emphasis py-10">
        <v-icon size="64" class="mb-3">mdi-robot-confused</v-icon>
        <div class="text-h6">No betting sessions yet</div>
        <div class="text-body-2">Select an agent and click "Analyze Markets" to create your first session.</div>
      </div>
    </div>

    <!-- Active session view -->
    <div v-else>
      <div class="d-flex align-center mb-4 flex-wrap ga-2">
        <v-btn variant="text" prepend-icon="mdi-arrow-left" size="small" @click="exitSession">
          Back
        </v-btn>
        <v-chip variant="tonal" :color="statusColor(currentSession.status)" size="small">
          {{ currentSession.status }}
        </v-chip>
        <div class="text-caption text-medium-emphasis">
          {{ formatDate(currentSession.created_at) }}
          &middot; {{ currentSession.total_events }} events
          &middot; {{ currentSession.total_bets }} opportunities
        </div>
        <v-spacer />
        <v-text-field
          v-model.number="sessionMinMultiplier"
          label="Min x"
          type="number"
          min="1.1"
          step="0.5"
          density="compact"
          variant="outlined"
          hide-details
          prefix="x"
          style="max-width: 100px;"
          class="mr-2"
        />
        <v-text-field
          v-model.number="sessionDefaultAmount"
          label="Default $"
          type="number"
          min="0.1"
          step="0.5"
          density="compact"
          variant="outlined"
          hide-details
          prefix="$"
          style="max-width: 120px;"
          @update:model-value="applyDefaultAmount"
        />
      </div>

      <!-- Session sub-tabs -->
      <v-tabs v-model="sessionTab" density="compact" class="mb-3" color="deep-purple-accent-2">
        <v-tab value="bets">
          <v-icon start size="16">mdi-format-list-bulleted</v-icon>
          Bets ({{ filteredBets.length }})
        </v-tab>
        <v-tab value="thinking_logs">
          <v-icon start size="16">mdi-brain</v-icon>
          Thinking Logs
          <v-chip v-if="analysisLogs.length" size="x-small" class="ml-1" color="deep-purple" variant="tonal">{{ analysisLogs.length }}</v-chip>
        </v-tab>
        <v-tab value="rejected">
          <v-icon start size="16">mdi-cancel</v-icon>
          Rejected
          <v-chip v-if="rejectedBets.length" size="x-small" class="ml-1" color="red" variant="tonal">{{ rejectedBets.length }}</v-chip>
        </v-tab>
      </v-tabs>

      <div v-if="sessionTab === 'bets'">
      <!-- Summary & Actions bar -->
      <v-card variant="tonal" color="deep-purple" class="mb-3">
        <v-card-text class="py-2">
          <v-row align="center" no-gutters class="ga-3 flex-wrap">
            <v-col cols="auto">
              <div class="text-caption text-medium-emphasis">Selected</div>
              <div class="text-subtitle-2 font-weight-bold">
                {{ selectedBets.length }} / {{ filteredBets.length }}
              </div>
            </v-col>
            <v-col cols="auto">
              <div class="text-caption text-medium-emphasis">Total Bet</div>
              <div class="text-subtitle-2 font-weight-bold">${{ totalBet.toFixed(2) }}</div>
            </v-col>
            <v-col cols="auto">
              <div class="text-caption text-medium-emphasis">If All Win</div>
              <div class="text-subtitle-2 font-weight-bold text-green">${{ totalPayout.toFixed(2) }}</div>
            </v-col>
            <v-col cols="auto">
              <div class="text-caption text-medium-emphasis">Break Even</div>
              <div class="text-subtitle-2 font-weight-bold">Min {{ minWinsToBreakEven }} win{{ minWinsToBreakEven !== 1 ? 's' : '' }}</div>
            </v-col>
            <v-spacer />
            <v-col cols="auto">
              <v-text-field
                v-model.number="totalBudget"
                label="Budget"
                type="number"
                min="1"
                step="10"
                density="compact"
                variant="outlined"
                hide-details
                prefix="$"
                style="max-width: 110px;"
              />
            </v-col>
            <v-col cols="auto">
              <v-btn
                color="amber-darken-2"
                variant="tonal"
                size="small"
                prepend-icon="mdi-brain"
                :loading="agentAnalyzing"
                :disabled="!filteredBets.length || !currentSession.agent_id"
                @click="agentAnalyze"
                class="mr-2"
              >
                Analyze (top {{ maxBetsForBudget }})
              </v-btn>
              <v-btn
                color="deep-purple-accent-2"
                variant="tonal"
                size="small"
                prepend-icon="mdi-text-box-outline"
                :loading="agentReasoningLoading"
                :disabled="!currentSession.agent_analyzed || !currentSession.agent_id"
                @click="agentReasoning"
                class="mr-2"
              >
                Reasoning
              </v-btn>
              <v-btn
                color="green"
                variant="flat"
                size="small"
                prepend-icon="mdi-cash-multiple"
                :loading="placing"
                :disabled="!selectedBets.length || currentSession.status === 'placed'"
                @click="requestPlaceAll"
              >
                Place {{ selectedBets.length }} Bet{{ selectedBets.length !== 1 ? 's' : '' }}
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- Agent analysis alert -->
      <v-alert
        v-if="agentAnalyzeResult"
        type="info"
        variant="tonal"
        closable
        class="mb-3"
        @click:close="agentAnalyzeResult = null"
      >
        Agent analyzed {{ agentAnalyzeResult.analyzed }} bets:
        <v-chip size="x-small" color="green" variant="tonal" class="mx-1">{{ agentAnalyzeResult.green }} green</v-chip>
        <v-chip size="x-small" color="amber" variant="tonal" class="mx-1">{{ agentAnalyzeResult.yellow }} neutral</v-chip>
        <v-chip size="x-small" color="red" variant="tonal" class="mx-1">{{ agentAnalyzeResult.red }} red</v-chip>
      </v-alert>

      <!-- Place results -->
      <v-alert
        v-if="placeResult"
        :type="placeResult.failed === 0 ? 'success' : 'warning'"
        variant="tonal"
        closable
        class="mb-3"
        @click:close="placeResult = null"
      >
        Placed {{ placeResult.placed }} bet(s).
        <span v-if="placeResult.failed"> {{ placeResult.failed }} failed.</span>
      </v-alert>

      <!-- Search & filters bar -->
      <div class="d-flex align-center mb-2 ga-2">
        <v-text-field
          v-model="betSearch"
          label="Search events..."
          density="compact"
          variant="outlined"
          hide-details
          clearable
          prepend-inner-icon="mdi-magnify"
          style="max-width: 320px;"
        />
        <v-btn-toggle v-model="dateFilter" mandatory density="compact" variant="outlined" divided color="deep-purple">
          <v-btn value="week" size="small">Week</v-btn>
          <v-btn value="month" size="small">Month</v-btn>
          <v-btn value="quarter" size="small">Quarter</v-btn>
          <v-btn value="all" size="small">All</v-btn>
        </v-btn-toggle>
        <div class="text-caption text-medium-emphasis ml-2">
          {{ displayBets.length }} / {{ currentSession.bets.length }} bets
        </div>
      </div>

      <!-- Bets table (plain HTML for performance with 1000+ rows) -->
      <div class="ai-betting-table-wrap">
        <table class="ai-betting-table">
          <thead>
            <tr>
              <th style="width:36px">
                <input type="checkbox" :checked="allSelected" :indeterminate.prop="someSelected && !allSelected" @change="toggleAll($event.target.checked)" />
              </th>
              <th style="width:40px" class="sortable" @click="setSort('number')"># <span v-if="sortKey==='number'">{{ sortAsc ? '\u25B2' : '\u25BC' }}</span></th>
              <th class="sortable" @click="setSort('event_title')">Event <span v-if="sortKey==='event_title'">{{ sortAsc ? '\u25B2' : '\u25BC' }}</span></th>
              <th class="sortable" @click="setSort('market_question')">Bet <span v-if="sortKey==='market_question'">{{ sortAsc ? '\u25B2' : '\u25BC' }}</span></th>
              <th class="text-center sortable" style="width:80px" @click="setSort('end_date')">Ends <span v-if="sortKey==='end_date'">{{ sortAsc ? '\u25B2' : '\u25BC' }}</span></th>
              <th class="text-center" style="width:60px">Side</th>
              <th class="text-center sortable" style="width:80px" @click="setSort('odds')">Odds <span v-if="sortKey==='odds'">{{ sortAsc ? '\u25B2' : '\u25BC' }}</span></th>
              <th class="text-center sortable" style="width:44px" @click="setSort('agent_rating')">R <span v-if="sortKey==='agent_rating'">{{ sortAsc ? '\u25B2' : '\u25BC' }}</span></th>
              <th style="width:80px">Amt</th>
              <th class="text-right sortable" style="width:90px" @click="setSort('expected_payout')">Payout <span v-if="sortKey==='expected_payout'">{{ sortAsc ? '\u25B2' : '\u25BC' }}</span></th>
              <th style="width:44px"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="bet in displayBets" :key="bet.number">
              <tr :class="betRowClass(bet)">
                <td><input type="checkbox" v-model="bet.selected" :disabled="bet.placed" @change="saveSession" /></td>
                <td class="num">{{ bet.number }}</td>
                <td class="ev" :title="bet.event_title">
                  <span :class="{ strike: bet.agent_verdict === 'red' }">{{ bet.event_title }}</span>
                </td>
                <td class="mq" :title="bet.market_question">
                  <span :class="{ strike: bet.agent_verdict === 'red' }">{{ bet.market_question }}</span>
                </td>
                <td class="text-center text-caption">
                  <span v-if="bet.end_date">{{ shortDate(bet.end_date) }}</span>
                  <span v-else class="text-medium-emphasis">—</span>
                </td>
                <td class="text-center">
                  <span class="side-chip" :class="bet.side === 'YES' ? 'side-yes' : 'side-no'">{{ bet.side }}</span>
                </td>
                <td class="text-center">
                  <div>{{ (bet.odds * 100).toFixed(1) }}%</div>
                  <div class="mul">x{{ bet.payout_multiplier }}</div>
                </td>
                <td class="text-center">
                  <span v-if="bet.agent_rating" class="rating-badge" :class="'c-' + (bet.agent_verdict || 'grey')">{{ bet.agent_rating }}</span>
                </td>
                <td>
                  <input type="number" v-model.number="bet.amount" min="0.1" step="0.5" class="amt-input" :disabled="bet.placed" @change="updateBetPayout(bet)" />
                </td>
                <td class="text-right payout" :class="{ 'text-green': bet.expected_payout > 10 }">
                  <span v-if="bet.placed" class="placed-badge">PLACED</span>
                  <span v-else>${{ bet.expected_payout.toFixed(2) }}</span>
                </td>
                <td class="text-center">
                  <button
                    v-if="!bet.placed"
                    class="place-single-btn"
                    :disabled="bet._placing"
                    :title="'Place this bet ($' + (bet.amount || 0) + ')'"
                    @click="requestPlaceSingle(bet)"
                  >{{ bet._placing ? '...' : '$' }}</button>
                </td>
              </tr>
              <tr v-if="bet.agent_reasoning" class="reasoning-row">
                <td></td>
                <td colspan="10" class="reasoning-cell">
                  <span class="reasoning-icon" :class="'c-' + (bet.agent_verdict || 'grey')">{{ bet.agent_verdict === 'green' ? '\u2713' : bet.agent_verdict === 'red' ? '\u2717' : '?' }}</span>
                  <span class="reasoning-text" :class="'c-' + (bet.agent_verdict || 'grey')">{{ bet.agent_reasoning }}</span>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      </div> <!-- end bets tab -->

      <!-- Thinking Logs Tab -->
      <div v-if="sessionTab === 'thinking_logs'">
        <div class="d-flex align-center mb-3">
          <div class="text-subtitle-2 text-medium-emphasis">Analysis Thinking Logs</div>
          <v-spacer />
          <v-btn variant="text" size="x-small" prepend-icon="mdi-refresh" @click="loadAnalysisLogs" :loading="logsLoading">Reload</v-btn>
        </div>

        <div v-if="!analysisLogs.length && !logsLoading" class="text-center text-medium-emphasis py-8">
          <v-icon size="48" class="mb-2">mdi-brain</v-icon>
          <div>No analysis logs yet. Run "Analyze" to generate thinking logs.</div>
        </div>

        <!-- Log list -->
        <v-card v-for="(log, idx) in analysisLogs" :key="idx" variant="outlined" class="mb-3">
          <v-card-text class="py-2">
            <div class="d-flex align-center ga-2 flex-wrap">
              <v-chip size="x-small" color="deep-purple" variant="tonal">#{{ analysisLogs.length - idx }}</v-chip>
              <v-chip v-if="log.status === 'error'" size="x-small" color="red" variant="flat">ERROR</v-chip>
              <span class="text-caption text-medium-emphasis">{{ formatDate(log.created_at) }}</span>
              <span class="text-caption">&middot; {{ log.bets_analyzed }} bets analyzed</span>
              <template v-if="log.verdicts_summary">
                <v-chip size="x-small" color="green" variant="tonal">{{ log.verdicts_summary?.green || 0 }} green</v-chip>
                <v-chip size="x-small" color="amber" variant="tonal">{{ log.verdicts_summary?.yellow || 0 }} yellow</v-chip>
                <v-chip size="x-small" color="red" variant="tonal">{{ log.verdicts_summary?.red || 0 }} red</v-chip>
              </template>
              <span v-if="log.error" class="text-caption text-red">{{ log.error }}</span>
              <v-spacer />
              <v-btn size="x-small" variant="tonal" color="deep-purple" @click="toggleLogDetail(log)" :loading="log._loading">
                {{ log._expanded ? 'Hide' : 'Details' }}
              </v-btn>
            </div>

            <!-- Expanded detail -->
            <div v-if="log._expanded && log._detail" class="mt-3">
              <div class="d-flex ga-4 flex-wrap mb-2">
                <div class="text-caption"><b>Status:</b> {{ log._detail.status }}</div>
                <div class="text-caption"><b>Model:</b> {{ log._detail.model_name || '—' }}</div>
                <div class="text-caption"><b>Duration:</b> {{ (log._detail.total_duration_ms / 1000).toFixed(1) }}s</div>
                <div class="text-caption"><b>Tokens:</b> {{ log._detail.total_tokens?.toLocaleString() }}</div>
              </div>

              <!-- Steps -->
              <div v-if="log._detail.steps?.length" class="mt-2">
                <div class="text-caption font-weight-bold mb-1">Steps:</div>
                <div v-for="step in log._detail.steps" :key="step.id" class="step-row mb-2">
                  <div class="d-flex align-center ga-2">
                    <v-chip size="x-small" :color="step.status === 'completed' ? 'green' : step.status === 'error' ? 'red' : 'grey'" variant="tonal">
                      {{ step.step_type }}
                    </v-chip>
                    <span class="text-caption">{{ step.step_name }}</span>
                    <span class="text-caption text-medium-emphasis">{{ step.duration_ms }}ms</span>
                  </div>
                  <div v-if="step.output_data?.response" class="thinking-output mt-1">
                    <pre class="text-caption">{{ typeof step.output_data.response === 'string' ? step.output_data.response.substring(0, 2000) : JSON.stringify(step.output_data.response, null, 2).substring(0, 2000) }}</pre>
                  </div>
                  <div v-if="step.output_data?.content" class="thinking-output mt-1">
                    <pre class="text-caption">{{ typeof step.output_data.content === 'string' ? step.output_data.content.substring(0, 2000) : JSON.stringify(step.output_data.content, null, 2).substring(0, 2000) }}</pre>
                  </div>
                  <div v-if="step.error_message" class="text-caption text-red mt-1">{{ step.error_message }}</div>
                </div>
              </div>

              <!-- Agent output -->
              <div v-if="log._detail.agent_output" class="mt-2">
                <div class="text-caption font-weight-bold mb-1">Agent Output:</div>
                <div class="thinking-output"><pre class="text-caption">{{ log._detail.agent_output }}</pre></div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </div>

      <!-- Rejected Bets Tab -->
      <div v-if="sessionTab === 'rejected'">
        <div class="d-flex align-center mb-3">
          <div class="text-subtitle-2 text-medium-emphasis">Rejected Bets (agent rated red)</div>
          <v-spacer />
          <v-btn variant="text" size="x-small" prepend-icon="mdi-refresh" @click="loadRejectedGlobal" :loading="rejectedLoading">Reload Global</v-btn>
        </div>

        <!-- Session rejected bets -->
        <div v-if="!rejectedBets.length && !rejectedGlobal.length" class="text-center text-medium-emphasis py-8">
          <v-icon size="48" class="mb-2">mdi-cancel</v-icon>
          <div>No rejected bets yet. Run "Analyze" to have the agent filter out bad bets.</div>
        </div>

        <!-- Session rejected -->
        <div v-if="rejectedBets.length" class="mb-4">
          <div class="text-caption font-weight-bold mb-2">This Session ({{ rejectedBets.length }})</div>
          <v-table density="compact" class="rejected-table">
            <thead>
              <tr>
                <th style="width:40px">#</th>
                <th>Event</th>
                <th>Question</th>
                <th style="width:55px">Side</th>
                <th style="width:55px">x</th>
                <th style="width:45px">R</th>
                <th style="width:90px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="bet in rejectedBets" :key="bet.number">
                <td class="text-caption">{{ bet.number }}</td>
                <td class="text-caption" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="bet.event_title">{{ bet.event_title }}</td>
                <td class="text-caption" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="bet.market_question">{{ bet.market_question }}</td>
                <td class="text-caption">{{ bet.side }}</td>
                <td class="text-caption font-weight-bold">{{ bet.payout_multiplier }}x</td>
                <td>
                  <span class="rating-badge" :class="'c-' + (bet.agent_verdict || 'grey')">{{ bet.agent_rating ?? '—' }}</span>
                </td>
                <td>
                  <v-btn size="x-small" color="amber" variant="tonal" prepend-icon="mdi-lock-open-variant" @click="unblockBet(bet)" :loading="bet._unblocking">
                    Unblock
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>

        <!-- Global rejected -->
        <div v-if="rejectedGlobal.length" class="mb-4">
          <div class="text-caption font-weight-bold mb-2">Globally Rejected ({{ rejectedGlobal.length }}) — excluded from all future sessions</div>
          <v-table density="compact" class="rejected-table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Question</th>
                <th style="width:55px">Side</th>
                <th style="width:55px">x</th>
                <th style="width:90px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in rejectedGlobal" :key="item.token_id">
                <td class="text-caption" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="item.event_title">{{ item.event_title || '—' }}</td>
                <td class="text-caption" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="item.market_question">{{ item.market_question || '—' }}</td>
                <td class="text-caption">{{ item.side || '—' }}</td>
                <td class="text-caption font-weight-bold">{{ item.payout_multiplier ? item.payout_multiplier + 'x' : '—' }}</td>
                <td>
                  <v-btn size="x-small" color="amber" variant="tonal" prepend-icon="mdi-lock-open-variant" @click="unblockGlobal(item)" :loading="item._unblocking">
                    Unblock
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </div>

    </div>

    <!-- Delete Confirmation Dialog -->
    <v-dialog v-model="deleteDialog" max-width="420" persistent>
      <v-card>
        <v-card-title class="text-h6">Delete Session</v-card-title>
        <v-card-text>
          <div class="mb-3">Are you sure you want to delete this session? This action cannot be undone.</div>
          <div class="text-caption text-medium-emphasis mb-2">Type <b>CONFIRM</b> to proceed:</div>
          <v-text-field
            v-model="deleteConfirmText"
            density="compact"
            variant="outlined"
            placeholder="CONFIRM"
            hide-details
            autofocus
            @keydown.enter="confirmDelete"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="cancelDelete">Cancel</v-btn>
          <v-btn color="red" variant="flat" :disabled="deleteConfirmText !== 'CONFIRM'" @click="confirmDelete">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Place All Bets Confirmation Dialog -->
    <v-dialog v-model="placeAllDialog" max-width="420" persistent>
      <v-card>
        <v-card-title class="text-h6">Place {{ selectedBets.length }} Bet{{ selectedBets.length !== 1 ? 's' : '' }}</v-card-title>
        <v-card-text>
          <div class="mb-3">
            You are about to place <b>{{ selectedBets.length }}</b> bet(s) totaling <b>${{ totalBet.toFixed(2) }}</b>.
            This will send real orders to Polymarket.
          </div>
          <div class="text-caption text-medium-emphasis mb-2">Type <b>CONFIRM</b> to proceed:</div>
          <v-text-field
            v-model="placeConfirmText"
            density="compact"
            variant="outlined"
            placeholder="CONFIRM"
            hide-details
            autofocus
            @keydown.enter="confirmPlaceAll"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="placeAllDialog = false; placeConfirmText = ''">Cancel</v-btn>
          <v-btn color="green" variant="flat" :disabled="placeConfirmText !== 'CONFIRM'" @click="confirmPlaceAll">Place Bets</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Place Single Bet Confirmation Dialog -->
    <v-dialog v-model="placeSingleDialog" max-width="420" persistent>
      <v-card>
        <v-card-title class="text-h6">Place Single Bet</v-card-title>
        <v-card-text>
          <div v-if="placeSingleTarget" class="mb-3">
            <div class="mb-1"><b>#{{ placeSingleTarget.number }}</b> {{ placeSingleTarget.event_title }}</div>
            <div class="text-caption text-medium-emphasis">{{ placeSingleTarget.market_question }} &middot; {{ placeSingleTarget.side }} &middot; ${{ placeSingleTarget.amount }}</div>
          </div>
          <div class="text-caption text-medium-emphasis mb-2">Type <b>CONFIRM</b> to place this bet:</div>
          <v-text-field
            v-model="placeConfirmText"
            density="compact"
            variant="outlined"
            placeholder="CONFIRM"
            hide-details
            autofocus
            @keydown.enter="confirmPlaceSingle"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="placeSingleDialog = false; placeConfirmText = ''; placeSingleTarget = null">Cancel</v-btn>
          <v-btn color="green" variant="flat" :disabled="placeConfirmText !== 'CONFIRM'" @click="confirmPlaceSingle">Place Bet</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject } from 'vue'
import api from '@src/api'

const props = defineProps({
  configured: Boolean,
})

const showSnackbar = inject('showSnackbar')

// ─── State ───
const activeStrategy = ref('rare_events_micro')
const selectedAgentId = ref(localStorage.getItem('ai_betting_agent_id') || null)
const defaultAmount = ref(parseFloat(localStorage.getItem('ai_betting_default_amount')) || 1)
const maxOdds = ref(parseFloat(localStorage.getItem('ai_betting_max_odds')) || 0.35)
const minMultiplier = ref(parseFloat(localStorage.getItem('ai_betting_min_multiplier')) || 2.5)
const analyzing = ref(false)
const placing = ref(false)
const agentAnalyzing = ref(false)
const agentAnalyzeResult = ref(null)
const placeResult = ref(null)
const agentItems = ref([])
const agentsLoading = ref(false)
const pastSessions = ref([])
const sessionsLoading = ref(false)
const currentSession = ref(null)
const sessionDefaultAmount = ref(1)
const sessionMinMultiplier = ref(2.5)
const totalBudget = ref(parseFloat(localStorage.getItem('ai_betting_budget')) || 100)
const betSearch = ref('')
const sortKey = ref('')
const sortAsc = ref(true)
const dateFilter = ref('week')  // week, month, quarter, all
const sessionTab = ref('bets')
const analysisLogs = ref([])
const logsLoading = ref(false)
const deleteDialog = ref(false)
const deleteConfirmText = ref('')
const deleteTargetId = ref(null)
const placeAllDialog = ref(false)
const placeSingleDialog = ref(false)
const placeConfirmText = ref('')
const placeSingleTarget = ref(null)
const agentReasoningLoading = ref(false)
const rejectedGlobal = ref([])
const rejectedLoading = ref(false)

const STORAGE_KEY = 'ai_betting_current_session'

// ─── Computed ───
const filteredBets = computed(() => {
  if (!currentSession.value) return []
  const minMul = sessionMinMultiplier.value || 1
  let bets = currentSession.value.bets.filter(b => (b.payout_multiplier || 0) >= minMul && !b.rejected)

  // Date filter
  if (dateFilter.value !== 'all') {
    const now = new Date()
    let cutoff = new Date()
    if (dateFilter.value === 'week') cutoff.setDate(now.getDate() + 7)
    else if (dateFilter.value === 'month') cutoff.setMonth(now.getMonth() + 1)
    else if (dateFilter.value === 'quarter') cutoff.setMonth(now.getMonth() + 3)
    bets = bets.filter(b => {
      if (!b.end_date) return true  // keep bets without end_date
      return new Date(b.end_date) <= cutoff
    })
  }

  const q = (betSearch.value || '').toLowerCase().trim()
  if (q) {
    bets = bets.filter(b =>
      (b.event_title || '').toLowerCase().includes(q) ||
      (b.market_question || '').toLowerCase().includes(q)
    )
  }
  return bets
})

// Bets available for analysis (not yet placed)
const analyzableBets = computed(() => {
  return filteredBets.value.filter(b => !b.placed)
})

// Bets rejected by agent (red verdict)
const rejectedBets = computed(() => {
  if (!currentSession.value) return []
  return currentSession.value.bets.filter(b => b.rejected)
})

const displayBets = computed(() => {
  const bets = filteredBets.value
  if (!sortKey.value) return bets
  const key = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  return [...bets].sort((a, b) => {
    const av = a[key] ?? ''
    const bv = b[key] ?? ''
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
    return String(av).localeCompare(String(bv)) * dir
  })
})

const selectedBets = computed(() => {
  return filteredBets.value.filter(b => b.selected && !b.placed)
})

const allSelected = computed(() => {
  const selectable = filteredBets.value.filter(b => !b.placed)
  if (!selectable.length) return false
  return selectable.every(b => b.selected)
})

const someSelected = computed(() => {
  const selectable = filteredBets.value.filter(b => !b.placed)
  if (!selectable.length) return false
  return selectable.some(b => b.selected)
})

const totalBet = computed(() => {
  return selectedBets.value.reduce((s, b) => s + (b.amount || 0), 0)
})

const totalPayout = computed(() => {
  return selectedBets.value.reduce((s, b) => s + (b.expected_payout || 0), 0)
})

const maxBetsForBudget = computed(() => {
  const betAmt = sessionDefaultAmount.value || 1
  return Math.floor((totalBudget.value || 100) / betAmt)
})

const minWinsToBreakEven = computed(() => {
  const sel = selectedBets.value
  if (!sel.length) return 0
  const total = totalBet.value
  if (total <= 0) return 0
  // Sort by highest payout first — what's the fewest wins needed
  const sorted = [...sel].sort((a, b) => b.expected_payout - a.expected_payout)
  let sum = 0
  for (let i = 0; i < sorted.length; i++) {
    sum += sorted[i].expected_payout
    if (sum >= total) return i + 1
  }
  return sorted.length
})

// ─── Watchers ───
watch(selectedAgentId, (v) => localStorage.setItem('ai_betting_agent_id', v || ''))
watch(defaultAmount, (v) => localStorage.setItem('ai_betting_default_amount', String(v)))
watch(maxOdds, (v) => localStorage.setItem('ai_betting_max_odds', String(v)))
watch(minMultiplier, (v) => localStorage.setItem('ai_betting_min_multiplier', String(v)))
watch(totalBudget, (v) => localStorage.setItem('ai_betting_budget', String(v)))
watch(sessionTab, (v) => {
  if (v === 'rejected') loadRejectedGlobal()
})

function setSort(key) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = true
  }
}
watch(sessionMinMultiplier, (v) => {
  if (currentSession.value) currentSession.value.min_multiplier = v
  saveSession()
})
watch(sessionDefaultAmount, (v) => {
  if (currentSession.value) currentSession.value.default_amount = v
  saveSession()
})

// ─── Methods ───
function strategyLabel(key) {
  const map = {
    rare_events_micro: 'Micro Bets: Rare Events',
  }
  return map[key] || key
}

function statusColor(status) {
  const map = { draft: 'grey', placed: 'green', partial: 'orange', failed: 'red' }
  return map[status] || 'grey'
}

function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function verdictColor(verdict) {
  const map = { green: 'green', yellow: 'amber', red: 'red' }
  return map[verdict] || 'grey'
}

function verdictIcon(verdict) {
  const map = { green: 'mdi-check-circle', yellow: 'mdi-help-circle', red: 'mdi-close-circle' }
  return map[verdict] || 'mdi-help-circle'
}

function betRowClass(bet) {
  if (bet.placed) return 'bet-placed'
  if (!bet.agent_verdict) return bet.selected ? '' : 'opacity-50'
  const cls = []
  if (bet.agent_verdict === 'green') cls.push('bg-green-darken-4')
  else if (bet.agent_verdict === 'yellow') cls.push('bg-amber-darken-4')
  else if (bet.agent_verdict === 'red') cls.push('bg-red-darken-4', 'opacity-60')
  if (!bet.selected) cls.push('opacity-50')
  return cls.join(' ')
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadAgents() {
  agentsLoading.value = true
  try {
    const { data } = await api.get('/agents')
    agentItems.value = (data || []).map(a => ({ id: a.id, name: a.name }))
  } catch (e) {
    console.error('Failed to load agents:', e)
  } finally {
    agentsLoading.value = false
  }
}

async function loadSessions() {
  sessionsLoading.value = true
  try {
    const { data } = await api.get('/addons/polymarket/ai-betting/sessions')
    pastSessions.value = data || []
  } catch (e) {
    console.error('Failed to load sessions:', e)
  } finally {
    sessionsLoading.value = false
  }
}

async function analyzeMarkets() {
  analyzing.value = true
  try {
    const { data } = await api.post('/addons/polymarket/ai-betting/analyze', {
      strategy: activeStrategy.value,
      agent_id: selectedAgentId.value,
      default_amount: defaultAmount.value,
      max_odds: maxOdds.value,
      min_multiplier: minMultiplier.value,
    })
    currentSession.value = data
    sessionDefaultAmount.value = data.default_amount || defaultAmount.value
    sessionMinMultiplier.value = minMultiplier.value
    saveToLocalStorage()
    showSnackbar(`Session created: ${data.total_bets} betting opportunities found`, 'success')
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    showSnackbar(`Analysis failed: ${msg}`, 'error')
  } finally {
    analyzing.value = false
  }
}

async function openSession(sessionId) {
  try {
    const { data } = await api.get(`/addons/polymarket/ai-betting/sessions/${sessionId}`)
    currentSession.value = data
    sessionDefaultAmount.value = data.default_amount || 1
    sessionMinMultiplier.value = data.min_multiplier || 2.5
    sessionTab.value = 'bets'
    saveToLocalStorage()
    loadAnalysisLogs()
  } catch (e) {
    showSnackbar('Failed to load session', 'error')
  }
}

async function agentAnalyze() {
  if (!currentSession.value) return
  const agentId = currentSession.value.agent_id || selectedAgentId.value
  if (!agentId) {
    showSnackbar('No agent selected for analysis', 'warning')
    return
  }
  agentAnalyzing.value = true
  agentAnalyzeResult.value = null
  try {
    // Send only non-placed filtered bets for analysis
    const betNumbers = analyzableBets.value.map(b => b.number)
    const { data } = await api.post(
      `/addons/polymarket/ai-betting/sessions/${currentSession.value.id}/agent-analyze`,
      {
        agent_id: agentId,
        bet_numbers: betNumbers,
        total_budget: totalBudget.value || 100,
        bet_amount: sessionDefaultAmount.value || 1,
        min_multiplier: sessionMinMultiplier.value || 2.5,
      },
      { timeout: 600000 }  // 10 minutes for LLM analysis
    )
    agentAnalyzeResult.value = data
    // Reload session to get updated verdicts
    const res = await api.get(`/addons/polymarket/ai-betting/sessions/${currentSession.value.id}`)
    currentSession.value = res.data
    saveToLocalStorage()
    showSnackbar(`Agent analyzed ${data.analyzed} bets: ${data.green} green, ${data.yellow} neutral, ${data.red} rejected`, 'success')
    // Reload thinking logs
    await loadAnalysisLogs()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    showSnackbar(`Agent analysis failed: ${msg}`, 'error')
  } finally {
    agentAnalyzing.value = false
  }
}

async function agentReasoning() {
  if (!currentSession.value) return
  const agentId = currentSession.value.agent_id || selectedAgentId.value
  if (!agentId) {
    showSnackbar('No agent selected', 'warning')
    return
  }
  agentReasoningLoading.value = true
  try {
    const { data } = await api.post(
      `/addons/polymarket/ai-betting/sessions/${currentSession.value.id}/agent-reasoning`,
      { agent_id: agentId },
      { timeout: 600000 }
    )
    // Reload session to get updated reasoning
    const res = await api.get(`/addons/polymarket/ai-betting/sessions/${currentSession.value.id}`)
    currentSession.value = res.data
    saveToLocalStorage()
    showSnackbar(`Reasoning added for ${data.reasoning_added} bets`, 'success')
    await loadAnalysisLogs()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    showSnackbar(`Reasoning failed: ${msg}`, 'error')
  } finally {
    agentReasoningLoading.value = false
  }
}

async function loadRejectedGlobal() {
  rejectedLoading.value = true
  try {
    const { data } = await api.get('/addons/polymarket/ai-betting/rejected-bets')
    rejectedGlobal.value = data.items || []
  } catch (e) {
    showSnackbar('Failed to load rejected bets', 'error')
  } finally {
    rejectedLoading.value = false
  }
}

async function unblockBet(bet) {
  if (!currentSession.value) return
  bet._unblocking = true
  try {
    await api.post(`/addons/polymarket/ai-betting/sessions/${currentSession.value.id}/unblock-bet/${bet.number}`)
    // Reload session
    const res = await api.get(`/addons/polymarket/ai-betting/sessions/${currentSession.value.id}`)
    currentSession.value = res.data
    saveToLocalStorage()
    showSnackbar(`Bet #${bet.number} unblocked`, 'success')
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    showSnackbar(`Unblock failed: ${msg}`, 'error')
  } finally {
    bet._unblocking = false
  }
}

async function unblockGlobal(item) {
  item._unblocking = true
  try {
    await api.delete(`/addons/polymarket/ai-betting/rejected-bets/${encodeURIComponent(item.token_id)}`)
    rejectedGlobal.value = rejectedGlobal.value.filter(r => r.token_id !== item.token_id)
    showSnackbar('Bet unblocked globally', 'success')
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    showSnackbar(`Unblock failed: ${msg}`, 'error')
  } finally {
    item._unblocking = false
  }
}

// ─── Thinking Logs ───
async function loadAnalysisLogs() {
  if (!currentSession.value) return
  logsLoading.value = true
  try {
    const { data } = await api.get(`/addons/polymarket/ai-betting/sessions/${currentSession.value.id}/thinking-logs`)
    // Preserve reactivity helpers
    analysisLogs.value = (data.items || data || []).map(log => ({
      ...log,
      _expanded: false,
      _loading: false,
      _detail: null,
    }))
  } catch (e) {
    console.error('Failed to load analysis logs', e)
  } finally {
    logsLoading.value = false
  }
}

async function toggleLogDetail(log) {
  if (log._expanded) {
    log._expanded = false
    return
  }
  if (log._detail) {
    log._expanded = true
    return
  }
  log._loading = true
  try {
    const { data } = await api.get(`/addons/polymarket/ai-betting/thinking-logs/${log.thinking_log_id}`)
    log._detail = data
    log._expanded = true
  } catch (e) {
    showSnackbar('Failed to load thinking log details', 'error')
  } finally {
    log._loading = false
  }
}

function requestDelete(sessionId) {
  deleteTargetId.value = sessionId
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

function cancelDelete() {
  deleteDialog.value = false
  deleteTargetId.value = null
  deleteConfirmText.value = ''
}

async function confirmDelete() {
  if (deleteConfirmText.value !== 'CONFIRM') return
  const sessionId = deleteTargetId.value
  deleteDialog.value = false
  deleteTargetId.value = null
  deleteConfirmText.value = ''
  try {
    await api.delete(`/addons/polymarket/ai-betting/sessions/${sessionId}`)
    pastSessions.value = pastSessions.value.filter(s => s.id !== sessionId)
    if (currentSession.value?.id === sessionId) {
      currentSession.value = null
      localStorage.removeItem(STORAGE_KEY)
    }
    showSnackbar('Session deleted', 'success')
  } catch (e) {
    showSnackbar('Failed to delete session', 'error')
  }
}

function exitSession() {
  currentSession.value = null
  localStorage.removeItem(STORAGE_KEY)
  loadSessions()
}

function toggleAll(val) {
  if (!currentSession.value) return
  filteredBets.value.forEach(b => {
    if (!b.placed) b.selected = !!val
  })
  saveSession()
}

function updateBetPayout(bet) {
  bet.expected_payout = Math.round((bet.amount || 0) * (bet.payout_multiplier || 0) * 100) / 100
  saveSession()
}

function applyDefaultAmount() {
  if (!currentSession.value) return
  currentSession.value.bets.forEach(b => {
    b.amount = sessionDefaultAmount.value
    b.expected_payout = Math.round(b.amount * (b.payout_multiplier || 0) * 100) / 100
  })
  saveSession()
}

function saveSession() {
  saveToLocalStorage()
  // Also persist to backend (debounced won't help here, just fire-and-forget)
  if (currentSession.value?.id) {
    api.patch(`/addons/polymarket/ai-betting/sessions/${currentSession.value.id}`, {
      bets: currentSession.value.bets,
      default_amount: sessionDefaultAmount.value,
      min_multiplier: sessionMinMultiplier.value,
    }).catch(() => {})
  }
}

function saveToLocalStorage() {
  if (currentSession.value) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(currentSession.value))
  }
}

function restoreFromLocalStorage() {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (raw) {
    try {
      currentSession.value = JSON.parse(raw)
      sessionDefaultAmount.value = currentSession.value.default_amount || 1
      sessionMinMultiplier.value = currentSession.value.min_multiplier || minMultiplier.value
      // Load thinking logs for restored session
      loadAnalysisLogs()
    } catch { /* ignore */ }
  }
}

async function placeSingleBet(bet) {
  if (!currentSession.value || bet.placed || bet._placing) return
  bet._placing = true
  try {
    const { data } = await api.post(
      `/addons/polymarket/ai-betting/sessions/${currentSession.value.id}/place-single/${bet.number}`
    )
    if (data.success) {
      bet.placed = true
      bet.selected = false
      saveToLocalStorage()
      showSnackbar(`Bet #${bet.number} placed successfully`, 'success')
    } else {
      showSnackbar(`Bet #${bet.number} failed: ${data.detail || 'Unknown error'}`, 'error')
    }
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    showSnackbar(`Failed to place bet #${bet.number}: ${msg}`, 'error')
  } finally {
    bet._placing = false
  }
}

function requestPlaceAll() {
  placeConfirmText.value = ''
  placeAllDialog.value = true
}

function confirmPlaceAll() {
  if (placeConfirmText.value !== 'CONFIRM') return
  placeAllDialog.value = false
  placeConfirmText.value = ''
  placeBets()
}

function requestPlaceSingle(bet) {
  placeSingleTarget.value = bet
  placeConfirmText.value = ''
  placeSingleDialog.value = true
}

function confirmPlaceSingle() {
  if (placeConfirmText.value !== 'CONFIRM') return
  const bet = placeSingleTarget.value
  placeSingleDialog.value = false
  placeConfirmText.value = ''
  placeSingleTarget.value = null
  if (bet) placeSingleBet(bet)
}

async function placeBets() {
  if (!currentSession.value) return
  placing.value = true
  placeResult.value = null
  try {
    const { data } = await api.post(
      `/addons/polymarket/ai-betting/sessions/${currentSession.value.id}/place`
    )
    placeResult.value = data
    // Mark successfully placed bets
    const placedNumbers = new Set(
      (data.results || []).filter(r => r.success).map(r => r.bet_number)
    )
    if (placedNumbers.size && currentSession.value) {
      currentSession.value.bets.forEach(b => {
        if (placedNumbers.has(b.number)) {
          b.placed = true
          b.selected = false
        }
      })
    }
    currentSession.value.status = data.failed === 0 ? 'placed' : 'partial'
    saveToLocalStorage()
    showSnackbar(
      `Placed ${data.placed} bet(s)${data.failed ? `, ${data.failed} failed` : ''}`,
      data.failed ? 'warning' : 'success'
    )
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    showSnackbar(`Failed to place bets: ${msg}`, 'error')
  } finally {
    placing.value = false
  }
}

// ─── Init ───
onMounted(() => {
  loadAgents()
  loadSessions()
  restoreFromLocalStorage()
})
</script>

<style scoped>
.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: rgba(255,255,255,0.8); }
.sortable span { font-size: 0.65rem; margin-left: 2px; }
.ai-betting-table-wrap {
  max-height: 70vh;
  overflow-y: auto;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 6px;
}
.ai-betting-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.ai-betting-table thead {
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
}
.ai-betting-table th {
  padding: 6px 8px;
  text-align: left;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(255,255,255,0.5);
  border-bottom: 1px solid rgba(255,255,255,0.1);
}
.ai-betting-table td {
  padding: 3px 8px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  white-space: nowrap;
}
.ai-betting-table tbody tr:hover {
  background: rgba(255,255,255,0.03);
}
.ai-betting-table input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #b388ff;
}
.num { color: rgba(255,255,255,0.4); }
.ev, .mq { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.strike { text-decoration: line-through; opacity: 0.5; }
.side-chip {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 700;
}
.side-yes { background: rgba(76,175,80,0.25); color: #81c784; }
.side-no { background: rgba(244,67,54,0.2); color: #ef9a9a; }
.mul { font-size: 0.7rem; color: rgba(255,255,255,0.35); }
.amt-input {
  width: 64px;
  padding: 2px 4px;
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font-size: 0.82rem;
  text-align: right;
}
.amt-input:focus { outline: 1px solid #b388ff; }
.payout { font-weight: 700; }
.text-green { color: #81c784 !important; }
.text-right { text-align: right; }
.text-center { text-align: center; }
.reasoning-row td { border-bottom: none !important; }
.reasoning-row + tr td { border-top: none !important; }
.reasoning-cell { padding: 0 8px 4px 8px !important; white-space: normal; }
.reasoning-icon { margin-right: 6px; font-weight: 700; }
.reasoning-text { font-size: 0.75rem; }
.c-green { color: #81c784; }
.c-amber, .c-yellow { color: #ffb74d; }
.c-red { color: #ef9a9a; }
.c-grey { color: rgba(255,255,255,0.4); }
.bg-green-darken-4 { background-color: rgba(46,125,50,0.15) !important; }
.bg-amber-darken-4 { background-color: rgba(255,160,0,0.10) !important; }
.bg-red-darken-4 { background-color: rgba(211,47,47,0.12) !important; }
.opacity-50 { opacity: 0.5; }
.opacity-60 { opacity: 0.6; }
.session-row { cursor: pointer; }
.bet-placed {
  opacity: 0.35;
  pointer-events: none;
  background: rgba(76,175,80,0.06) !important;
}
.bet-placed td { color: rgba(255,255,255,0.4) !important; }
.placed-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  background: rgba(76,175,80,0.25);
  color: #81c784;
  pointer-events: auto;
}
.place-single-btn {
  width: 28px;
  height: 22px;
  border: 1px solid rgba(76,175,80,0.4);
  border-radius: 4px;
  background: rgba(76,175,80,0.12);
  color: #81c784;
  font-size: 0.72rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}
.place-single-btn:hover {
  background: rgba(76,175,80,0.3);
  border-color: #81c784;
}
.place-single-btn:disabled {
  opacity: 0.4;
  cursor: wait;
}
.rating-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  min-width: 24px;
  text-align: center;
  border-radius: 4px;
  padding: 1px 4px;
  background: rgba(255,255,255,0.07);
}
.rating-badge.c-green { color: #81c784; }
.rating-badge.c-yellow { color: #ffd54f; }
.rating-badge.c-red { color: #ef9a9a; }
.rating-badge.c-grey { color: #999; }

/* Thinking Logs */
.thinking-output {
  background: rgba(0,0,0,0.2);
  border-radius: 4px;
  padding: 8px;
  max-height: 300px;
  overflow-y: auto;
}
.thinking-output pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
.step-row {
  border-left: 2px solid rgba(255,255,255,0.1);
  padding-left: 10px;
}
</style>
