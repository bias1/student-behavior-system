<script setup>
/**
 * 群体概览页（/overview）
 *
 * 布局（CSS Grid，1920px 一屏）：
 *   工具栏 → 4 张 KPI 卡 → [消费趋势(6) | 热力图(4) | 饼图(2)] → [图书馆(6) | 聚类(6)]
 *
 * 变化 vs 旧 Dashboard：
 *   - 移除所有 el-* 组件，改用自研 UI 组件库
 *   - 聚类相关内容（散点图/手肘图/簇质量/成员抽屉）迁移到分群工作台
 *   - KPI 卡改用 KpiCard 组件（有环比 sparkline，更好看）
 *   - 刷新逻辑与 API 层保持不变
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { RefreshCw } from 'lucide-vue-next'
import { ConsumptionApi, LibraryApi, OverviewApi } from '@/api'
import { dataSpan, windowOptions } from '@/utils/window'
import { fmtInt, fmtMoney, fmtNum } from '@/utils/format'
import BaseChart from '@/components/BaseChart.vue'
import ConsumeHeatmap from '@/components/ConsumeHeatmap.vue'
import UCard from '@/components/ui/UCard.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import USegmented from '@/components/ui/USegmented.vue'
import UButton from '@/components/ui/UButton.vue'

const router = useRouter()

/* ---------------- 全局筛选 ---------------- */
// 窗口选项按真实数据跨度生成（“全部”不再是硬编码 90 天）
const span = ref(0)
const DAYS_OPTS = computed(() => windowOptions(span.value))
const days = ref(30)
const heatMetric = ref('records')
const heatRef = ref(null)
const autoRefresh = ref(false)
const dateWin = ref(['', ''])

const loading = reactive({ overview: false, trend: false, pie: false, lib: false })
const ov = ref({})
const summary = ref({})
const trend = ref({})
const category = ref({})
const libHours = ref({})

/* ---------------- 数据获取 ---------------- */
async function safe(key, fn) {
  loading[key] = true
  try { return await fn() }
  catch (e) { console.warn('[overview] 加载失败:', key, e.message); return null }
  finally { loading[key] = false }
}

async function loadOverview() {
  const [d, s] = await Promise.all([
    safe('overview', () => OverviewApi.stats({ days: days.value })),
    safe('overview', () => OverviewApi.summary({ days: days.value })),
  ])
  if (d) { ov.value = d; dateWin.value = [d.date_start, d.date_end] }
  if (s) summary.value = s
}
async function loadTrend() {
  const d = await safe('trend', () => ConsumptionApi.trend({ days: days.value }))
  if (d) trend.value = d
}
async function loadPie() {
  const d = await safe('pie', () => ConsumptionApi.category({ days: days.value }))
  if (d) category.value = d
}
async function loadLib() {
  const d = await safe('lib', () => LibraryApi.hours({ days: days.value }))
  if (d) libHours.value = d
}

function loadAll() {
  loadOverview(); loadTrend(); loadPie(); loadLib()
}

onMounted(async () => {
  // 先拿数据跨度再首拉：days 被钳到跨度时不会多请求一轮（重拉靠用户交互事件）
  span.value = await dataSpan()
  if (span.value > 0 && days.value > span.value) days.value = span.value
  loadAll()
})

/* ---------------- 自动刷新 ---------------- */
let timer = null
function toggleAuto(v) {
  clearInterval(timer)
  if (v) timer = setInterval(loadAll, 60000)
}
onBeforeUnmount(() => clearInterval(timer))

function refreshAll() {
  loadAll()
  heatRef.value?.reload()
}

/* ---------------- KPI 卡（环比 + sparkline 来自 /overview/summary） ---------------- */
const cards = computed(() => {
  const d = ov.value
  const s = summary.value
  return [
    {
      label: 'STUDENTS', cn: '学生总数',
      value: Number(s.student_count ?? d.student_count) || 0,
      suffix: ' 人',
      delta: s.active_delta ?? null,   // 活跃率百分比点位变化
      color: 'var(--ci-cyan)',
      spark: [],
    },
    {
      label: 'CONSUMPTION', cn: '总消费额',
      value: Number(s.total_amount ?? d.total_amount) || 0,
      prefix: '¥',
      decimals: 2,
      delta: s.amount_delta ?? null,
      color: 'var(--ci-warning)',
      spark: s.spark_amount || [],
    },
    {
      label: 'LIBRARY', cn: '日均在馆时长',
      value: Number(s.avg_daily_study_minutes ?? d.avg_daily_study_minutes) || 0,
      suffix: ' 分',
      decimals: 1,
      delta: s.study_delta ?? null,
      color: 'var(--ci-success)',
      spark: s.spark_library || [],
    },
    {
      label: 'WARNINGS', cn: '累计预警数',
      value: Number(s.warning_count ?? d.warning_count) || 0,
      suffix: ' 条',
      delta: s.warning_delta ?? null,
      goodWhenUp: false,
      color: 'var(--ci-danger)',
      spark: s.spark_warning || [],
      click: () => router.push({ name: 'risk' }),
    },
  ]
})

