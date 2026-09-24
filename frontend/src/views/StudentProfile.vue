<script setup>
/**
 * 个体画像页（/student/:id?）
 *
 * 数据源全部来自 GET /api/student/<id>/profile 一个接口（后端已把 kpi/radar/daily/cluster/warnings 拼好），
 * 明细表格再单独分页拉取，避免一次把几千条流水传给前端。
 *
 * 关键交互：
 * - 学号搜索用 el-select 远程检索（后端 keyword 支持学号前缀与姓名），比让评委手打学号友好
 * - :id 变化即重新查询，因此从大屏簇成员表、预警列表点进来的跳转都能自动出结果
 * - 查无此人（404）用表单内提示而不是全局 toast，所以该请求带 silent: true
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { StudentApi } from '@/api'
import { fmtInt, fmtNum } from '@/utils/format'
import PanelBox from '@/components/PanelBox.vue'
import BaseChart from '@/components/BaseChart.vue'

const route = useRoute()
const router = useRouter()

const MERCHANT_TYPES = { 1: '食堂', 2: '超市', 3: '浴室', 4: '机房', 5: '其他' }

const sid = ref('')
const days = ref(30)
const featureSet = ref('full')     // full 特征集雷达维度更多，画像页演示效果更完整
const loading = ref(false)
const error = ref('')
const data = ref({})
const options = ref([])
const searching = ref(false)

/* ---------------- 搜索 ---------------- */
async function remoteSearch(q) {
  searching.value = true
  try {
    const d = await StudentApi.list({ keyword: q || '', size: 20 })
    options.value = (d?.items || []).map((s) => ({
      value: s.student_id,
      label: `${s.student_id}  ${s.name}`,
      sub: `${s.college || ''} ${s.major || ''} ${s.class_name || ''}`,
    }))
  } finally {
    searching.value = false
  }
}

function go(id) {
  if (id) router.push({ name: 'student-profile', params: { id } })
}

/* ---------------- 主体数据 ---------------- */
async function load() {
  const id = sid.value
  if (!id) return
  loading.value = true
  error.value = ''
  try {
    data.value = await StudentApi.profile(id, { days: days.value, features: featureSet.value }, { silent: true, timeout: 60000 })
    loadDetail(1)
  } catch (e) {
    data.value = {}
    error.value = e.httpStatus === 404 ? `学号 ${id} 不存在，请核对后重试` : e.message
  } finally {
    loading.value = false
  }
}

/* ---------------- 明细（消费 / 进馆 两个表格共用分页状态） ---------------- */
const tab = ref('consumption')
const detail = ref({})
const page = ref(1)
const size = ref(10)

async function loadDetail(p = page.value) {
  const id = sid.value
  if (!id) return
  const params = { page: p, size: size.value }
  detail.value = tab.value === 'consumption'
    ? await StudentApi.consumption(id, params)
    : await StudentApi.library(id, params)
}

watch([tab], () => {
  page.value = 1
  loadDetail(1)
})
watch(() => [route.params.id], ([v]) => {
  sid.value = v || ''
  if (!sid.value) { data.value = {}; return }
  load()
})
watch([days, featureSet], load)

onMounted(async () => {
  sid.value = route.params.id || ''
  await remoteSearch('')
  if (sid.value) load()
})

