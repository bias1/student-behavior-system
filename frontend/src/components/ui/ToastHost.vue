<script setup>
/**
 * toast 宿主：由 toast.js 懒挂载，页面不直接引用。
 * 顶部居中，同屏最多叠 4 条，进/出场只做透明度+微位移。
 */
defineProps({
  items: { type: Array, required: true },
})
</script>

<template>
  <Teleport to="body">
    <div class="ci-toasts">
      <TransitionGroup name="ci-toast">
        <div v-for="t in items" :key="t.id" class="ci-toast" :class="`t-${t.type}`">
          <i class="ci-toast__bar" />
          {{ t.msg }}
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.ci-toasts {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  pointer-events: none;
}
.ci-toast {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  font-size: 13px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border-strong);
  border-radius: var(--r-md);
  box-shadow: var(--ci-shadow-pop);
  color: var(--ci-text);
}
.ci-toast__bar {
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--ci-cyan);
}
.t-success .ci-toast__bar {
  background: var(--ci-success);
}
.t-error .ci-toast__bar {
  background: var(--ci-danger);
}
.t-warn .ci-toast__bar {
  background: var(--ci-warning);
}

.ci-toast-enter-active,
.ci-toast-leave-active {
  transition: all var(--dur) var(--ease);
}
.ci-toast-enter-from,
.ci-toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