/* ---------------- 图 1：消费趋势 ---------------- */
const trendOption = computed(() => {
  const t = trend.value
  const s = t.series || {}
  const areas = []
  const flags = t.is_weekend || []
  for (let i = 0; i < flags.length; i++) {
    if (flags[i] && (i === 0 || !flags[i - 1])) areas.push([i, i])
    else if (flags[i] && areas.length) areas[areas.length - 1][1] = i
  }
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['日消费总额', '消费笔数', '全校在馆时长(小时)'], top: 2, right: 8 },
    grid: { left: 8, right: 8, top: 34, bottom: 6, containLabel: true },
    xAxis: { type: 'category', data: t.dates || [], axisLabel: { formatter: (v) => v.slice(5) } },
    yAxis: [
      { type: 'value', name: '元' },
      { type: 'value', name: '笔', position: 'right', splitLine: { show: false } },
    ],
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: '日消费总额', type: 'line', data: s.amount || [], yAxisIndex: 0,
        areaStyle: { opacity: 0.15 }, smooth: true, showSymbol: false,
        markArea: {
          silent: true, itemStyle: { color: 'rgba(255,180,84,0.06)' },
          data: areas.map(([a, b]) => [{ xAxis: (t.dates || [])[a] }, { xAxis: (t.dates || [])[b] }]),
        },
      },
      { name: '消费笔数', type: 'bar', data: s.records || [], yAxisIndex: 1, barMaxWidth: 10, opacity: 0.6 },
      { name: '全校在馆时长(小时)', type: 'line', data: s.library_minutes || [], yAxisIndex: 1, smooth: true, showSymbol: false },
    ],
  }
})

/* ---------------- 图 2：消费类别饼图 ---------------- */
const pieOption = computed(() => {
  const rows = category.value.by_merchant_type || []
  return {
    tooltip: { trigger: 'item', formatter: (p) => `${p.name}<br/>¥${p.value.toFixed(0)}（${p.percent}%）` },
    legend: { orient: 'vertical', right: 4, top: 'center', itemWidth: 10, itemHeight: 10 },
    series: [
      {
        type: 'pie', radius: ['40%', '66%'], center: ['36%', '52%'], avoidLabelOverlap: true,
        itemStyle: { borderColor: 'rgba(11,15,20,0.9)', borderWidth: 2 },
        label: { show: true, formatter: '{b}\n{d}%', fontSize: 11 },
        labelLine: { length: 6, length2: 8 },
        data: rows.map((r) => ({ name: r.merchant_type, value: r.amount })),
      },
    ],
  }
})

/* ---------------- 图 3：图书馆时段分布 ---------------- */
const libOption = computed(() => {
  const rows = libHours.value.hour_dist || []
  return {
    tooltip: { trigger: 'axis', formatter: (p) => `${p[0].name}:00 进馆 ${p[0].value} 人次` },
    // top 要给足：y 轴名“人次”画在轴线顶端，containLabel 不把它算进去，
    // 10px 时会和最大刻度标签（如 5200）重叠并贴边被裁
    grid: { left: 6, right: 6, top: 32, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.hour), axisLabel: { interval: (i) => i % 3 === 0 } },
    yAxis: { type: 'value', name: '人次', nameTextStyle: { color: '#8b96a5', fontSize: 11, padding: [0, 0, 0, -16] } },
    series: [
      {
        type: 'bar', barMaxWidth: 14, data: rows.map((r) => r.n),
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: (p) => ([14, 15, 16, 19, 20, 21].includes(p.dataIndex) ? '#4fd1ff' : 'rgba(79,209,255,0.3)'),
        },
        markPoint: { symbolSize: 34, data: [{ type: 'max', name: '最高峰' }], itemStyle: { color: '#ffb454' } },
      },
    ],
  }
})
</script>

