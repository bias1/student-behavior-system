<script setup>
/**
 * 通用输入框：v-model + prefix 图标插槽 + 可清空。
 * 搜索场景：slot="prefix" 放 <Search :size="14"/>，@enter 绑查询。
 * 注意：focus/blur 必须在内层 input 上显式 emit——根元素是 div，
 * 而 focus/blur 不冒泡，父组件的 @focus 透传到 div 上根本不会触发。
 */
import { X } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  placeholder: { type: String, default: '' },
  type: { type: String, default: 'text' },
  disabled: Boolean,
  width: { type: String, default: '' },          // 如 '320px'，不设则走 CSS 默认 min-width
})
const emit = defineEmits(['update:modelValue', 'enter', 'clear', 'focus', 'blur'])

function onInput(e) {
  emit('update:modelValue', e.target.value)
}
</script>

<template>
  <div
    class="ci-input"
    :class="{ 'is-disabled': props.disabled }"
    :style="props.width ? { width: props.width, minWidth: props.width } : undefined"
  >
    <span v-if="$slots.prefix" class="ci-input__prefix"><slot name="prefix" /></span>
    <input
      :value="props.modelValue"
      :placeholder="props.placeholder"
      :type="props.type"
      :disabled="props.disabled"
      @input="onInput"
      @keyup.enter="emit('enter')"
      @focus="emit('focus')"
      @blur="emit('blur')"
    />
    <button
      v-if="!props.disabled && String(props.modelValue || '') !== ''"
      class="ci-input__clear"
      type="button"
      aria-label="清空"
      @click="emit('update:modelValue', ''); emit('clear')"
    >
      <X :size="13" />
    </button>
  </div>
</template>

<style scoped>
.ci-input {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  height: 32px;
  min-width: 180px;
  padding: 0 10px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  transition: border-color var(--dur-fast) var(--ease);
}
.ci-input:focus-within {
  border-color: var(--ci-primary);
}
.ci-input.is-disabled {
  opacity: 0.55;
}
.ci-input__prefix {
  display: inline-flex;
  color: var(--ci-text-3);
}
.ci-input input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ci-text);
  font: inherit;
  color-scheme: dark;
}
.ci-input input::placeholder {
  color: var(--ci-text-3);
}
.ci-input__clear {
  display: inline-flex;
  border: 0;
  padding: 2px;
  background: transparent;
  color: var(--ci-text-3);
  cursor: pointer;
  border-radius: var(--r-full);
}
.ci-input__clear:hover {
  color: var(--ci-text);
  background: var(--ci-surface-3);
}
</style>
