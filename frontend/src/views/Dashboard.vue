<script setup>
/**
 * 群体概览大屏（/dashboard）—— 1920×1080 一屏放下，深色主题
 *
 * 布局（CSS Grid 命名区域，改布局只动 grid-template-areas 不动 DOM）：
 *   工具条 → 4 张指标卡 → [左 消费趋势 | 中 时段热力 | 右 类别饼图 + 图书馆人流] → [聚类分布 + 簇画像说明]
 *
 * 数据加载策略：
 * - 各面板独立 loading / 独立 catch：任何一个接口失败只让那块区域空，不整屏白屏
 * - 聚类是最慢的接口（首次要训练模型），放最后并行发，慢不阻塞前 5 块图
 * - 时间窗口(days)/簇数(k)/特征集(features) 变化才重算，避免切窗口重复训练
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ClusteringApi, ConsumptionApi, LibraryApi, OverviewApi, PALETTE } from '@/api'
import { fmtInt, fmtMoney, fmtNum } from '@/utils/format'
import PanelBox from '@/components/PanelBox.vue'
import StatCard from '@/components/StatCard.vue'
import BaseChart from '@/components/BaseChart.vue'
import ConsumeHeatmap from '@/components/ConsumeHeatmap.vue'

const router = useRouter()

/* ---------------- 全局筛选状态 ---------------- */
const days = ref(30)
const k = ref(4)
const featureSet = ref('core')      // core = 毕设总纲要求的 4 特征
const heatMetric = ref('records')   // records 笔数 / amount 金额
const heatRef = ref(null)           // ConsumeHeatmap 组件实例，手动刷新时调它的 reload()
const autoRefresh = ref(false)
const dateWin = ref(['', ''])       // 后端数据实际起止（不叫 window，避开全局对象歧义）

const loading = reactive({ overview: false, trend: false, pie: false, lib: false, cluster: false })
const ov = ref({})
const trend = ref({})
const category = ref({})
const libHours = ref({})
const clu = ref({})
const elbow = ref({})

/* ---------------- 数据获取 ---------------- */
async function safe(key, fn) {
  loading[key] = true
  try {
    return await fn()
  } catch (e) {
    // 错误提示已由 axios 拦截器统一弹出，这里只保证 Promise.all 不被打断
    console.warn('[dashboard] 加载失败:', key, e.message)
    return null
  } finally {
    loading[key] = false
  }
}

