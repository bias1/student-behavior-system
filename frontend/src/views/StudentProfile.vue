<script setup>
/**
 * 个体画像页（/student/:id?）—— 重构版，无 EP
 *
 * 数据源：GET /api/student/<id>/profile（kpi/radar/daily/cluster/warnings 已拼好）
 * 明细：单独分页拉 /student/<id>/consumption 和 /student/<id>/library
 *
 * 变化：
 *   - 学号搜索用 UInput + 下拉建议（远程搜索），不再用 el-select remote
 *   - KPI、雷达、趋势图逻辑不变，图表容器改用 UCard
 *   - 预警历史、明细表格用 UTable / UPagination
 *   - toast 替代 ElMessage
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, Shuffle } from 'lucide-vue-next'
import { StudentApi } from '@/api'
import { dataSpan, windowOptions } from '@/utils/window'
import { fmtInt, fmtNum } from '@/utils/format'
import BaseChart from '@/components/BaseChart.vue'
import UCard from '@/components/ui/UCard.vue'
import UInput from '@/components/ui/UInput.vue'
import USelect from '@/components/ui/USelect.vue'
import USegmented from '@/components/ui/USegmented.vue'
import UButton from '@/components/ui/UButton.vue'
import UBadge from '@/components/ui/UBadge.vue'
import UTable from '@/components/ui/UTable.vue'
import UPagination from '@/components/ui/UPagination.vue'
import USkeleton from '@/components/ui/USkeleton.vue'
import UEmptyState from '@/components/ui/UEmptyState.vue'

const route = useRoute()
const router = useRouter()

const MERCHANT_TYPES = { 1: '食堂', 2: '超市', 3: '浴室', 4: '机房', 5: '其他' }

const sid = ref('')
const days = ref(30)
// 数据实际跨度（天），来自 /overview/meta，“全部”选项用它而不是硬编码 90
const span = ref(0)
const featureSet = ref('full')
const loading = ref(false)
const error = ref('')
const data = ref({})

/* ---------------- 搜索建议下拉 ---------------- */
const suggestions = ref([])
const searchQuery = ref('')
const searching = ref(false)
const showSuggest = ref(false)

async function remoteSearch(q, openList = true) {
  searching.value = true
  try {
    const d = await StudentApi.list({ keyword: q || '', size: 10 })
    suggestions.value = (d?.items || []).map((s) => ({
      value: s.student_id,
      label: `${s.student_id}  ${s.name}`,
      sub: `${s.college || ''} ${s.major || ''}`,
    }))
    // openList=false 仅预热数据（随机看一位需要建议列表），不弹出下拉：
    // 列表只在用户点击/输入搜索框时才出现
    if (openList) showSuggest.value = suggestions.value.length > 0
  } finally { searching.value = false }
}

function pickSuggest(item) {
  searchQuery.value = item.label
  sid.value = item.value
  showSuggest.value = false
  router.push({ name: 'student-profile', params: { id: item.value } })
}

function onSearchBlur() {
  // 延时，避免点击 suggestion 时 blur 早于 click
  setTimeout(() => { showSuggest.value = false }, 200)
}

// 点击搜索框：预热的建议立即展示（不等网络往返），随后后台刷新
function onSearchFocus() {
  if (suggestions.value.length) showSuggest.value = true
  remoteSearch('')
}

function go(id) {
  if (id) router.push({ name: 'student-profile', params: { id } })
  else load()
}

// 输入后 sid 已被 @input 清空，回车若只绑 go(sid) 会空转；改成默认采纳第一条建议
function onEnter() {
  if (sid.value) go(sid.value)
  else if (suggestions.value.length) pickSuggest(suggestions.value[0])
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
  } finally { loading.value = false }
}

/* ---------------- 明细 ---------------- */
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

const DAYS_OPTS = computed(() => windowOptions(span.value))

const FEATURE_OPTS = [
  { value: 'core', label: 'core 4 特征' },
  { value: 'full', label: 'full 11 特征' },
]

watch(tab, () => { page.value = 1; loadDetail(1) })
// :id? 是普通路由参数，回调拿到的是字符串；不能数组解构（字符串可迭代，
// ([v]) 会取到学号首字符，导致请求 /api/student/2/profile 404
watch(() => route.params.id, (v) => {
  sid.value = v || ''
  if (!sid.value) { data.value = {}; return }
  load()
})
watch([days, featureSet], load)

