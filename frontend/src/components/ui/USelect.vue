<script setup>
/**
 * 下拉选择：v-model + clearable + 可选搜索（filterable）。
 * 浮层用 Teleport + fixed 定位（组件小、页面 grid 里不会被 overflow 裁切），
 * 外点/esc 关闭；已选项高亮。不追求 EP Select 的全部能力，覆盖现有筛选场景即可。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Check, ChevronDown, Search } from 'lucide-vue-next'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },   // [{ value, label }]
  placeholder: { type: String, default: '请选择' },
  clearable: { type: Boolean, default: true },
  filterable: Boolean,
  width: { type: String, default: '160px' },
})
const emit = defineEmits(['update:modelValue', 'change'])

const root = ref()
const panel = ref()
const open = ref(false)
const query = ref('')
const dropStyle = ref({})

const current = computed(() => props.options.find((o) => o.value === props.modelValue))
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? props.options.filter((o) => String(o.label).toLowerCase().includes(q)) : props.options
})

async function toggle() {
  open.value = !open.value
  if (open.value) {
    const r = root.value.getBoundingClientRect()
    dropStyle.value = { left: `${r.left}px`, top: `${r.bottom + 6}px`, width: `${Math.max(r.width, 200)}px` }
    query.value = ''
    await nextTick()
    panel.value?.querySelector('input')?.focus()
  }
}

function pick(o) {
  emit('update:modelValue', o.value)
  emit('change', o.value)
  open.value = false
}

function clear(e) {
  e.stopPropagation()
  emit('update:modelValue', '')
  emit('change', '')
}

function onDocClick(e) {
  if (open.value && !root.value?.contains(e.target) && !panel.value?.contains(e.target)) open.value = false
}
function onDocKey(e) {
  if (e.key === 'Escape') open.value = false
}
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onDocKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onDocKey)
})
// 选项异步加载后若面板开着，重算一次位置即可（简单起见不动）
watch(() => props.options, () => { if (!props.options.some((o) => o.value === props.modelValue) && props.modelValue !== '') emit('update:modelValue', '') })
</script>

<template>
  <div ref="root" class="ci-select" :style="{ width }" @click="toggle">
    <span class="ci-select__val" :class="{ 'is-ph': !current }">{{ current ? current.label : placeholder }}</span>
    <button v-if="clearable && modelValue !== ''" class="ci-select__clear" @click="clear">×</button>
    <ChevronDown v-else :size="14" class="ci-select__arrow" :class="{ 'is-open': open }" />

    <Teleport to="body">
      <div v-if="open" ref="panel" class="ci-select__panel" :style="dropStyle">
        <div v-if="filterable" class="ci-select__search">
          <Search :size="13" />
          <input v-model="query" placeholder="搜索…" @click.stop />
        </div>
        <div class="ci-select__list">
          <div v-for="o in filtered" :key="o.value" class="ci-select__opt" :class="{ 'is-on': o.value === modelValue }" @click.stop="pick(o)">
            {{ o.label }}
            <Check v-if="o.value === modelValue" :size="13" class="ci-select__tick" />
          </div>
          <div v-if="!filtered.length" class="ci-select__none">无匹配项</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.ci-select {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  cursor: pointer;
  user-select: none;
  transition: border-color var(--dur-fast) var(--ease);
}
.ci-select:hover {
  border-color: var(--ci-border-strong);
}
.ci-select__val {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.ci-select__val.is-ph {
  color: var(--ci-text-3);
}
.ci-select__arrow {
  color: var(--ci-text-3);
  transition: transform var(--dur-fast) var(--ease);
  flex: none;
}
.ci-select__arrow.is-open {
  transform: rotate(180deg);
}
.ci-select__clear {
  border: 0;
  background: transparent;
  color: var(--ci-text-3);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}
.ci-select__clear:hover {
  color: var(--ci-text);
}
</style>

<style>
/* 面板被 Teleport 到 body，scoped 无效，这里收进全局但用独立类名隔离 */
.ci-select__panel {
  position: fixed;
  z-index: var(--z-modal);
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border-strong);
  border-radius: var(--r-md);
  box-shadow: var(--ci-shadow-pop);
  padding: 6px;
  animation: ci-fade-up 0.14s var(--ease) both;
}
.ci-select__search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  color: var(--ci-text-3);
  border-bottom: 1px solid var(--ci-border);
  margin-bottom: 4px;
}
.ci-select__search input {
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ci-text);
  font: inherit;
  font-size: 13px;
}
.ci-select__list {
  max-height: 264px;
  overflow: auto;
}
.ci-select__opt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  font-size: 13px;
  border-radius: 7px;
  cursor: pointer;
  color: var(--ci-text);
}
.ci-select__opt:hover {
  background: var(--ci-surface-3);
}
.ci-select__opt.is-on {
  color: var(--ci-cyan);
  background: var(--ci-cyan-soft);
}
.ci-select__tick {
  flex: none;
}
.ci-select__none {
  padding: 10px;
  text-align: center;
  color: var(--ci-text-3);
  font-size: 12px;
}
</style>
