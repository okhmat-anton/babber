import { defineStore } from 'pinia'
import api from '../api'

export const useProjectsStore = defineStore('projects', {
  state: () => ({
    projects: [],
    loading: false,
    currentProject: null,
    currentTasks: [],
    currentFiles: [],
    currentLogs: [],
  }),

  getters: {
    activeProjects: (state) => state.projects.filter(p => p.status === 'active'),
  },

  actions: {
    async fetchProjects(params = {}) {
      this.loading = true
      try {
        const { data } = await api.get('/projects', { params })
        this.projects = data.items || []
      } finally {
        this.loading = false
      }
    },

    async fetchProject(slug) {
      const { data } = await api.get(`/projects/${slug}`)
      this.currentProject = data
      return data
    },

    async fetchProjectsForAgent(agentId) {
      const { data } = await api.get(`/projects/by-agent/${agentId}`)
      return data.items || []
    },

    async createProject(payload) {
      const { data } = await api.post('/projects', payload)
      this.projects.unshift(data)
      return data
    },

    async updateProject(slug, payload) {
      const { data } = await api.patch(`/projects/${slug}`, payload)
      this.currentProject = data
      const idx = this.projects.findIndex(p => p.slug === slug)
      if (idx !== -1) this.projects[idx] = data
      return data
    },

    async deleteProject(slug) {
      await api.delete(`/projects/${slug}`)
      this.projects = this.projects.filter(p => p.slug !== slug)
    },

    // Tasks
    async fetchTasks(slug, params = {}) {
      const { data } = await api.get(`/projects/${slug}/tasks`, { params })
      this.currentTasks = data.items || []
      return this.currentTasks
    },

    async createTask(slug, payload) {
      const { data } = await api.post(`/projects/${slug}/tasks`, payload)
      this.currentTasks.push(data)
      return data
    },

    async updateTask(slug, taskId, payload) {
      const { data } = await api.patch(`/projects/${slug}/tasks/${taskId}`, payload)
      const idx = this.currentTasks.findIndex(t => t.id === taskId)
      if (idx !== -1) this.currentTasks[idx] = data
      return data
    },

    async deleteTask(slug, taskId) {
      await api.delete(`/projects/${slug}/tasks/${taskId}`)
      this.currentTasks = this.currentTasks.filter(t => t.id !== taskId)
    },

    // Files
    async fetchFiles(slug) {
      const { data } = await api.get(`/projects/${slug}/files`)
      this.currentFiles = data
      return data
    },

    async readFile(slug, path) {
      const { data } = await api.get(`/projects/${slug}/files/read`, { params: { path } })
      return data
    },

    async createFile(slug, payload) {
      await api.post(`/projects/${slug}/files/create`, payload)
      await this.fetchFiles(slug)
    },

    async writeFile(slug, path, content) {
      await api.put(`/projects/${slug}/files/write`, { path, content })
    },

    async deleteFile(slug, path) {
      await api.delete(`/projects/${slug}/files/delete`, { params: { path } })
      await this.fetchFiles(slug)
    },

    async renameFile(slug, oldPath, newPath) {
      await api.post(`/projects/${slug}/files/rename`, { old_path: oldPath, new_path: newPath })
      await this.fetchFiles(slug)
    },

    // Execution
    async executeCommand(slug, payload) {
      const { data } = await api.post(`/projects/${slug}/execute`, payload)
      return data
    },

    // Logs
    async fetchLogs(slug, params = {}) {
      const { data } = await api.get(`/projects/${slug}/logs`, { params })
      this.currentLogs = data.items || []
      return this.currentLogs
    },
  },
})