<template>
  <div class="overview">
    <!-- 工具栏 -->
    <div class="ov-bar">
      <span class="ov-date">数据区间：{{ dateWin[0] }} ~ {{ dateWin[1] }}</span>
      <USegmented v-model="days" :options="DAYS_OPTS" size="sm" @update:model-value="loadAll" />
      <div class="ov-bar__right">
        <label class="ov-auto">
          <input type="checkbox" v-model="autoRefresh" @change="toggleAuto(autoRefresh)" />
          自动刷新
        </label>
        <UButton variant="ghost" size="sm" @click="refreshAll">
          <RefreshCw :size="13" /> 刷新
        </UButton>
      </div>
    </div>

    <!-- KPI 卡 -->
    <div class="ov-kpi">
      <KpiCard
        v-for="c in cards" :key="c.label"
        :label="c.label" :cn="c.cn" :value="c.value"
        :decimals="c.decimals || 0" :prefix="c.prefix || ''" :suffix="c.suffix || ''"
        :delta="c.delta" :good-when-up="c.goodWhenUp !== false"
        :spark="c.spark" :color="c.color"
        :clickable="!!c.click" @click="c.click && c.click()"
      />
    </div>

    <!-- 趋势 + 热力 + 饼图 -->
    <div class="ov-row1">
      <UCard title="消费趋势" :subtitle="`近 ${days} 天，浅色区域为周末`" class="ov-trend">
        <BaseChart :option="trendOption" :loading="loading.trend" height="280px" />
      </UCard>
      <UCard title="消费时段热力" subtitle="24小时 × 7天" class="ov-heat">
        <template #extra>
          <USegmented v-model="heatMetric" size="sm"
            :options="[{ value:'records',label:'笔数' },{ value:'amount',label:'金额' }]" />
        </template>
        <ConsumeHeatmap ref="heatRef" :days="days" :metric="heatMetric" height="280px" />
      </UCard>
      <UCard title="消费类别" subtitle="按商户类型" class="ov-pie">
        <BaseChart :option="pieOption" :loading="loading.pie" height="280px" />
      </UCard>
    </div>

    <!-- 图书馆 + 底部说明 -->
    <div class="ov-row2">
      <UCard title="图书馆人流分布" subtitle="高亮学习高峰时段" class="ov-lib">
        <BaseChart :option="libOption" :loading="loading.lib" height="220px" />
      </UCard>
      <UCard title="说明" class="ov-note">
        <p class="note-text">
          群体数据仅用于教学服务与资助帮扶参考，不构成对学生的个人评价或定性。
          如需查看聚类分群详情，请前往
          <a class="note-link" @click="router.push({ name: 'segmentation' })">分群工作台</a>。
        </p>
      </UCard>
    </div>
  </div>
</template>

<style scoped>
.overview {
  height: 100%;
  padding: 16px 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
  min-width: 0;
}

.ov-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
}

.ov-date {
  font-size: 12px;
  color: var(--ci-text-3);
  white-space: nowrap;
}

.ov-bar__right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.ov-auto {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--ci-text-2);
  cursor: pointer;
  user-select: none;
}

.ov-auto input {
  cursor: pointer;
  accent-color: var(--ci-primary);
}

/* KPI 卡 */
.ov-kpi {
  flex: none;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

/* 第一行：趋势 + 热力 + 饼 */
.ov-row1 {
  display: grid;
  grid-template-columns: 1fr 1fr 0.55fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

/* 第二行：图书馆 + 说明 */
.ov-row2 {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 12px;
  flex: none;
}

.note-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--ci-text-2);
}

.note-link {
  color: var(--ci-primary);
  cursor: pointer;
  text-decoration: underline;
  &:hover { color: var(--ci-cyan); }
}

@media (max-width: 1400px) {
  .ov-kpi { grid-template-columns: repeat(2, 1fr); }
  .ov-row1 { grid-template-columns: 1fr 1fr; }
  .ov-pie { grid-column: 1 / -1; }
}

@media (max-width: 900px) {
  .ov-kpi { grid-template-columns: 1fr 1fr; }
  .ov-row1 { grid-template-columns: 1fr; }
  .ov-row2 { grid-template-columns: 1fr; }
}
</style>
