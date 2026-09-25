<script setup>
/**
 * 空态/错误态统一出口：tone = empty | error | search；
 * error 时给 #action 插槽放"重试"按钮（页面自己决定动作）。
 */
import { FileSearch, Inbox, TriangleAlert } from 'lucide-vue-next'

defineProps({
  tone: { type: String, default: 'empty' },
  title: { type: String, default: '暂无数据' },
  hint: { type: String, default: '' },
})
</script>

<template>
  <div class="ci-empty">
    <span class="ci-empty__icon" :class="`t-${tone}`">
      <TriangleAlert v-if="tone === 'error'" :size="22" />
      <FileSearch v-else-if="tone === 'search'" :size="22" />
      <Inbox v-else :size="22" />
    </span>
    <p class="ci-empty__title">{{ title }}</p>
    <p v-if="hint" class="ci-empty__hint">{{ hint }}</p>
    <div v-if="$slots.action" class="ci-empty__action"><slot name="action" /></div>
  </div>
</template>

<style scoped>
.ci-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 36px 16px;
  text-align: center;
}
.ci-empty__icon {
  display: inline-flex;
  padding: 12px;
  margin-bottom: 6px;
  border-radius: var(--r-full);
  background: var(--ci-surface-2);
  color: var(--ci-text-3);
}
.t-error {
  color: var(--ci-danger);
  background: var(--ci-danger-soft);
}
.ci-empty__title {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ci-text-2);
}
.ci-empty__hint {
  margin: 0;
  font-size: 12px;
  color: var(--ci-text-3);
  max-width: 360px;
}
.ci-empty__action {
  margin-top: 10px;
}
</style>
