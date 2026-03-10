<template>
  <Teleport to="body">
    <div
      v-if="visible"
      ref="popupRef"
      class="text-selection-popup"
      :style="{ top: posY + 'px', left: posX + 'px' }"
      @mousedown.stop
    >
      <!-- Personal section -->
      <div class="popup-section">
        <div class="popup-section-label">Personal</div>
        <div class="popup-actions">
          <button class="popup-btn" @click="emit('save', 'notes')" title="Save to Notes">
            <v-icon size="14">mdi-notebook-outline</v-icon>
            <span>Notes</span>
          </button>
          <button class="popup-btn" @click="emit('save', 'goals')" title="Add as Goal">
            <v-icon size="14">mdi-flag-outline</v-icon>
            <span>Goals</span>
          </button>
          <button class="popup-btn" @click="emit('save', 'ideas')" title="Add as Idea">
            <v-icon size="14">mdi-lightbulb-outline</v-icon>
            <span>Ideas</span>
          </button>
          <button class="popup-btn" @click="emit('save', 'dreams')" title="Add as Dream">
            <v-icon size="14">mdi-creation-outline</v-icon>
            <span>Dreams</span>
          </button>
        </div>
      </div>

      <!-- Global section -->
      <div class="popup-section">
        <div class="popup-section-label">Global</div>
        <div class="popup-actions">
          <button class="popup-btn" @click="emit('save', 'global_fact')" title="Save as Global Fact">
            <v-icon size="14">mdi-check-decagram</v-icon>
            <span>Fact</span>
          </button>
          <button class="popup-btn" @click="emit('save', 'global_analysis')" title="Create Analysis Topic">
            <v-icon size="14">mdi-chart-line</v-icon>
            <span>Analysis</span>
          </button>
          <button class="popup-btn" @click="emit('save', 'global_idea')" title="Save as Idea">
            <v-icon size="14">mdi-lightbulb-on-outline</v-icon>
            <span>Idea</span>
          </button>
        </div>
      </div>

      <!-- Agent section (only when agents available) -->
      <div v-if="agents.length" class="popup-section">
        <div class="popup-section-label">Agent</div>

        <!-- Step 1: pick what to add -->
        <div v-if="agentStep === 'type'" class="popup-actions">
          <button class="popup-btn" v-for="t in agentTargets" :key="t.key" @click="pickAgentType(t.key)" :title="t.label">
            <v-icon size="14">{{ t.icon }}</v-icon>
            <span>{{ t.label }}</span>
            <v-icon size="12" class="ml-auto">mdi-chevron-right</v-icon>
          </button>
        </div>

        <!-- Step 2: pick which agent -->
        <div v-else-if="agentStep === 'agent'" class="popup-agent-list">
          <button
            v-for="agent in agents"
            :key="agent.id"
            class="popup-btn agent-btn"
            @click="emit('save', selectedAgentType, { agentId: agent.id })"
            :title="agent.name"
          >
            <v-icon size="14">mdi-robot</v-icon>
            <span class="agent-name">{{ agent.name }}</span>
          </button>
          <button class="popup-btn back-btn" @click="agentStep = 'type'">
            <v-icon size="12">mdi-chevron-left</v-icon>
            <span>Back</span>
          </button>
        </div>
      </div>

      <!-- Status message -->
      <div v-if="statusMsg" class="popup-status" :class="statusClass">
        <v-icon size="12">{{ statusClass === 'success' ? 'mdi-check-circle' : 'mdi-alert-circle' }}</v-icon>
        {{ statusMsg }}
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  /** The DOM element to monitor for text selection (e.g. messagesContainer) */
  containerEl: { type: Object, default: null },
  /** Available agents list */
  agents: { type: Array, default: () => [] },
})

const emit = defineEmits(['save', 'selection-change'])

const visible = ref(false)
const posX = ref(0)
const posY = ref(0)
const popupRef = ref(null)
const agentStep = ref('type')        // 'type' → 'agent'
const selectedAgentType = ref('')     // 'agent_fact', 'agent_belief', etc.
const statusMsg = ref('')
const statusClass = ref('')

const agentTargets = [
  { key: 'agent_fact',       label: 'Fact',       icon: 'mdi-database-outline' },
  { key: 'agent_belief',     label: 'Belief',     icon: 'mdi-shield-check-outline' },
  { key: 'agent_aspiration', label: 'Aspiration',  icon: 'mdi-star-outline' },
  { key: 'agent_event',      label: 'Event',      icon: 'mdi-calendar-star' },
  { key: 'agent_task',       label: 'Task',       icon: 'mdi-checkbox-marked-outline' },
]