async function loadOverview() {
  const d = await safe('overview', () => OverviewApi.stats({ days: days.value }))
  if (d) {
    ov.value = d
    dateWin.value = [d.date_start, d.date_end]
  }
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
async function loadCluster() {
  const params = { k: k.value, days: days.value, features: featureSet.value }
  const [r, e] = await Promise.all([
    safe('cluster', () => ClusteringApi.result(params, { timeout: 60000 })),
    safe('cluster', () => ClusteringApi.elbow({ ...params, k_min: 2, k_max: 8 }, { timeout: 60000 })),
  ])
  if (r) clu.value = r
  if (e) elbow.value = e
}

function loadAll() {
  // 前 4 块是纯 SQL 聚合，先出图；聚类单独发（首次训练可能几秒）
  // 热力图由 ConsumeHeatmap 组件自取数（watch days 自动 reload），这里不用管
  loadOverview(); loadTrend(); loadPie(); loadLib()
  loadCluster()
}

onMounted(() => {
  loadAll()
})

/* ---------------- 指标卡 ---------------- */
const cards = computed(() => {
  const d = ov.value
  return [
    {
      label: '学生总数', value: fmtInt(d.student_count), unit: '人', icon: 'UserFilled', color: '#37e2f0',
      hint: `消费流水 ${fmtInt(d.consumption_records)} 条 · 进馆 ${fmtInt(d.library_records)} 条`,
    },
    {
      label: '总消费额', value: fmtMoney(d.total_amount), unit: '元', icon: 'Money', color: '#ffd166',
      hint: `人均日消费 ${fmtNum(d.avg_daily_amount)} 元 · 高峰 ${d.consume_peak_hour ?? '--'} 时`,
    },
    {
      label: '日均图书馆时长', value: fmtNum(d.avg_daily_study_minutes, 1), unit: '分钟', icon: 'Reading', color: '#7ee787',
      hint: `人均累计 ${fmtNum(d.total_study_hours, 1)} 小时 · 高峰 ${d.library_peak_hour ?? '--'} 时`,
    },
    {
      label: '异常预警数', value: fmtInt(d.warning_count), unit: '条', icon: 'WarningFilled', color: '#ff6b81',
      hint: `未处理 ${fmtInt(d.warning_pending)} 条，点击右侧查看明细`, click: () => router.push({ name: 'warning' }),
    },
  ]
})

/* ---------------- 图 1：消费趋势（双 Y 轴 + 周末底色） ---------------- */
const trendOption = computed(() => {
  const t = trend.value
  const s = t.series || {}
  // 把连续的周末日期合并成 markArea 区间，比逐日着色更醒目
  const areas = []
  const flags = t.is_weekend || []
  for (let i = 0; i < flags.length; i++) {
    if (flags[i] && (i === 0 || !flags[i - 1])) areas.push([i, i])
    else if (flags[i] && areas.length) areas[areas.length - 1][1] = i
  }
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['日消费总额', '消费笔数', '日均在馆(小时)'], top: 2, right: 8 },
    grid: { left: 8, right: 8, top: 34, bottom: 6, containLabel: true },
    xAxis: { type: 'category', data: t.dates || [], axisLabel: { formatter: (v) => v.slice(5) } },
    yAxis: [
      { type: 'value', name: '元', nameTextStyle: { color: '#9fbadb' } },
      { type: 'value', name: '笔', position: 'right', splitLine: { show: false } },
    ],
    dataZoom: [{ type: 'inside', start: 0, end: 100 }],
    series: [
      {
        name: '日消费总额', type: 'line', data: s.amount || [], yAxisIndex: 0, areaStyle: { opacity: 0.18 },
        markArea: {
          silent: true, itemStyle: { color: 'rgba(255,209,102,0.07)' },
          data: areas.map(([a, b]) => [{ xAxis: (t.dates || [])[a] }, { xAxis: (t.dates || [])[b] }]),
        },
      },
      { name: '消费笔数', type: 'bar', data: s.records || [], yAxisIndex: 1, barMaxWidth: 10, itemStyle: { color: '#4ea1ff', opacity: 0.55 } },
      { name: '日均在馆(小时)', type: 'line', data: s.library_minutes || [], yAxisIndex: 1, smooth: true, lineStyle: { color: '#7ee787' }, itemStyle: { color: '#7ee787' } },
    ],
  }
})

/* ---------------- 图 2：消费时段热力图已抽成 ConsumeHeatmap 组件（自带补零/配色/峰值），此处不再内联 ---------------- */

/* ---------------- 图 3：消费类别饼图（金额占比） ---------------- */
const pieOption = computed(() => {
  const rows = category.value.by_merchant_type || []
  return {
    tooltip: { trigger: 'item', formatter: (p) => `${p.name}<br/>${p.value} 元（${p.percent}%）` },
    legend: { orient: 'vertical', right: 4, top: 'center', itemWidth: 10, itemHeight: 10 },
    series: [
      {
        type: 'pie', radius: ['42%', '68%'], center: ['38%', '52%'], avoidLabelOverlap: true,
        itemStyle: { borderColor: 'rgba(6,16,32,0.9)', borderWidth: 2 },
        label: { show: true, formatter: '{b}\n{d}%', color: '#c8ddf7', fontSize: 11 },
        labelLine: { length: 6, length2: 8 },
        data: rows.map((r) => ({ name: r.merchant_type, value: r.amount })),
      },
    ],
  }
})

/* ---------------- 图 4：图书馆分时段人流柱状图（标出双高峰） ---------------- */
const libOption = computed(() => {
  const rows = libHours.value.hour_dist || []
  return {
    tooltip: { trigger: 'axis', formatter: (p) => `${p[0].name}:00 进馆 ${p[0].value} 人次` },
    grid: { left: 6, right: 6, top: 10, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.hour), axisLabel: { interval: (i) => i % 3 === 0 } },
    yAxis: { type: 'value', name: '人次' },
    series: [
      {
        type: 'bar', barMaxWidth: 14, data: rows.map((r) => r.n),
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          // 学习高峰时段（14-16、19-21）高亮成主色，其余压暗，一眼看出双峰
          color: (p) => ([14, 15, 16, 19, 20, 21].includes(p.dataIndex) ? '#37e2f0' : 'rgba(78,161,255,0.42)'),
        },
        markPoint: { symbolSize: 34, data: [{ type: 'max', name: '最高峰' }], itemStyle: { color: '#ffd166' } },
      },
    ],
  }
})

