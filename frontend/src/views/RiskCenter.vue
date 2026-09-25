<script setup>
/**
 * 风险中心（/risk）—— 替换原 WarningList.vue
 *
 * 变化：
 *   - 去掉所有 el-* 组件，用自研 UI 库
 *   - 预警统计图保留（规则分布 + 新增趋势）
 *   - 详情从弹窗改为 Drawer（宽屏右侧滑出，体验更好）
 *   - 处置确认改用 confirmDialog（useConfirm.js）
 *   - toast 替代 ElMessage
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Calculator, Eye, RotateCcw, Search, TriangleAlert } from 'lucide-vue-next'
import { WARNING_TYPE_TEXT, WarningApi } from '@/api'
import { fmtInt } from '@/utils/format'
import BaseChart from '@/components/BaseChart.vue'
import UCard from '@/components/ui/UCard.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import UButton from '@/components/ui/UButton.vue'
import UInput from '@/components/ui/UInput.vue'
import USelect from '@/components/ui/USelect.vue'
import UDateRange from '@/components/ui/UDateRange.vue'
import UBadge from '@/components/ui/UBadge.vue'
import UTable from '@/components/ui/UTable.vue'
import UPagination from '@/components/ui/UPagination.vue'
import UDrawer from '@/components/ui/UDrawer.vue'
import USkeleton from '@/components/ui/USkeleton.vue'
import UEmptyState from '@/components/ui/UEmptyState.vue'
import { toast } from '@/components/ui/toast'
import { confirmDialog } from '@/components/ui/useConfirm'

const route = useRoute()
const router = useRouter()

const LEVEL_TEXT = { 1: '低', 2: '中', 3: '高' }
const LEVEL_TONE = { 3: 'danger', 2: 'warning', 1: 'primary' }
const STATUS_OPTS = [
  { value: '0', label: '未处理' },
  { value: '1', label: '已处理' },
  { value: '2', label: '已忽略' },
]
const TYPE_OPTS = Object.entries(WARNING_TYPE_TEXT).map(([value, label]) => ({ value, label }))

const loading = ref(false)
const scanning = ref(false)
const page = ref(1)
const size = ref(20)
const tableData = ref([])
const total = ref(0)
const stats = ref({})
const rules = ref([])

const filters = reactive({
  type: '',
  rule_code: '',
  level: '',
  status: '0',
  keyword: route.query.keyword || '',
  range: null,
})

function queryParams(withPage = true) {
  const p = {}
  if (filters.type) p.type = filters.type
  if (filters.rule_code) p.rule_code = filters.rule_code
  if (filters.level) p.level = filters.level
  if (filters.status) p.status = filters.status
  if (filters.keyword) p.keyword = filters.keyword
  if (filters.range?.length === 2) { p.start = filters.range[0]; p.end = filters.range[1] }
  if (withPage) Object.assign(p, { page: page.value, size: size.value })
  return p
}

async function loadList() {
  loading.value = true
  try {
    const d = await WarningApi.list(queryParams())
    tableData.value = d.items || []
    total.value = d.total || 0
  } finally { loading.value = false }
}

async function loadStats() {
  stats.value = await WarningApi.stats(queryParams(false))
}

async function loadRules() {
  rules.value = await WarningApi.rules()
}

function search() {
  page.value = 1
  loadList(); loadStats()
}

function reset() {
  Object.assign(filters, { type: '', rule_code: '', level: '', status: '0', keyword: '', range: null })
  search()
}

async function rescan() {
  scanning.value = true
  try {
    const d = await WarningApi.refresh({ scope: 'all' })
    toast.success(
      `重算完成：写入/更新 ${d.written} 条，清理失效 ${d.removed_stale} 条` +
      `（${(d.weeks_compared || []).join('、') || '不足两个完整周'}）`
    )
    await Promise.all([loadStats(), loadList()])
  } finally { scanning.value = false }
}

async function handle(row, status) {
  const statusText = { 1: '已处理', 2: '已忽略', 0: '未处理' }[status]
  const ok = await confirmDialog({
    title: '处置确认',
    message: `确认将该预警标记为「${statusText}」？`,
    confirmText: '确定',
    danger: status === 2,
  })
  if (!ok) return
  await WarningApi.handle(row.id, { status, handled_by: 'admin' })
  toast.success('处置成功')
  loadList(); loadStats()
}

/* ---------------- 详情 Drawer ---------------- */
const detailOpen = ref(false)
const detail = ref({})
function showDetail(row) {
  detail.value = row
  detailOpen.value = true
}

