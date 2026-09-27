<script setup>
/**
 * 登录页（Campus Insight 增强版）
 *
 * 变化：
 *   - 动态粒子背景（CSS keyframes + 浮动光晕）
 *   - 品牌区增加版本号与实时时钟
 *   - 表单增加密码可见切换
 *   - 登录按钮增加渐变动画
 *   - 错误提示增加抖动动画
 */
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Eye, EyeOff, Lock, LogIn, User, ShieldCheck, BarChart3, Database, BrainCircuit } from 'lucide-vue-next'
import { useSession } from '@/composables/useSession'
import UButton from '@/components/ui/UButton.vue'
import UInput from '@/components/ui/UInput.vue'
import { toast } from '@/components/ui/toast'

const route = useRoute()
const router = useRouter()
const session = useSession()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const errText = ref('')
const showPw = ref(false)
const shake = ref(false)

/* 实时时钟 */
const now = ref(new Date())
let clockTimer = null

function formatTime(d) {
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

onMounted(() => {
  clockTimer = setInterval(() => { now.value = new Date() }, 1000)
})
onBeforeUnmount(() => clearInterval(clockTimer))

/* 特色统计徽章 */
const FEATURES = [
  { icon: Database, label: '2000+', sub: '学生数据' },
  { icon: BarChart3, label: '5', sub: '分析模块' },
  { icon: BrainCircuit, label: 'K-Means', sub: '智能分群' },
]

async function submit() {
  if (!form.username.trim()) {
    errText.value = '请输入用户名'
    triggerShake()
    return
  }
  if (!form.password) {
    errText.value = '请输入密码'
    triggerShake()
    return
  }
  errText.value = ''
  loading.value = true
  try {
    // 调用会话单例登录：后端通过 Set-Cookie 下发 httpOnly 会话，响应体仅含身份信息
    await session.login(form.username.trim(), form.password)
    // 如果提示必须改密码，可在此引导跳转
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/overview'
    router.replace(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/overview')
  } catch (e) {
    errText.value = e.message || '登录失败，请检查后端服务'
    triggerShake()
    toast.error(errText.value)
  } finally {
    loading.value = false
  }
}

function triggerShake() {
  shake.value = true
  setTimeout(() => { shake.value = false }, 500)
}
</script>

<template>
  <div class="login-page">
    <!-- 动态背景层 -->
    <div class="login-bg" aria-hidden="true">
      <div class="bg-orb bg-orb--1"></div>
      <div class="bg-orb bg-orb--2"></div>
      <div class="bg-orb bg-orb--3"></div>
      <div class="bg-grid"></div>
    </div>

    <!-- 浮动统计徽章 -->
    <div class="login-badges">
      <div v-for="f in FEATURES" :key="f.label" class="badge-card">
        <component :is="f.icon" :size="14" class="badge-icon" />
        <span class="badge-label">{{ f.label }}</span>
        <span class="badge-sub">{{ f.sub }}</span>
      </div>
    </div>

    <!-- 登录卡片 -->
    <div class="login-card" :class="{ 'login-card--shake': shake }">
      <!-- 头部品牌 -->
      <div class="login-brand">
        <div class="login-logo">
          <ShieldCheck :size="22" />
        </div>
        <h1>Campus Insight</h1>
        <p>学生行为数据分析平台</p>
        <div class="login-meta">
          <span class="meta-dot"></span>
          <span>系统在线</span>
          <span class="meta-sep">·</span>
          <span>{{ formatTime(now) }}</span>
        </div>
      </div>

      <!-- 表单 -->
      <form class="login-form" @submit.prevent="submit">
        <div class="field">
          <label>用户名</label>
          <UInput
            v-model="form.username"
            placeholder="admin"
            autocomplete="username"
            :disabled="loading"
          >
            <template #prefix><User :size="14" /></template>
          </UInput>
        </div>
        <div class="field">
          <label>密码</label>
          <UInput
            v-model="form.password"
            :type="showPw ? 'text' : 'password'"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
            @enter="submit"
          >
            <template #prefix><Lock :size="14" /></template>
            <template #suffix>
              <button type="button" class="pw-toggle" @click="showPw = !showPw">
                <EyeOff v-if="showPw" :size="13" />
                <Eye v-else :size="13" />
              </button>
            </template>
          </UInput>
        </div>

        <p v-if="errText" class="login-err">{{ errText }}</p>

        <UButton
          type="submit"
          variant="primary"
          :loading="loading"
          class="login-btn"
        >
          <LogIn :size="14" />
          登 录
        </UButton>
      </form>

      <p class="login-hint">账号由管理员分配，遗失密码请联系系统管理员重置</p>
    </div>

    <!-- 底部 -->
    <div class="login-footer">
      <span>© 2026 Campus Insight · 高校学生行为数据采集与可视化系统</span>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow: hidden;
  background:
    radial-gradient(ellipse 80% 60% at 20% 5%, rgba(124,108,255,0.15) 0%, transparent 60%),
    radial-gradient(ellipse 60% 50% at 85% 90%, rgba(79,209,255,0.1) 0%, transparent 55%),
    var(--ci-bg);
}

/* ===== 动态背景 ===== */
.login-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
  animation: orb-float 12s ease-in-out infinite;
}

