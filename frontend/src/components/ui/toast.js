import { createApp, reactive } from 'vue'
import ToastHost from './ToastHost.vue'

/**
 * 全局轻提示（替代 EP 的 ElMessage）：
 *   import { toast } from '@/components/ui/toast'
 *   toast.success('处置成功') / toast.error(msg) / toast.info(msg)
 * 首次调用才挂载宿主，纯离线页面不产生任何 DOM。
 */
const state = reactive({ items: [] })
let seq = 0
let mounted = false

function ensureMounted() {
  if (mounted) return
  mounted = true
  const el = document.createElement('div')
  document.body.appendChild(el)
  createApp(ToastHost, { items: state.items }).mount(el)
}

function push(msg, type = 'info', duration = 2800) {
  if (!msg) return
  ensureMounted()
  const id = ++seq
  // 同屏最多 4 条：新消息挤掉最旧的一条，避免错误风暴糊满屏幕
  if (state.items.length >= 4) state.items.shift()
  state.items.push({ id, msg: String(msg), type })
  setTimeout(() => {
    const i = state.items.findIndex((t) => t.id === id)
    if (i >= 0) state.items.splice(i, 1)
  }, duration)
}

export const toast = {
  info: (m, d) => push(m, 'info', d),
  success: (m, d) => push(m, 'success', d),
  error: (m, d) => push(m, 'error', d ?? 3600),
  warn: (m, d) => push(m, 'warn', d),
}

export default toast
