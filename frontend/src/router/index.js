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
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/DashboardView.vue') },
      { path: 'agents', name: 'Agents', component: () => import('../views/AgentsView.vue') },
      { path: 'agents/new', name: 'AgentCreate', component: () => import('../views/AgentFormView.vue') },
      { path: 'agents/:id', name: 'AgentEdit', component: () => import('../views/AgentFormView.vue') },
      { path: 'agents/:id/detail', name: 'AgentDetail', component: () => import('../views/AgentDetailView.vue') },
      { path: 'protocols', name: 'Protocols', component: () => import('../views/ProtocolsView.vue') },
      { path: 'tasks', name: 'Tasks', component: () => import('../views/TasksView.vue') },
      { path: 'tasks/new', name: 'TaskCreate', component: () => import('../views/TaskFormView.vue') },
      { path: 'tasks/:id', name: 'TaskEdit', component: () => import('../views/TaskFormView.vue') },
      { path: 'skills', name: 'Skills', component: () => import('../views/SkillsView.vue') },
      { path: 'skills/new', name: 'SkillCreate', component: () => import('../views/SkillFormView.vue') },
      { path: 'skills/:id', name: 'SkillEdit', component: () => import('../views/SkillFormView.vue') },
      { path: 'settings', name: 'Settings', component: () => import('../views/SettingsView.vue') },
      { path: 'settings/models', name: 'Models', component: () => import('../views/ModelsView.vue') },
      { path: 'settings/api-keys', name: 'ApiKeys', component: () => import('../views/ApiKeysView.vue') },
      { path: 'system/logs', name: 'SystemLogs', component: () => import('../views/SystemLogsView.vue') },
      { path: 'ollama', name: 'Ollama', component: () => import('../views/OllamaView.vue') },
      { path: 'files', name: 'FileBrowser', component: () => import('../views/FileBrowserView.vue') },
      { path: 'terminal', name: 'Terminal', component: () => import('../views/TerminalView.vue') },
      { path: 'system', name: 'System', component: () => import('../views/SystemView.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    next('/login')
  } else if (to.meta.guest && auth.isAuthenticated) {
    next('/')
  } else {
    next()
  }
})

export default router
