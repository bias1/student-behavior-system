<script setup>
/**
 * 消费时段热力图（X = 0-23 小时，Y = 周一至周日）
 *
 * 数据源：GET /api/consumption/heatmap?days=N（axios 封装已把 {code,data,msg} 拆成 data）
 *
 * 兼容三种输入，页面侧不用关心后端哪天改了结构：
 *   A. 明细对象数组  [{ weekday: 0-6, hour: 0-23, count: 数量 }, ...]
 *   B. 后端真实响应  { hours[], weekdays[], data[[hour, weekday, 笔数]], amount_data[], max_records }
 *   C. 裸三元组数组  [[hour, weekday, value], ...]
 *
 * 两个易错点（论文里也值得写一句）：
 *   1) 元组顺序：后端是 [hour, weekday, value]，heatmap 系列的 value[0] 对应 x、value[1] 对应 y，
 *      写反就得到一张 7×24 的转置图 —— 尺寸看着还对，只有峰值位置诡异，很难排查。
 *   2) 补零：稀疏数据直接丢给 heatmap，缺值格子是"不绘制"而不是"画成最小色"，
 *      深色底上会出现空洞，被误读成数据丢失。所以这里强制铺满 24×7=168 格。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ConsumptionApi } from '@/api'
import { C } from '@/styles/palette'
import BaseChart from './BaseChart.vue'

const props = defineProps({
  days: { type: [Number, String], default: 30 },
  /** records = 消费笔数（看行为习惯） / amount = 消费金额（看资金分布） */
  metric: { type: String, default: 'records' },
  height: { type: String, default: '100%' },
  /** 外部直接喂数据（单测、静态截图、父组件已有数据时不再发请求）：数组或后端响应对象 */
  raw: { type: [Array, Object], default: null },
  /** 传了 raw 就禁用内部请求 */
  autoFetch: { type: Boolean, default: true },
})

// MySQL WEEKDAY() 返回 0=周一，与这里的顺序一致，前后端不用再做偏移
const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const resp = ref({})
const loading = ref(false)

/** 星期轴文案：后端返回了 weekdays 就以后端为准（长度必须为 7，否则退回默认） */
const labels = computed(() => {
  const src = props.raw ?? resp.value
  return !Array.isArray(src) && src?.weekdays?.length === 7 ? src.weekdays : WEEKDAYS
})

async function reload() {
  if (!props.autoFetch || props.raw) return
  loading.value = true
  try {
    resp.value = await ConsumptionApi.heatmap({ days: props.days })
  } finally {
    loading.value = false
  }
}

/**
 * 统一转成 ECharts 需要的 [x = hour, y = weekday, value]，并顺带算出补零后的最大值
 * @returns {{ cells: Array<[number, number, number]>, max: number }}
 */
function toCells(source, metric = 'records') {
  const isAmount = metric === 'amount'
  const rows = Array.isArray(source)
    ? source
    : (source ? (isAmount ? source.amount_data ?? source.data : source.data ?? source.amount_data) : [])

  const pickAmount = (r) => (r.amount ?? r.count ?? r.value ?? 0)
  const pickCount = (r) => (r.count ?? r.value ?? r.amount ?? 0)

  const grid = new Map()                       // key = hour * 7 + weekday，避免二维数组来回建
  for (const r of rows || []) {
    let hour, weekday, value
    if (Array.isArray(r)) {
      ;[hour, weekday, value] = r              // 情况 B / C：[hour, weekday, value]
    } else if (r && typeof r === 'object') {
      hour = r.hour ?? r.hh                    // 情况 A：{weekday, hour, count}
      weekday = r.weekday ?? r.wd
      value = isAmount ? pickAmount(r) : pickCount(r)
    }
    hour = Number(hour); weekday = Number(weekday)
    if (!(hour >= 0 && hour < 24) || !(weekday >= 0 && weekday < 7)) continue   // 脏索引直接丢掉
    grid.set(hour * 7 + weekday, Number(value) || 0)
  }

  const cells = []
  let max = 0
  for (let h = 0; h < 24; h++) {
    for (let w = 0; w < 7; w++) {
      const v = grid.get(h * 7 + w) ?? 0
      if (v > max) max = v
      cells.push([h, w, v])
    }
  }
  // 后端已经算好整格最大值（未补零时与补零结果相同），优先信它，避免两套口径
  const backendMax = source && !Array.isArray(source) ? (isAmount ? source.max_amount : source.max_records) : null
  return { cells, max: Number(backendMax) > 0 ? Number(backendMax) : max }
}

