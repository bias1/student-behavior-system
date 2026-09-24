<script setup>
/** 指标卡：大屏顶部 4 张，数值用等宽字体 + 入场动画，副行放同比/占比等补充口径 */
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], default: 0 },
  unit: { type: String, default: '' },
  hint: { type: String, default: '' },
  icon: { type: String, default: 'DataLine' },     // Element Plus 图标组件名
  color: { type: String, default: '#37e2f0' },
  precision: { type: Number, default: 2 },
  thousands: { type: Boolean, default: true },
})

const display = computed(() => {
  const v = props.value
  if (typeof v !== 'number') return v ?? '--'
  const s = props.precision >= 0 ? v.toFixed(props.precision) : String(v)
  if (!props.thousands) return s
  // 只在整数部分加分位符，小数部分原样保留
  const [i, d] = s.split('.')
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d ? '.' + d : '')
})
</script>

<template>
  <div class="stat-card sb-panel">
    <div class="stat-card__icon" :style="{ color, boxShadow: `inset 0 0 0 1px ${color}33` }">
      <el-icon :size="22"><component :is="icon" /></el-icon>
    </div>
    <div class="stat-card__main">
      <div class="stat-card__label">{{ label }}</div>
      <div class="stat-card__value sb-num" :style="{ color }">
        {{ display }}<em v-if="unit" class="stat-card__unit">{{ unit }}</em>
      </div>
      <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  height: 100%;
}

.stat-card__icon {
  width: 46px;
  height: 46px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
}

.stat-card__main {
  min-width: 0;
}

.stat-card__label {
  font-size: clamp(12px, 0.75vw, 15px);
  color: var(--sb-text-dim);
  letter-spacing: 1px;
}

.stat-card__value {
  font-size: clamp(22px, 1.6vw, 32px);
  font-weight: 700;
  line-height: 1.25;
  text-shadow: 0 0 14px rgba(55, 226, 240, 0.25);
  white-space: nowrap;
}

.stat-card__unit {
  font-style: normal;
  font-size: 0.5em;
  margin-left: 4px;
  color: var(--sb-text-dim);
}

.stat-card__hint {
  font-size: 12px;
  color: var(--sb-text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
