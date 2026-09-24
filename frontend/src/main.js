import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElIcons from '@element-plus/icons-vue'

import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'   // 暗黑主题变量，配合 index.html 的 <html class="dark">
import '@/styles/theme.css'
import '@/plugins/echarts'                            // 副作用导入：注册 sb-dark 主题

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 图标全局注册：<el-icon><Refresh /></el-icon> 才认得组件名（模板里用字符串组件名解析）
for (const [name, comp] of Object.entries(ElIcons)) {
  app.component(name, comp)
}

// Element Plus 全量引入：演示项目换取配置简单；若要瘦身可换 unplugin-vue-components 按需自动导入
app.use(ElementPlus, { locale: zhCn })
app.use(router)
app.mount('#app')
