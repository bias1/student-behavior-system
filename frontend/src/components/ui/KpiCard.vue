<script setup>
/**
 * KPI 数据卡（用户指定的形态）：
 *   左上英文 eyebrow（STUDENTS） + 右上环比徽标（↗ 4.2%）
 *   中间大数字（CountUp） + 底部 Sparkline
 * delta 语义：正负着色默认"涨=绿"；预警数这类"涨=坏"的传 goodWhenUp=false。
 */
import CountUp from './CountUp.vue'
import USparkline from './USparkline.vue'
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-vue-next'

const props = defineProps({
  label: { type: String, required: true },        // 英文 eyebrow
  cn: { type: String, default: '' },              // 中文小注
  value: { type: Number, default: 0 },
  decimals: { type: Number, default: 0 },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
  delta: { type: Number, default: null },         // 百分比数值，如 4.2 / -8.3
  goodWhenUp: { type: Boolean, default: true },
  spark: { type: Array, default: () => [] },
  color: { type: String, default: 'var(--ci-cyan)' },
  hint: { type: String, default: '' },
  clickable: Boolean,
  loading: Boolean,
})
defineEmits(['click'])
</script>

<template>
  <div v-if="loading" class="kpi is-skel" />
  <div v-else class="kpi" :class="{ clickable }" @click="clickable && $emit('click')">
    <div class="kpi__top">
      <span class="ci-caps">{{ label }}</span>
      <span
        v-if="delta !== null && Number.isFinite(delta)"
        class="kpi__delta"
        :class="delta === 0 ? 'flat' : (delta > 0) === goodWhenUp ? 'up' : 'down'"
      >
        <ArrowUpRight v-if="delta > 0" :size="13" />
        <ArrowDownRight v-else-if="delta < 0" :size="13" />
        <Minus v-else :size="13" />
        {{ Math.abs(delta).toFixed(1) }}%
      </span>
    </div>
    <div class="kpi__value" :style="{ color: 'var(--ci-text)' }">
      <CountUp :value="value" :decimals="decimals" :prefix="prefix" :suffix="suffix" />
    </div>
    <p v-if="cn || hint" class="kpi__cn">{{ hint || cn }}</p>
    <USparkline v-if="spark.length > 1" :values="spark" :color="color" :height="30" class="kpi__spark" />
  </div>
</template>

<style scoped>
.kpi {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--sp-4) var(--sp-5) var(--sp-3);
  background: var(--ci-surface);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-lg);
  min-height: 132px;
  transition:
    border-color var(--dur) var(--ease),
    transform var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}
.kpi:hover {
  border-color: var(--ci-border-strong);
  transform: translateY(-1px);
  box-shadow: var(--ci-shadow-2);
}
.kpi.clickable {
  cursor: pointer;
}
.kpi.is-skel {
  background: linear-gradient(100deg, var(--ci-surface) 40%, var(--ci-surface-3) 50%, var(--ci-surface) 60%);
  background-size: 220% 100%;
  animation: ci-shimmer 1.4s linear infinite;
}

.kpi__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.kpi__value {
  font-size: 30px;
  line-height: 1.25;
  margin-top: 2px;
}
.kpi__cn {
  margin: 0;
  font-size: 12px;
  color: var(--ci-text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kpi__spark {
  margin-top: auto;
}

.kpi__delta {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  font-weight: 600;
  padding: 1px 7px 1px 4px;
  border-radius: var(--r-full);
}
.kpi__delta.up {
  color: var(--ci-success);
  background: var(--ci-success-soft);
}
.kpi__delta.down {
  color: var(--ci-danger);
  background: var(--ci-danger-soft);
}
.kpi__delta.flat {
  color: var(--ci-text-2);
  background: rgba(255, 255, 255, 0.05);
}
</style>
