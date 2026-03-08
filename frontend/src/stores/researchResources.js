import { defineStore } from 'pinia'
import api from '../api'

export const useResearchResourcesStore = defineStore('researchResources', {
  state: () => ({
    resources: [],
    loading: false,
  }),

  actions: {
    async fetchResources(params = {}) {
      this.loading = true
      try {
        const { data } = await api.get('/research-resources', { params })
        this.resources = data.items || []
      } finally {
        this.loading = false
      }
    },

    async fetchResource(id) {
      const { data } = await api.get(`/research-resources/${id}`)
      return data
    },

    async createResource(payload) {
      const { data } = await api.post('/research-resources', payload)
      this.resources.unshift(data)
      return data
    },

    async updateResource(id, payload) {
      const { data } = await api.patch(`/research-resources/${id}`, payload)
      const idx = this.resources.findIndex((r) => r.id === id)
      if (idx >= 0) this.resources[idx] = data
      return data
    },

    async deleteResource(id) {
      await api.delete(`/research-resources/${id}`)
      this.resources = this.resources.filter((r) => r.id !== id)
    },

    async recordUsage(id) {
      const { data } = await api.post(`/research-resources/${id}/use`)
      const idx = this.resources.findIndex((r) => r.id === id)
      if (idx >= 0) this.resources[idx] = data
      return data
    },
  },
})
