import * as echarts from 'echarts'
import { C, PALETTE } from '@/styles/palette'

/**
 * ECharts 深色主题（注册名 insight-dark）
 *
 * 为什么注册主题而不是每张图各写颜色：大屏有 6+ 张图，坐标轴/分割线/提示框样式
 * 必须完全一致，逐图配置既啰嗦又容易漂移；主题里定好后，图里只写业务相关配置。
 * 全部色值来自 styles/palette.js（与 CSS token 同源），改主色只需改那一处。
 */

const AXIS_LINE = { show: true, lineStyle: { color: 'rgba(255,255,255,0.14)' } }
const SPLIT_LINE = { show: true, lineStyle: { color: 'rgba(255,255,255,0.07)', type: [4, 4] } }

echarts.registerTheme('insight-dark', {
  color: PALETTE,
  backgroundColor: 'transparent',
  textStyle: { fontFamily: "'Inter Variable','PingFang SC','Microsoft YaHei',sans-serif" },
  title: { textStyle: { color: C.text }, subtextStyle: { color: C.text2 } },
  legend: { textStyle: { color: C.text2 }, inactiveColor: C.text3 },
  tooltip: {
    backgroundColor: 'rgba(22,31,43,0.96)',
    borderColor: C.borderStrong,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: C.text, fontSize: 12 },
    extraCssText: 'border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.5)',
    axisPointer: { lineStyle: { color: C.borderStrong }, crossStyle: { color: C.borderStrong } },
  },
  categoryAxis: { axisLine: AXIS_LINE, axisTick: { show: false }, axisLabel: { color: C.text2 }, splitLine: { show: false }, splitArea: { show: false } },
  valueAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: C.text2 }, splitLine: SPLIT_LINE },
  timeAxis: { axisLine: AXIS_LINE, axisLabel: { color: C.text2 }, splitLine: SPLIT_LINE },
  grid: { borderColor: C.border, containLabel: true },
  // 热力图渐变：底色 → 主色紫 → 青 → 黄 → 红，暗背景下层次最分明
  visualMap: { textStyle: { color: C.text2 }, inRange: { color: ['#131a24', '#37346b', '#7c6cff', '#4fd1ff', '#ffb454', '#ff5c7c'] } },
  radar: {
    axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.09)' } },
    splitArea: { areaStyle: { color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.04)'] } },
    name: { textStyle: { color: C.text2 } },
  },
  line: { smooth: true, symbolSize: 5, lineStyle: { width: 2 } },
  bar: { itemStyle: { borderRadius: [4, 4, 0, 0] } },
})

export default echarts
export { echarts }
