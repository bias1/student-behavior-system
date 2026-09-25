<script setup>
/**
 * 通用按钮：primary（紫底）/ soft（主色浅底）/ ghost（描边）/ danger / text
 * loading 时内置转圈并禁用点击；图标按钮传 class="is-icon"（默认插槽放 lucide 组件）。
 */
defineProps({
  variant: { type: String, default: 'primary' },
  size: { type: String, default: 'md' },       // sm | md
  loading: Boolean,
  disabled: Boolean,
  type: { type: String, default: 'button' },
})
</script>

<template>
  <button
    :type="type"
    class="ci-btn"
    :class="[`v-${variant}`, `s-${size}`, { 'is-loading': loading }]"
    :disabled="disabled || loading"
  >
    <span v-if="loading" class="ci-btn__spin" aria-hidden="true" />
    <slot />
  </button>
</template>

<style scoped>
.ci-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  border: 1px solid transparent;
  border-radius: var(--r-md);
  cursor: pointer;
  white-space: nowrap;
  transition:
    background var(--dur-fast) var(--ease),
    border-color var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease),
    transform var(--dur-fast) var(--ease);
}
.ci-btn:active:not(:disabled) {
  transform: translateY(1px);
}
.ci-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.s-md {
  height: 34px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
}
.s-sm {
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 500;
}

.v-primary {
  background: var(--ci-primary);
  color: #fff;
}
.v-primary:hover:not(:disabled) {
  background: #8d7fff;
}
.v-soft {
  background: var(--ci-primary-soft);
  color: #b3a8ff;
}
.v-soft:hover:not(:disabled) {
  background: rgba(124, 108, 255, 0.22);
}
.v-ghost {
  background: transparent;
  border-color: var(--ci-border-strong);
  color: var(--ci-text);
}
.v-ghost:hover:not(:disabled) {
  background: var(--ci-surface-3);
  border-color: rgba(255, 255, 255, 0.22);
}
.v-danger {
  background: var(--ci-danger-soft);
  color: var(--ci-danger);
}
.v-danger:hover:not(:disabled) {
  background: rgba(255, 92, 124, 0.2);
}
.v-text {
  background: transparent;
  color: var(--ci-text-2);
  padding: 0 6px;
}
.v-text:hover:not(:disabled) {
  color: var(--ci-text);
}

.ci-btn__spin {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: ci-rotate 0.7s linear infinite;
}
@keyframes ci-rotate {
  to {
    transform: rotate(360deg);
  }
}
</style>