/* ---------------- KPI 卡 ---------------- */
const cards = computed(() => {
  const s = stats.value
  const high = (s.by_level || []).find((x) => x.level === 3)?.count || 0
  const pending = (s.by_status || []).find((x) => x.status === 0)?.count || 0
  return [
    { label: 'TOTAL', cn: '预警总数', value: Number(s.total) || 0, suffix: ' 条', color: 'var(--ci-cyan)' },
    { label: 'PENDING', cn: '未处理', value: pending, suffix: ' 条', color: 'var(--ci-warning)', goodWhenUp: false },
    { label: 'HIGH', cn: '高危级别', value: high, suffix: ' 条', color: 'var(--ci-danger)', goodWhenUp: false },
    { label: 'RULES', cn: '涉及规则', value: (s.by_rule || []).length, suffix: ' 条', color: 'var(--ci-success)' },
  ]
})

const ruleOpts = computed(() =>
  rules.value.map((r) => ({ value: r.rule_code, label: r.rule_name }))
)

const levelOpts = [
  { value: 1, label: '低及以上' },
  { value: 2, label: '中及以上' },
  { value: 3, label: '仅高危' },
]

/* ---------------- 图表 ---------------- */
const ruleBarOption = computed(() => {
  const rows = [...(stats.value.by_rule || [])].reverse()
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 6, right: 30, top: 8, bottom: 4, containLabel: true },
    xAxis: { type: 'value', name: '条' },
    yAxis: { type: 'category', data: rows.map((r) => r.rule_name), axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar', data: rows.map((r) => r.count), barMaxWidth: 16,
      label: { show: true, position: 'right' },
      itemStyle: {
        color: (p) => rows[p.dataIndex]?.level === 3 ? '#ff5c7c' : rows[p.dataIndex]?.level === 2 ? '#ffb454' : '#4fd1ff',
        borderRadius: [0, 4, 4, 0],
      },
    }],
  }
})

const trendOption = computed(() => {
  const rows = stats.value.trend || []
  return {
    tooltip: { trigger: 'axis' },
    // 同图书馆图：y 轴名贴在轴线顶端，top 留足避开最大刻度标签
    grid: { left: 6, right: 10, top: 26, bottom: 2, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.date.slice(5)), boundaryGap: false },
    yAxis: { type: 'value', name: '条' },
    series: [{ type: 'line', data: rows.map((r) => r.count), areaStyle: { opacity: 0.15 }, smooth: true }],
  }
})

onMounted(() => { loadRules(); loadStats(); loadList() })
</script>

