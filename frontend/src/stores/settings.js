import { defineStore } from 'pinia'
import api from '../api'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    models: [],
    apiKeys: [],
    systemSettings: {},
    loading: false,
    // Model roles global state (for base model alert)
    roleAssignments: {},       // { role: model_config_id }
    rolesLoaded: false,
    ollamaRunningModels: [],   // [{ name, ... }]
  }),

  getters: {
    runningOllamaNames: (state) => new Set(state.ollamaRunningModels.map(m => m.name)),

    hasActiveBaseModel(state) {
      const baseId = state.roleAssignments['base']
      if (!baseId) return false
      const model = state.models.find(m => m.id === baseId)
      if (!model || !model.is_active) return false
      if (model.provider === 'ollama' && !this.runningOllamaNames.has(model.model_id)) return false
      return true
    },

    baseModelAlertText(state) {
      if (!state.rolesLoaded) return null
      if (this.hasActiveBaseModel) return null
      const baseId = state.roleAssignments['base']
      if (!baseId) return 'Base model is not assigned! Assign a base model in role settings.'
      return 'Base model is not available (not running). Assign a base model in role settings.'
    },
  },

  actions: {
    // --- System settings ---
    async fetchSystemSettings() {
      const { data } = await api.get('/settings/system')
      const map = {}
      for (const s of data) {
        map[s.key] = s
      }
      this.systemSettings = map
    },

    async updateSystemSetting(key, value) {
      const { data } = await api.put(`/settings/system/${key}`, { value })
      this.systemSettings[key] = data
      return data
    },

    async fetchModels() {
      const { data } = await api.get('/settings/models')
      this.models = data
    },

    async createModel(payload) {
      const { data } = await api.post('/settings/models', payload)
      this.models.unshift(data)
      return data
    },

    async updateModel(id, payload) {
      const { data } = await api.put(`/settings/models/${id}`, payload)
      const idx = this.models.findIndex((m) => m.id === id)
      if (idx >= 0) this.models[idx] = data
      return data
    },

    async deleteModel(id) {
      await api.delete(`/settings/models/${id}`)
      this.models = this.models.filter((m) => m.id !== id)
    },

    async testModel(id) {
      const { data } = await api.post(`/settings/models/${id}/test`)
      return data
    },

    async listAvailableModels(id) {
      const { data } = await api.get(`/settings/models/${id}/available`)
      return data.models
    },

    async fetchApiKeys() {
      const { data } = await api.get('/settings/api-keys')
      this.apiKeys = data
    },

    async createApiKey(payload) {
      const { data } = await api.post('/settings/api-keys', payload)
      return data
    },

    async deleteApiKey(id) {
      await api.delete(`/settings/api-keys/${id}`)
      this.apiKeys = this.apiKeys.filter((k) => k.id !== id)
    },

    async changePassword(oldPassword, newPassword) {
      await api.put('/settings/password', { old_password: oldPassword, new_password: newPassword })
    },

    // --- Model Roles ---
    async fetchModelRoles() {
      try {
        const { data } = await api.get('/settings/model-roles')
        const map = {}
        for (const a of data.assignments) {
          map[a.role] = a.model_config_id
        }
        this.roleAssignments = map
        this.rolesLoaded = true
        return data
      } catch (e) {
        console.error('Failed to fetch model roles:', e)
      }
    },

    // --- Ollama running models ---
    async fetchOllamaRunning() {
      try {
        const { data } = await api.get('/ollama/running')
        this.ollamaRunningModels = data
      } catch {
        this.ollamaRunningModels = []
      }
    },

    // Refresh all data needed for base model alert
    async refreshBaseModelStatus() {
      await Promise.all([
        this.fetchModels(),
        this.fetchModelRoles(),
        this.fetchOllamaRunning(),
      ])
    },
  },
})
