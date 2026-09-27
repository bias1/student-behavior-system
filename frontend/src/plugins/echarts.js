/**
 * ECharts 按需引入 + 深色主题注册（insight-dark）
 *
 * 为什么按需注册：之前 import * as echarts 全量打包，dev 预构建产物 2.5MB、
 * 生产 chunk 1MB，登录页/列表页也被迫等它。这里只注册项目真实用到的
 * 6 种系列与组件，首屏 JS 体积降到一个量级；新增图表类型时记得同步补 use()。
 *
 * 清单来源（全仓扫描 option 后的结论，删条目会导致运行时静默缺图）：
 * - 系列：line/bar（概览·风险·画像·分群）pie（概览）scatter（PCA 散点）
 *   radar（画像五维）heatmap（消费热力图）
 * - 组件：grid/legend（含 scroll 型）/tooltip+axisPointer（cross、shadow）
 *   /dataZoom-inside（趋势缩放）/markArea（周末底色区）/visualMap-continuous（热力图渐变）
 *   /radar 坐标系；title/toolbox/timeline 全项目未用，不注册
 * - features：LabelLayout（柱顶/饼图 label 定位）；渲染器只需 canvas
 *
 * 为什么注册主题而不是每张图各写颜色：大屏有 6+ 张图，坐标轴/分割线/提示框样式
 * 必须完全一致，逐图配置既啰嗦又容易漂移；主题里定好后，图里只写业务相关配置。
 * 全部色值来自 styles/palette.js（与 CSS token 同源），改主色只需改那一处。
 */
import * as echarts from 'echarts/core'
import { NEUTRAL, PALETTE_BY_MODE, VISUALMAP } from '@/styles/palette'
import { BarChart, HeatmapChart, LineChart, PieChart, RadarChart, ScatterChart } from 'echarts/charts'
import {
  AxisPointerComponent,
  DataZoomInsideComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  RadarComponent,
  TooltipComponent,
  VisualMapContinuousComponent,
} from 'echarts/components'
import { LabelLayout } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart, HeatmapChart, LineChart, PieChart, RadarChart, ScatterChart,
  AxisPointerComponent, DataZoomInsideComponent, GridComponent, LegendComponent,
  MarkAreaComponent, RadarComponent, TooltipComponent, VisualMapContinuousComponent,
  LabelLayout, CanvasRenderer,
])

// 主题工厂：深色/浅色只差一组中性色与序列色板，结构一份以免两套主题配置漂移
function buildTheme(mode) {
  const c = NEUTRAL[mode]
  const axisLine = { show: true, lineStyle: { color: c.borderStrong } }
  const splitLine = { show: true, lineStyle: { color: mode === 'dark' ? 'rgba(255,255,255,0.07)' : 'rgba(15,23,32,0.07)', type: [4, 4] } }
  return {
    color: PALETTE_BY_MODE[mode],
    backgroundColor: 'transparent',
    textStyle: { fontFamily: "'Inter Variable','PingFang SC','Microsoft YaHei',sans-serif" },
    title: { textStyle: { color: c.text }, subtextStyle: { color: c.text2 } },
    legend: { textStyle: { color: c.text2 }, inactiveColor: c.text3 },
    tooltip: {
      backgroundColor: mode === 'dark' ? 'rgba(22,31,43,0.96)' : 'rgba(255,255,255,0.98)',
      borderColor: c.borderStrong,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: c.text, fontSize: 12 },
      extraCssText: 'border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.18)',
      axisPointer: { lineStyle: { color: c.borderStrong }, crossStyle: { color: c.borderStrong } },
    },
    categoryAxis: { axisLine, axisTick: { show: false }, axisLabel: { color: c.text2 }, splitLine: { show: false }, splitArea: { show: false } },
    valueAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: c.text2 }, nameTextStyle: { color: c.text2 }, splitLine },
    timeAxis: { axisLine, axisLabel: { color: c.text2 }, splitLine },
    grid: { borderColor: c.border, containLabel: true },
    visualMap: { textStyle: { color: c.text2 }, inRange: { color: VISUALMAP[mode] } },
    radar: {
      axisLine: { lineStyle: { color: c.borderStrong } },
      splitLine: { lineStyle: { color: mode === 'dark' ? 'rgba(255,255,255,0.09)' : 'rgba(15,23,32,0.09)' } },
      splitArea: { areaStyle: { color: mode === 'dark' ? ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.04)'] : ['rgba(15,23,32,0.02)', 'rgba(15,23,32,0.04)'] } },
      name: { textStyle: { color: c.text2 } },
    },
    line: { smooth: true, symbolSize: 5, lineStyle: { width: 2 } },
    bar: { itemStyle: { borderRadius: [4, 4, 0, 0] } },
  }
}

echarts.registerTheme('insight-dark', buildTheme('dark'))
echarts.registerTheme('insight-light', buildTheme('light'))

export default echarts
export { echarts }