/** 峰值格（用于副标题与"最高峰"标注），并列时取小时最早的那个 */
const peak = computed(() => {
  const { cells } = toCells(props.raw ?? resp.value, props.metric)
  return cells.reduce((a, b) => (b[2] > a[2] ? b : a), [0, 0, 0])
})

const option = computed(() => {
  const src = props.raw ?? resp.value
  const isAmount = props.metric === 'amount'
  const { cells, max } = toCells(src, props.metric)
  const weekdays = labels.value
  const unit = isAmount ? '元' : '笔'
  // 金额有小数（后端 round 2 位），笔数是整数，两套精度分开处理避免 tooltip 里出现 12.00 元
  const fmt = (v) => (isAmount ? (Number.isInteger(+v) ? String(v) : Number(v).toFixed(1)) : String(v))

  return {
    tooltip: {
      // 热力图格子小，提示框放上方比跟随鼠标更不容易被遮挡
      position: 'top',
      formatter: (p) => {
        const [h, w, v] = p.value
        const [ph, pw] = peak.value
        const tag = h === ph && w === pw ? '<br/><span style="color:#ffd166">← 全窗口最高峰</span>' : ''
        return `${weekdays[w]} ${String(h).padStart(2, '0')}:00 - ${String(h + 1).padStart(2, '0')}:00`
          + `<br/>${isAmount ? '消费金额' : '消费笔数'}：<b>${fmt(v)}</b> ${unit}${tag}`
      },
    },
    grid: { left: 6, right: 12, top: 8, bottom: 46, containLabel: true },
    xAxis: {
      type: 'category',
      data: Array.from({ length: 24 }, (_, i) => i),
      name: '时',
      nameTextStyle: { color: C.text2 },
      splitArea: { show: true },              // 暗色棋盘格，帮眼睛对齐行列
      // 24 个标签挤一行会重叠，按需要隔 1 或隔 2 显示（窄容器用 3）
      axisLabel: { interval: (i) => i % 2 === 0, formatter: (v) => `${v}` },
    },
    yAxis: {
      type: 'category',
      data: weekdays,
      splitArea: { show: true },
      axisLabel: { fontSize: 12 },
    },
    visualMap: {
      type: 'continuous',
      min: 0,
      max: max || 1,                           // 全 0 时兜底成 1，否则 visualMap 会算出 NaN 渐变
      calculable: true,                        // 拖动手柄可动态截断高值，答辩时演示"只看热点"
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemWidth: 12,
      itemHeight: 100,
      precision: isAmount ? 1 : 0,
      text: ['高', '低'],
      textStyle: { color: C.text2 },
      // 深海蓝 → 青 → 黄 → 红：暗背景下明度递增，色盲同学也能区分强弱
      inRange: { color: ['#0b1a2e', '#1a5276', C.cyan, C.warning, C.danger] },
    },
    series: [
      {
        name: isAmount ? '消费金额' : '消费笔数',
        type: 'heatmap',
        data: cells,
        progressive: 0,                        // 168 格不需要增量渲染，关了可避免切换指标时残影
        label: { show: false },                // 打开会在每格写数字，投屏时太吵
        itemStyle: { borderColor: 'rgba(11,15,20,0.7)', borderWidth: 1 },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.6)', borderColor: C.text, borderWidth: 1 },
        },
      },
    ],
  }
})

watch(() => [props.days, props.metric], reload)
onMounted(reload)

defineExpose({ reload, peak, loading })
</script>

<template>
  <div class="hm">
    <div class="hm__sub sb-muted">
      <span v-if="peak[2] > 0">
        最高峰 {{ labels[peak[1]] }} {{ String(peak[0]).padStart(2, '0') }}:00（{{ peak[2] }} {{ metric === 'amount' ? '元' : '笔' }}）
      </span>
      <span v-else>窗口内无消费数据</span>
      <slot name="extra" />
    </div>
    <BaseChart :option="option" :loading="loading" :height="height" />
  </div>
</template>

<style scoped>
.hm {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.hm__sub {
  flex: none;
  height: 20px;
  line-height: 20px;
  font-size: 12px;
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>
