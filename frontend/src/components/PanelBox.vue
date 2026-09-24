<script setup>
/** 面板外壳：统一标题栏 + 右侧插槽（放筛选/按钮）+ 内容区，大屏所有区块共用 */
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
})
</script>

<template>
  <!-- 占位靠 grid 拉伸：不用主件上写行内 style，class/style 由 Vue 默认 fallthrough 到根元素 -->
  <section class="sb-panel">
    <header class="sb-panel__title">
      <span>{{ title }}<em v-if="subtitle" class="sb-muted"> {{ subtitle }}</em></span>
      <span class="sb-panel__extra"><slot name="extra" /></span>
    </header>
    <div class="sb-panel__body"><slot /></div>
  </section>
</template>

<style scoped>
.sb-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.sb-panel__body {
  flex: 1;
  min-height: 0;         /* 关键：不设 0 时内部图表会把面板撑高、溢出栅格行 */
  padding: 6px 10px 10px;
}

.sb-panel__extra {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 400;
  letter-spacing: 0;
}

em {
  font-style: normal;
  margin-left: 6px;
}
</style>
