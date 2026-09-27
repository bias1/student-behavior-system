import { createRouter, createWebHistory } from 'vue-router'
import { useSession } from '@/composables/useSession'

/**
 * 路由表（Campus Insight 重构版 + 阶段 1 生产化认证）
 *
 * 页面路径命名：
 *   /overview        → 群体概览（原 Dashboard）
 *   /students        → 学生列表（新）
 *   /student/:id?    → 个体画像（可选参数：无 ID 时显示搜索框）
 *   /risk            → 风险中心（原 WarningList）
 *   /segmentation    → 分群工作台（新，聚类结果独立成页）
 *
 * history 模式部署时需 nginx: try_files $uri /index.html
 * 登录守卫：使用 useSession 单例恢复 httpOnly Cookie 会话，不再检查 localStorage
 * 认证关闭（AUTH_ENABLED=0）时路由守卫直接放行，前端进入演示模式
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
    meta: { title: '群体概览', perm: 'stats:read' },
  },
  {
    path: '/students',
    name: 'students',
    component: () => import('@/views/Students.vue'),
    meta: { title: '学生列表', perm: 'student:read' },
  },
  {
    path: '/student/:id?',
    name: 'student-profile',
    component: () => import('@/views/StudentProfile.vue'),
    meta: { title: '个体画像', perm: 'student:detail' },
  },
  {
    path: '/risk',
    name: 'risk',
    component: () => import('@/views/RiskCenter.vue'),
    meta: { title: '风险中心', perm: 'warning:read' },
  },
  {
    path: '/segmentation',
    name: 'segmentation',
    component: () => import('@/views/Segmentation.vue'),
    meta: { title: '分群工作台', perm: 'clustering:read' },
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

router.beforeEach(async (to) => {
  // 公开页面（登录页）不需要会话探测
  if (to.meta.public) return true

  const session = useSession()
  // 首次导航时触发 bootstrap（认证开关探测 + /auth/me 恢复会话）
  // 已 bootstrap 过时立即返回缓存结果，不重发请求
  const loggedIn = await session.bootstrap()

  // 认证开启且未登录：跳转登录页，携带原始路径便于登录后返回
  if (!loggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 路由级权限检查（前端 UX 提示，后端已强制鉴权，这里提前跳转避免闪现空白页）
  if (to.meta.perm && !session.hasPerm(to.meta.perm)) {
    // 有登录但无该页权限：跳转到有权限的首个页面，或概览（如果有权）
    // 如果用户无任何权限，提示后端 403 即可
    const firstAllowed = routes.find(
      (r) => r.meta?.perm && session.hasPerm(r.meta.perm)
    )
    if (firstAllowed && firstAllowed.path !== to.path) {
      return firstAllowed.path
    }
    // 无其他可去页，放行（页面内容展示 "没有权限" 提示）
  }

  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'Campus Insight'} \u00b7 Campus Insight`
})

export default router
