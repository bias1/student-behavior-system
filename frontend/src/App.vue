<script setup>
/**
 * 应用外壳：左侧固定导航栏 + 右侧路由视图（Campus Insight 重构版 + 阶段 1 生产化）
 *
 * 设计要点：
 * - 侧栏宽 220px（折叠后 56px），底部可折叠，与主流后台布局一致
 * - 导航图标统一用 lucide-vue-next，不再依赖任何组件库图标
 * - 登录页 isLogin=true 时侧栏与头部均隐藏，内容区占满整个视口
 * - 顶部状态栏展示当前页标题 + 日期 + 用户信息 + 退出，保留旧版时钟逻辑
 * - 导航项按用户权限过滤：无权项目隐藏，后端保证最终安全
 * - 会话使用 httpOnly Cookie（useSession 单例），不再使用 localStorage
 */
import { useRoute, useRouter } from 'vue-router'
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { WarningApi } from '@/api'
import { useSession } from '@/composables/useSession'
import { useTheme } from '@/composables/useTheme'
// lucide 图标：按名称导入，避免全量注入
import {
  BarChart3,
  ChevronLeft,
  ChevronRight,
  CircuitBoard,
  Command,
  LogOut,
  Moon,
  Search,
  ShieldAlert,
  Sun,
  User,
  Users,
} from 'lucide-vue-next'
import CommandPalette from '@/components/CommandPalette.vue'

const route = useRoute()
const router = useRouter()
const session = useSession()
const theme = useTheme()
// 用于模板的别名：展示名优先，否则显示用户名
const username = computed(() => session.displayName.value || session.username.value)

/* ---------------- 导航列表（全量）---------------- */
// 每项对应一个权限码；无权项在导航中隐藏（后端 require_perm 确保最终安全）
const NAVS_ALL = [
  { name: 'overview',  icon: BarChart3,   label: '群体概览', title: '群体概览',     perm: 'stats:read' },
  { name: 'students',  icon: Users,       label: '学生列表', title: '学生列表',     perm: 'student:read' },
  { name: 'student-profile', icon: User,  label: '个体画像', title: '个体行为画像', perm: 'student:detail' },
  { name: 'risk',      icon: ShieldAlert, label: '风险中心', title: '风险中心',     perm: 'warning:read' },
  { name: 'segmentation', icon: CircuitBoard, label: '分群工作台', title: '分群工作台', perm: 'clustering:read' },
]

// 权限过滤：认证关闭（演示模式）时 hasPerm 全部返回 true，导航全量可见
const NAVS = computed(() => {
  if (!session.loggedIn.value) return []   // 未登录时不导航
  return NAVS_ALL.filter(n => session.hasPerm(n.perm))
})

const active = computed(() => route.name)
// 登录页不套导航壳
const isLogin = computed(() => route.name === 'login')
const pageTitle = computed(() => route.meta.title || 'Campus Insight')

const clock = new Date().toLocaleDateString('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  weekday: 'long',
})

/* ---------------- 侧栏折叠 ---------------- */
const collapsed = ref(false)
function toggleSidebar() {
  collapsed.value = !collapsed.value
}

/* ---------------- 命令面板 ---------------- */
const cmdOpen = ref(false)

/* ---------------- 登录状态与导航徽标 ---------------- */
const pendingWarnings = ref(0)
let warnTimer = null

async function loadPendingWarnings() {
  if (!session.hasPerm('warning:read')) return   // 无权限时跳过
  try {
    const s = await WarningApi.stats({ status: '0' })
    pendingWarnings.value = s?.total || 0
  } catch { /* 接口失败静默忽略 */ }
}

// 会话由路由守卫 bootstrap() 初始化，这里只需加载需会话数据的徽标
onMounted(() => {
  if (session.loggedIn.value && session.hasPerm('warning:read')) {
    loadPendingWarnings()
    warnTimer = setInterval(loadPendingWarnings, 120000)  // 每 2 分钟刷新
  }
})

onBeforeUnmount(() => clearInterval(warnTimer))

async function logout() {
  await session.logout()
  router.push({ name: 'login' })
}

function go(name) {
  router.push({ name })
}
</script>