/* ---------------- 图 5：聚类群体分布柱状图 ---------------- */
const clusterOption = computed(() => {
  const cs = clu.value.clusters || []
  return {
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (p) => {
        const c = cs[p[0].dataIndex]
        if (!c) return ''
        const lines = Object.entries(c.features || {}).map(([key, v]) => {
          const meta = clu.value.features?.[key]
          return `${meta?.label || key}：${v} ${meta?.unit || ''}`
        })
        return `<b>${c.label}</b>（簇 ${c.cluster}，${c.size} 人 / ${c.pct}%）<br/>` + lines.join('<br/>')
      },
    },
    grid: { left: 6, right: 6, top: 26, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: cs.map((c) => c.label), axisLabel: { interval: 0, fontSize: 12 } },
    yAxis: { type: 'value', name: '人数' },
    series: [
      {
        type: 'bar', barMaxWidth: 74, data: cs.map((c) => c.size),
        label: { show: true, position: 'top', color: '#dcecff', formatter: (p) => `${p.value} 人 / ${cs[p.dataIndex].pct}%` },
        itemStyle: { color: (p) => PALETTE[p.dataIndex % PALETTE.length], borderRadius: [5, 5, 0, 0] },
      },
    ],
  }
})

/* ---------------- 弹窗：PCA 散点 + 手肘曲线（答辩演示簇质量用） ---------------- */
const dialog = ref(false)
const scatterOption = computed(() => {
  const pts = clu.value.points || []
  const cs = clu.value.clusters || []
  return {
    tooltip: { formatter: (p) => `${p.data[2]}<br/>${p.seriesName}` },
    legend: { top: 2, type: 'scroll', data: cs.map((c) => c.label) },
    grid: { left: 30, right: 16, top: 40, bottom: 20, containLabel: true },
    xAxis: { type: 'value', name: 'PC1', scale: true },
    yAxis: { type: 'value', name: 'PC2', scale: true },
    series: cs.map((c, i) => ({
      name: c.label, type: 'scatter', symbolSize: 7,
      itemStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.8 },
      // 第 3 位存姓名，tooltip 里能直接点到具体学生
      data: pts.filter((p) => p.cluster === c.cluster).map((p) => [p.x, p.y, p.name || p.student_id]),
    })),
  }
})
const elbowOption = computed(() => {
  const e = elbow.value
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['SSE(误差平方和)', '轮廓系数'], top: 2 },
    grid: { left: 20, right: 20, top: 40, bottom: 10, containLabel: true },
    xAxis: { type: 'category', data: e.k || [], name: 'K' },
    yAxis: [
      { type: 'value', name: 'SSE', scale: true },
      { type: 'value', name: '轮廓系数', min: 0, max: 0.6, splitLine: { show: false } },
    ],
    series: [
      { name: 'SSE(误差平方和)', type: 'line', data: e.sse || [], areaStyle: { opacity: 0.12 } },
      { name: '轮廓系数', type: 'line', yAxisIndex: 1, data: e.silhouette || [], lineStyle: { color: '#ffd166' }, itemStyle: { color: '#ffd166' } },
    ],
  }
})

/* ---------------- 簇成员抽屉 ---------------- */
const drawer = ref(false)
const drawerData = ref({})
async function openMembers(idx) {
  const c = (clu.value.clusters || [])[idx]
  if (!c) return
  drawer.value = true
  drawerData.value = { cluster: c }
  const d = await ClusteringApi.members({ cluster: c.cluster, k: k.value, features: featureSet.value, limit: 50 })
  if (d) drawerData.value = { cluster: c, ...d }
}

function onClusterClick(p) {
  if (p.componentType === 'series') openMembers(p.dataIndex)
}

/* ---------------- 自动刷新（值班大屏长时间挂着，数据被重新扫描后要自己更新） ---------------- */
let timer = null
function toggleAuto(v) {
  clearInterval(timer)
  if (v) timer = setInterval(loadAll, 60000)
}
onBeforeUnmount(() => clearInterval(timer))

/* ---------------- 交互 ---------------- */
function refreshAll() {
  loadAll()
  // 热力图数据在子组件内部，父级刷新时通过 ref 调它的 reload()
  heatRef.value?.reload()
}
const clusterMeta = computed(() => ({
  silhouette: clu.value.silhouette, sse: clu.value.sse, pca: clu.value.pca_explained, n: clu.value.n_students,
}))
</script>

