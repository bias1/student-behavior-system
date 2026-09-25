<script setup>
/**
 * 右侧抽屉：预警详情/簇成员等"看大对象"场景。v-model:open，esc/遮罩关闭。
 */
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({
  open: Boolean,
  title: { type: String, default: '' },
  width: { type: String, default: '560px' },
})
const emit = defineEmits(['update:open', 'close'])

function close() {
  emit('update:open', false)
  emit('close')
}
function onKey(e) {
  if (e.key === 'Escape' && props.open) close()
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
watch(
  () => props.open,
  (v) => {
    document.body.style.overflow = v ? 'hidden' : ''
  }
)
</script>

<template>
  <Teleport to="body">
    <Transition name="ci-drawer">
      <div v-if="open" class="ci-drawer__mask" @click.self="close()">
        <aside class="ci-drawer__panel" :style="{ width }" role="dialog" aria-modal="true">
          <header class="ci-drawer__head">
            <slot name="head"><h3>{{ title }}</h3></slot>
            <button class="ci-drawer__x" aria-label="关闭" @click="close"><X :size="16" /></button>
          </header>
          <div class="ci-drawer__body"><slot /></div>
          <footer v-if="$slots.footer" class="ci-drawer__foot"><slot name="footer" /></footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ci-drawer__mask {
  position: fixed;
  inset: 0;
  z-index: var(--z-drawer);
  background: rgba(4, 6, 10, 0.55);
  backdrop-filter: blur(3px);
}
.ci-drawer__panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  max-width: 94vw;
  display: flex;
  flex-direction: column;
  background: var(--ci-surface);
  border-left: 1px solid var(--ci-border-strong);
  box-shadow: var(--ci-shadow-pop);
}
.ci-drawer__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--ci-border);
}
.ci-drawer__head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.ci-drawer__x {
  border: 0;
  background: transparent;
  color: var(--ci-text-3);
  cursor: pointer;
  display: inline-flex;
  padding: 4px;
  border-radius: var(--r-sm);
}
.ci-drawer__x:hover {
  color: var(--ci-text);
  background: var(--ci-surface-3);
}
.ci-drawer__body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--sp-5);
}
.ci-drawer__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  border-top: 1px solid var(--ci-border);
}

.ci-drawer-enter-active,
.ci-drawer-leave-active {
  transition: opacity var(--dur) var(--ease);
}
.ci-drawer-enter-active .ci-drawer__panel,
.ci-drawer-leave-active .ci-drawer__panel {
  transition: transform var(--dur) var(--ease);
}
.ci-drawer-enter-from,
.ci-drawer-leave-to {
  opacity: 0;
}
.ci-drawer-enter-from .ci-drawer__panel,
.ci-drawer-leave-to .ci-drawer__panel {
  transform: translateX(24px);
}
</style>
