import axios from 'axios'
import { toast } from '@/components/ui/toast'

/**
 * axios 统一封装
 *
 * 后端约定（backend/utils.py）：所有响应固定为 { code, data, msg }，
 * 且 HTTP 状态码与 body.code 保持一致。因此这里做三件事：
 * 1. 成功时直接把 data 抛给业务代码，页面里不用再 .data.data 套三层；
 * 2. 业务失败（code != 200）统一弹提示并 reject，页面只需处理"拿到数据"这一条路径；
 * 3. 网络层异常（后端没起、超时、404、500）翻译成中文可读文案。
 *
 * 单次请求可用 config 附加两个自定义开关：
 *   silent: true    不弹全局 toast，由页面自己决定怎么显示（如个体画像的"查无此人"）
 *   timeout: 60000  聚类首算等慢接口单独放宽超时
 */

const HTTP_TEXT = {
  400: '请求参数有误',
  401: '登录已过期',
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

// 登录令牌存储键：后端 auth 守卫开启后，除 /auth/* 外所有接口都要带 Bearer token
export const TOKEN_KEY = 'sb_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 20000,
  // 令牌走 Authorization 头而不是 Cookie，无 CSRF 面，不需要 withCredentials
})

service.interceptors.request.use(
  (cfg) => {
    // 登录守卫（backend/api/auth.py）：除白名单外一律要求 Bearer token
    const token = getToken()
    if (token) cfg.headers.Authorization = `Bearer ${token}`
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
      // 401 = 未登录/过期：清掉本地令牌跳登录页（登录接口自身的 401 是"密码错"，不能跳）
      const isAuthApi = (error.config?.url || '').startsWith('/auth/')
      if (status === 401 && !isAuthApi) {
        clearToken()
        if (!window.location.pathname.startsWith('/login')) {
          const redirect = encodeURIComponent(window.location.pathname + window.location.search)
          window.location.href = `/login?redirect=${redirect}`
        }
        msg = msg || '登录已过期，请重新登录'
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
