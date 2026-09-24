import { createRouter, createWebHistory } from 'vue-router'

/**
 * 路由表
 * - 三个页面全部懒加载：大屏首屏只下屏需要的代码，画像/预警页点到才拉
 * - /student/:id? 的问号表示可选：直接访问 /student 显示"输入学号查询"的空态，
 *   从大屏或预警页跳转时用 /student/202101001 自动查询
 * - history 模式需要部署时把 404 兜到 index.html（nginx: try_files $uri /index.html）
 */
const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '群体概览大屏', nav: '群体大屏' },
  },
  {
    path: '/student/:id?',
    name: 'student-profile',
    component: () => import('@/views/StudentProfile.vue'),
    meta: { title: '个体行为画像', nav: '个体画像' },
  },
  {
    path: '/warning',
    name: 'warning',
    component: () => import('@/views/WarningList.vue'),
    meta: { title: '异常行为预警', nav: '异常预警' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '学生行为分析'} - 高校学生行为数据采集与可视化系统`
})

export default router
