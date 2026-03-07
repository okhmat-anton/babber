import { defineStore } from 'pinia'
import api from '../api'

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: [],
    currentSession: null,
    messages: [],
    availableModels: [],
    loading: false,
    sending: false,
    panelOpen: localStorage.getItem('chat_panel_open') === 'true',
    showSessionList: false,
  }),

  getters: {
    sortedSessions: (state) => {
      return [...state.sessions].sort((a, b) =>
        new Date(b.updated_at) - new Date(a.updated_at)
      )
    },
    currentModels: (state) => {
      if (!state.currentSession) return []
      return state.currentSession.model_ids || []
    },
    isMultiModel: (state) => {
      return state.currentSession?.multi_model || false
    },
  },

  actions: {
    togglePanel() {
      this.panelOpen = !this.panelOpen
      localStorage.setItem('chat_panel_open', this.panelOpen)
    },
    openPanel() {
      this.panelOpen = true
      localStorage.setItem('chat_panel_open', 'true')
    },
    closePanel() {
      this.panelOpen = false
      localStorage.setItem('chat_panel_open', 'false')
    },

    async fetchAvailableModels() {
      try {
        const { data } = await api.get('/chat/available-models')
        this.availableModels = data
      } catch (e) {
        console.error('Failed to fetch available models:', e)
      }
    },

    async fetchSessions() {
      this.loading = true
      try {
        // Fetch all sessions - filtering by chat_type is done in the component
        const { data } = await api.get('/chat/sessions')
        this.sessions = data
      } catch (e) {
        console.error('Failed to fetch sessions:', e)
      } finally {
        this.loading = false
      }
    },

    async createSession(params = {}) {
      try {
        const { data } = await api.post('/chat/sessions', {
          title: params.title || 'New Chat',
          model_ids: params.model_ids || [],
          agent_id: params.agent_id || null,
          agent_ids: params.agent_ids || [],
          multi_model: params.multi_model || false,
          system_prompt: params.system_prompt || null,
          temperature: params.temperature ?? 0.7,
          chat_type: params.chat_type || 'user',
          project_slug: params.project_slug || null,
          task_id: params.task_id || null,
        })
        this.sessions.unshift(data)
        this.currentSession = data
        this.messages = []
        localStorage.setItem('chat_current_session_id', data.id)
        return data
      } catch (e) {
        console.error('Failed to create session:', e)
        throw e
      }
    },

    async loadSession(sessionId) {
      this.loading = true
      try {
        const { data } = await api.get(`/chat/sessions/${sessionId}`)
        this.currentSession = data
        this.messages = data.messages || []
        this.showSessionList = false
        localStorage.setItem('chat_current_session_id', sessionId)
        // Mark session as read (reset unread count)
        if (data.unread_count > 0) {
          await this.markSessionAsRead(sessionId)
        }
      } catch (e) {
        console.error('Failed to load session:', e)
      } finally {
        this.loading = false
      }
    },

    async updateSession(sessionId, params) {
      try {
        const { data } = await api.put(`/chat/sessions/${sessionId}`, params)
        const idx = this.sessions.findIndex(s => s.id === sessionId)
        if (idx >= 0) this.sessions[idx] = data
        if (this.currentSession?.id === sessionId) {
          this.currentSession = { ...this.currentSession, ...data }
        }
        return data
      } catch (e) {
        console.error('Failed to update session:', e)
        throw e
      }
    },

    async deleteSession(sessionId) {
      try {
        await api.delete(`/chat/sessions/${sessionId}`)
        this.sessions = this.sessions.filter(s => s.id !== sessionId)
        if (this.currentSession?.id === sessionId) {
          this.currentSession = null
          this.messages = []
          localStorage.removeItem('chat_current_session_id')
        }
      } catch (e) {
        console.error('Failed to delete session:', e)
        throw e
      }
    },

    async markSessionAsRead(sessionId) {
      try {
        await api.post(`/chat/sessions/${sessionId}/mark-read`)
        // Update local state
        const session = this.sessions.find(s => s.id === sessionId)
        if (session) {
          session.unread_count = 0
        }
        if (this.currentSession?.id === sessionId) {
          this.currentSession.unread_count = 0
        }
      } catch (e) {
        console.error('Failed to mark session as read:', e)
      }
    },

    async sendMessage(content, modelIds = null) {
      if (!this.currentSession) return
      this.sending = true

      // Optimistic: add user message
      const userMsg = {
        id: 'temp-' + Date.now(),
        role: 'user',
        content,
        model_name: null,
        model_responses: null,
        total_tokens: 0,
        duration_ms: 0,
        created_at: new Date().toISOString(),
      }
      this.messages.push(userMsg)

      const MAX_RETRIES = 2

      try {
        for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
          try {
            const { data } = await api.post(
              `/chat/sessions/${this.currentSession.id}/messages`,
              { content, model_ids: modelIds },
              { timeout: 300000 }
            )
            this.messages.push(data)

            // Update session in list
            const idx = this.sessions.findIndex(s => s.id === this.currentSession.id)
            if (idx >= 0) {
              this.sessions[idx].last_message = data.content?.substring(0, 100)
              this.sessions[idx].message_count = this.messages.length
              this.sessions[idx].updated_at = new Date().toISOString()
            }

            return data
          } catch (e) {
            const isNetworkError = !e.response && e.message === 'Network Error'
            const isTimeout = e.code === 'ECONNABORTED'

            // Retry only on transient network errors (not HTTP errors)
            if ((isNetworkError || isTimeout) && attempt < MAX_RETRIES) {
              console.warn(`Chat request failed (attempt ${attempt + 1}), retrying...`, e.message)
              await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
              continue
            }

            // Build human-readable error message
            let errorText
            if (isNetworkError) {
              errorText = 'Cannot connect to server. Check that the backend is running and try again.'
            } else if (isTimeout) {
              errorText = 'Request timed out. The model may be overloaded — try again later.'
            } else if (e.response?.data?.detail) {
              errorText = e.response.data.detail
            } else {
              errorText = e.message
            }

            this.messages.push({
              id: 'error-' + Date.now(),
              role: 'assistant',
              content: `**Error:** ${errorText}`,
              model_name: 'system',
              total_tokens: 0,
              duration_ms: 0,
              created_at: new Date().toISOString(),
            })
            throw e
          }
        }
      } finally {
        this.sending = false
      }
    },

    async autoTitle(sessionId) {
      try {
        const { data } = await api.post(`/chat/sessions/${sessionId}/auto-title`)
        const idx = this.sessions.findIndex(s => s.id === sessionId)
        if (idx >= 0) this.sessions[idx].title = data.title
        if (this.currentSession?.id === sessionId) {
          this.currentSession.title = data.title
        }
      } catch (e) {
        console.error('Failed to auto-title:', e)
      }
    },

    newChat() {
      this.currentSession = null
      this.messages = []
      this.showSessionList = false
      localStorage.removeItem('chat_current_session_id')
    },
  },
})
