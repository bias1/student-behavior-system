/**
 * 大屏页面的时间窗口选项。
 *
 * "全部"不再硬编码 90 天——数据跨度不足 90 天时，90 和 30 查的是同一段，
 * 选项形同虚设。这里从 /overview/meta 拿真实数据跨度动态生成选项，
 * 模块级缓存 promise，概览/画像/分群三个页面共用一次请求。
 */
import { OverviewApi } from '@/api'

let spanPromise = null

/** 数据实际跨度（天）；meta 请求失败时返回 0，调用方退回静态选项 */
export function dataSpan() {
  if (!spanPromise) {
    spanPromise = OverviewApi.meta()
      .then((m) => Math.round((new Date(m.date_end) - new Date(m.date_start)) / 86400000) + 1)
      .catch(() => 0)
  }
  return spanPromise
}

/** USegmented 用的窗口选项：小于数据跨度的固定档 + "全部（N 天）" */
export function windowOptions(span) {
  const opts = [7, 14, 30].filter((d) => (span ? d < span : true)).map((d) => ({ value: d, label: `近 ${d} 天` }))
  opts.push(span ? { value: span, label: `全部（${span} 天）` } : { value: 90, label: '全部' })
  return opts
}
