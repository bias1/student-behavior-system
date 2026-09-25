<script setup>
/**
 * 语义徽标：tone = neutral | cyan | primary | success | warning | danger
 * dot=true 时左侧带状态圆点；级别类徽标务必同时带文字（无障碍：颜色不是唯一通道）。
 */
defineProps({
  tone: { type: String, default: 'neutral' },
  dot: Boolean,
})
</script>

<template>
  <span class="ci-badge" :class="`t-${tone}`">
    <i v-if="dot" class="ci-badge__dot" />
    <slot />
  </span>
</template>

<style scoped>
.ci-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 18px;
  border-radius: var(--r-full);
  white-space: nowrap;
}
.ci-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.t-neutral {
  color: var(--ci-text-2);
  background: rgba(255, 255, 255, 0.06);
}
.t-cyan {
  color: var(--ci-cyan);
  background: var(--ci-cyan-soft);
}
.t-primary {
  color: #b3a8ff;
  background: var(--ci-primary-soft);
}
.t-success {
  color: var(--ci-success);
  background: var(--ci-success-soft);
}
.t-warning {
  color: var(--ci-warning);
  background: var(--ci-warning-soft);
}
.t-danger {
  color: var(--ci-danger);
  background: var(--ci-danger-soft);
}
</style>
