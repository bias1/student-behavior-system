import { createApp } from 'vue'

// 本地字体：Inter Variable 随构建产物打包，离线/内网环境可用；中文走系统栈（见 theme.css --font-sans）
import '@fontsource-variable/inter'

import '@/styles/theme.css'
// ECharts 不再在入口副作用导入：主题注册在 src/plugins/echarts.js 模块内完成，
// 由 BaseChart 随懒加载的路由 chunk 按需引入，登录页/纯表格页不再被迫等图表包

import App from './App.vue'
import router from './router'
import { useTheme } from '@/composables/useTheme'

/**
 * 入口（Campus Insight 重构后）：
 * 不再全局注册任何组件库 —— Element Plus 已移除，
 * 基础件在 src/components/ui/ 自研，页面按需 import；图标直接用 lucide-vue-next 组件。
 */
const app = createApp(App)

// 主题在挂载前初始化：尽早把 data-theme 写到 <html>，避免深色→浅色的首屏闪烁（FOUC）
useTheme().init()

app.use(router)
app.mount('#app')
