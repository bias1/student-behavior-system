<script setup>
/**
 * 分段控件：时间窗口（今日/7天/30天/90天）、列表/卡片视图切换等场景。
 * options: [{ value, label }]，v-model 绑定 value。
 */
defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  size: { type: String, default: 'md' },       // sm | md
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <div class="ci-seg" :class="`s-${size}`" role="tablist">
    <button
      v-for="o in options"
      :key="o.value"
      role="tab"
      class="ci-seg__item"
      :class="{ 'is-active': o.value === modelValue }"
      @click="emit('update:modelValue', o.value)"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.ci-seg {
  display: inline-flex;
  padding: 3px;
  gap: 2px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
}
.ci-seg__item {
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--ci-text-2);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
  white-space: nowrap;
}
.ci-seg__item:hover {
  color: var(--ci-text);
}
.ci-seg__item.is-active {
  background: var(--ci-surface-3);
  color: var(--ci-text);
  font-weight: 600;
  box-shadow: inset 0 0 0 1px var(--ci-border-strong);
}
.s-md .ci-seg__item {
  height: 26px;
  padding: 0 12px;
  font-size: 12.5px;
}
.s-sm .ci-seg__item {
  height: 22px;
  padding: 0 9px;
  font-size: 12px;
}
</style>