<template>
  <div class="risk-page">
    <!-- KPI 卡 -->
    <div class="rk-kpi">
      <KpiCard
        v-for="c in cards" :key="c.label"
        :label="c.label" :cn="c.cn" :value="c.value" :suffix="c.suffix"
        :color="c.color" :good-when-up="c.goodWhenUp !== false"
      />
    </div>

    <!-- 统计图 -->
    <div class="rk-charts">
      <UCard title="按规则分布" subtitle="颜色代表级别" class="rk-chart">
        <BaseChart :option="ruleBarOption" height="220px" />
      </UCard>
      <UCard title="预警新增趋势" class="rk-chart">
        <BaseChart :option="trendOption" height="220px" />
      </UCard>
    </div>

    <!-- 明细列表 -->
    <!-- 卡内有 USelect/UDateRange 弹层，allow-overflow 防被卡片 overflow 裁切 -->
    <UCard title="预警明细" subtitle="默认展示未处理，级别高者优先" padded allow-overflow>
      <template #extra>
        <UButton variant="ghost" size="sm" :loading="scanning" @click="rescan">
          <RotateCcw :size="13" /> 重新计算
        </UButton>
      </template>

      <!-- 筛选栏 -->
      <div class="rk-filters">
        <USelect v-model="filters.type" :options="TYPE_OPTS" placeholder="预警大类" width="128px" @change="search" />
        <USelect v-model="filters.rule_code" :options="ruleOpts" placeholder="具体规则" width="180px" filterable @change="search" />
        <USelect v-model="filters.level" :options="levelOpts" placeholder="最低级别" width="110px" @change="search" />
        <USelect v-model="filters.status" :options="STATUS_OPTS" placeholder="处置状态" width="106px" @change="search" />
        <UDateRange v-model="filters.range" width="220px" @change="search" />
        <UInput v-model="filters.keyword" placeholder="学号 / 姓名" width="160px" @enter="search">
          <template #prefix><Search :size="13" /></template>
        </UInput>
        <UButton variant="primary" size="sm" @click="search">查询</UButton>
        <UButton variant="ghost" size="sm" @click="reset">重置</UButton>
      </div>

      <!-- 表格 -->
      <div class="rk-table">
        <USkeleton v-if="loading && !tableData.length" :lines="6" />
        <UTable
          v-else-if="tableData.length"
          :columns="[
            { key: 'warning_date', label: '日期', width: '110px', sortable: true },
            { key: 'student_name', label: '学生', width: '160px' },
            { key: 'college', label: '学院', width: '160px' },
            { key: 'warning_type', label: '大类', width: '90px' },
            { key: 'rule_name', label: '规则', width: '150px' },
            { key: 'warning_level', label: '级别', width: '68px', align: 'center' },
            { key: 'metric_value', label: '指标值', width: '84px', align: 'right', sortable: true },
            { key: 'message', label: '说明', width: '260px' },
            { key: 'status', label: '状态', width: '80px', align: 'center' },
            { key: 'action', label: '操作', width: '160px' },
          ]"
          :items="tableData"
          row-key="id"
          @row-click="showDetail"
        >
          <template #cell-student_name="{ row }">
            <a class="rk-link" @click.stop="router.push(`/student/${row.student_id}`)">{{ row.student_name }}</a>
            <span class="rk-sid">{{ row.student_id }}</span>
          </template>
          <template #cell-warning-type="{ row }">
            {{ WARNING_TYPE_TEXT[row.warning_type] || row.warning_type }}
          </template>
          <template #cell-warning_level="{ row }">
            <UBadge :tone="LEVEL_TONE[row.warning_level] || 'neutral'">
              {{ LEVEL_TEXT[row.warning_level] || row.warning_level_text }}
            </UBadge>
          </template>
          <template #cell-message="{ row }">
            <span class="rk-msg">{{ row.message }}</span>
          </template>
          <template #cell-status="{ row }">
            <UBadge :tone="row.status === 0 ? 'danger' : row.status === 1 ? 'success' : 'neutral'" dot>
              {{ row.status_text }}
            </UBadge>
          </template>
          <template #cell-action="{ row }">
            <UButton variant="text" size="sm" @click.stop="showDetail(row)">
              <Eye :size="12" /> 详情
            </UButton>
            <UButton v-if="row.status === 0" variant="text" size="sm" @click.stop="handle(row, 1)">已处理</UButton>
            <UButton v-if="row.status === 0" variant="text" size="sm" @click.stop="handle(row, 2)">忽略</UButton>
          </template>
        </UTable>
        <UEmptyState v-else tone="search" title="暂无预警记录" hint="调整筛选条件试试" />
      </div>

      <UPagination
        v-if="total > 0"
        v-model:page="page"
        :size="size"
        :total="total"
        class="rk-pager"
        @change="loadList"
      />
    </UCard>

    <!-- 详情 Drawer -->
    <UDrawer v-model:open="detailOpen" title="预警详情" width="520px">
      <template v-if="detail.id">
        <div class="rk-detail">
          <div class="rk-detail__row">
            <span class="rk-detail__lbl">学生</span>
            <a class="rk-link" @click="router.push(`/student/${detail.student_id}`)">{{ detail.student_name }}</a>
            <span class="rk-sid">{{ detail.student_id }}</span>
          </div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">学院班级</span>{{ detail.college }} / {{ detail.class_name }}</div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">规则</span>{{ detail.rule_name }}（{{ detail.rule_code }}）</div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">预警日期</span>{{ detail.warning_date }}</div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">级别</span>
            <UBadge :tone="LEVEL_TONE[detail.warning_level] || 'neutral'">{{ LEVEL_TEXT[detail.warning_level] }}</UBadge>
          </div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">说明</span>{{ detail.message }}</div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">指标值</span>{{ detail.metric_value }}</div>
          <div v-if="detail.handled_at" class="rk-detail__row">
            <span class="rk-detail__lbl">处置</span>{{ detail.handled_by }} 于 {{ detail.handled_at }} 标记为 {{ detail.status_text }}
          </div>
          <div class="rk-detail__block">
            <p class="rk-detail__lbl">计算明细</p>
            <pre class="rk-json">{{ JSON.stringify(detail.detail, null, 2) }}</pre>
          </div>
        </div>
      </template>
      <template #footer>
        <UButton variant="ghost" @click="detailOpen = false">关闭</UButton>
        <UButton variant="primary" @click="router.push(`/student/${detail.student_id}`)">查看该生画像</UButton>
      </template>
    </UDrawer>
  </div>
</template>

<style scoped>
.risk-page {
  padding: 16px 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
}

.rk-kpi {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.rk-charts {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 12px;
}

.rk-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.rk-table { min-height: 200px; }

.rk-pager { margin-top: 10px; }

.rk-link {
  color: var(--ci-primary);
  cursor: pointer;
  &:hover { text-decoration: underline; }
}

.rk-sid {
  margin-left: 4px;
  font-size: 11px;
  color: var(--ci-text-3);
}

.rk-msg {
  font-size: 12px;
  color: var(--ci-text-2);
}

.rk-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rk-detail__row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ci-text);
}

.rk-detail__lbl {
  min-width: 60px;
  color: var(--ci-text-3);
  font-size: 12px;
  flex-shrink: 0;
}

.rk-detail__block {
  margin-top: 8px;
}

.rk-json {
  margin: 6px 0 0;
  padding: 10px;
  background: var(--ci-surface-2);
  border-radius: var(--r-md);
  font-size: 11px;
  color: var(--ci-text-2);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 220px;
  overflow: auto;
  line-height: 1.6;
}

@media (max-width: 1200px) {
  .rk-kpi { grid-template-columns: repeat(2, 1fr); }
  .rk-charts { grid-template-columns: 1fr; }
}
</style>