onMounted(async () => {
  sid.value = route.params.id || ''
  span.value = await dataSpan()
  let clamped = false
  if (span.value > 0 && days.value > span.value) { days.value = span.value; clamped = true }
  await remoteSearch('', false)   // 只预热建议数据，不在加载时弹出下拉
  if (sid.value) {
    searchQuery.value = sid.value
    if (!clamped) load()   // 被钳窗口时 watch(days) 已触发过 load，不重复拉
  }
})

/* ---------------- KPI 卡片数据 ---------------- */
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

/* ---------------- 雷达图 ---------------- */
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
        return `<b>${p.name}</b><br/>` + names.map((n, i) => `${n}：${p.value[i]} 分位（${raw[i]}）`).join('<br/>')
      },
    },
    legend: { bottom: 0, data: ['本人', '全校平均基线'] },
    radar: {
      indicator: inds, radius: '62%', center: ['50%', '46%'],
      axisName: { color: '#8b96a5', fontSize: 12 },
    },
    series: [{
      type: 'radar',
      data: [
        {
          name: '本人', value: r.values || [],
          lineStyle: { width: 2, color: '#4fd1ff' },
          itemStyle: { color: '#4fd1ff' },
          areaStyle: { color: 'rgba(79,209,255,0.2)' },
          raw: names.map((n, i) => `${fmtNum((r.raw || {})[r.keys[i]])}${unitOf(r.keys[i])}`),
        },
        {
          name: '全校平均基线', value: names.map(() => 50), symbol: 'none',
          lineStyle: { width: 1, type: 'dashed', color: 'rgba(139,150,165,0.6)' },
        },
      ],
    }],
  }
})

function unitOf(key) {
  return { avg_daily_amount: ' 元', avg_daily_records: ' 笔', avg_daily_study_minutes: ' 分', meal_time_std: ' 分' }[key] || ''
}

/* ---------------- 每日趋势 ---------------- */
const dailyOption = computed(() => {
  const d = data.value.daily || {}
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['日消费(元)', '在馆(小时)', '正餐段数'] },
    grid: { left: 6, right: 6, top: 30, bottom: 4, containLabel: true },
    xAxis: { type: 'category', data: d.dates || [] },
    yAxis: [{ type: 'value', name: '元' }, { type: 'value', name: '小时/餐', splitLine: { show: false } }],
    series: [
      { name: '日消费(元)', type: 'bar', data: d.amount || [], barMaxWidth: 14, itemStyle: { color: '#4fd1ff', opacity: 0.7 } },
      { name: '在馆(小时)', type: 'line', yAxisIndex: 1, data: d.library_minutes || [], itemStyle: { color: '#37d996' }, lineStyle: { color: '#37d996' } },
      { name: '正餐段数', type: 'line', yAxisIndex: 1, data: d.meals || [], itemStyle: { color: '#ffb454' }, lineStyle: { color: '#ffb454' }, step: 'middle' },
    ],
  }
})

/* ---------------- 时间线 ---------------- */
const timeline = computed(() => {
  const d = data.value.daily || {}
  const n = (d.dates || []).length
  if (!n) return []
  const warnSet = new Set((data.value.warnings || []).map((w) => String(w.warning_date).slice(5)))
  const from = Math.max(0, n - 14)
  const out = []
  for (let i = n - 1; i >= from; i--) {
    const date = d.dates[i]
    const meals = d.meals[i] ?? 0
    out.push({
      date,
      warn: warnSet.has(date),
      color: warnSet.has(date) ? 'var(--ci-danger)' : (d.library_minutes[i] > 1 ? 'var(--ci-success)' : 'var(--ci-cyan)'),
      text: [
        `消费 ${fmtNum(d.amount[i])} 元 / ${d.records[i]} 笔`,
        `正餐 ${meals} 段`,
        d.library_visits[i] ? `进馆 ${d.library_visits[i]} 次、待 ${fmtNum(d.library_minutes[i])} 小时` : '未进馆',
      ].join(' · '),
    })
  }
  return out
})