.bg-orb--1 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(124,108,255,0.3), transparent 70%);
  top: -10%; left: -5%;
  animation-delay: 0s;
}

.bg-orb--2 {
  width: 350px; height: 350px;
  background: radial-gradient(circle, rgba(79,209,255,0.25), transparent 70%);
  bottom: -10%; right: -5%;
  animation-delay: -4s;
}

.bg-orb--3 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(55,217,150,0.2), transparent 70%);
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  animation-delay: -8s;
  animation-duration: 15s;
}

@keyframes orb-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(30px, -20px) scale(1.05); }
  50% { transform: translate(-20px, 30px) scale(0.95); }
  75% { transform: translate(15px, 15px) scale(1.02); }
}

/* 网格纹理 */
.bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse 60% 50% at 50% 50%, black 30%, transparent 80%);
}

/* ===== 浮动统计徽章 ===== */
.login-badges {
  position: absolute;
  bottom: 60px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 12px;
  z-index: 1;
}

.badge-card {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--ci-glass);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-full);
  backdrop-filter: blur(12px);
  animation: badge-fade-in 0.6s ease-out both;
}

.badge-card:nth-child(1) { animation-delay: 0.2s; }
.badge-card:nth-child(2) { animation-delay: 0.4s; }
.badge-card:nth-child(3) { animation-delay: 0.6s; }

@keyframes badge-fade-in {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.badge-icon {
  color: var(--ci-primary);
}

.badge-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ci-text);
  font-variant-numeric: tabular-nums;
}

.badge-sub {
  font-size: 11px;
  color: var(--ci-text-3);
}

/* ===== 登录卡片 ===== */
.login-card {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 420px;
  padding: 44px 38px 34px;
  background: var(--ci-glass);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-xl, 20px);
  box-shadow:
    0 0 0 1px rgba(124,108,255,0.06),
    0 32px 64px rgba(0,0,0,0.5),
    inset 0 1px 0 rgba(255,255,255,0.04);
  backdrop-filter: blur(20px);
  animation: card-entrance 0.5s ease-out both;
}

@keyframes card-entrance {
  from { opacity: 0; transform: translateY(20px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.login-card--shake {
  animation: card-shake 0.4s ease-in-out;
}

@keyframes card-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-8px); }
  40% { transform: translateX(8px); }
  60% { transform: translateX(-4px); }
  80% { transform: translateX(4px); }
}

/* 卡片顶部光晕 */
.login-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 10%;
  right: 10%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(124,108,255,0.5), transparent);
}

.login-brand {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo {
  width: 56px;
  height: 56px;
  margin: 0 auto 14px;
  border-radius: var(--r-lg);
  background: linear-gradient(135deg, var(--ci-primary), var(--ci-cyan));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 8px 24px rgba(124,108,255,0.3);
  animation: logo-pulse 3s ease-in-out infinite;
}

@keyframes logo-pulse {
  0%, 100% { box-shadow: 0 8px 24px rgba(124,108,255,0.3); }
  50% { box-shadow: 0 8px 32px rgba(124,108,255,0.5); }
}

.login-brand h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--ci-text);
  letter-spacing: -0.3px;
  margin: 0 0 4px;
  background: linear-gradient(135deg, var(--ci-text), var(--ci-cyan));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.login-brand p {
  font-size: 13px;
  color: var(--ci-text-2);
  margin: 0 0 12px;
}

.login-meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 11px;
  color: var(--ci-text-3);
  font-family: var(--font-mono);
}

.meta-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ci-success);
  box-shadow: 0 0 6px var(--ci-success);
  animation: dot-pulse 2s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.meta-sep {
  opacity: 0.3;
}

/* 表单 */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--ci-text-2);
  letter-spacing: 0.3px;
  margin-bottom: 6px;
}

.pw-toggle {
  display: flex;
  align-items: center;
  background: none;
  border: none;
  color: var(--ci-text-3);
  cursor: pointer;
  padding: 0;
  transition: color 0.15s;
}

.pw-toggle:hover {
  color: var(--ci-text-2);
}

.login-err {
  margin: 0;
  font-size: 12px;
  color: var(--ci-danger);
  padding: 8px 12px;
  background: rgba(255,92,124,0.08);
  border-radius: var(--r-sm);
  border-left: 2px solid var(--ci-danger);
  animation: err-slide-in 0.2s ease-out;
}

@keyframes err-slide-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.login-btn {
  margin-top: 4px;
  width: 100%;
  justify-content: center;
  letter-spacing: 2px;
  position: relative;
  overflow: hidden;
}

.login-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, transparent 30%, rgba(255,255,255,0.1) 50%, transparent 70%);
  background-size: 200% 200%;
  animation: btn-shine 3s ease-in-out infinite;
}

@keyframes btn-shine {
  0%, 100% { background-position: 200% 0; }
  50% { background-position: -100% 0; }
}

.login-hint {
  margin: 16px 0 0;
  font-size: 11px;
  color: var(--ci-text-3);
  text-align: center;
}

/* 底部 */
.login-footer {
  position: absolute;
  bottom: 20px;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 11px;
  color: var(--ci-text-3);
  opacity: 0.6;
}

@media (max-width: 600px) {
  .login-badges { display: none; }
  .login-card { padding: 32px 24px 26px; }
}
</style>
