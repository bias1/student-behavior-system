import { createRouter, createWebHistory } from 'vue-router'
import { AuthApi } from '@/api'
import { getToken } from '@/api/request'

/**
 * 路由表（Campus Insight 重构版）
 *
 * 页面路径命名：
 *   /overview        → 群体概览（原 Dashboard）
 *   /students        → 学生列表（新）
 *   /student/:id?    → 个体画像（可选参数：无 ID 时显示搜索框）
 *   /risk            → 风险中心（原 WarningList）
 *   /segmentation    → 分群工作台（新，聚类结果独立成页）
 *
 * history 模式部署时需 nginx: try_files $uri /index.html
 * 登录守卫与旧版相同（后端 AUTH_ENABLED=1 时拦截未登录）
 */
const routes = [
  { path: '/', redirect: '/overview' },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/overview',
    name: 'overview',
    component: () => import('@/views/Overview.vue'),
    meta: { title: '群体概览', nav: '群体概览' },
  },
  {
    path: '/students',
    name: 'students',
    component: () => import('@/views/Students.vue'),
    meta: { title: '学生列表', nav: '学生列表' },
  },
  {
    path: '/student/:id?',
    name: 'student-profile',
    component: () => import('@/views/StudentProfile.vue'),
    meta: { title: '个体画像', nav: '个体画像' },
  },
  {
    path: '/risk',
    name: 'risk',
    component: () => import('@/views/RiskCenter.vue'),
    meta: { title: '风险中心', nav: '风险中心' },
  },
  {
    path: '/segmentation',
    name: 'segmentation',
    component: () => import('@/views/Segmentation.vue'),
    meta: { title: '分群工作台', nav: '分群工作台' },
  },
  // 旧路径兼容重定向（书签不失效）
  { path: '/dashboard', redirect: '/overview' },
  { path: '/warning', redirect: '/risk' },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

// null=未探测；探测失败（后端未起）按"需要登录"处理，避免降级窗口内把未登录请求放行
let authEnabled = null
async function resolveAuthEnabled() {
  if (authEnabled === null) {
    try {
      authEnabled = !!(await AuthApi.status()).enabled
    } catch {
      authEnabled = true
    }
  }
  return authEnabled
}

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if ((await resolveAuthEnabled()) && !getToken()) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'Campus Insight'} · Campus Insight`
})

export default router