function pickAgentType(key) {
  selectedAgentType.value = key
  agentStep.value = 'agent'
}

let selectedText = ''

function getSelectedText() {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed) return ''
  return sel.toString().trim()
}

function isSelectionInsideContainer(sel) {
  if (!props.containerEl || !sel.rangeCount) return false
  const range = sel.getRangeAt(0)
  const container = props.containerEl
  // Check if the range is within the container
  return container.contains(range.startContainer) && container.contains(range.endContainer)
}

function handleMouseUp(e) {
  // Ignore clicks on the popup itself
  if (popupRef.value && popupRef.value.contains(e.target)) return

  // Small delay to let the selection finalize
  setTimeout(() => {
    const sel = window.getSelection()
    const text = getSelectedText()

    if (text && text.length > 2 && sel && isSelectionInsideContainer(sel)) {
      selectedText = text
      emit('selection-change', text)
      positionPopup(sel)
      visible.value = true
      agentStep.value = 'type'
      statusMsg.value = ''
    } else {
      hidePopup()
    }
  }, 10)
}

function positionPopup(sel) {
  if (!sel.rangeCount) return
  const range = sel.getRangeAt(0)
  const rect = range.getBoundingClientRect()

  // Position above the selection
  const popupWidth = 200
  let x = rect.left + rect.width / 2 - popupWidth / 2
  let y = rect.top - 10 // Will be adjusted with transform in CSS

  // Keep within viewport
  x = Math.max(8, Math.min(x, window.innerWidth - popupWidth - 8))
  y = Math.max(8, y)

  posX.value = x
  posY.value = y
}

function hidePopup() {
  visible.value = false
  selectedText = ''
  agentStep.value = 'type'
  statusMsg.value = ''
}

function handleKeydown(e) {
  if (e.key === 'Escape' && visible.value) {
    hidePopup()
  }
}

function handleScroll() {
  if (visible.value) hidePopup()
}

// Expose methods for parent
defineExpose({
  /** Get the currently selected text */
  getSelectedText: () => selectedText,
  /** Show success/error status */
  showStatus(msg, type = 'success') {
    statusMsg.value = msg
    statusClass.value = type
    setTimeout(() => {
      statusMsg.value = ''
      hidePopup()
    }, 1200)
  },
  hide: hidePopup,
})

onMounted(() => {
  document.addEventListener('mouseup', handleMouseUp)
  document.addEventListener('keydown', handleKeydown)
  if (props.containerEl) {
    props.containerEl.addEventListener('scroll', handleScroll)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('mouseup', handleMouseUp)
  document.removeEventListener('keydown', handleKeydown)
  if (props.containerEl) {
    props.containerEl.removeEventListener('scroll', handleScroll)
  }
})

// Watch containerEl changes for scroll listener
watch(() => props.containerEl, (newEl, oldEl) => {
  if (oldEl) oldEl.removeEventListener('scroll', handleScroll)
  if (newEl) newEl.addEventListener('scroll', handleScroll)
})
</script>

<style scoped>
.text-selection-popup {
  position: fixed;
  z-index: 9999;
  transform: translateY(-100%);
  background: #1e2a3a;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.05);
  padding: 6px;
  min-width: 180px;
  max-width: 240px;
  animation: popup-appear 0.15s ease-out;
}

@keyframes popup-appear {
  from {
    opacity: 0;
    transform: translateY(-100%) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(-100%) scale(1);
  }
}

.popup-section {
  padding: 2px 0;
}
.popup-section + .popup-section {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  margin-top: 2px;
  padding-top: 4px;
}

.popup-section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(255, 255, 255, 0.4);
  padding: 2px 8px;
  user-select: none;
}

.popup-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 2px 2px;
}

.popup-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  white-space: nowrap;
  width: 100%;
  text-align: left;
}
.popup-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}
.popup-btn:active {
  background: rgba(255, 255, 255, 0.15);
}

.popup-agent-list {
  max-height: 180px;
  overflow-y: auto;
  padding: 2px;
}
.agent-btn .agent-name {
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
}
.back-btn {
  opacity: 0.6;
  font-size: 11px;
  margin-top: 2px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 6px;
}
.back-btn:hover {
  opacity: 1;
}

.popup-status {
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  margin-top: 2px;
}
.popup-status.success {
  color: #66bb6a;
}
.popup-status.error {
  color: #ef5350;
}
</style>
