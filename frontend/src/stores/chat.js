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
    // Edit & regenerate support
    abortController: null,
    lastSentContent: '',
    // Pending input from external sources (e.g. Video tab)
    pendingInput: '',
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
          video_id: params.video_id || null,
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
        console.log('[ChatStore] loadSession: fetching', sessionId)
        const { data } = await api.get(`/chat/sessions/${sessionId}`)
        console.log('[ChatStore] loadSession: received', { id: data.id, title: data.title, messageCount: data.messages?.length, keys: Object.keys(data) })
        this.currentSession = data
        this.messages = data.messages || []
        console.log('[ChatStore] loadSession: state updated. messages:', this.messages.length, 'currentSession:', this.currentSession?.id)
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

    async deleteMessage(messageId) {
      try {
        const sessionId = this.currentSession?.id
        if (!sessionId) return
        await api.delete(`/chat/sessions/${sessionId}/messages/${messageId}`)
        this.messages = this.messages.filter(m => m.id !== messageId)
      } catch (e) {
        console.error('Failed to delete message:', e)
        throw e
      }
    },

    async clearHistory(sessionId) {
      try {
        await api.post(`/chat/sessions/${sessionId}/clear`)
        if (this.currentSession?.id === sessionId) {
          this.messages = []
        }
      } catch (e) {
        console.error('Failed to clear history:', e)
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

    async sendMessage(content, modelIds = null, replaceLast = false) {
      if (!this.currentSession) return
      this.sending = true
      this.lastSentContent = content

      // Create AbortController for cancellation support
      const controller = new AbortController()
      this.abortController = controller

      // Optimistic: add user message (unless replacing last)
      if (!replaceLast) {
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
      } else {
        // For replace_last: update the last user message content in local state
        for (let i = this.messages.length - 1; i >= 0; i--) {
          if (this.messages[i].role === 'user') {
            this.messages[i].content = content
            break
          }
        }
      }

      const MAX_RETRIES = 2

      try {
        for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
          try {
            const { data } = await api.post(
              `/chat/sessions/${this.currentSession.id}/messages`,
              { content, model_ids: modelIds, replace_last: replaceLast },
              { timeout: 300000, signal: controller.signal }
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
            // Check if deliberately cancelled (edit & regenerate or stop)
            const isCancelled = e.code === 'ERR_CANCELED' || e.name === 'CanceledError'
            if (isCancelled) {
              return null
            }

            const isNetworkError = !e.response && e.message === 'Network Error'
            const isTimeout = e.code === 'ECONNABORTED'
            const httpStatus = e.response?.status
            const isServerError = httpStatus && httpStatus >= 500

            // Retry on transient errors: network, timeout, or server 5xx (overloaded, etc.)
            if ((isNetworkError || isTimeout || isServerError) && attempt < MAX_RETRIES) {
              console.warn(`Chat request failed (attempt ${attempt + 1}/${MAX_RETRIES + 1}), retrying...`, e.message)
              // On retry, use replace_last to avoid duplicating user message in DB
              replaceLast = true
              await new Promise(r => setTimeout(r, 2000 * (attempt + 1)))
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
        this.abortController = null
      }
    },

    cancelGeneration() {
      if (this.abortController) {
        this.abortController.abort()
      }
    },

    async editAndRegenerate(newContent) {
      // 1. Cancel current generation
      this.cancelGeneration()

      // 2. Wait for current request to complete (abort triggers finally block)
      for (let i = 0; i < 100 && this.sending; i++) {
        await new Promise(r => setTimeout(r, 50))
      }

      // 3. Remove trailing error/temp messages from the cancelled request
      while (this.messages.length > 0) {
        const last = this.messages[this.messages.length - 1]
        if (last.id?.startsWith?.('error-') || last.id?.startsWith?.('temp-')) {
          this.messages.pop()
        } else {
          break
        }
      }

      // 4. Re-send with replace_last flag
      return this.sendMessage(newContent, null, true)
    },

    async editUserMessage(msgIndex, newContent) {
      /**
       * Edit an already-sent user message and regenerate assistant response.
       * Like VSCode Copilot: click pencil → edit → submit → old response replaced.
       * Works even during generation — cancels current request first.
       */
      const msg = this.messages[msgIndex]
      if (!msg || msg.role !== 'user') return

      // 1. Cancel current generation if active
      if (this.sending) {
        this.cancelGeneration()
        // Wait for abort to settle
        for (let i = 0; i < 100 && this.sending; i++) {
          await new Promise(r => setTimeout(r, 50))
        }
      }

      // 2. Update user message content locally
      msg.content = newContent

      // 3. Remove all messages after this user message (assistant responses, errors, temp, etc.)
      this.messages.splice(msgIndex + 1)
      // Also clean trailing temp/error messages that might remain
      while (this.messages.length > 0) {
        const last = this.messages[this.messages.length - 1]
        if (last.id?.startsWith?.('error-') || last.id?.startsWith?.('temp-')) {
          this.messages.pop()
        } else {
          break
        }
      }

      // 4. Re-send with replace_last flag so backend updates DB + regenerates
      return this.sendMessage(newContent, null, true)
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
