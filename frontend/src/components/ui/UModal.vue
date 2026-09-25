<script setup>
/**
 * 模态框：v-model:open 控制，teleport 到 body，esc/遮罩关闭，打开时锁 body 滚动。
 * CommandPalette、确认框都基于它，尺寸用 width 传。
 */
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({
  open: Boolean,
  title: { type: String, default: '' },
  width: { type: String, default: '520px' },
  closeOnMask: { type: Boolean, default: true },
})
const emit = defineEmits(['update:open', 'close'])

function close() {
  emit('update:open', false)
  emit('close')
}

function onKey(e) {
  if (e.key === 'Escape' && props.open) close()
}
// 监听只挂一次：多实例共存时各自只在 open=true 时响应自己的 close
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
    <Transition name="ci-modal">
      <div v-if="open" class="ci-modal__mask" @click.self="closeOnMask && close()">
        <div class="ci-modal__panel" :style="{ width }" role="dialog" aria-modal="true">
          <header v-if="title || $slots.head" class="ci-modal__head">
            <slot name="head"><h3>{{ title }}</h3></slot>
            <button class="ci-modal__x" aria-label="关闭" @click="close"><X :size="16" /></button>
          </header>
          <div class="ci-modal__body"><slot /></div>
          <footer v-if="$slots.footer" class="ci-modal__foot"><slot name="footer" /></footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ci-modal__mask {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 12vh 16px 16px;
  background: rgba(4, 6, 10, 0.62);
  backdrop-filter: blur(4px);
}
.ci-modal__panel {
  max-width: 94vw;
  max-height: 76vh;
  display: flex;
  flex-direction: column;
  background: var(--ci-surface);
  border: 1px solid var(--ci-border-strong);
  border-radius: var(--r-lg);
  box-shadow: var(--ci-shadow-pop);
}
.ci-modal__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--sp-5);
  border-bottom: 1px solid var(--ci-border);
}
.ci-modal__head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.ci-modal__x {
  border: 0;
  background: transparent;
  color: var(--ci-text-3);
  cursor: pointer;
  display: inline-flex;
  padding: 4px;
  border-radius: var(--r-sm);
}
.ci-modal__x:hover {
  color: var(--ci-text);
  background: var(--ci-surface-3);
}
.ci-modal__body {
  padding: var(--sp-5);
  overflow: auto;
}
.ci-modal__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  border-top: 1px solid var(--ci-border);
}

.ci-modal-enter-active,
.ci-modal-leave-active {
  transition: opacity var(--dur-fast) var(--ease);
}
.ci-modal-enter-active .ci-modal__panel,
.ci-modal-leave-active .ci-modal__panel {
  transition: transform var(--dur) var(--ease);
}
.ci-modal-enter-from,
.ci-modal-leave-to {
  opacity: 0;
}
.ci-modal-enter-from .ci-modal__panel {
  transform: translateY(10px) scale(0.985);
}
.ci-modal-leave-to .ci-modal__panel {
  transform: translateY(6px) scale(0.99);
}
</style>
