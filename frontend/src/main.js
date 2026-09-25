import { createApp } from 'vue'

// 本地字体：Inter Variable 随构建产物打包，离线/内网环境可用；中文走系统栈（见 theme.css --font-sans）
import '@fontsource-variable/inter'

import '@/styles/theme.css'
import '@/plugins/echarts'                            // 副作用导入：注册 insight-dark 主题

import App from './App.vue'
import router from './router'

/**
 * 入口（Campus Insight 重构后）：
 * 不再全局注册任何组件库 —— Element Plus 已移除，
 * 基础件在 src/components/ui/ 自研，页面按需 import；图标直接用 lucide-vue-next 组件。
 */
const app = createApp(App)

app.use(router)
app.mount('#app')
