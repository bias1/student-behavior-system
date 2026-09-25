<script setup>
/**
 * 微型趋势线（KPI 卡底部）：纯 SVG，无图表实例开销。
 * viewBox 固定 100x32 + preserveAspectRatio=none，随容器宽度拉伸；
 * 数据 <2 个点时整体不渲染（没趋势可言）。
 */
import { computed } from 'vue'

const props = defineProps({
  values: { type: Array, default: () => [] },
  color: { type: String, default: 'var(--ci-cyan)' },
  height: { type: Number, default: 32 },
  fill: { type: Boolean, default: true },
})

const uid = `sp-${Math.random().toString(36).slice(2, 8)}`

const path = computed(() => {
  const vs = (props.values || []).filter((v) => Number.isFinite(v))
  if (vs.length < 2) return null
  const min = Math.min(...vs)
  const max = Math.max(...vs)
  const span = max - min || 1
  const step = 100 / (vs.length - 1)
  const pts = vs.map((v, i) => [i * step, 28 - ((v - min) / span) * 24 + 2])
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `M0,32 L${line.replace(/ /g, ' L')} L100,32 Z`
  return { line, area, last: pts[pts.length - 1] }
})
</script>

<template>
  <svg v-if="path" class="ci-spark" :height="height" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <linearGradient :id="uid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="currentColor" stop-opacity="0.28" />
        <stop offset="100%" stop-color="currentColor" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path v-if="fill" :d="path.area" :fill="`url(#${uid})`" :color="color" stroke="none" />
    <polyline :points="path.line" fill="none" :stroke="color" stroke-width="1.6" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round" />
    <circle :cx="path.last[0]" :cy="path.last[1]" r="2" :fill="color" vector-effect="non-scaling-stroke" />
  </svg>
</template>

<style scoped>
.ci-spark {
  display: block;
  width: 100%;
  overflow: visible;
}
</style>