/* ---------------- 簇对比 ---------------- */
const cluster = computed(() => data.value.cluster)
const FEATURE_LABELS = {
  avg_daily_amount: '日均消费(元)', avg_daily_records: '日均频次(笔)',
  avg_daily_study_minutes: '日均在馆(分)', meal_time_std: '消费时间标准差(分)',
  amount_cv: '消费波动(%)', night_ratio: '深夜消费率(%)', meal_reg: '三餐规律率(%)',
  weekend_ratio: '周末消费率(%)', library_days_ratio: '进馆天数率(%)',
  avg_stay_minutes: '单次在馆(分)', evening_study_ratio: '晚间进馆率(%)',
}
const compareRows = computed(() => {
  const c = cluster.value
  const raw = data.value.radar?.raw || {}
  const gm = data.value.radar?.group_mean || {}
  return Object.keys(raw).map((key) => ({
    key, name: FEATURE_LABELS[key] || key,
    self: raw[key], group: gm[key], clusterMean: c?.cluster_mean?.[key],
  }))
})

const warnings = computed(() => data.value.warnings || [])
const info = computed(() => data.value.info || {})
</script>

<template>
  <div class="profile-page">
    <!-- 查询工具栏 -->
    <!-- 搜索建议是卡内绝对定位浮层，必须 allow-overflow，否则被卡片 overflow 裁切 -->
    <UCard title="个体行为画像" subtitle="输入学号或姓名检索" allow-overflow>
      <template #extra>
        <USegmented v-model="days" :options="DAYS_OPTS" size="sm" />
        <USelect v-model="featureSet" :options="FEATURE_OPTS" width="136px" placeholder="特征集" />
      </template>

      <div class="pf-search">
        <div class="pf-suggest-wrap">
          <UInput
            v-model="searchQuery"
            placeholder="学号前缀 / 姓名"
            width="320px"
            @enter="onEnter"
            @focus="onSearchFocus"
            @input="() => { sid = ''; remoteSearch(searchQuery) }"
            @blur="onSearchBlur"
          >
            <template #prefix><Search :size="13" /></template>
          </UInput>
          <div v-if="showSuggest" class="pf-suggest">
            <div
              v-for="item in suggestions" :key="item.value"
              class="pf-suggest__item"
              @mousedown="pickSuggest(item)"
            >
              <span>{{ item.label }}</span>
              <span class="pf-suggest__sub">{{ item.sub }}</span>
            </div>
            <div v-if="!suggestions.length && searching" class="pf-suggest__empty">搜索中...</div>
          </div>
        </div>
        <UButton variant="primary" @click="go(sid)">查询画像</UButton>
        <UButton variant="ghost" @click="() => { const r = suggestions[Math.floor(Math.random() * suggestions.length)]; r && pickSuggest(r) }">
          <Shuffle :size="13" /> 随机看一位
        </UButton>
        <span v-if="error" class="pf-err">{{ error }}</span>
      </div>
    </UCard>

    <!-- 加载中骨架 -->
    <USkeleton v-if="loading && !data.info" :lines="10" class="pf-mt" />

    <!-- 无数据空态 -->
    <UEmptyState v-else-if="!data.info" title="请先查询一名学生" hint="在上方输入学号或姓名搜索" class="pf-mt" />

    <template v-else>
      <!-- 基本信息 + KPI + 簇标签 -->
      <div class="pf-row1">
        <UCard title="基本信息" padded class="pf-col1">
          <div class="pf-info">
            <div class="pf-info__row"><span>学号</span><b>{{ info.student_id }}</b></div>
            <div class="pf-info__row"><span>姓名</span><b>{{ info.name }}</b><UBadge tone="neutral" style="margin-left:6px">{{ info.gender_text }}</UBadge></div>
            <div class="pf-info__row"><span>学院</span><b>{{ info.college }}</b></div>
            <div class="pf-info__row"><span>专业班级</span><b>{{ info.major }} / {{ info.class_name }}</b></div>
            <div class="pf-info__row"><span>年级</span><b>{{ info.grade_year }}</b></div>
            <div class="pf-info__row"><span>宿舍</span><b>{{ info.dorm_building }}</b></div>
            <div class="pf-info__row"><span>统计窗口</span><b>{{ data.window?.[0] }} ~ {{ data.window?.[1] }}（{{ data.days }} 天）</b></div>
          </div>
        </UCard>

        <UCard title="行为指标" :subtitle="`窗口 ${data.days} 天`" padded class="pf-col2">
          <div class="pf-kpis">
            <div v-for="k in kpiCards" :key="k.label" class="pf-kpi" :class="{ 'pf-kpi--warn': k.warn }">
              <span class="pf-kpi__lbl">{{ k.label }}</span>
              <b class="pf-kpi__v">{{ k.v }}</b>
              <i class="pf-kpi__s">{{ k.s }}</i>
            </div>
          </div>
        </UCard>

        <UCard title="聚类标签" padded class="pf-col3">
          <div v-if="cluster" class="pf-cluster">
            <UBadge tone="primary" size="lg">{{ cluster.label }}</UBadge>
            <p class="pf-cluster__meta">簇 {{ cluster.cluster }} / 共 {{ cluster.k }} 类 · {{ cluster.feature_set }} 特征集</p>
            <p class="pf-cluster__desc">{{ cluster.desc }}</p>
            <UTable
              :columns="[
                { key:'name', label:'特征', width:'140px' },
                { key:'self', label:'本人', width:'70px', align:'right' },
                { key:'clusterMean', label:'所属簇', width:'80px', align:'right' },
                { key:'group', label:'全校', width:'70px', align:'right' },
              ]"
              :items="compareRows"
              row-key="key"
              dense
            />
          </div>
          <UEmptyState v-else description="该窗口无聚类结果" />
        </UCard>
      </div>

      <!-- 雷达 + 趋势 -->
      <div class="pf-row2">
        <UCard title="多维行为雷达" subtitle="群体内百分位（50 = 全校平均）" class="pf-col-half">
          <BaseChart :option="radarOption" height="320px" />
        </UCard>
        <UCard title="近期行为趋势" subtitle="消费 / 在馆 / 正餐段数" class="pf-col-half">
          <BaseChart :option="dailyOption" height="320px" />
        </UCard>
      </div>

      <!-- 时间线 + 明细 -->
      <div class="pf-row3">
        <UCard title="近期行为时间线" subtitle="最近 14 天，红点表示当天有预警" padded class="pf-col-half">
          <div class="pf-timeline">
            <div v-for="t in timeline" :key="t.date" class="pf-tl__item">
              <span class="pf-tl__dot" :style="{ background: t.color }" />
              <div class="pf-tl__body">
                <span class="pf-tl__date">{{ t.date }}</span>
                <span class="pf-tl__text" :class="{ 'pf-tl__text--warn': t.warn }">{{ t.text }}</span>
              </div>
            </div>
          </div>
        </UCard>

        <UCard title="行为明细" padded class="pf-col-half">
          <template #extra>
            <USegmented v-model="tab" size="sm"
              :options="[{ value:'consumption',label:'消费流水' },{ value:'library',label:'进馆记录' }]" />
          </template>

          <UTable
            v-if="tab === 'consumption'"
            :columns="[
              { key:'consumed_at', label:'时间', width:'150px' },
              { key:'merchant_type', label:'类型', width:'70px' },
              { key:'merchant_name', label:'商户', width:'130px' },
              { key:'meal_period', label:'餐段', width:'70px' },
              { key:'amount', label:'金额(元)', width:'90px', align:'right' },
              { key:'balance', label:'余额(元)', width:'90px', align:'right' },
            ]"
            :items="detail.items || []"
            row-key="id"
            dense
          >
            <template #cell-merchant_type="{ row }">{{ MERCHANT_TYPES[row.merchant_type] || '其他' }}</template>
          </UTable>
          <UTable
            v-else
            :columns="[
              { key:'venue', label:'馆舍', width:'110px' },
              { key:'area_name', label:'区域', width:'110px' },
              { key:'gate_in_time', label:'进馆', width:'140px' },
              { key:'gate_out_time', label:'离馆', width:'140px' },
              { key:'stay_minutes', label:'时长(分)', width:'80px', align:'right' },
            ]"
            :items="detail.items || []"
            row-key="id"
            dense
          />
          <UPagination
            v-if="detail.total > 0"
            v-model:page="page" :size="size" :total="detail.total || 0"
            @change="loadDetail"
            class="pf-mt"
          />
        </UCard>
      </div>

      <!-- 该生历史预警 -->
      <UCard :title="`该生预警记录`" :subtitle="`共 ${warnings.length} 条`" padded class="pf-mt">
        <UTable
          :columns="[
            { key:'warning_date', label:'日期', width:'110px' },
            { key:'rule_name', label:'规则', width:'150px' },
            { key:'warning_level', label:'级别', width:'70px', align:'center' },
            { key:'message', label:'说明', width:'260px' },
            { key:'metric_value', label:'指标值', width:'80px', align:'right' },
            { key:'action', label:'操作', width:'80px' },
          ]"
          :items="warnings"
          row-key="id"
          dense
        >
          <template #cell-warning_level="{ row }">
            <UBadge :tone="row.warning_level === 3 ? 'danger' : row.warning_level === 2 ? 'warning' : 'neutral'">
              {{ row.warning_level_text }}
            </UBadge>
          </template>
          <template #cell-action="{ row }">
            <UButton variant="text" size="sm" @click="router.push({ name: 'risk', query: { keyword: row.student_id } })">
              去处置
            </UButton>
          </template>
        </UTable>
        <UEmptyState v-if="!warnings.length" title="暂无预警记录" />
      </UCard>
    </template>
  </div>