<template>
  <div class="dashboard">
    <!-- 工具条 -->
    <div class="dash-bar">
      <span class="sb-muted">数据区间：{{ dateWin[0] }} ~ {{ dateWin[1] }}</span>
      <el-radio-group v-model="days" size="small" @change="loadAll">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="14">近 14 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">全部</el-radio-button>
      </el-radio-group>
      <el-divider direction="vertical" />
      <span class="sb-muted">聚类</span>
      <el-select v-model="k" size="small" style="width: 92px" @change="loadCluster">
        <el-option v-for="i in [3, 4, 5, 6]" :key="i" :label="`K=${i}`" :value="i" />
      </el-select>
      <el-select v-model="featureSet" size="small" style="width: 130px" @change="loadCluster">
        <el-option value="core" label="core 4 特征" />
        <el-option value="full" label="full 11 特征" />
      </el-select>
      <div class="dash-bar__right">
        <el-switch v-model="autoRefresh" size="small" active-text="自动刷新" @change="toggleAuto" />
        <el-button size="small" text @click="refreshAll"><el-icon><Refresh /></el-icon>刷新</el-button>
      </div>
    </div>

    <!-- 4 个指标卡 -->
    <div class="dash-kpi">
      <StatCard
        v-for="c in cards" :key="c.label" :label="c.label" :value="c.value" :unit="c.unit"
        :icon="c.icon" :color="c.color" :hint="c.hint" :style="c.click ? { cursor: 'pointer' } : {}"
        @click="c.click && c.click()"
      />
    </div>

    <PanelBox class="p-trend" title="消费趋势" :subtitle="`近 ${days} 天（底色为周末）`">
      <BaseChart :option="trendOption" :loading="loading.trend" />
    </PanelBox>

    <PanelBox class="p-heat" title="消费时段热力图" subtitle="24 小时 × 7 天">
      <template #extra>
        <el-radio-group v-model="heatMetric" size="small">
          <el-radio-button value="records">笔数</el-radio-button>
          <el-radio-button value="amount">金额</el-radio-button>
        </el-radio-group>
      </template>
      <ConsumeHeatmap ref="heatRef" :days="days" :metric="heatMetric" />
    </PanelBox>

    <PanelBox class="p-pie" title="消费类别占比" subtitle="按商户类型">
      <BaseChart :option="pieOption" :loading="loading.pie" />
    </PanelBox>

    <PanelBox class="p-lib" title="图书馆人流时段分布" subtitle="高亮学习高峰">
      <BaseChart :option="libOption" :loading="loading.lib" />
    </PanelBox>

    <PanelBox class="p-cluster" title="K-Means 群体分布" :subtitle="`K=${k} · ${featureSet} 特征集`">
      <template #extra>
        <span v-if="clusterMeta.silhouette != null" class="sb-muted">
          轮廓系数 {{ clusterMeta.silhouette }} · SSE {{ clusterMeta.sse }} · 样本 {{ clusterMeta.n }} 人
        </span>
        <el-button size="small" text @click="dialog = true">簇质量图</el-button>
      </template>
      <BaseChart :option="clusterOption" :loading="loading.cluster" @click="onClusterClick" />
    </PanelBox>

    <PanelBox class="p-list" title="簇画像解读" subtitle="点击查看成员">
      <div class="cluster-list">
        <div
          v-for="(c, i) in clu.clusters || []" :key="c.cluster" class="cluster-item"
          @click="openMembers(i)"
        >
          <div class="cluster-item__head">
            <i class="dot" :style="{ background: PALETTE[i % PALETTE.length] }" />
            <b>{{ c.label }}</b>
            <span class="sb-muted">{{ c.size }} 人 / {{ c.pct }}%</span>
          </div>
          <div class="cluster-item__bar">
            <i :style="{ width: c.pct + '%', background: PALETTE[i % PALETTE.length] }" />
          </div>
          <div class="cluster-item__desc">{{ c.desc }}</div>
        </div>
        <el-empty v-if="!(clu.clusters || []).length && !loading.cluster" description="暂无聚类结果" :image-size="60" />
      </div>
    </PanelBox>

    <!-- 簇质量：PCA 散点 + 手肘曲线 -->
    <el-dialog v-model="dialog" title="聚类质量评估" width="1080px" align-center>
      <div class="quality">
        <div class="quality__box"><BaseChart :option="scatterOption" height="420px" /></div>
        <div class="quality__box"><BaseChart :option="elbowOption" height="420px" /></div>
      </div>
      <p class="sb-muted quality__note">
        左图是标准化特征经 PCA 降到前两主成分后的散点（解释度 {{ clu.pca_explained || '--' }}），
        仅用于观察簇分离程度，不参与聚类；右图是 K=2~8 的 SSE 与轮廓系数，簇数按"SSE 边际收益明显下降 + 可解释性"确定。
      </p>
    </el-dialog>

    <!-- 簇成员 -->
    <el-drawer v-model="drawer" size="720px" :title="`簇 ${drawerData.cluster?.cluster ?? ''}：${drawerData.cluster?.label ?? ''}`">
      <el-alert v-if="drawerData.cluster" :title="drawerData.cluster.desc" :description="drawerData.cluster.definition" type="info" :closable="false" class="mb" />
      <el-descriptions v-if="drawerData.cluster" :column="2" border size="small" class="mb">
        <el-descriptions-item v-for="(v, key) in drawerData.cluster.features" :key="key" :label="clu.features?.[key]?.label || key">
          {{ v }} {{ clu.features?.[key]?.unit }}
        </el-descriptions-item>
      </el-descriptions>
      <el-table :data="drawerData.items || []" height="calc(100% - 190px)" size="small" @row-click="(r) => router.push(`/student/${r.student_id}`)">
        <el-table-column prop="student_id" label="学号" width="120" />
        <el-table-column prop="name" label="姓名" width="90" />
        <el-table-column prop="college" label="学院" min-width="160" show-overflow-tooltip />
        <el-table-column
          v-for="key in clu.feature_keys || []" :key="key" :label="clu.features?.[key]?.label || key" width="118" align="right"
        >
          <template #default="{ row }">{{ row.features?.[key] }}</template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<style scoped>
