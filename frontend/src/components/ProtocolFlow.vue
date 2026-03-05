<template>
  <div class="protocol-flow">
    <!-- Start node -->
    <div class="flow-node flow-start">
      <div class="flow-node-circle bg-success">
        <v-icon size="16" color="white">mdi-play</v-icon>
      </div>
      <span class="flow-label">Start</span>
    </div>
    <div class="flow-connector" />

    <!-- Steps -->
    <template v-for="(step, idx) in steps" :key="idx">
      <!-- Action step -->
      <div v-if="step.type === 'action'" class="flow-node flow-action">
        <div class="flow-node-box flow-action-box">
          <div class="flow-node-header d-flex align-center ga-1">
            <v-icon size="14" color="primary">mdi-play-circle</v-icon>
            <span class="font-weight-bold text-primary">{{ step.name || 'Action' }}</span>
            <v-chip v-if="step.category && step.category !== 'other'" size="x-small" variant="tonal" :color="catColor(step.category)">{{ step.category }}</v-chip>
          </div>
          <div v-if="step.instruction" class="flow-instruction">{{ step.instruction }}</div>
        </div>
      </div>

      <!-- Decision step -->
      <div v-else-if="step.type === 'decision'" class="flow-node flow-decision">
        <div class="flow-node-diamond">
          <div class="flow-diamond-inner">
            <v-icon size="14" color="teal">mdi-help-rhombus</v-icon>
            <span class="font-weight-bold text-teal">{{ step.name || 'Decision' }}</span>
          </div>
        </div>
        <div v-if="step.instruction" class="flow-instruction flow-decision-instruction">{{ step.instruction }}</div>
        <div v-if="step.exit_condition" class="flow-condition">
          <v-icon size="12" color="amber">mdi-alert-circle</v-icon>
          <span>{{ step.exit_condition }}</span>
        </div>
      </div>

      <!-- Loop step -->
      <div v-else-if="step.type === 'loop'" class="flow-node flow-loop-wrapper">
        <div class="flow-loop-container">
          <!-- Loop header -->
          <div class="flow-loop-header d-flex align-center ga-2">
            <v-icon size="16" color="orange">mdi-refresh</v-icon>
            <span class="font-weight-bold text-orange">{{ step.name || 'Loop' }}</span>
            <v-chip size="x-small" color="orange" variant="tonal">max {{ step.max_iterations || '∞' }} iterations</v-chip>
          </div>
          <div v-if="step.instruction" class="flow-instruction px-3 pb-1">{{ step.instruction }}</div>

          <!-- Loop body -->
          <div class="flow-loop-body">
            <template v-for="(sub, si) in (step.steps || [])" :key="si">
              <div class="flow-connector flow-connector-sm" />
              <div v-if="sub.type === 'action'" class="flow-node flow-action flow-nested">
                <div class="flow-node-box flow-action-box flow-nested-box">
                  <div class="flow-node-header d-flex align-center ga-1">
                    <v-icon size="12" color="primary">mdi-play-circle</v-icon>
                    <span class="font-weight-bold text-primary text-body-2">{{ sub.name || 'Action' }}</span>
                  </div>
                  <div v-if="sub.instruction" class="flow-instruction text-caption">{{ sub.instruction }}</div>
                </div>
              </div>
              <div v-else-if="sub.type === 'decision'" class="flow-node flow-decision flow-nested">
                <div class="flow-node-diamond flow-nested-diamond">
                  <div class="flow-diamond-inner">
                    <v-icon size="12" color="teal">mdi-help-rhombus</v-icon>
                    <span class="font-weight-bold text-teal text-body-2">{{ sub.name || 'Decision' }}</span>
                  </div>
                </div>
                <div v-if="sub.exit_condition" class="flow-condition flow-condition-sm">
                  <v-icon size="10" color="amber">mdi-alert-circle</v-icon>
                  <span>{{ sub.exit_condition }}</span>
                </div>
              </div>
            </template>
          </div>

          <!-- Loop return arrow -->
          <div v-if="step.exit_condition" class="flow-loop-exit">
            <v-icon size="12" color="orange">mdi-arrow-left-top</v-icon>
            <span>{{ step.exit_condition }}</span>
          </div>
          <div class="flow-loop-return">
            <v-icon size="14" color="orange">mdi-arrow-u-left-top</v-icon>
            <span class="text-caption text-orange">Repeat</span>
          </div>
        </div>
      </div>

      <div v-if="idx < steps.length - 1" class="flow-connector" />
    </template>

    <!-- End node -->
    <div class="flow-connector" />
    <div class="flow-node flow-end">
      <div class="flow-node-circle bg-error">
        <v-icon size="16" color="white">mdi-stop</v-icon>
      </div>
      <span class="flow-label">End</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  steps: { type: Array, default: () => [] },
})

const catColor = (cat) => ({
  analysis: 'deep-purple', planning: 'indigo', execution: 'blue',
  verification: 'green', output: 'cyan', other: 'grey',
}[cat] || 'grey')
</script>

<style scoped>
.protocol-flow {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 8px;
}

/* Connector line */
.flow-connector {
  width: 2px;
  height: 24px;
  background: rgba(255,255,255,0.2);
  position: relative;
}
.flow-connector::after {
  content: '';
  position: absolute;
  bottom: -4px;
  left: -3px;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid rgba(255,255,255,0.2);
}
.flow-connector-sm { height: 14px; }

/* Node base */
.flow-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 500px;
}
.flow-nested { max-width: 420px; }

/* Start / End circle */
.flow-node-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.flow-label {
  font-size: 11px;
  color: rgba(255,255,255,0.5);
  margin-top: 4px;
}

/* Action box */
.flow-node-box {
  width: 100%;
  border-radius: 8px;
  padding: 10px 14px;
  background: rgba(33,150,243,0.08);
  border: 1px solid rgba(33,150,243,0.25);
}
.flow-nested-box {
  padding: 8px 10px;
  background: rgba(33,150,243,0.05);
}
.flow-node-header {
  font-size: 13px;
}
.flow-instruction {
  font-size: 12px;
  color: rgba(255,255,255,0.6);
  margin-top: 4px;
  white-space: pre-wrap;
  line-height: 1.4;
}

/* Decision diamond */
.flow-decision { align-items: center; }
.flow-node-diamond {
  width: 100%;
  padding: 10px 14px;
  background: rgba(0,150,136,0.08);
  border: 1px solid rgba(0,150,136,0.25);
  border-radius: 4px;
  clip-path: none;
  position: relative;
}
.flow-nested-diamond { padding: 8px 10px; }
.flow-diamond-inner {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.flow-decision-instruction {
  text-align: center;
  max-width: 400px;
}
.flow-condition {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgba(255,193,7,0.8);
  margin-top: 4px;
}
.flow-condition-sm { font-size: 10px; }

/* Loop container */
.flow-loop-wrapper { width: 100%; max-width: 540px; }
.flow-loop-container {
  width: 100%;
  border: 2px dashed rgba(255,152,0,0.3);
  border-radius: 12px;
  padding: 12px;
  background: rgba(255,152,0,0.03);
}
.flow-loop-header { font-size: 13px; padding: 0 4px; }
.flow-loop-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 0;
}
.flow-loop-return {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
  padding: 4px 8px 0;
  font-size: 12px;
}
.flow-loop-exit {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px 0;
  font-size: 11px;
  color: rgba(255,152,0,0.7);
}
</style>
