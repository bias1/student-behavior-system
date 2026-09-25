<script setup>
/**
 * 分页：页码窗口 ±2 + 首尾 + 省略号；右侧可传每页条数。
 * v-model:page / v-model:size，total 为总条数。
 */
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps({
  page: { type: Number, default: 1 },
  size: { type: Number, default: 20 },
  total: { type: Number, default: 0 },
})
const emit = defineEmits(['update:page', 'change'])

const pages = computed(() => Math.max(1, Math.ceil(props.total / props.size)))

// 页码序列：'…' 表示省略段（窗口算法保证首尾恒在）
const items = computed(() => {
  const n = pages.value
  const cur = props.page
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1)
  const set = new Set([1, n, cur - 1, cur, cur + 1])
  const arr = [...set].filter((p) => p >= 1 && p <= n).sort((a, b) => a - b)
  const out = []
  let prev = 0
  for (const p of arr) {
    if (p - prev > 1) out.push('…')
    out.push(p)
    prev = p
  }
  return out
})

function go(p) {
  const v = Math.min(Math.max(1, p), pages.value)
  if (v === props.page) return
  emit('update:page', v)
  emit('change', v)
}
</script>

<template>
  <div class="ci-pager">
    <span class="ci-pager__info ci-num">共 {{ total.toLocaleString('zh-CN') }} 条 · 第 {{ page }}/{{ pages }} 页</span>
    <div class="ci-pager__btns">
      <button class="ci-pager__btn" :disabled="page <= 1" aria-label="上一页" @click="go(page - 1)">
        <ChevronLeft :size="14" />
      </button>
      <button
        v-for="(p, i) in items"
        :key="`${p}-${i}`"
        class="ci-pager__page ci-num"
        :class="{ 'is-on': p === page, 'is-gap': p === '…' }"
        :disabled="p === '…'"
        @click="go(p)"
      >
        {{ p }}
      </button>
      <button class="ci-pager__btn" :disabled="page >= pages" aria-label="下一页" @click="go(page + 1)">
        <ChevronRight :size="14" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.ci-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  flex-wrap: wrap;
  padding-top: var(--sp-3);
  font-size: 12.5px;
}
.ci-pager__info {
  color: var(--ci-text-2);
}
.ci-pager__btns {
  display: flex;
  align-items: center;
  gap: 4px;
}
.ci-pager__btn,
.ci-pager__page {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 26px;
  padding: 0 6px;
  border: 1px solid var(--ci-border);
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ci-text-2);
  font: inherit;
  cursor: pointer;
  transition: all var(--dur-fast) var(--ease);
}
.ci-pager__btn:hover:not(:disabled),
.ci-pager__page:hover:not(:disabled):not(.is-on) {
  color: var(--ci-text);
  background: var(--ci-surface-2);
}
.ci-pager__btn:disabled,
.ci-pager__page:disabled {
  opacity: 0.4;
  cursor: default;
}
.ci-pager__page.is-on {
  background: var(--ci-primary);
  border-color: var(--ci-primary);
  color: #fff;
  font-weight: 600;
}
.ci-pager__page.is-gap {
  border-color: transparent;
  opacity: 0.6;
}
</style>