</template>

<style scoped>
.profile-page {
  padding: 16px 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
}

.pf-mt { margin-top: 4px; }

.pf-search {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
}

.pf-suggest-wrap {
  position: relative;
}

.pf-suggest {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: var(--z-dropdown);
  margin-top: 4px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  overflow: hidden;
  box-shadow: var(--ci-shadow-2);
}

.pf-suggest__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.12s;
}

.pf-suggest__item:hover { background: var(--ci-surface-3); }

.pf-suggest__sub {
  font-size: 11px;
  color: var(--ci-text-3);
}

.pf-suggest__empty {
  padding: 10px 12px;
  font-size: 12px;
  color: var(--ci-text-3);
}

.pf-err {
  font-size: 12px;
  color: var(--ci-danger);
}

/* 行布局 */
.pf-row1 {
  display: grid;
  grid-template-columns: 1.05fr 1.7fr 1.25fr;
  gap: 12px;
}

.pf-row2, .pf-row3 {
  display: grid;
  grid-template-columns: 1fr 1.35fr;
  gap: 12px;
}

.pf-col-half { min-height: 0; }

/* 基本信息 */
.pf-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pf-info__row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.pf-info__row > span {
  min-width: 50px;
  color: var(--ci-text-3);
  font-size: 12px;
  flex-shrink: 0;
}