<template>
  <div class="app-shell" :class="{ 'is-login': isLogin }">
    <!-- 侧边导航（登录页隐藏） -->
    <nav
      v-if="!isLogin"
      class="app-sidebar"
      :class="{ 'is-collapsed': collapsed }"
    >
      <!-- Logo 区 -->
      <div class="sidebar-brand">
        <span v-if="!collapsed" class="brand-text">
          <b>Campus Insight</b>
          <em>学生行为分析平台</em>
        </span>
        <span v-else class="brand-icon">CI</span>
      </div>

      <!-- 导航列表 -->
      <ul class="sidebar-nav">
        <li
          v-for="n in NAVS"
          :key="n.name"
          class="nav-item"
          :class="{ 'is-active': active === n.name }"
          :title="collapsed ? n.label : ''"
          @click="go(n.name)"
        >
          <component :is="n.icon" :size="17" class="nav-icon" />
          <span v-if="!collapsed" class="nav-label">{{ n.label }}</span>
          <span
            v-if="n.name === 'risk' && pendingWarnings > 0 && !collapsed"
            class="nav-badge"
          >{{ pendingWarnings > 99 ? '99+' : pendingWarnings }}</span>
          <span
            v-else-if="n.name === 'risk' && pendingWarnings > 0 && collapsed"
            class="nav-badge nav-badge--dot"
          />
        </li>
      </ul>

      <!-- 底部：折叠按钮 + 用户 -->
      <div class="sidebar-footer">
        <button class="collapse-btn" @click="toggleSidebar">
          <ChevronLeft v-if="!collapsed" :size="15" />
          <ChevronRight v-else :size="15" />
          <span v-if="!collapsed">收起</span>
        </button>
        <div v-if="username && !collapsed" class="sidebar-user">
          <User :size="13" />
          <span>{{ username }}</span>
          <button class="logout-btn" title="退出登录" @click="logout">
            <LogOut :size="13" />
          </button>
        </div>
      </div>
    </nav>

    <!-- 主内容区 -->
    <div class="app-body">
      <!-- 顶部面包屑/标题栏（登录页隐藏） -->
      <header v-if="!isLogin" class="app-header">
        <h1 class="header-title">{{ pageTitle }}</h1>
        <div class="header-right sb-muted">
          <!-- 深/浅主题切换：图标随当前模式翻转 -->
          <button
            class="theme-toggle"
            :title="theme.isLight.value ? '切换到深色' : '切换到浅色'"
            @click="theme.toggle()"
          >
            <Moon v-if="theme.isLight.value" :size="14" />
            <Sun v-else :size="14" />
          </button>
          <!-- 系统状态指示 -->
          <span class="header-status">
            <span class="status-dot"></span>
            <span class="status-text">在线</span>
          </span>
          <!-- Ctrl+K 命令面板触发 -->
          <button class="header-cmd" @click="cmdOpen = true">
            <Search :size="12" />
            <span>搜索</span>
            <kbd><Command :size="10" />K</kbd>
          </button>
          <span class="header-clock">{{ clock }}</span>
          <template v-if="username">
            <span class="header-user"><User :size="13" />{{ username }}</span>
            <button class="header-logout" @click="logout"><LogOut :size="13" />退出</button>
          </template>
        </div>
      </header>

      <main class="app-main">
        <router-view v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" />
          </Transition>
        </router-view>
      </main>
    </div>

    <!-- 命令面板：全局挂载，登录页也能打开 -->
    <CommandPalette v-model:open="cmdOpen" />
  </div>
</template>

<style scoped>
/* 整体布局：侧栏 + 右侧 body */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--ci-bg);
  color: var(--ci-text);
  font-family: var(--font-sans);
}

/* 登录页无侧栏，铺满 */
.app-shell.is-login {
  display: block;
}

/* ---------------- 侧栏 ---------------- */
.app-sidebar {
  flex: none;
  width: 220px;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, var(--ci-surface) 0%, var(--ci-sidebar-to) 100%);
  border-right: 1px solid var(--ci-border);
  transition: width 0.22s ease;
  overflow: hidden;
  z-index: 10;
  position: relative;
}

