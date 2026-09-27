import axios from 'axios'
import { toast } from '@/components/ui/toast'

/**
 * axios 统一封装（阶段 1 生产化改造：Cookie 会话 + 双提交 CSRF）
 *
 * 后端约定（backend/utils.py）：所有响应固定为 { code, data, msg }，
 * HTTP 状态码与 body.code 保持一致。
 *
 * 会话机制（与 backend/security.py 对齐）：
 * - 会话令牌存于 httpOnly Cookie（sb_session），浏览器随请求自动发送，JS 无法读取。
 * - CSRF 令牌存于可读 Cookie（sb_csrf），本模块自动将其写入 X-CSRF-Token 请求头，
 *   后端守卫对非 GET 请求做双提交比对（库中值 vs 请求头值）。
 * - axios withCredentials=true 确保跨域请求也携带 Cookie（同源部署时同样有效）。
 *
 * 单次请求可用 config 附加两个自定义开关：
 *   silent: true    不弹全局 toast，由页面自己决定怎么显示
 *   timeout: 60000  聚类首算等慢接口单独放宽超时
 */

const HTTP_TEXT = {
  400: '请求参数有误',
  401: '登录已过期，请重新登录',
  403: '没有访问权限',
  404: '接口或资源不存在',
  405: '请求方法不被允许',
  429: '请求过于频繁',
  500: '服务器内部错误',
  502: '网关异常',
  503: '服务不可用',
  504: '网关超时',
}

// 同一时刻多个接口一起失败（后端没起）会弹一堆一样的 toast，用一个标志位合并
let notifying = false
function notifyError(msg, type = 'error') {
  if (notifying) return
  notifying = true
  if (type === 'error') toast.error(msg)
  else toast.success(msg)
  setTimeout(() => (notifying = false), 800)
}

/**
 * 从 document.cookie 读取 CSRF 令牌（sb_csrf 由后端以非 httpOnly Cookie 下发）。
 * 与 backend/security.py 中 CSRF_COOKIE = "sb_csrf" 对齐。
 */
export function getCsrfToken() {
  const match = document.cookie.match(/(?:^|[;\s])sb_csrf=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

/** 清除 CSRF Cookie（401 会话过期时调用；sb_session 是 httpOnly，JS 无法删除，由后端在 /auth/logout 时清除）*/
function clearCsrfCookie() {
  // 写入同路径同名但立即过期的 Cookie，兼容有/无 Secure 标志两种情况
  const secure = location.protocol === 'https:' ? ';Secure' : ''
  document.cookie = `sb_csrf=;Path=/;Max-Age=0${secure}`
}

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 20000,
  // 会话令牌通过 httpOnly Cookie 传递，axios 需要开启 withCredentials
  // 才能在跨源（如前端 5173 → 后端 5000 dev server proxy）时携带 Cookie
  withCredentials: true,
})

service.interceptors.request.use(
  (cfg) => {
    // 非安全方法（POST/PUT/DELETE）须带 CSRF 头（后端守卫对 GET/HEAD/OPTIONS 不检查）
    const method = (cfg.method || 'get').toUpperCase()
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const csrf = getCsrfToken()
      if (csrf) cfg.headers['X-CSRF-Token'] = csrf
    }
    return cfg
  },
  (error) => Promise.reject(error)
)

service.interceptors.response.use(
  (response) => {
    const body = response.data
    // 代理目标是后端未启动时会被 HTML 错误页命中，这类"结构不对"要单独报出来
    if (!body || typeof body !== 'object' || !('code' in body)) {
      notifyError('接口返回结构异常，请确认后端服务版本')
      return Promise.reject(new Error('unexpected response shape'))
    }
    if (body.code !== 200) {
      if (!response.config.silent) notifyError(body.msg || '请求失败')
      const err = new Error(body.msg || 'business error')
      err.code = body.code
      err.data = body.data
      return Promise.reject(err)
    }
    return body.data
  },
  (error) => {
    const silent = !!(error.config && error.config.silent)
    let msg
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      msg = '请求超时：统计窗口过大或聚类正在计算，请稍后重试'
    } else if (error.response) {
      const { status, data } = error.response
      msg = data?.msg || HTTP_TEXT[status] || `HTTP ${status}`
      // 401 = 会话未携带/已过期/已吊销：清除 CSRF Cookie，全页跳转登录页
      // （登录接口本身的 401 是"密码错误"，不能跳登录，已在 silent 中处理）
      const isAuthApi = (error.config?.url || '').startsWith('/auth/')
      if (status === 401 && !isAuthApi) {
        clearCsrfCookie()
        if (!window.location.pathname.startsWith('/login')) {
          const redirect = encodeURIComponent(window.location.pathname + window.location.search)
          window.location.href = `/login?redirect=${redirect}`
        }
        msg = data?.msg || '登录已过期，请重新登录'
      }
    } else {
      // 没有 response 说明请求没拿到 HTTP 响应：后端未启动 / 代理目标错误 / 网络断开
      msg = '无法连接后端服务，请先启动 python app.py（默认 http://127.0.0.1:5000）'
    }
    if (!silent) notifyError(msg)
    const err = new Error(msg)
    err.silent = silent
    err.original = error
    err.httpStatus = error.response?.status
    return Promise.reject(err)
  }
)

/** 便捷方法：返回值即后端 data */
export const http = {
  get: (url, params, config = {}) => service.get(url, { params, ...config }),
  post: (url, data, config = {}) => service.post(url, data, config),
}

export default service
