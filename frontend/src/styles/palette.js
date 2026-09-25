/**
 * JS 侧色板常量 —— 与 styles/theme.css 的 :root token 一一对应。
 * ECharts 配置、Sparkline、动态徽标色等"运行时要拿颜色字符串"的场景一律从这里取，
 * 页面里不允许出现写死的 hex（CSS 里也只允许引用 --ci-* 变量）。
 */
export const C = {
  bg: '#0b0f14',
  surface: '#111821',
  surface2: '#161f2b',
  surface3: '#1c2734',
  text: '#f5f7fa',
  text2: '#8b96a5',
  text3: '#5b6673',
  primary: '#7c6cff',
  cyan: '#4fd1ff',
  success: '#37d996',
  warning: '#ffb454',
  danger: '#ff5c7c',
  border: 'rgba(255,255,255,0.08)',
  borderStrong: 'rgba(255,255,255,0.14)',
}

/** 序列色板：冷色领头、语义色殿后，同页超过 7 个序列的概率极低 */
export const PALETTE = [C.cyan, C.primary, C.success, C.warning, C.danger, '#c084fc', '#f97316']

/** 预警级别 → 颜色（全站唯一映射：雷达、徽标、事件卡共用） */
export const LEVEL_COLOR = { 3: C.danger, 2: C.warning, 1: C.cyan }
export const LEVEL_TEXT = { 3: 'HIGH', 2: 'MEDIUM', 1: 'LOW' }

/** 透明度工具：给 ECharts areaStyle/soft 底色用，避免手写 rgba 字符串漂移 */
export function alpha(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}
