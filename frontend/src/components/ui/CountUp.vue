<script setup>
/**
 * 数字滚动（Count Up）：值变化时 rAF 从上一值缓动到新值，仅首次挂载从 0 起跳。
 * 尊重 prefers-reduced-motion；非整数用 decimals 固定小数位。
 * 输出带千分位与 tabular-nums（跳宽问题是数字刷新的大忌）。
 */
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  decimals: { type: Number, default: 0 },
  duration: { type: Number, default: 700 },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
})

const shown = ref(0)
let raf = 0
const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function animate(to) {
  cancelAnimationFrame(raf)
  const from = shown.value
  if (reduced || props.duration <= 0 || !Number.isFinite(to)) {
    shown.value = Number.isFinite(to) ? to : 0
    return
  }
  const t0 = performance.now()
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / props.duration)
    const ease = 1 - Math.pow(1 - p, 3)            // easeOutCubic：起步快、落点稳
    shown.value = from + (to - from) * ease
    if (p < 1) raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
}

watch(() => props.value, (v) => animate(Number(v) || 0), { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(raf))

function fmt(n) {
  return (Number.isFinite(n) ? n : 0).toLocaleString('zh-CN', {
    minimumFractionDigits: props.decimals,
    maximumFractionDigits: props.decimals,
  })
}
</script>

<template>
  <span class="ci-count ci-num">{{ prefix }}{{ fmt(shown) }}{{ suffix }}</span>
</template>

<style scoped>
.ci-count {
  font-weight: 700;
  letter-spacing: -0.01em;
}
</style>
