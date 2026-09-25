<script setup>
/**
 * 卡片容器（PanelBox 的继任者）：标题 + 英文副标 + 右上操作槽 + 内容。
 * hover 只做边框/阴影微变（克制原则），不做整卡发光。
 * allow-overflow：关掉根节点的 overflow 裁剪——卡片内有绝对定位浮层
 * （搜索建议、下拉面板）时必须开，否则超出卡身的部分被剪掉、显示不完整。
 */
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  padded: { type: Boolean, default: true },
  hoverable: { type: Boolean, default: true },
  allowOverflow: Boolean,
})
</script>

<template>
  <section class="ci-card" :class="{ 'no-hover': !hoverable, 'ci-card--float': allowOverflow }">
    <header v-if="title || $slots.extra" class="ci-card__head">
      <div>
        <h3 class="ci-card__title">{{ title }}</h3>
        <p v-if="subtitle" class="ci-card__sub">{{ subtitle }}</p>
      </div>
      <div class="ci-card__extra"><slot name="extra" /></div>
    </header>
    <div class="ci-card__body" :class="{ 'no-pad': !padded }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.ci-card {
  background: var(--ci-surface);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-lg);
  box-shadow: var(--ci-shadow-1);
  overflow: hidden;
  transition:
    border-color var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease),
    transform var(--dur) var(--ease);
}
.ci-card:not(.no-hover):hover {
  border-color: var(--ci-border-strong);
  box-shadow: var(--ci-shadow-2);
  transform: translateY(-1px);
}
/* 浮层裁剪开关：定义在 .ci-card 之后，同特异性靠顺序覆盖 overflow: hidden */
.ci-card--float {
  overflow: visible;
}

.ci-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  padding: var(--sp-4) var(--sp-5) 0;
}
.ci-card__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.ci-card__sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--ci-text-2);
}
.ci-card__extra {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: none;
}
.ci-card__body {
  padding: var(--sp-4) var(--sp-5) var(--sp-5);
}
.ci-card__body.no-pad {
  padding: 0;
}
</style>
