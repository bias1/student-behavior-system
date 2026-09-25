<script setup>
/**
 * 骨架屏块：给卡片/表格行占位。默认一行文本高；传 h/w 定制。
 */
defineProps({
  w: { type: String, default: '100%' },
  h: { type: String, default: '14px' },
  r: { type: String, default: '6px' },
  lines: { type: Number, default: 0 },       // >0 时渲染多行，末行 60% 宽更像段落
})
</script>

<template>
  <div v-if="!lines" class="ci-sk" :style="{ width: w, height: h, borderRadius: r }" />
  <div v-else class="ci-sk-stack">
    <div v-for="i in lines" :key="i" class="ci-sk" :style="{ width: i === lines ? '58%' : '100%', borderRadius: r }" />
  </div>
</template>

<style scoped>
.ci-sk {
  background: linear-gradient(100deg, var(--ci-surface-2) 40%, var(--ci-surface-3) 50%, var(--ci-surface-2) 60%);
  background-size: 220% 100%;
  animation: ci-shimmer 1.4s linear infinite;
}
.ci-sk-stack {
  display: grid;
  gap: 10px;
}
.ci-sk-stack .ci-sk {
  height: 14px;
}
</style>