.pf-info__row > b {
  color: var(--ci-text);
  font-weight: 500;
}

/* KPI 卡 */
.pf-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.pf-kpi {
  padding: 8px 10px;
  border-radius: var(--r-md);
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pf-kpi__lbl { font-size: 11px; color: var(--ci-text-3); }
.pf-kpi__v { font-size: 16px; font-weight: 600; color: var(--ci-text); font-variant-numeric: tabular-nums; }
.pf-kpi__s { font-size: 10px; color: var(--ci-text-3); font-style: normal; }
.pf-kpi--warn .pf-kpi__v { color: var(--ci-danger); }

/* 簇 */
.pf-cluster {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pf-cluster__meta { margin: 0; font-size: 12px; color: var(--ci-text-3); }
.pf-cluster__desc { margin: 0; font-size: 12px; color: var(--ci-text-2); line-height: 1.5; }

/* 时间线 */
.pf-timeline {
  max-height: 320px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 0;
}

.pf-tl__item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 8px;
  border-radius: var(--r-sm);
}

.pf-tl__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}

.pf-tl__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pf-tl__date {
  font-size: 11px;
  color: var(--ci-text-3);
  font-family: var(--font-mono);
}

.pf-tl__text {
  font-size: 12px;
  color: var(--ci-text-2);
  line-height: 1.5;
}

.pf-tl__text--warn { color: var(--ci-danger); }

@media (max-width: 1400px) {
  .pf-row1 { grid-template-columns: 1fr 1fr; }
  .pf-col3 { grid-column: 1 / -1; }
  .pf-row2, .pf-row3 { grid-template-columns: 1fr; }
}

@media (max-width: 900px) {
  .pf-row1 { grid-template-columns: 1fr; }
  .pf-col1, .pf-col2, .pf-col3 { grid-column: auto; }
}
</style>
