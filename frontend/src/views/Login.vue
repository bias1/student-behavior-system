<script setup>
/**
 * 登录页（Campus Insight 重构版，无组件库）
 *
 * - 单管理员账号，对应后端 backend/api/auth.py
 * - 成功后 token 存 localStorage（sb_token），axios 拦截器自动注入
 * - redirect query 只允许站内相对路径，防止开放重定向
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Lock, LogIn, User } from 'lucide-vue-next'
import { AuthApi } from '@/api'
import { setToken } from '@/api/request'
import UButton from '@/components/ui/UButton.vue'
import UInput from '@/components/ui/UInput.vue'
import { toast } from '@/components/ui/toast'

const route = useRoute()
const router = useRouter()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const errText = ref('')

async function submit() {
  if (!form.username.trim()) { errText.value = '请输入用户名'; return }
  if (!form.password) { errText.value = '请输入密码'; return }
  errText.value = ''
  loading.value = true
  try {
    const data = await AuthApi.login(form.username.trim(), form.password)
    setToken(data.token)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/overview'
    router.replace(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/overview')
  } catch (e) {
    errText.value = e.message || '登录失败，请检查后端服务'
    toast.error(errText.value)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <!-- 头部品牌 -->
      <div class="login-brand">
        <div class="login-logo">CI</div>
        <h1>Campus Insight</h1>
        <p>学生行为数据分析平台</p>
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
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loading"
            @enter="submit"
          >
            <template #prefix><Lock :size="14" /></template>
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

      <p class="login-hint">默认账号 admin，详见 backend/config.py</p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse 80% 60% at 20% 5%, rgba(124,108,255,0.18) 0%, transparent 60%),
    radial-gradient(ellipse 60% 50% at 85% 90%, rgba(79,209,255,0.12) 0%, transparent 55%),
    var(--ci-bg);
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  padding: 40px 36px 32px;
  background: var(--ci-glass);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-xl);
  box-shadow: 0 0 0 1px rgba(124,108,255,0.06), 0 32px 64px rgba(0,0,0,0.5);
  backdrop-filter: blur(16px);
}

.login-brand {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo {
  width: 52px;
  height: 52px;
  margin: 0 auto 12px;
  border-radius: var(--r-lg);
  background: linear-gradient(135deg, var(--ci-primary), var(--ci-cyan));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 800;
  color: #fff;
  letter-spacing: -0.5px;
}

.login-brand h1 {
  font-size: 22px;
  font-weight: 700;
  color: var(--ci-text);
  letter-spacing: -0.3px;
  margin: 0 0 4px;
}

.login-brand p {
  font-size: 13px;
  color: var(--ci-text-2);
  margin: 0;
}

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

.login-err {
  margin: 0;
  font-size: 12px;
  color: var(--ci-danger);
  padding: 6px 10px;
  background: rgba(255,92,124,0.08);
  border-radius: var(--r-sm);
  border-left: 2px solid var(--ci-danger);
}

.login-btn {
  margin-top: 4px;
  width: 100%;
  justify-content: center;
  letter-spacing: 2px;
}

.login-hint {
  margin: 16px 0 0;
  font-size: 11px;
  color: var(--ci-text-3);
  text-align: center;
}
</style>
