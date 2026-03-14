<template>
  <div style="padding-bottom: 80px;">
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <v-icon size="32" color="teal-accent-3" class="mr-3">mdi-wallet-outline</v-icon>
      <div class="text-h4 font-weight-bold">Budgeting</div>
      <v-spacer />

      <!-- Month selector -->
      <v-btn icon="mdi-chevron-left" variant="text" size="small" @click="prevMonth" />
      <v-chip variant="tonal" color="teal" class="mx-1" style="min-width: 120px; justify-content: center">
        {{ formatMonthLabel(currentMonth) }}
      </v-chip>
      <v-btn icon="mdi-chevron-right" variant="text" size="small" @click="nextMonth" :disabled="currentMonth >= todayMonth" />
      <v-btn v-if="currentMonth !== todayMonth" variant="text" size="small" class="ml-1" @click="currentMonth = todayMonth">
        Today
      </v-btn>

      <v-btn color="teal" variant="tonal" prepend-icon="mdi-refresh" class="ml-4" @click="refreshAll" :loading="loading">
        Refresh
      </v-btn>
    </div>

    <!-- Summary chips -->
    <div class="d-flex flex-wrap ga-2 mb-4" v-if="summary">
      <v-chip variant="tonal" color="green" size="large">
        <v-icon start size="16">mdi-arrow-down</v-icon>
        Income: ${{ fmt(summary.total_income) }}
      </v-chip>
      <v-chip variant="tonal" color="red" size="large">
        <v-icon start size="16">mdi-arrow-up</v-icon>
        Expenses: ${{ fmt(summary.total_expense) }}
      </v-chip>
      <v-chip variant="tonal" :color="summary.balance >= 0 ? 'green' : 'red'" size="large">
        <v-icon start size="16">mdi-scale-balance</v-icon>
        Balance: ${{ fmt(summary.balance) }}
      </v-chip>
      <v-chip variant="tonal" color="orange" size="large" v-if="summary.min_daily_earnings > 0">
        <v-icon start size="16">mdi-calendar-clock</v-icon>
        Min ${{ fmt(summary.min_daily_earnings) }}/day ({{ summary.remaining_days }}d left)
      </v-chip>
      <v-chip variant="tonal" color="cyan" size="large" v-if="availableCash > 0">
        <v-icon start size="16">mdi-cash</v-icon>
        Cash: ${{ fmt(availableCash) }}
      </v-chip>
      <v-chip variant="tonal" color="purple" size="large" v-if="summary.total_loan_payments > 0">
        <v-icon start size="16">mdi-bank</v-icon>
        Loan Payments: ${{ fmt(summary.total_loan_payments) }}/mo
      </v-chip>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="teal-accent-3" class="mb-4">
      <v-tab value="budget">
        <v-icon start>mdi-cash-register</v-icon>
        Budget
      </v-tab>
      <v-tab value="calendar">
        <v-icon start>mdi-calendar-month</v-icon>
        Calendar
      </v-tab>
      <v-tab value="settings">
        <v-icon start>mdi-cog</v-icon>
        Settings
      </v-tab>
    </v-tabs>

    <!-- ═══════ BUDGET TAB ═══════ -->
    <v-window v-model="activeTab">
      <v-window-item value="budget">
        <v-row>
          <!-- LEFT: Income -->
          <v-col cols="12" md="4">
            <v-card variant="outlined" class="pa-3">
              <div class="d-flex align-center mb-3">
                <v-icon color="green" class="mr-2">mdi-arrow-down-bold</v-icon>
                <span class="text-h6">Income</span>
                <v-spacer />
                <span class="text-h6 text-green">${{ fmt(totalIncome) }}</span>
              </div>

              <div v-if="incomeEntries.length === 0" class="text-center text-medium-emphasis py-4">
                No income entries yet
              </div>

              <v-list density="compact" class="bg-transparent">
                <v-list-item
                  v-for="item in incomeEntries"
                  :key="item.id"
                  class="px-0 rounded mb-1"
                  :class="entryBgClass(item, 'green')"
                >
                  <template #prepend>
                    <v-checkbox-btn
                      :model-value="item.is_paid"
                      color="green"
                      density="compact"
                      @update:model-value="togglePaid(item)"
                    />
                  </template>
                  <v-list-item-title :class="item.is_paid ? 'text-decoration-line-through text-medium-emphasis' : ''">
                    {{ item.name }}
                    <v-chip v-if="item.day_of_month" size="x-small" color="teal" variant="tonal" class="ml-1">{{ item.day_of_month }}th</v-chip>
                    <v-chip v-if="item.frequency === 'daily'" size="x-small" color="blue" variant="tonal" class="ml-1">Daily</v-chip>
                    <v-chip v-else-if="item.frequency === 'weekly'" size="x-small" color="indigo" variant="tonal" class="ml-1">Weekly</v-chip>
                  </v-list-item-title>
                  <v-list-item-subtitle>
                    <v-chip size="x-small" variant="text" class="px-0">{{ item.category || 'No category' }}</v-chip>
                    <v-icon v-if="item.is_recurring" size="12" class="ml-1" title="Recurring">mdi-repeat</v-icon>
                  </v-list-item-subtitle>
                  <template #append>
                    <span class="text-green font-weight-bold mr-2">
                      ${{ fmt(item.amount) }}
                      <span v-if="item.frequency === 'daily'" class="text-caption text-blue">/day</span>
                      <span v-else-if="item.frequency === 'weekly'" class="text-caption text-indigo">/wk</span>
                    </span>
                    <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="openEditEntry(item)" />
                    <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="confirmDeleteEntry(item)" />
                  </template>
                </v-list-item>
              </v-list>

              <v-btn block variant="tonal" color="green" class="mt-2" prepend-icon="mdi-plus" @click="openAddEntry('income')">
                Add Income
              </v-btn>
            </v-card>
          </v-col>

          <!-- CENTER: Expenses -->
          <v-col cols="12" md="4">
            <v-card variant="outlined" class="pa-3">
              <div class="d-flex align-center mb-3">
                <v-icon color="red" class="mr-2">mdi-arrow-up-bold</v-icon>
                <span class="text-h6">Expenses</span>
                <span v-if="summary && summary.unpaid_expense > 0" class="text-caption text-orange ml-2">(unpaid: ${{ fmt(summary.unpaid_expense) }})</span>
                <v-spacer />
                <v-btn
                  :icon="expensesCollapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
                  size="x-small"
                  variant="text"
                  @click="expensesCollapsed = !expensesCollapsed"
                  class="mr-1"
                />
                <span class="text-h6 text-red">${{ fmt(totalExpenseWithLoans) }}</span>
              </div>

              <div v-if="expenseEntries.length === 0" class="text-center text-medium-emphasis py-4">
                No expense entries yet
              </div>

              <v-list density="compact" class="bg-transparent">
                <v-list-item
                  v-for="item in (expensesCollapsed ? expenseEntries.filter(e => !e.is_paid) : expenseEntries)"
                  :key="item.id"
                  class="px-0 rounded mb-1"
                  :class="entryBgClass(item, 'red')"
                >
                  <template #prepend>
                    <v-checkbox-btn
                      :model-value="item.is_paid"
                      color="red"
                      density="compact"
                      @update:model-value="togglePaid(item)"
                    />
                  </template>
                  <v-list-item-title :class="item.is_paid ? 'text-decoration-line-through text-medium-emphasis' : ''">
                    {{ item.name }}
                    <v-chip v-if="item.day_of_month" size="x-small" color="teal" variant="tonal" class="ml-1">{{ item.day_of_month }}th</v-chip>
                    <v-chip v-if="item.frequency === 'daily'" size="x-small" color="blue" variant="tonal" class="ml-1">Daily</v-chip>
                    <v-chip v-else-if="item.frequency === 'weekly'" size="x-small" color="indigo" variant="tonal" class="ml-1">Weekly</v-chip>
                  </v-list-item-title>
                  <v-list-item-subtitle>
                    <v-chip size="x-small" variant="text" class="px-0">{{ item.category || 'No category' }}</v-chip>
                    <v-icon v-if="item.is_recurring" size="12" class="ml-1" title="Recurring">mdi-repeat</v-icon>
                    <v-chip v-if="item.is_credit_card" size="x-small" color="orange" variant="tonal" class="ml-1">CC</v-chip>
                  </v-list-item-subtitle>
                  <template #append>
                    <span class="text-red font-weight-bold mr-2">
                      ${{ fmt(item.amount) }}
                      <span v-if="item.frequency === 'daily'" class="text-caption text-blue">/day</span>
                      <span v-else-if="item.frequency === 'weekly'" class="text-caption text-indigo">/wk</span>
                    </span>
                    <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="openEditEntry(item)" />
                    <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="confirmDeleteEntry(item)" />
                  </template>
                </v-list-item>
              </v-list>

              <v-btn block variant="tonal" color="red" class="mt-2" prepend-icon="mdi-plus" @click="openAddEntry('expense')">
                Add Expense
              </v-btn>

              <!-- Auto loan payments -->
              <div v-if="loans.length && (!expensesCollapsed || sortedLoans.some(l => !isLoanPaid(l)))" class="mt-3">
                <v-divider class="mb-2" />
                <div class="text-caption text-medium-emphasis mb-1">
                  <v-icon size="14" class="mr-1">mdi-bank</v-icon>
                  Loan Payments (auto)
                </div>
                <v-list density="compact" class="bg-transparent">
                  <v-list-item
                    v-for="loan in (expensesCollapsed ? sortedLoans.filter(l => !isLoanPaid(l)) : sortedLoans)"
                    :key="'loan-' + loan.id"
                    class="px-0 rounded mb-1"
                    :class="isLoanPaid(loan) ? 'bg-purple-darken-4' : ''"
                    style="opacity: 0.85"
                  >
                    <template #prepend>
                      <v-checkbox-btn
                        :model-value="isLoanPaid(loan)"
                        color="purple"
                        density="compact"
                        @update:model-value="toggleLoanPaid(loan)"
                      />
                    </template>
                    <v-list-item-title :class="isLoanPaid(loan) ? 'text-decoration-line-through text-medium-emphasis' : ''">
                      {{ loan.bank }}
                    </v-list-item-title>
                    <v-list-item-subtitle>
                      <v-chip size="x-small" variant="text" class="px-0">Loan Payment</v-chip>
                      <v-chip v-if="loan.payment_date" size="x-small" color="teal" variant="tonal" class="ml-1">{{ loan.payment_date }}th</v-chip>
                    </v-list-item-subtitle>
                    <template #append>
                      <span class="text-purple font-weight-bold">${{ fmt(loan.monthly_payment) }}</span>
                    </template>
                  </v-list-item>
                </v-list>
              </div>
            </v-card>
          </v-col>

          <!-- RIGHT: Summary by category -->
          <v-col cols="12" md="4">
            <v-card variant="outlined" class="pa-3 mb-4">
              <div class="d-flex align-center mb-3">
                <v-icon color="teal" class="mr-2">mdi-chart-pie</v-icon>
                <span class="text-h6">Summary</span>
              </div>

              <!-- Expense categories -->
              <div class="text-subtitle-2 text-medium-emphasis mb-1">Expenses by Category</div>
              <div v-if="summary && Object.keys(summary.expense_by_category).length">
                <div v-for="(amt, cat) in summary.expense_by_category" :key="'ec-' + cat" class="d-flex justify-space-between mb-1">
                  <span class="text-body-2">{{ cat }}</span>
                  <span class="text-body-2 font-weight-bold text-red">${{ fmt(amt) }}</span>
                </div>
                <v-divider class="my-2" />
                <div class="d-flex justify-space-between">
                  <span class="font-weight-bold">Total Expenses</span>
                  <span class="font-weight-bold text-red">${{ fmt(summary.total_expense) }}</span>
                </div>
              </div>
              <div v-else class="text-medium-emphasis text-body-2">No expenses yet</div>

              <v-divider class="my-3" />

              <!-- Income categories -->
              <div class="text-subtitle-2 text-medium-emphasis mb-1">Income by Category</div>
              <div v-if="summary && Object.keys(summary.income_by_category).length">
                <div v-for="(amt, cat) in summary.income_by_category" :key="'ic-' + cat" class="d-flex justify-space-between mb-1">
                  <span class="text-body-2">{{ cat }}</span>
                  <span class="text-body-2 font-weight-bold text-green">${{ fmt(amt) }}</span>
                </div>
                <v-divider class="my-2" />
                <div class="d-flex justify-space-between">
                  <span class="font-weight-bold">Total Income</span>
                  <span class="font-weight-bold text-green">${{ fmt(summary.total_income) }}</span>
                </div>
              </div>
              <div v-else class="text-medium-emphasis text-body-2">No income yet</div>

              <v-divider class="my-3" />

              <!-- Balance -->
              <div class="d-flex justify-space-between mb-2">
                <span class="text-h6">Balance</span>
                <span class="text-h6" :class="summary && summary.balance >= 0 ? 'text-green' : 'text-red'">
                  ${{ summary ? fmt(summary.balance) : '0.00' }}
                </span>
              </div>

              <!-- Available Cash -->
              <v-text-field
                v-model.number="availableCash"
                label="Available Cash"
                type="number"
                prefix="$"
                variant="outlined"
                density="compact"
                class="mt-2 mb-0"
                hide-details
                @change="loadSummary"
                hint="Cash on hand to offset required earnings"
              />

              <!-- Min daily earnings -->
              <v-alert
                v-if="summary && summary.min_daily_earnings > 0"
                density="compact"
                type="warning"
                variant="tonal"
                class="mt-2"
              >
                <div class="text-body-2">
                  Need to earn at least <strong>${{ fmt(summary.min_daily_earnings) }}/day</strong>
                  over the next {{ summary.remaining_days }} days to cover unpaid expenses.
                  <span v-if="availableCash > 0" class="text-medium-emphasis">(with ${{ fmt(availableCash) }} cash on hand)</span>
                </div>
              </v-alert>
            </v-card>

            <!-- Month transition -->
            <v-card variant="outlined" class="pa-3" v-if="!hasEntriesForMonth && currentMonth === todayMonth">
              <div class="text-subtitle-2 mb-2">New Month</div>
              <div class="text-body-2 text-medium-emphasis mb-3">
                No entries for {{ formatMonthLabel(currentMonth) }} yet. Copy recurring entries from last month?
              </div>
              <v-btn block variant="tonal" color="teal" prepend-icon="mdi-content-copy" @click="transitionMonth" :loading="transitionLoading">
                Copy Recurring Entries
              </v-btn>
            </v-card>
          </v-col>
        </v-row>

        <!-- ── Accounts & Loans at bottom ── -->
        <v-row class="mt-4">
          <v-col cols="12" md="6">
            <v-card variant="outlined">
              <v-card-title class="d-flex align-center">
                <v-icon class="mr-2">mdi-bank</v-icon>
                Accounts
                <v-spacer />
                <span class="text-subtitle-1 mr-3" :class="totalAccountBalance >= 0 ? 'text-green' : 'text-red'">
                  ${{ fmt(totalAccountBalance) }}
                </span>
                <v-btn color="teal" variant="tonal" prepend-icon="mdi-plus" size="x-small" @click="openAddAccount">
                  Add
                </v-btn>
              </v-card-title>
              <v-table density="compact" v-if="accounts.length">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Purpose</th>
                    <th>Balance</th>
                    <th>Pay Day</th>
                    <th style="width: 80px"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="acc in accounts" :key="acc.id">
                    <td class="font-weight-bold">{{ acc.name }}</td>
                    <td class="text-medium-emphasis">{{ acc.purpose || '—' }}</td>
                    <td :class="acc.balance >= 0 ? 'text-green' : 'text-red'" class="font-weight-bold">
                      ${{ fmt(acc.balance) }}
                    </td>
                    <td>{{ acc.payment_date ? acc.payment_date : '—' }}</td>
                    <td>
                      <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="openEditAccount(acc)" />
                      <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="confirmDeleteAccount(acc)" />
                    </td>
                  </tr>
                </tbody>
              </v-table>
              <v-card-text v-else class="text-center text-medium-emphasis py-3 text-body-2">
                No accounts yet
              </v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="6">
            <v-card variant="outlined">
              <v-card-title class="d-flex align-center">
                <v-icon class="mr-2">mdi-credit-card-clock</v-icon>
                Loans & Credits
                <v-spacer />
                <span class="text-subtitle-1 text-red mr-3">
                  ${{ fmt(totalDebt) }}
                </span>
                <v-btn color="teal" variant="tonal" prepend-icon="mdi-plus" size="x-small" @click="openAddLoan">
                  Add
                </v-btn>
              </v-card-title>
              <v-table density="compact" v-if="loans.length">
                <thead>
                  <tr>
                    <th>Bank / Lender</th>
                    <th>Purpose</th>
                    <th>Debt</th>
                    <th>Limit</th>
                    <th>Monthly</th>
                    <th>Remaining</th>
                    <th>Pay Day</th>
                    <th style="width: 80px"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="loan in sortedLoans" :key="loan.id">
                    <td class="font-weight-bold">{{ loan.bank }}</td>
                    <td class="text-medium-emphasis">{{ loan.purpose || '—' }}</td>
                    <td class="text-red font-weight-bold">${{ fmt(loan.remaining_debt) }}</td>
                    <td>{{ loan.credit_limit ? '$' + fmt(loan.credit_limit) : '—' }}</td>
                    <td class="text-orange font-weight-bold">${{ fmt(loan.monthly_payment) }}</td>
                    <td>
                      <v-chip v-if="loan.monthly_payment > 0" size="x-small" color="teal" variant="tonal">
                        {{ Math.ceil(loan.remaining_debt / loan.monthly_payment) }} mo
                      </v-chip>
                      <span v-else>—</span>
                    </td>
                    <td>{{ loan.payment_date ? loan.payment_date : '—' }}</td>
                    <td>
                      <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="openEditLoan(loan)" />
                      <v-btn icon="mdi-delete" size="x-small" variant="text" color="red" @click="confirmDeleteLoan(loan)" />
                    </td>
                  </tr>
                </tbody>
              </v-table>
              <v-card-text v-else class="text-center text-medium-emphasis py-3 text-body-2">
                No loans yet
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>

      <!-- ═══════ CALENDAR TAB ═══════ -->
      <v-window-item value="calendar">
        <v-card variant="outlined" class="pa-4">
          <div class="d-flex align-center mb-3">
            <v-icon color="teal" class="mr-2">mdi-calendar-month</v-icon>
            <span class="text-h6">{{ formatMonthLabel(currentMonth) }} Calendar</span>
            <v-spacer />
            <v-chip variant="tonal" color="blue" size="small" class="mr-2">
              Starting Balance: ${{ fmt(calendarData?.starting_balance || 0) }}
            </v-chip>
            <v-btn icon="mdi-minus" size="x-small" variant="tonal" class="mr-1" @click="calendarZoom = Math.max(0.6, calendarZoom - 0.15)" />
            <span class="text-caption mx-1">{{ Math.round(calendarZoom * 100) }}%</span>
            <v-btn icon="mdi-plus" size="x-small" variant="tonal" class="mr-3" @click="calendarZoom = Math.min(2, calendarZoom + 0.15)" />
            <v-btn variant="tonal" color="teal" size="small" prepend-icon="mdi-refresh" @click="loadCalendar" :loading="calendarLoading">
              Refresh
            </v-btn>
          </div>

          <!-- Weekday header -->
          <div class="calendar-grid mb-1">
            <div v-for="wd in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']" :key="wd"
              class="text-center text-caption font-weight-bold text-medium-emphasis pa-1">
              {{ wd }}
            </div>
          </div>

          <!-- Calendar grid -->
          <div class="calendar-grid" v-if="calendarData" :style="{ '--cal-zoom': calendarZoom }">
            <!-- Empty cells for offset -->
            <div v-for="n in calendarData.first_weekday" :key="'empty-' + n" class="calendar-cell empty"></div>

            <!-- Day cells -->
            <div
              v-for="dayInfo in calendarData.days"
              :key="dayInfo.day"
              class="calendar-cell"
              :class="{
                'today-cell': isToday(dayInfo.day),
                'has-items': dayInfo.items.length > 0,
              }"
            >
              <div class="d-flex justify-space-between align-center mb-1">
                <span class="text-caption font-weight-bold" :class="isToday(dayInfo.day) ? 'text-teal' : ''">
                  {{ dayInfo.day }}
                </span>
                <v-chip
                  v-if="dayInfo.income > 0 || dayInfo.expense > 0"
                  size="x-small"
                  :color="dayInfo.balance >= 0 ? 'green' : 'red'"
                  variant="tonal"
                  class="px-1"
                  style="height: calc(16px * var(--cal-zoom)); font-size: calc(9px * var(--cal-zoom));"
                >
                  ${{ fmtShort(dayInfo.balance) }}
                </v-chip>
              </div>

              <!-- Items in this day -->
              <div
                v-for="(item, idx) in dayInfo.items"
                :key="item.id + '-' + idx"
                class="calendar-item mb-0"
                :class="{
                  'calendar-item-paid': item.is_paid,
                  'calendar-item-daily': item.frequency === 'daily',
                  'calendar-item-weekly': item.frequency === 'weekly',
                }"
              >
                <div class="d-flex align-center" :style="{ fontSize: (10 * calendarZoom) + 'px', lineHeight: '1.2' }">
                  <v-icon
                    v-if="item.is_paid"
                    :size="Math.round(10 * calendarZoom)"
                    color="grey"
                    class="mr-1 flex-shrink-0"
                  >
                    mdi-check
                  </v-icon>
                  <v-icon
                    v-else
                    :size="Math.round(10 * calendarZoom)"
                    :color="item.type === 'income' ? 'green' : (item.source === 'loan' ? 'purple' : 'red')"
                    class="mr-1 flex-shrink-0"
                  >
                    {{ item.type === 'income' ? 'mdi-arrow-down' : (item.source === 'loan' ? 'mdi-bank-outline' : 'mdi-arrow-up') }}
                  </v-icon>
                  <span class="text-truncate" :class="item.is_paid ? 'text-decoration-line-through text-medium-emphasis' : ''" :style="{ maxWidth: (80 * calendarZoom) + 'px' }">{{ item.name }}</span>
                  <v-spacer />
                  <span
                    class="font-weight-bold flex-shrink-0"
                    :class="item.is_paid ? 'text-medium-emphasis text-decoration-line-through' : (item.type === 'income' ? 'text-green' : 'text-red')"
                    :style="{ fontSize: (9 * calendarZoom) + 'px' }"
                  >
                    ${{ fmtShort(item.amount) }}
                  </span>
                </div>
              </div>

              <!-- Day totals -->
              <div v-if="dayInfo.income > 0 || dayInfo.expense > 0" class="mt-1 pt-1" :style="{ borderTop: '1px solid rgba(255,255,255,0.05)', fontSize: (9 * calendarZoom) + 'px' }">
                <span v-if="dayInfo.income > 0" class="text-green mr-1">+${{ fmtShort(dayInfo.income) }}</span>
                <span v-if="dayInfo.expense > 0" class="text-red">-${{ fmtShort(dayInfo.expense) }}</span>
              </div>
            </div>
          </div>

          <div v-else class="text-center text-medium-emphasis py-8">
            <v-progress-circular v-if="calendarLoading" indeterminate color="teal" />
            <span v-else>No calendar data. Click Refresh to load.</span>
          </div>

          <!-- Unscheduled items -->
          <div v-if="calendarData?.unscheduled?.length" class="mt-4">
            <v-divider class="mb-3" />
            <div class="text-subtitle-2 mb-2">
              <v-icon size="16" class="mr-1">mdi-calendar-question</v-icon>
              Unscheduled Items (no day set)
            </div>
            <v-row>
              <v-col v-for="item in calendarData.unscheduled" :key="item.id" cols="12" sm="6" md="4" lg="3">
                <v-chip
                  :color="item.type === 'income' ? 'green' : (item.source === 'loan' ? 'purple' : 'red')"
                  variant="tonal"
                  size="small"
                  class="mr-1 mb-1"
                >
                  <v-icon start size="14">
                    {{ item.type === 'income' ? 'mdi-arrow-down' : 'mdi-arrow-up' }}
                  </v-icon>
                  {{ item.name }}: ${{ fmt(item.amount) }}
                </v-chip>
              </v-col>
            </v-row>
          </div>
        </v-card>
      </v-window-item>

      <!-- ═══════ SETTINGS TAB ═══════ -->
      <v-window-item value="settings">
        <v-row>
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="pa-4">
              <v-card-title>Budgeting Settings</v-card-title>
              <v-card-text>
                <p class="text-medium-emphasis mb-4">
                  The budgeting addon has no external configuration.
                  All data is stored locally in MongoDB.
                </p>
                <v-alert type="info" variant="tonal" density="compact">
                  Agents can read your budget using the <strong>budget_view</strong> skill
                  and add entries using the <strong>budget_add_entry</strong> skill.
                </v-alert>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>
    </v-window>

    <!-- ═══════ ADD/EDIT ENTRY DIALOG ═══════ -->
    <v-dialog v-model="entryDialog" max-width="500" persistent>
      <v-card>
        <v-card-title>{{ editingEntry ? 'Edit Entry' : (entryForm.type === 'income' ? 'Add Income' : 'Add Expense') }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="entryForm.name" label="Name" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model.number="entryForm.amount" label="Amount" type="number" prefix="$" variant="outlined" density="compact" class="mb-2" />
          <v-combobox
            v-model="entryForm.category"
            :items="entryForm.type === 'income' ? incomeCategoryOptions : expenseCategoryOptions"
            label="Category"
            variant="outlined"
            density="compact"
            class="mb-2"
            clearable
            prepend-inner-icon="mdi-tag-outline"
          />
          <div class="mb-3">
            <div class="text-caption text-medium-emphasis mb-1">Frequency</div>
            <v-btn-toggle v-model="entryForm.frequency" mandatory color="teal" density="compact" class="w-100">
              <v-btn value="once" size="small" class="flex-grow-1">One-time / Monthly</v-btn>
              <v-btn value="daily" size="small" class="flex-grow-1">Daily</v-btn>
              <v-btn value="weekly" size="small" class="flex-grow-1">Weekly</v-btn>
            </v-btn-toggle>
          </div>
          <v-text-field
            v-if="entryForm.frequency !== 'daily'"
            v-model.number="entryForm.day_of_month"
            :label="entryForm.frequency === 'weekly' ? 'Starting day of month (1-31)' : 'Day of month (1-31, optional)'"
            type="number"
            :min="1"
            :max="31"
            variant="outlined"
            density="compact"
            class="mb-2"
            clearable
            :hint="entryForm.frequency === 'weekly' ? 'First occurrence day, repeats every 7 days' : 'Which day this payment/income is expected'"
            persistent-hint
          />
          <v-switch v-model="entryForm.is_recurring" label="Recurring (monthly)" color="teal" density="compact" class="mb-2" />
          <v-switch v-model="entryForm.is_paid" :label="entryForm.type === 'income' ? 'Received' : 'Paid'" color="teal" density="compact" class="mb-2" />
          <v-switch v-if="entryForm.type === 'expense'" v-model="entryForm.is_credit_card" label="Credit Card payment" color="orange" density="compact" class="mb-2" />
          <v-textarea v-model="entryForm.notes" label="Notes" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="entryDialog = false">Cancel</v-btn>
          <v-btn color="teal" variant="flat" @click="saveEntry" :loading="entrySaving">
            {{ editingEntry ? 'Save' : 'Add' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ ADD/EDIT ACCOUNT DIALOG ═══════ -->
    <v-dialog v-model="accountDialog" max-width="500" persistent>
      <v-card>
        <v-card-title>{{ editingAccount ? 'Edit Account' : 'Add Account' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="accountForm.name" label="Account Name" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model="accountForm.purpose" label="Purpose (what it's for)" variant="outlined" density="compact" class="mb-2" placeholder="e.g. Everyday spending, Savings, Emergency fund" />
          <v-text-field v-model.number="accountForm.balance" label="Balance" type="number" prefix="$" variant="outlined" density="compact" class="mb-2" />
          <v-text-field
            v-model.number="accountForm.payment_date"
            label="Payment Date (day of month)"
            type="number"
            :min="1"
            :max="31"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-textarea v-model="accountForm.notes" label="Notes" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="accountDialog = false">Cancel</v-btn>
          <v-btn color="teal" variant="flat" @click="saveAccount" :loading="accountSaving">
            {{ editingAccount ? 'Save' : 'Add' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ ADD/EDIT LOAN DIALOG ═══════ -->
    <v-dialog v-model="loanDialog" max-width="500" persistent>
      <v-card>
        <v-card-title>{{ editingLoan ? 'Edit Loan' : 'Add Loan' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="loanForm.bank" label="Bank / Lender" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model="loanForm.purpose" label="Purpose (what it's for)" variant="outlined" density="compact" class="mb-2" placeholder="e.g. Car loan, Mortgage, Student loan" />
          <v-text-field v-model.number="loanForm.credit_limit" label="Credit Limit" type="number" prefix="$" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model.number="loanForm.remaining_debt" label="Remaining Debt" type="number" prefix="$" variant="outlined" density="compact" class="mb-2" />
          <v-text-field v-model.number="loanForm.monthly_payment" label="Monthly Payment" type="number" prefix="$" variant="outlined" density="compact" class="mb-2" />
          <v-text-field
            v-model.number="loanForm.payment_date"
            label="Payment Date (day of month)"
            type="number"
            :min="1"
            :max="31"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-textarea v-model="loanForm.notes" label="Notes" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="loanDialog = false">Cancel</v-btn>
          <v-btn color="teal" variant="flat" @click="saveLoan" :loading="loanSaving">
            {{ editingLoan ? 'Save' : 'Add' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════ DELETE CONFIRM ═══════ -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-red">Confirm Delete</v-card-title>
        <v-card-text>
          Are you sure you want to delete <strong>{{ deleteTarget?.name || deleteTarget?.bank || '' }}</strong>?
          <v-text-field
            v-model="deleteConfirmText"
            label='Type "DELETE" to confirm'
            variant="outlined"
            density="compact"
            class="mt-3"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="red" variant="flat" :disabled="deleteConfirmText !== 'DELETE'" @click="executeDelete" :loading="deleteLoading">
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack" :color="snackColor" timeout="3000" location="bottom right">
      {{ snackMsg }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '@src/api'
import { useSettingsStore } from '@src/stores/settings'

const settingsStore = useSettingsStore()

// ── State ───────────────────────────────────────────────────────────

const loading = ref(false)
const activeTab = ref('budget')

// Month
const todayMonth = (() => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
})()
const currentMonth = ref(todayMonth)

// Data
const entries = ref([])
const summary = ref(null)
const accounts = ref([])
const loans = ref([])
// Sort helper: by frequency, day_of_month ascending, recurring items grouped
function sortByDay(a, b) {
  const freqOrder = { once: 0, weekly: 1, daily: 2 }
  const aOrder = freqOrder[a.frequency] ?? 0
  const bOrder = freqOrder[b.frequency] ?? 0
  if (aOrder !== bOrder) return aOrder - bOrder
  const aDay = a.day_of_month || 999
  const bDay = b.day_of_month || 999
  return aDay - bDay
}

// Calculate effective monthly amount based on frequency
function effectiveAmount(e) {
  const freq = e.frequency || 'once'
  if (freq === 'daily') {
    const [y, m] = currentMonth.value.split('-').map(Number)
    const days = new Date(y, m, 0).getDate()
    return (e.amount || 0) * days
  }
  if (freq === 'weekly') {
    const [y, m] = currentMonth.value.split('-').map(Number)
    const days = new Date(y, m, 0).getDate()
    const start = e.day_of_month || 1
    let count = 0
    for (let d = start; d <= days; d += 7) count++
    return (e.amount || 0) * count
  }
  return e.amount || 0
}

// Entry background class based on paid status and frequency
function entryBgClass(item, paidColor) {
  if (item.is_paid) return `bg-${paidColor}-darken-4`
  const freq = item.frequency || 'once'
  if (freq === 'daily') return 'bg-blue-darken-4'
  if (freq === 'weekly') return 'bg-indigo-darken-4'
  return ''
}

// Computed
const incomeEntries = computed(() => entries.value.filter(e => e.type === 'income').sort(sortByDay))
const expenseEntries = computed(() => entries.value.filter(e => e.type === 'expense').sort(sortByDay))
const sortedLoans = computed(() => [...loans.value].sort((a, b) => (a.payment_date || 999) - (b.payment_date || 999)))
const totalIncome = computed(() => incomeEntries.value.reduce((s, e) => s + effectiveAmount(e), 0))
const totalExpense = computed(() => expenseEntries.value.reduce((s, e) => s + effectiveAmount(e), 0))
const totalAccountBalance = computed(() => accounts.value.reduce((s, a) => s + (a.balance || 0), 0))
const totalDebt = computed(() => loans.value.reduce((s, l) => s + (l.remaining_debt || 0), 0))
const totalLoanPayments = computed(() => loans.value.reduce((s, l) => s + (l.monthly_payment || 0), 0))
const totalExpenseWithLoans = computed(() => totalExpense.value + totalLoanPayments.value)
const hasEntriesForMonth = computed(() => entries.value.length > 0)

const expenseCategoryOptions = computed(() => {
  const cats = [...new Set(entries.value.filter(e => e.type === 'expense').map(e => e.category).filter(Boolean))]
  return cats.sort()
})
const incomeCategoryOptions = computed(() => {
  const cats = [...new Set(entries.value.filter(e => e.type === 'income').map(e => e.category).filter(Boolean))]
  return cats.sort()
})

// Entry dialog
const entryDialog = ref(false)
const editingEntry = ref(null)
const entrySaving = ref(false)
const entryForm = ref({ type: 'expense', name: '', amount: 0, category: '', is_recurring: true, is_paid: false, is_credit_card: false, frequency: 'once', day_of_month: null, notes: '' })

// Account dialog
const accountDialog = ref(false)
const editingAccount = ref(null)
const accountSaving = ref(false)
const accountForm = ref({ name: '', purpose: '', balance: 0, payment_date: null, notes: '' })

// Loan dialog
const loanDialog = ref(false)
const editingLoan = ref(null)
const loanSaving = ref(false)
const loanForm = ref({ bank: '', purpose: '', credit_limit: 0, remaining_debt: 0, monthly_payment: 0, payment_date: null, notes: '' })

// Delete dialog
const deleteDialog = ref(false)
const deleteTarget = ref(null)
const deleteType = ref('')  // 'entry', 'account', 'loan'
const deleteConfirmText = ref('')
const deleteLoading = ref(false)

// Month transition
const transitionLoading = ref(false)

// Collapse state (persisted in localStorage)
const expensesCollapsed = ref(localStorage.getItem('budget_expenses_collapsed') === 'true')
watch(expensesCollapsed, (v) => localStorage.setItem('budget_expenses_collapsed', String(v)))

// Available cash (persisted in localStorage)
const availableCash = ref(parseFloat(localStorage.getItem('budget_available_cash')) || 0)
watch(availableCash, (v) => localStorage.setItem('budget_available_cash', String(v ?? 0)))

// Calendar
const calendarData = ref(null)
const calendarLoading = ref(false)
const calendarZoom = ref(1.0)

// Snackbar
const snack = ref(false)
const snackMsg = ref('')
const snackColor = ref('success')

function showSnack(msg, color = 'success') {
  snackMsg.value = msg
  snackColor.value = color
  snack.value = true
}

function fmt(n) {
  if (n == null) return '0.00'
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtShort(n) {
  if (n == null) return '0'
  const num = Number(n)
  if (Math.abs(num) >= 1000) return (num / 1000).toFixed(1) + 'k'
  return num.toFixed(0)
}

function isToday(day) {
  const today = new Date()
  const [y, m] = currentMonth.value.split('-').map(Number)
  return today.getFullYear() === y && today.getMonth() + 1 === m && today.getDate() === day
}

function formatMonthLabel(mk) {
  const [y, m] = mk.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[parseInt(m) - 1]} ${y}`
}

function prevMonth() {
  const [y, m] = currentMonth.value.split('-').map(Number)
  if (m === 1) currentMonth.value = `${y - 1}-12`
  else currentMonth.value = `${y}-${String(m - 1).padStart(2, '0')}`
}

function nextMonth() {
  const [y, m] = currentMonth.value.split('-').map(Number)
  if (m === 12) currentMonth.value = `${y + 1}-01`
  else currentMonth.value = `${y}-${String(m + 1).padStart(2, '0')}`
}

// ── API calls ───────────────────────────────────────────────────────

async function loadEntries() {
  try {
    const { data } = await api.get('/addons/budgeting/entries', { params: { month_key: currentMonth.value } })
    entries.value = data.items || []
  } catch { entries.value = [] }
}

async function loadSummary() {
  try {
    const { data } = await api.get('/addons/budgeting/summary', { params: { month_key: currentMonth.value, available_cash: availableCash.value || 0 } })
    summary.value = data
  } catch { summary.value = null }
}

async function loadAccounts() {
  try {
    const { data } = await api.get('/addons/budgeting/accounts')
    accounts.value = data || []
  } catch { accounts.value = [] }
}

async function loadLoans() {
  try {
    const { data } = await api.get('/addons/budgeting/loans')
    loans.value = data || []
  } catch { loans.value = [] }
}

async function loadCalendar() {
  calendarLoading.value = true
  try {
    const { data } = await api.get('/addons/budgeting/calendar', { params: { month_key: currentMonth.value } })
    calendarData.value = data
  } catch { calendarData.value = null }
  finally { calendarLoading.value = false }
}

async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([loadEntries(), loadSummary(), loadAccounts(), loadLoans(), loadCalendar()])
  } finally {
    loading.value = false
  }
}

watch(currentMonth, () => {
  loadEntries()
  loadSummary()
  loadCalendar()
})

// ── Entry CRUD ──────────────────────────────────────────────────────

function openAddEntry(type) {
  editingEntry.value = null
  entryForm.value = { type, name: '', amount: 0, category: '', is_recurring: true, is_paid: false, is_credit_card: false, frequency: 'once', day_of_month: null, notes: '' }
  entryDialog.value = true
}

function openEditEntry(item) {
  editingEntry.value = item
  entryForm.value = { ...item }
  entryDialog.value = true
}

async function saveEntry() {
  entrySaving.value = true
  try {
    if (editingEntry.value) {
      await api.patch(`/addons/budgeting/entries/${editingEntry.value.id}`, {
        name: entryForm.value.name,
        amount: entryForm.value.amount,
        category: entryForm.value.category,
        is_recurring: entryForm.value.is_recurring,
        is_paid: entryForm.value.is_paid,
        is_credit_card: entryForm.value.is_credit_card,
        frequency: entryForm.value.frequency || 'once',
        day_of_month: entryForm.value.day_of_month || null,
        notes: entryForm.value.notes,
      })
      showSnack('Entry updated')
    } else {
      await api.post('/addons/budgeting/entries', {
        ...entryForm.value,
        month_key: currentMonth.value,
      })
      showSnack('Entry added')
    }
    entryDialog.value = false
    await Promise.all([loadEntries(), loadSummary(), loadCalendar()])
  } catch (e) {
    showSnack(e.response?.data?.detail || 'Failed to save entry', 'error')
  } finally {
    entrySaving.value = false
  }
}

async function togglePaid(item) {
  try {
    await api.patch(`/addons/budgeting/entries/${item.id}/toggle-paid`)
    await Promise.all([loadEntries(), loadSummary(), loadCalendar()])
  } catch (e) {
    showSnack('Failed to update', 'error')
  }
}

function isLoanPaid(loan) {
  return (loan.paid_months || []).includes(currentMonth.value)
}

async function toggleLoanPaid(loan) {
  try {
    await api.patch(`/addons/budgeting/loans/${loan.id}/toggle-paid`, null, {
      params: { month_key: currentMonth.value },
    })
    await Promise.all([loadLoans(), loadSummary(), loadCalendar()])
  } catch (e) {
    showSnack('Failed to update loan payment', 'error')
  }
}

function confirmDeleteEntry(item) {
  deleteTarget.value = item
  deleteType.value = 'entry'
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

// ── Account CRUD ────────────────────────────────────────────────────

function openAddAccount() {
  editingAccount.value = null
  accountForm.value = { name: '', purpose: '', balance: 0, payment_date: null, notes: '' }
  accountDialog.value = true
}

function openEditAccount(acc) {
  editingAccount.value = acc
  accountForm.value = { ...acc }
  accountDialog.value = true
}

async function saveAccount() {
  accountSaving.value = true
  try {
    if (editingAccount.value) {
      await api.patch(`/addons/budgeting/accounts/${editingAccount.value.id}`, accountForm.value)
      showSnack('Account updated')
    } else {
      await api.post('/addons/budgeting/accounts', accountForm.value)
      showSnack('Account added')
    }
    accountDialog.value = false
    await loadAccounts()
  } catch (e) {
    showSnack(e.response?.data?.detail || 'Failed to save account', 'error')
  } finally {
    accountSaving.value = false
  }
}

function confirmDeleteAccount(acc) {
  deleteTarget.value = acc
  deleteType.value = 'account'
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

// ── Loan CRUD ───────────────────────────────────────────────────────

function openAddLoan() {
  editingLoan.value = null
  loanForm.value = { bank: '', purpose: '', credit_limit: 0, remaining_debt: 0, monthly_payment: 0, payment_date: null, notes: '' }
  loanDialog.value = true
}

function openEditLoan(loan) {
  editingLoan.value = loan
  loanForm.value = { ...loan }
  loanDialog.value = true
}

async function saveLoan() {
  loanSaving.value = true
  try {
    if (editingLoan.value) {
      await api.patch(`/addons/budgeting/loans/${editingLoan.value.id}`, loanForm.value)
      showSnack('Loan updated')
    } else {
      await api.post('/addons/budgeting/loans', loanForm.value)
      showSnack('Loan added')
    }
    loanDialog.value = false
    await Promise.all([loadLoans(), loadCalendar()])
  } catch (e) {
    showSnack(e.response?.data?.detail || 'Failed to save loan', 'error')
  } finally {
    loanSaving.value = false
  }
}

function confirmDeleteLoan(loan) {
  deleteTarget.value = loan
  deleteType.value = 'loan'
  deleteConfirmText.value = ''
  deleteDialog.value = true
}

// ── Delete handler ──────────────────────────────────────────────────

async function executeDelete() {
  deleteLoading.value = true
  try {
    const id = deleteTarget.value?.id
    if (deleteType.value === 'entry') {
      await api.delete(`/addons/budgeting/entries/${id}`)
      await Promise.all([loadEntries(), loadSummary(), loadCalendar()])
    } else if (deleteType.value === 'account') {
      await api.delete(`/addons/budgeting/accounts/${id}`)
      await loadAccounts()
    } else if (deleteType.value === 'loan') {
      await api.delete(`/addons/budgeting/loans/${id}`)
      await loadLoans()
    }
    deleteDialog.value = false
    showSnack('Deleted successfully')
  } catch (e) {
    showSnack('Failed to delete', 'error')
  } finally {
    deleteLoading.value = false
  }
}

// ── Month transition ────────────────────────────────────────────────

async function transitionMonth() {
  transitionLoading.value = true
  try {
    const { data } = await api.post('/addons/budgeting/months/transition', null, {
      params: { target_month: currentMonth.value },
    })
    showSnack(data.message || `Created ${data.created} entries`)
    await Promise.all([loadEntries(), loadSummary(), loadCalendar()])
  } catch (e) {
    showSnack(e.response?.data?.detail || 'Failed to transition month', 'error')
  } finally {
    transitionLoading.value = false
  }
}

// ── Init ────────────────────────────────────────────────────────────

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}

.calendar-cell {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 6px 8px;
  min-height: calc(160px * var(--cal-zoom, 1));
  font-size: calc(11px * var(--cal-zoom, 1));
  overflow: hidden;
  transition: background-color 0.15s;
}

.calendar-cell:hover {
  background-color: rgba(255, 255, 255, 0.03);
}

.calendar-cell.empty {
  border-color: transparent;
  min-height: auto;
}

.calendar-cell.today-cell {
  border-color: rgb(var(--v-theme-teal-accent-3, 29, 233, 182));
  background-color: rgba(29, 233, 182, 0.05);
}

.calendar-cell.has-items {
  background-color: rgba(255, 255, 255, 0.02);
}

.calendar-item {
  border-radius: 2px;
  padding: 1px 0;
}

.calendar-item-paid {
  opacity: 0.5;
}

.calendar-item-daily {
  background-color: rgba(33, 150, 243, 0.1);
  border-left: 2px solid rgba(33, 150, 243, 0.4);
  padding-left: 4px;
}

.calendar-item-weekly {
  background-color: rgba(63, 81, 181, 0.1);
  border-left: 2px solid rgba(63, 81, 181, 0.4);
  padding-left: 4px;
}
</style>
