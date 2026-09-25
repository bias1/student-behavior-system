/**
 * Promise 化确认框（替代 ElMessageBox.confirm）：
 *   import { confirmDialog } from '@/components/ui/useConfirm'
 *   if (!(await confirmDialog({ title:'处置确认', message:'......', confirmText:'确定', danger:true }))) return
 * 每次调用挂载独立实例，resolve 后自动卸载，无全局状态。
 */
import { createApp, h } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'

export function confirmDialog({
  title = '确认操作',
  message = '',
  confirmText = '确定',
  cancelText = '取消',
  danger = false,
} = {}) {
  return new Promise((resolve) => {
    const el = document.createElement('div')
    document.body.appendChild(el)
    const app = createApp({
      render: () =>
        h(ConfirmDialog, {
          title,
          message,
          confirmText,
          cancelText,
          danger,
          onResolve: (v) => {
            resolve(v)
            // 等出场动画结束再卸载（固定 240ms，与 token 动效同量级）
            setTimeout(() => {
              app.unmount()
              el.remove()
            }, 240)
          },
        }),
    })
    app.mount(el)
  })
}
