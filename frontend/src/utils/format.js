/** 页面通用格式化：后端给的数值统一在这里定口径，避免每张卡片各写一遍 toFixed */

export function fmtNum(v, digits = 2, dash = '--') {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return dash
  return Number(v).toFixed(digits)
}

export function fmtInt(v, dash = '--') {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return dash
  return Math.round(Number(v)).toLocaleString('zh-CN')
}

/** 金额：超过 1 万自动换成"万元"，大屏卡片才不会挤成 210,185.72 这么长 */
export function fmtMoney(v, dash = '--') {
  const n = Number(v)
  if (!Number.isFinite(n)) return dash
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(2)} 万`
  return n.toFixed(2)
}

/** 分钟 → "1 小时 15 分"，图书馆时长比纯分钟好读 */
export function fmtMinutes(v, dash = '--') {
  const n = Math.round(Number(v))
  if (!Number.isFinite(n)) return dash
  if (n < 60) return `${n} 分钟`
  return `${Math.floor(n / 60)} 小时 ${n % 60} 分`
}

/** 0.2538 → 25.4%；后端比率类字段有的是百分数有的是小数，用这个显式区分 */
export function fmtPct(v, digits = 1, alreadyPercent = true) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  return `${(alreadyPercent ? n : n * 100).toFixed(digits)}%`
}

/** 日期 "2026-05-01" → "05-01"，X 轴更清爽（后端 daily 已给 MM-DD，这里做兜底） */
export function shortDate(s) {
  if (!s) return ''
  const str = String(s)
  return str.length > 7 ? str.slice(5) : str
}

/** 特征英文名 → 中文（后端 features 字典里带了 label，这里只做兜底） */
export function featureLabel(dict, key) {
  return dict?.[key]?.label || key
}