.app-sidebar::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--ci-primary), var(--ci-cyan));
  opacity: 0.6;
}

.app-sidebar.is-collapsed {
  width: 56px;
}

.sidebar-brand {
  flex: none;
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid var(--ci-border);
  overflow: hidden;
  white-space: nowrap;
}

.brand-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.brand-text b {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--ci-text);
  background: linear-gradient(135deg, var(--ci-primary), var(--ci-cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.brand-text em {
  font-style: normal;
  font-size: 10px;
  color: var(--ci-text-3);
  letter-spacing: 0.5px;
}

.brand-icon {
  font-size: 16px;
  font-weight: 800;
  background: linear-gradient(135deg, var(--ci-primary), var(--ci-cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

/* 导航列表 */
.sidebar-nav {
  flex: 1;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  height: 38px;
  border-radius: var(--r-md);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--ci-text-2);
  transition: all 0.15s;
  white-space: nowrap;
  user-select: none;
  flex: none;
}

.nav-item:hover {
  background: var(--ci-surface-2);
  color: var(--ci-text);
}

.nav-item.is-active {
  background: var(--ci-primary-dim);
  color: var(--ci-primary);
  font-weight: 600;
}

.nav-icon {
  flex: none;
  position: relative;
}

.nav-label {
  flex: 1;
}

/* 未处理预警角标 */
.nav-badge {
  margin-left: auto;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--r-full);
  background: var(--ci-danger);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  animation: badge-pulse 2s ease-in-out infinite;
}

.nav-badge--dot {
  width: 8px;
  height: 8px;
  min-width: 8px;
  padding: 0;
  position: absolute;
  top: -2px;
  right: -2px;
}

@keyframes badge-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255,92,124,0.4); }
  50% { box-shadow: 0 0 0 4px rgba(255,92,124,0); }
}

/* 侧栏底部 */
.sidebar-footer {
  flex: none;
  padding: 10px 8px;
  border-top: 1px solid var(--ci-border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.collapse-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: none;
  border-radius: var(--r-md);
  background: transparent;
  color: var(--ci-text-3);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s;
  white-space: nowrap;
}

.collapse-btn:hover {
  color: var(--ci-text-2);
  background: var(--ci-surface-2);
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--ci-text-2);
  white-space: nowrap;
  overflow: hidden;
}

.logout-btn {
  margin-left: auto;
  display: flex;
  align-items: center;
  border: none;
  background: transparent;
  color: var(--ci-text-3);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  transition: color 0.15s;
}

.logout-btn:hover {
  color: var(--ci-danger);
}

/* ---------------- 右侧主体 ---------------- */
.app-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.app-header {
  flex: none;
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  border-bottom: 1px solid var(--ci-border);
  background: var(--ci-bg-soft);
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ci-text);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
  font-size: 12px;
  color: var(--ci-text-3);
}

.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  background: transparent;
  color: var(--ci-text-3);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.theme-toggle:hover {
  border-color: var(--ci-border-strong, rgba(255,255,255,0.14));
  color: var(--ci-text);
  background: var(--ci-hover);
}

.header-clock {
  color: var(--ci-text-3);
}

/* 系统状态指示 */
.header-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--ci-text-3);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ci-success);
  box-shadow: 0 0 6px rgba(55,217,150,0.5);
  animation: status-pulse 2s ease-in-out infinite;
}

.status-text {
  font-size: 11px;
}

@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.header-cmd {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  background: transparent;
  color: var(--ci-text-3);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.header-cmd:hover {
  border-color: var(--ci-border-strong, rgba(255,255,255,0.14));
  color: var(--ci-text-2);
}

.header-cmd kbd {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 1px 5px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  border-radius: 3px;
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--ci-text-3);
}

.header-user {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--ci-text-2);
}

.header-logout {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  background: transparent;
  color: var(--ci-text-3);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.header-logout:hover {
  color: var(--ci-danger);
  border-color: var(--ci-danger-dim, rgba(255,92,124,0.3));
  background: rgba(255,92,124,0.06);
}

.app-main {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0;
}

/* 页面切换动画 */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-leave-to {
  opacity: 0;
}
</style>
