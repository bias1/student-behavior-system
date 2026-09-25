<script setup>
/**
 * 日期范围选择：两个原生 date 输入的组合（color-scheme:dark 后原生日历也是深色）。
 * v-model 为 [start, end] 或 null；任一端变化即 emit，两端齐全才算有效值。
 */
import { Calendar } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: Array, default: null },
  width: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'change'])

function setPart(idx, val) {
  const cur = props.modelValue || ['', '']
  const next = [...cur]
  next[idx] = val || ''
  const out = next[0] && next[1] ? next : null
  emit('update:modelValue', out)
  emit('change', out)
}
</script>

<template>
  <div class="ci-range" :style="width ? { width } : null">
    <Calendar :size="13" class="ci-range__icon" />
    <input
      type="date"
      :value="props.modelValue?.[0] || ''"
      :max="props.modelValue?.[1] || undefined"
      @input="setPart(0, $event.target.value)"
    />
    <span class="ci-range__dash">→</span>
    <input
      type="date"
      :value="props.modelValue?.[1] || ''"
      :min="props.modelValue?.[0] || undefined"
      @input="setPart(1, $event.target.value)"
    />
    <button v-if="props.modelValue" class="ci-range__clear" @click="emit('update:modelValue', null); emit('change', null)">×</button>
  </div>
</template>

<style scoped>
.ci-range {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  transition: border-color var(--dur-fast) var(--ease);
}
.ci-range:focus-within {
  border-color: var(--ci-primary);
}
.ci-range__icon {
  color: var(--ci-text-3);
  flex: none;
}
.ci-range input {
  width: 130px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ci-text);
  font: inherit;
  font-size: 12.5px;
  color-scheme: dark;
}
.ci-range__dash {
  color: var(--ci-text-3);
}
.ci-range__clear {
  border: 0;
  background: transparent;
  color: var(--ci-text-3);
  cursor: pointer;
  font-size: 14px;
}
.ci-range__clear:hover {
  color: var(--ci-text);
}
</style>
