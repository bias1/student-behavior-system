import * as echarts from 'echarts'

/**
 * ECharts 深色主题（注册名 sb-dark）
 *
 * 为什么注册主题而不是每张图各写颜色：大屏有 6+ 张图，坐标轴/分割线/提示框样式
 * 必须完全一致，逐图配置既啰嗦又容易漂移；主题里定好后，图里只写业务相关配置。
 * 这里用完整 echarts 包（演示项目体积不敏感）；若要瘦身，可改成 echarts/core + 按需 use()。
 */
export const PALETTE = ['#37e2f0', '#4ea1ff', '#ffd166', '#7ee787', '#ff6b81', '#b28dff', '#ff9f43']

const AXIS_LINE = { show: true, lineStyle: { color: 'rgba(120,165,215,0.35)' } }
const SPLIT_LINE = { show: true, lineStyle: { color: 'rgba(90,130,190,0.16)', type: 'dashed' } }

echarts.registerTheme('sb-dark', {
  color: PALETTE,
  backgroundColor: 'transparent',
  textStyle: { fontFamily: 'Microsoft YaHei, PingFang SC, sans-serif' },
  title: { textStyle: { color: '#dcecff' }, subtextStyle: { color: '#8fabc9' } },
  legend: { textStyle: { color: '#a9c4e4' }, inactiveColor: '#4a5f7a' },
  tooltip: {
    backgroundColor: 'rgba(8,20,38,0.94)',
    borderColor: 'rgba(55,226,240,0.45)',
    borderWidth: 1,
    textStyle: { color: '#e6f2ff', fontSize: 12 },
    axisPointer: { lineStyle: { color: 'rgba(55,226,240,0.6)' }, crossStyle: { color: 'rgba(55,226,240,0.6)' } },
  },
  categoryAxis: { axisLine: AXIS_LINE, axisTick: { show: false }, axisLabel: { color: '#9fbadb' }, splitLine: { show: false }, splitArea: { show: false } },
  valueAxis: { axisLine: AXIS_LINE, axisTick: { show: false }, axisLabel: { color: '#9fbadb' }, splitLine: SPLIT_LINE },
  timeAxis: { axisLine: AXIS_LINE, axisLabel: { color: '#9fbadb' }, splitLine: SPLIT_LINE },
  grid: { borderColor: 'rgba(90,130,190,0.25)', containLabel: true },
  // 热力图渐变：深海蓝 → 青 → 黄 → 红，暗背景下对比度最高
  visualMap: { textStyle: { color: '#9fbadb' }, inRange: { color: ['#0e2440', '#1d6fa5', '#37e2f0', '#ffd166', '#ff6b81'] } },
  radar: {
    axisLine: { lineStyle: { color: 'rgba(120,165,215,0.35)' } },
    splitLine: { lineStyle: { color: 'rgba(90,130,190,0.28)' } },
    splitArea: { areaStyle: { color: ['rgba(30,60,105,0.18)', 'rgba(20,45,82,0.18)'] } },
    name: { textStyle: { color: '#bcd6f5' } },
  },
  line: { smooth: true, symbolSize: 5, lineStyle: { width: 2 } },
  bar: { itemStyle: { borderRadius: [3, 3, 0, 0] } },
})

export default echarts
export { echarts }