/* ---------------- 派生：KPI 卡片 ---------------- */
const kpiCards = computed(() => {
  const k = data.value.kpi || {}
  return [
    { label: '窗口总消费', v: `${fmtNum(k.total_amount)} 元`, s: `共 ${fmtInt(k.records)} 笔` },
    { label: '日均消费', v: `${fmtNum(k.avg_daily_amount)} 元`, s: `在校有消费 ${fmtInt(k.active_days)} 天` },
    { label: '日均消费频次', v: `${fmtNum(k.avg_daily_records)} 笔`, s: `单笔均额 ${fmtNum(k.avg_per_record)} 元` },
    { label: '三餐规律率', v: `${fmtNum(k.meal_regular_rate, 1)}%`, s: `缺餐率 ${fmtNum(k.missing_meal_rate, 1)}%`, warn: (k.meal_regular_rate ?? 100) < 30 },
    { label: '日均图书馆', v: `${fmtNum(k.avg_daily_study_minutes, 1)} 分`, s: `累计 ${fmtNum(k.total_study_hours, 1)} 小时` },
    { label: '进馆天数率', v: `${fmtNum(k.library_days_ratio, 1)}%`, s: `单次均留 ${fmtNum(k.avg_stay_minutes, 1)} 分钟` },
    { label: '深夜消费', v: `${fmtInt(k.night_times)} 次`, s: '23:00-05:00 口径', warn: (k.night_times ?? 0) > 0 },
    { label: '晚间自习', v: `${fmtInt(k.evening_study_visits)} 次`, s: '18 点后进馆' },
  ]
})

/* ---------------- 雷达图：值已经是"群体内百分位"，所以统一 0-100 可读 ---------------- */
const radarOption = computed(() => {
  const r = data.value.radar || {}
  const inds = r.indicators || []
  if (!inds.length) return {}
  const names = inds.map((i) => i.name)
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const raw = p.data?.raw || {}
        return `<b>${p.name}</b><br/>` + names.map((n, i) =>
          `${n}：${p.value[i]} 分位（${raw[i]}）`).join('<br/>')
      },
    },
    legend: { bottom: 0, data: ['本人', '全校平均基线'] },
    radar: {
      indicator: inds, radius: '62%', center: ['50%', '46%'],
      axisName: { color: '#bcd6f5', fontSize: 12 },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            name: '本人', value: r.values || [], lineStyle: { width: 2, color: '#37e2f0' },
            itemStyle: { color: '#37e2f0' }, areaStyle: { color: 'rgba(55,226,240,0.25)' },
            // 原始值随点带出去，tooltip 里"分位 + 实际值"同时显示
            raw: names.map((n, i) => `${fmtNum((r.raw || {})[r.keys[i]])}${unitOf(r.keys[i])}`),
          },
          {
            name: '全校平均基线', value: names.map(() => 50), symbol: 'none',
            lineStyle: { width: 1, type: 'dashed', color: 'rgba(200,220,247,0.6)' },
          },
        ],
      },
    ],
  }
})

/** 百分位雷达丢了单位，tooltip 里按特征名补回来（反向项在括号里说明） */
function unitOf(key) {
  return { avg_daily_amount: ' 元', avg_daily_records: ' 笔', avg_daily_study_minutes: ' 分', meal_time_std: ' 分' }[key] || ''
}

/* ---------------- 每日趋势（消费 + 在馆时长双轴） ---------------- */
const dailyOption = computed(() => {
  const d = data.value.daily || {}
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['日消费(元)', '在馆(小时)', '正餐段数'] },
    grid: { left: 6, right: 6, top: 30, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: d.dates || [] },
    yAxis: [{ type: 'value', name: '元' }, { type: 'value', name: '小时/餐', splitLine: { show: false } }],
    series: [
      { name: '日消费(元)', type: 'bar', data: d.amount || [], barMaxWidth: 14, itemStyle: { color: '#4ea1ff' } },
      { name: '在馆(小时)', type: 'line', yAxisIndex: 1, data: d.library_minutes || [], itemStyle: { color: '#7ee787' } },
      { name: '正餐段数', type: 'line', yAxisIndex: 1, data: d.meals || [], itemStyle: { color: '#ffd166' }, step: 'middle' },
    ],
  }
})

