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

/* ==========================================================================
 * 浅色主题色板（阶段 5）
 * - NEUTRAL[mode]：坐标轴/文字/网格/提示框等"结构色"，随主题切换由 ECharts 注册主题消费；
 * - PALETTE_BY_MODE[mode]：数据序列色，浅色下把亮青/亮紫压深一档保证白底可辨；
 * - VISUALMAP[mode]：热力图渐变端点（深色从近黑起、浅色从浅灰起）。
 * 页面里的图表一律不写死中性色，全部交给注册主题，切主题只需换主题名即可整体变色。
 * ========================================================================== */
export const NEUTRAL = {
  dark: C,
  light: {
    bg: '#ffffff', surface: '#ffffff', surface2: '#f2f4f8', surface3: '#e8ecf2',
    text: '#0f1720', text2: '#4a5563', text3: '#8a94a2',
    primary: '#5b4bf0', cyan: '#0e8fc4', success: '#12a06a', warning: '#c9821f', danger: '#e23b5e',
    border: 'rgba(15,23,32,0.10)', borderStrong: 'rgba(15,23,32,0.16)',
  },
}

export const PALETTE_BY_MODE = {
  dark: PALETTE,
  light: ['#0e8fc4', '#5b4bf0', '#12a06a', '#c9821f', '#e23b5e', '#9333ea', '#ea580c'],
}

export const VISUALMAP = {
  dark: ['#131a24', '#37346b', '#7c6cff', '#4fd1ff', '#ffb454', '#ff5c7c'],
  light: ['#eef2f7', '#c7d2fe', '#818cf8', '#0e8fc4', '#f59e0b', '#e23b5e'],
}