/* 1920×1080 一屏：命名区域把 8 个块摆进 5 行 12 列，改布局只改这张表 */
.dashboard {
  height: 100%;
  padding: 10px 14px 14px;
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(12, 1fr);
  grid-template-rows: 34px 100px minmax(0, 1fr) minmax(0, 1fr) 236px;
  grid-template-areas:
    'bar bar bar bar bar bar bar bar bar bar bar bar'
    'kpi kpi kpi kpi kpi kpi kpi kpi kpi kpi kpi kpi'
    'tr  tr  tr  tr  hm  hm  hm  hm  hm  pt  pt  pt'
    'tr  tr  tr  tr  hm  hm  hm  hm  hm  br  br  br'
    'cl  cl  cl  cl  cl  cl  cl  cl  cl  ls  ls  ls';
}

.dash-bar {
  grid-area: bar;
  display: flex;
  align-items: center;
  gap: 12px;
}

.dash-bar__right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.dash-kpi {
  grid-area: kpi;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  min-height: 0;
}

.p-trend { grid-area: tr; }
.p-heat  { grid-area: hm; }
.p-pie   { grid-area: pt; }
.p-lib   { grid-area: br; }
.p-cluster { grid-area: cl; }
.p-list  { grid-area: ls; }

.cluster-list {
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 2px;
}

.cluster-item {
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(64, 128, 200, 0.14);
  cursor: pointer;
  transition: 0.2s;
}

.cluster-item:hover {
  border-color: rgba(55, 226, 240, 0.55);
  background: rgba(55, 226, 240, 0.07);
}

.cluster-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.cluster-item__head .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.cluster-item__head span {
  margin-left: auto;
}

.cluster-item__bar {
  height: 3px;
  margin: 6px 0;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.cluster-item__bar i {
  display: block;
  height: 100%;
}

.cluster-item__desc {
  font-size: 12px;
  color: var(--sb-text-dim);
  line-height: 1.5;
}

.quality {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.quality__box {
  height: 420px;
  border: 1px solid rgba(64, 128, 200, 0.18);
  border-radius: 8px;
}

.quality__note {
  margin: 10px 2px 0;
  line-height: 1.7;
}

.mb {
  margin-bottom: 12px;
}

/* 笔记本/投影比 1920 窄时，允许纵向滚动而不是把图表压扁 */
@media (max-width: 1600px), (max-height: 940px) {
  .dashboard {
    height: auto;
    min-height: 100%;
    grid-template-rows: 34px 100px 320px 320px 300px;
  }
}
</style>