/* ---------------- 时间线：近 14 天行为流水叙述 + 当天是否触发过预警 ---------------- */
const timeline = computed(() => {
  const d = data.value.daily || {}
  const n = (d.dates || []).length
  if (!n) return []
  // 预警接口给的是 YYYY-MM-DD，日趋势给的是 MM-DD，用后 5 位对齐
  const warnSet = new Set((data.value.warnings || []).map((w) => String(w.warning_date).slice(5)))
  const from = Math.max(0, n - 14)
  const out = []
  for (let i = n - 1; i >= from; i--) {
    const date = d.dates[i]
    const meals = d.meals[i] ?? 0
    out.push({
      date,
      warn: warnSet.has(date),
      color: warnSet.has(date) ? '#ff6b81' : (d.library_minutes[i] > 1 ? '#7ee787' : '#4ea1ff'),
      text: [
        `消费 ${fmtNum(d.amount[i])} 元 / ${d.records[i]} 笔`,
        `正餐 ${meals} 段`,
        d.library_visits[i] ? `进馆 ${d.library_visits[i]} 次、待 ${fmtNum(d.library_minutes[i])} 小时` : '未进馆',
      ].join(' · '),
    })
  }
  return out
})

/* ---------------- 簇对比：本人 vs 所属簇均值 vs 全校均值 ---------------- */
const cluster = computed(() => data.value.cluster)
const compareRows = computed(() => {
  const c = cluster.value
  const raw = data.value.radar?.raw || {}
  const gm = data.value.radar?.group_mean || {}
  // 后端 cluster 块不带 feature_keys，直接用 raw 的 key 集合（就是当前特征集的全部列）
  const keys = Object.keys(raw)
  return keys.map((key) => ({
    key,
    name: FEATURE_LABELS[key] || key,
    self: raw[key],
    group: gm[key],
    clusterMean: c?.cluster_mean?.[key],
  }))
})
// 与后端 clustering.FEATURES 的 label 保持同名同单位，避免前后端两套中文描述
const FEATURE_LABELS = {
  avg_daily_amount: '日均消费(元)', avg_daily_records: '日均频次(笔)',
  avg_daily_study_minutes: '日均在馆(分)', meal_time_std: '消费时间标准差(分)',
  amount_cv: '消费波动(%)', night_ratio: '深夜消费率(%)', meal_reg: '三餐规律率(%)',
  weekend_ratio: '周末消费率(%)', library_days_ratio: '进馆天数率(%)',
  avg_stay_minutes: '单次在馆(分)', evening_study_ratio: '晚间进馆率(%)',
}

/* ---------------- 预警记录 ---------------- */
const warnings = computed(() => data.value.warnings || [])

const info = computed(() => data.value.info || {})
</script>

