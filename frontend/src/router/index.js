import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/disclaimer',
    name: 'Disclaimer',
    component: () => import('../views/DisclaimerView.vue'),
    meta: { requiresAuth: true, skipDisclaimer: true },
  },
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/DashboardView.vue') },
      { path: 'agents', name: 'Agents', component: () => import('../views/AgentsView.vue') },
      { path: 'agents/new', name: 'AgentCreate', component: () => import('../views/AgentFormView.vue') },
      { path: 'agents/:id', name: 'AgentEdit', component: () => import('../views/AgentFormView.vue') },
      { path: 'agents/:id/detail', name: 'AgentDetail', component: () => import('../views/AgentDetailView.vue') },
      { path: 'research-resources', name: 'ResearchResources', component: () => import('../views/ResearchResourcesView.vue') },
      { path: 'tasks', name: 'Tasks', component: () => import('../views/TasksView.vue') },
      { path: 'tasks/new', name: 'TaskCreate', component: () => import('../views/TaskFormView.vue') },
      { path: 'tasks/:id', name: 'TaskEdit', component: () => import('../views/TaskFormView.vue') },
      { path: 'models', name: 'Models', component: () => import('../views/ModelsView.vue') },
      { path: 'ollama', redirect: '/models' },

      // Settings tabs
      { path: 'settings', name: 'Settings', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/protocols', name: 'SettingsProtocols', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/skills', name: 'SettingsSkills', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/skills/new', name: 'SkillCreate', component: () => import('../views/SkillFormView.vue') },
      { path: 'settings/skills/:id', name: 'SkillEdit', component: () => import('../views/SkillFormView.vue') },
      { path: 'settings/agent-errors', name: 'SettingsAgentErrors', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/files', name: 'SettingsFiles', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/terminal', name: 'SettingsTerminal', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/system', name: 'SettingsSystem', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/system-logs', name: 'SettingsSystemLogs', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/models', redirect: '/models' },
      { path: 'settings/api-keys', name: 'ApiKeys', component: () => import('../views/ApiKeysView.vue') },

      // Old URL redirects
      { path: 'protocols', redirect: '/settings/protocols' },
      { path: 'skills', redirect: '/settings/skills' },
      { path: 'skills/new', redirect: '/settings/skills/new' },
      { path: 'skills/:id', redirect: to => `/settings/skills/${to.params.id}` },
      { path: 'agent-errors', redirect: '/settings/agent-errors' },
      { path: 'files', redirect: '/settings/files' },
      { path: 'terminal', redirect: '/settings/terminal' },
      { path: 'system', redirect: '/settings/system' },
      { path: 'system/logs', redirect: '/settings/system-logs' },
      { path: 'projects', name: 'Projects', component: () => import('../views/ProjectsView.vue') },
      { path: 'projects/:slug', name: 'ProjectDetail', component: () => import('../views/ProjectDetailView.vue') },
      { path: 'creator', name: 'Creator', component: () => import('../views/CreatorView.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    next('/login')
  } else if (to.meta.guest && auth.isAuthenticated) {
    next('/')
  } else if (to.meta.requiresAuth && auth.isAuthenticated && !to.meta.skipDisclaimer) {
    // Check if user has accepted disclaimer
    if (!auth.user) {
      await auth.fetchUser()
    }
    if (auth.user && !auth.user.disclaimer_accepted) {
      next('/disclaimer')
    } else {
      next()
    }
  } else {
    next()
  }
})

export default router
