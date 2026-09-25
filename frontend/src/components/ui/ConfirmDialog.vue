<script setup>
/**
 * 确认框实体：由 useConfirm.js 命令式挂载，open 恒为 true，
 * 点按钮 emit('resolve', boolean) 后由宿主负责关场与卸载。
 */
import { onMounted, ref } from 'vue'
import UModal from './UModal.vue'
import UButton from './UButton.vue'
import { TriangleAlert } from 'lucide-vue-next'

const props = defineProps({
  title: String,
  message: String,
  confirmText: String,
  cancelText: String,
  danger: Boolean,
})
const emit = defineEmits(['resolve'])

const open = ref(false)
onMounted(() => {
  // 下一帧再开，保证 Transition 有入场动画
  requestAnimationFrame(() => (open.value = true))
})
</script>

<template>
  <UModal :open="open" :title="props.title" width="420px" :close-on-mask="false" @close="emit('resolve', false)">
    <div class="cf-body">
      <span v-if="props.danger" class="cf-icon"><TriangleAlert :size="18" /></span>
      <p class="cf-msg">{{ props.message }}</p>
    </div>
    <template #footer>
      <UButton variant="ghost" size="sm" @click="emit('resolve', false)">{{ props.cancelText }}</UButton>
      <UButton :variant="props.danger ? 'danger' : 'primary'" size="sm" @click="emit('resolve', true)">
        {{ props.confirmText }}
      </UButton>
    </template>
  </UModal>
</template>

<style scoped>
.cf-body {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.cf-icon {
  color: var(--ci-warning);
  display: inline-flex;
  padding-top: 2px;
}
.cf-msg {
  margin: 0;
  font-size: 13.5px;
  color: var(--ci-text);
  white-space: pre-line;
}
</style>