<template>
  <div class="page">
    <!-- 查询条 -->
    <PanelBox title="个体行为画像" subtitle="输入学号或姓名检索">
      <template #extra>
        <el-select v-model="days" size="small" style="width: 108px">
          <el-option :value="7" label="近 7 天" />
          <el-option :value="14" label="近 14 天" />
          <el-option :value="30" label="近 30 天" />
          <el-option :value="90" label="全部" />
        </el-select>
        <el-select v-model="featureSet" size="small" style="width: 128px">
          <el-option value="core" label="core 4 特征" />
          <el-option value="full" label="full 11 特征" />
        </el-select>
      </template>
      <div class="search">
        <el-select
          v-model="sid" filterable remote reserve-keyword clearable placeholder="学号前缀 / 姓名"
          :remote-method="remoteSearch" :loading="searching" style="width: 320px" @change="go"
        >
          <el-option v-for="o in options" :key="o.value" :value="o.value" :label="o.label">
            <span style="float: left">{{ o.label }}</span>
            <span style="float: right; color: #8fabc9; font-size: 12px">{{ o.sub }}</span>
          </el-option>
        </el-select>
        <el-button type="primary" @click="go(sid)">查询画像</el-button>
        <el-button text @click="go(options[0]?.value)">随机看一位</el-button>
        <span v-if="error" class="search__err">{{ error }}</span>
      </div>
    </PanelBox>

    <el-skeleton v-if="loading && !data.info" :rows="8" animated class="mt" />

    <el-empty v-else-if="!data.info" description="请先查询一名学生" class="mt" />

    <template v-else>
      <!-- 基本信息 + KPI + 簇标签 -->
      <div class="row-top">
        <PanelBox class="cell" title="基本信息">
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="学号">{{ info.student_id }}</el-descriptions-item>
            <el-descriptions-item label="姓名">{{ info.name }}（{{ info.gender_text }}）</el-descriptions-item>
            <el-descriptions-item label="学院">{{ info.college }}</el-descriptions-item>
            <el-descriptions-item label="专业班级">{{ info.major }} / {{ info.class_name }}</el-descriptions-item>
            <el-descriptions-item label="年级">{{ info.grade_year }}</el-descriptions-item>
            <el-descriptions-item label="宿舍">{{ info.dorm_building }}</el-descriptions-item>
            <el-descriptions-item label="统计窗口">
              {{ data.window?.[0] }} ~ {{ data.window?.[1] }}（{{ data.days }} 天）
            </el-descriptions-item>
          </el-descriptions>
        </PanelBox>

        <PanelBox class="cell" title="行为指标" :subtitle="`窗口 ${data.days} 天，比率分母为窗口天数`">
          <div class="kpis">
            <div v-for="k in kpiCards" :key="k.label" class="kpi" :class="{ 'kpi--warn': k.warn }">
              <span>{{ k.label }}</span>
              <b>{{ k.v }}</b>
              <i>{{ k.s }}</i>
            </div>
          </div>
        </PanelBox>

        <PanelBox class="cell" title="画像聚类标签">
          <div v-if="cluster" class="cluster-card">
            <el-tag size="large" effect="dark" class="cluster-card__tag">{{ cluster.label }}</el-tag>
            <div class="sb-muted">簇 {{ cluster.cluster }} / 共 {{ cluster.k }} 类 · {{ cluster.feature_set }} 特征集</div>
            <p class="cluster-card__desc">{{ cluster.desc }}</p>
            <p class="cluster-card__def">{{ cluster.definition }}</p>
            <el-table :data="compareRows" size="small" max-height="190">
              <el-table-column prop="name" label="特征" min-width="140" show-overflow-tooltip />
              <el-table-column prop="self" label="本人" width="78" align="right" />
              <el-table-column prop="clusterMean" label="所属簇" width="86" align="right" />
              <el-table-column prop="group" label="全校" width="76" align="right" />
            </el-table>
          </div>
          <el-empty v-else description="该窗口无聚类结果" :image-size="60" />
        </PanelBox>
      </div>

      <!-- 雷达 + 趋势 -->
      <div class="row-mid">
        <PanelBox class="cell" title="多维行为雷达" subtitle="群体内百分位（50 = 全校平均）">
          <BaseChart :option="radarOption" height="330px" />
        </PanelBox>
        <PanelBox class="cell" title="近期行为趋势" subtitle="消费 / 在馆 / 正餐段数">
          <BaseChart :option="dailyOption" height="330px" />
        </PanelBox>
      </div>

      <!-- 时间线 + 明细 -->
      <div class="row-bottom">
        <PanelBox class="cell" title="近期行为时间线" subtitle="最近 14 天，红点表示当天有预警">
          <div class="tl">
            <el-timeline>
              <el-timeline-item
                v-for="t in timeline" :key="t.date" :timestamp="t.date" placement="top"
                :color="t.color" :hollow="!t.warn" size="normal"
              >
                <span :class="{ 'tl__warn': t.warn }">{{ t.text }}</span>
              </el-timeline-item>
            </el-timeline>
          </div>
        </PanelBox>

        <PanelBox class="cell" title="行为明细">
          <el-tabs v-model="tab" class="tabs">
            <el-tab-pane label="消费流水" name="consumption" />
            <el-tab-pane label="进馆记录" name="library" />
          </el-tabs>
          <el-table v-if="tab === 'consumption'" :data="detail.items || []" size="small" height="300">
            <el-table-column prop="consumed_at" label="时间" min-width="150" />
            <el-table-column label="类型" width="72">
              <template #default="{ row }">{{ MERCHANT_TYPES[row.merchant_type] || '其他' }}</template>
            </el-table-column>
            <el-table-column prop="merchant_name" label="商户" min-width="130" show-overflow-tooltip />
            <el-table-column prop="meal_period" label="餐段" width="72" />
            <el-table-column prop="amount" label="金额(元)" width="92" align="right" />
            <el-table-column prop="balance" label="余额(元)" width="96" align="right" />
          </el-table>
          <el-table v-else :data="detail.items || []" size="small" height="300">
            <el-table-column prop="venue" label="馆舍" min-width="110" />
            <el-table-column prop="area_name" label="区域" min-width="110" />
            <el-table-column prop="gate_in_time" label="进馆" min-width="150" />
            <el-table-column prop="gate_out_time" label="离馆" min-width="150" />
            <el-table-column prop="stay_minutes" label="时长(分)" width="92" align="right" />
          </el-table>
          <el-pagination
            v-model:current-page="page" :page-size="size" :total="detail.total || 0"
            layout="prev, pager, next, total" small class="mt" @current-change="loadDetail"
          />
        </PanelBox>
      </div>

      <!-- 该生历史预警 -->
      <PanelBox class="mt" title="该生预警记录" :subtitle="`共 ${warnings.length} 条（最多显示 20 条）`">
        <el-table :data="warnings" size="small" max-height="260">
          <el-table-column prop="warning_date" label="日期" width="118" />
          <el-table-column prop="rule_name" label="规则" width="150" />
          <el-table-column label="级别" width="80">
            <template #default="{ row }">
              <el-tag :type="row.warning_level === 3 ? 'danger' : row.warning_level === 2 ? 'warning' : 'info'" size="small">
                {{ row.warning_level_text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="说明" min-width="300" show-overflow-tooltip />
          <el-table-column prop="metric_value" label="指标值" width="96" align="right" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" text @click="router.push({ name: 'warning', query: { keyword: row.student_id } })">
                去处置
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </PanelBox>
    </template>
  </div>
</template>

<style scoped>
.mt {
  margin-top: 12px;
}

.search {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0 2px;
}

.search__err {
  color: var(--sb-red);
  font-size: 13px;
}

.row-top,
.row-mid,
.row-bottom {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.row-top {
  grid-template-columns: 1.05fr 1.7fr 1.25fr;
}

.row-mid,
.row-bottom {
  grid-template-columns: 1fr 1.35fr;
}

.row-top .cell,
.row-bottom .cell {
  min-height: 320px;
}

.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.kpi {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(64, 128, 200, 0.14);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kpi span {
  font-size: 12px;
  color: var(--sb-text-dim);
}

.kpi b {
  font-size: 17px;
  color: var(--sb-accent);
  font-variant-numeric: tabular-nums;
}

.kpi i {
  font-style: normal;
  font-size: 11px;
  color: var(--sb-text-dim);
}

.kpi--warn b {
  color: var(--sb-red);
}

.cluster-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cluster-card__tag {
  align-self: flex-start;
  font-size: 15px;
  letter-spacing: 1px;
}

.cluster-card__desc,
.cluster-card__def {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--sb-text);
}

.cluster-card__def {
  color: var(--sb-text-dim);
}

.tl {
  max-height: 330px;
  overflow: auto;
  padding: 6px 4px 0 6px;
}

.tl__warn {
  color: var(--sb-red);
}

.tabs {
  margin-top: -6px;
}

@media (max-width: 1500px) {
  .row-top,
  .row-mid,
  .row-bottom {
    grid-template-columns: 1fr;
  }
}
</style>
