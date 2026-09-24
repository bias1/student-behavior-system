<script setup>
/**
 * 应用外壳：顶部导航 + 路由视图
 * 高度用 100vh 分配（导航 46px + 内容区剩余），大屏内部再用 grid 铺满剩余空间，
 * 这样 1920×1080 下不出现整页滚动条，符合"投屏一屏看完"的要求。
 */
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()
const router = useRouter()

const NAVS = [
  { name: 'dashboard', icon: 'Monitor', label: '群体概览大屏' },
  { name: 'student-profile', icon: 'User', label: '个体行为画像' },
  { name: 'warning', icon: 'WarningFilled', label: '异常行为预警' },
]

const active = computed(() => route.name)
const clock = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'long' })

function go(name) {
  router.push({ name })
}
</script>

<template>
  <div class="app-shell">
    <header class="app-nav">
      <div class="app-nav__brand">
        <el-icon :size="20" color="#37e2f0"><DataAnalysis /></el-icon>
        <b>高校学生行为数据采集与可视化系统</b>
        <span class="sb-muted">Student Behavior Analytics</span>
      </div>
      <nav class="app-nav__menu">
        <button
          v-for="n in NAVS"
          :key="n.name"
          class="app-nav__item"
          :class="{ 'is-active': active === n.name }"
          @click="go(n.name)"
        >
          <el-icon><component :is="n.icon" /></el-icon>{{ n.label }}
        </button>
      </nav>
      <div class="app-nav__right sb-muted">{{ clock }}</div>
    </header>

    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app-nav {
  flex: none;
  height: 46px;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 0 18px;
  background: linear-gradient(90deg, rgba(12, 28, 54, 0.95), rgba(10, 22, 42, 0.7));
  border-bottom: 1px solid rgba(64, 128, 200, 0.28);
}

.app-nav__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  letter-spacing: 1px;
  white-space: nowrap;
}

.app-nav__brand b {
  background: linear-gradient(90deg, #9fe9ff, #4ea1ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.app-nav__menu {
  display: flex;
  gap: 6px;
  flex: 1;
}

.app-nav__item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  color: var(--sb-text-dim);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.app-nav__item:hover {
  color: var(--sb-text);
  background: rgba(78, 161, 255, 0.1);
}

.app-nav__item.is-active {
  color: #04121f;
  font-weight: 600;
  background: linear-gradient(90deg, var(--sb-accent), var(--sb-blue));
  box-shadow: 0 0 14px rgba(55, 226, 240, 0.35);
}

.app-nav__right {
  white-space: nowrap;
}

.app-main {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
