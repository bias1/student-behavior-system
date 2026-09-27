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
import {
  SIGNAL_KIND_TEXT, VERIFY_RESULT_TEXT, WARNING_TYPE_TEXT,
  WORKFLOW_STATE_TEXT, WORKFLOW_STATE_TONE, WarningApi,
} from '@/api'
import { useSession } from '@/composables/useSession'
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
const session = useSession()
const canHandle = computed(() => session.hasPerm('warning:handle'))

const LEVEL_TEXT = { 1: '低', 2: '中', 3: '高' }
const LEVEL_TONE = { 3: 'danger', 2: 'warning', 1: 'primary' }
const STATUS_OPTS = [
  { value: '', label: '全部处置态' },
  { value: '0', label: '未处理' },
  { value: '1', label: '已处理' },
  { value: '2', label: '已忽略' },
]
const WF_OPTS = [
  { value: '', label: '全部核实态' },
  { value: '0', label: '待核实' },
  { value: '1', label: '已分配' },
  { value: '2', label: '核实中' },
  { value: '3', label: '已核实' },
  { value: '4', label: '已关闭' },
]
const VERIFY_OPTS = Object.entries(VERIFY_RESULT_TEXT).map(([value, label]) => ({ value, label }))
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
  status: '',
  workflow_state: '',
  keyword: route.query.keyword || '',
  range: null,
})

function queryParams(withPage = true) {
  const p = {}
  if (filters.type) p.type = filters.type
  if (filters.rule_code) p.rule_code = filters.rule_code
  if (filters.level) p.level = filters.level
  if (filters.status) p.status = filters.status
  if (filters.workflow_state) p.workflow_state = filters.workflow_state
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
  Object.assign(filters, { type: '', rule_code: '', level: '', status: '', workflow_state: '', keyword: '', range: null })
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

/* ---------------- 人工核实工作流（阶段 4） ---------------- */
const wfBusy = ref(false)
async function runWorkflow(row, action, extra = {}) {
  wfBusy.value = true
  try {
    const d = await WarningApi.workflow(row.id, { action, ...extra })
    toast.success(`操作成功：${d.workflow_state_text}`)
    detail.value = d
    await Promise.all([loadList(), loadStats()])
  } finally { wfBusy.value = false }
}
async function confirmWorkflow(row, action, message, danger = false) {
  const ok = await confirmDialog({ title: '工作流确认', message, confirmText: '确定', danger })
  if (ok) await runWorkflow(row, action)
}
function doAssign(row) {
  const who = window.prompt('分配给（填写处理人登录名）：', row.assigned_to || '')
  if (who && who.trim()) runWorkflow(row, 'assign', { assigned_to: who.trim() })
}
// 核实结论表单
const verifyForm = reactive({ open: false, result: '', note: '' })
function openVerify() { verifyForm.result = ''; verifyForm.note = ''; verifyForm.open = true }
async function submitVerify() {
  if (!verifyForm.result || !verifyForm.note.trim()) return
  await runWorkflow(detail.value, 'verify', { verify_result: verifyForm.result, verify_note: verifyForm.note.trim() })
  verifyForm.open = false
}
function doAppeal(row) {
  const reason = window.prompt('申诉/纠正理由（必填）：', '')
  if (reason && reason.trim()) runWorkflow(row, 'appeal', { verify_note: reason.trim() })
}

/* ---------------- 详情 Drawer ---------------- */
const detailOpen = ref(false)
const detail = ref({})
function showDetail(row) {
  detail.value = row
  verifyForm.open = false
  detailOpen.value = true
}

/* ---------------- KPI 卡 ---------------- */
const cards = computed(() => {
  const s = stats.value
  const high = (s.by_level || []).find((x) => x.level === 3)?.count || 0
  const pending = (s.by_workflow || []).find((x) => x.state === 0)?.count || 0
  return [
    { label: 'TOTAL', cn: '预警总数', value: Number(s.total) || 0, suffix: ' 条', color: 'var(--ci-cyan)' },
    { label: 'PENDING', cn: '待核实', value: pending, suffix: ' 条', color: 'var(--ci-warning)', goodWhenUp: false },
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
    <UCard title="预警明细" subtitle="级别高者优先；默认不含数据质量问题与重复预警" padded allow-overflow>
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
        <USelect v-model="filters.status" :options="STATUS_OPTS" placeholder="处置状态" width="110px" @change="search" />
        <USelect v-model="filters.workflow_state" :options="WF_OPTS" placeholder="核实态" width="110px" @change="search" />
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
            { key: 'college', label: '学院', width: '150px' },
            { key: 'rule_name', label: '规则', width: '150px' },
            { key: 'warning_level', label: '级别', width: '64px', align: 'center' },
            { key: 'signal_kind', label: '信号类别', width: '132px' },
            { key: 'workflow_state', label: '核实态', width: '92px', align: 'center' },
            { key: 'message', label: '说明', width: '260px' },
            { key: 'action', label: '操作', width: '96px' },
          ]"
          :items="tableData"
          row-key="id"
          @row-click="showDetail"
        >
          <template #cell-student_name="{ row }">
            <a class="rk-link" @click.stop="router.push(`/student/${row.student_id}`)">{{ row.student_name }}</a>
            <span class="rk-sid">{{ row.student_id }}</span>
          </template>
          <template #cell-warning_level="{ row }">
            <UBadge :tone="LEVEL_TONE[row.warning_level] || 'neutral'">
              {{ LEVEL_TEXT[row.warning_level] || row.warning_level_text }}
            </UBadge>
          </template>
          <template #cell-signal_kind="{ row }">
            <span class="rk-signal">{{ SIGNAL_KIND_TEXT[row.signal_kind] || row.signal_kind_text || row.signal_kind }}</span>
          </template>
          <template #cell-workflow_state="{ row }">
            <UBadge :tone="WORKFLOW_STATE_TONE[row.workflow_state] || 'neutral'" dot>
              {{ row.workflow_state_text }}
            </UBadge>
          </template>
          <template #cell-message="{ row }">
            <span class="rk-msg">{{ row.message }}</span>
          </template>
          <template #cell-action="{ row }">
            <UButton variant="text" size="sm" @click.stop="showDetail(row)">
              <Eye :size="12" /> 详情
            </UButton>
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
    <UDrawer v-model:open="detailOpen" title="预警详情" width="560px">
      <template v-if="detail.id">
        <div class="rk-detail">
          <div class="rk-detail__row">
            <span class="rk-detail__lbl">学生</span>
            <a class="rk-link" @click="router.push(`/student/${detail.student_id}`)">{{ detail.student_name }}</a>
            <span class="rk-sid">{{ detail.student_id }}</span>
          </div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">学院班级</span>{{ detail.college }} / {{ detail.class_name }}</div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">规则</span>{{ detail.rule_name }}（{{ detail.rule_code }}）
            <UBadge v-if="detail.rule_version" tone="neutral">{{ detail.rule_version }}</UBadge>
          </div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">预警日期</span>{{ detail.warning_date }}</div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">级别</span>
            <UBadge :tone="LEVEL_TONE[detail.warning_level] || 'neutral'">{{ LEVEL_TEXT[detail.warning_level] }}</UBadge>
          </div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">信号类别</span>
            <UBadge :tone="detail.signal_kind === 'data_quality' ? 'warning' : 'neutral'">
              {{ SIGNAL_KIND_TEXT[detail.signal_kind] || detail.signal_kind_text }}
            </UBadge>
          </div>
          <div class="rk-detail__row"><span class="rk-detail__lbl">核实态</span>
            <UBadge :tone="WORKFLOW_STATE_TONE[detail.workflow_state] || 'neutral'" dot>{{ detail.workflow_state_text }}</UBadge>
          </div>

          <!-- 阶段 4：口径快照 -->
          <div class="rk-detail__group">
            <p class="rk-detail__group-t">口径快照（触发时冻结）</p>
            <div class="rk-detail__row"><span class="rk-detail__lbl">指标定义</span>{{ detail.metric_def || '—' }}</div>
            <div class="rk-detail__row"><span class="rk-detail__lbl">时间窗口</span>{{ detail.window_start || '?' }} ~ {{ detail.window_end || '?' }}</div>
            <div class="rk-detail__row"><span class="rk-detail__lbl">数据量</span>有效 {{ detail.valid_data_days ?? '—' }} / 至少 {{ detail.min_data_days ?? '—' }} 天</div>
            <div class="rk-detail__row"><span class="rk-detail__lbl">指标值</span>{{ detail.metric_value }}</div>
            <div v-if="detail.baseline_ref" class="rk-detail__row"><span class="rk-detail__lbl">个人基线</span>{{ detail.baseline_ref }}</div>
            <div v-if="detail.data_gap_note" class="rk-detail__row"><span class="rk-detail__lbl">缺失说明</span>
              <span class="rk-warn">{{ detail.data_gap_note }}</span>
            </div>
          </div>

          <div class="rk-detail__row"><span class="rk-detail__lbl">说明</span>{{ detail.message }}</div>

          <div class="rk-detail__group">
            <p class="rk-detail__group-t">人工核实记录</p>
            <div class="rk-detail__row"><span class="rk-detail__lbl">分配</span>
              {{ detail.assigned_to ? `${detail.assigned_to} 于 ${detail.assigned_at}` : '未分配' }}</div>
            <div v-if="detail.verify_result" class="rk-detail__row"><span class="rk-detail__lbl">结论</span>
              <UBadge :tone="detail.verify_result === 'need_support' ? 'success' : detail.verify_result === 'false_positive' ? 'neutral' : 'warning'">
                {{ VERIFY_RESULT_TEXT[detail.verify_result] || detail.verify_result }}
              </UBadge>
              {{ detail.verified_by }} · {{ detail.verified_at }}
            </div>
            <div v-if="detail.verify_note" class="rk-detail__row"><span class="rk-detail__lbl">备注</span>{{ detail.verify_note }}</div>
          </div>

          <div class="rk-detail__block">
            <p class="rk-detail__lbl">计算明细（触发证据）</p>
            <pre class="rk-json">{{ JSON.stringify(detail.detail, null, 2) }}</pre>
          </div>

          <!-- 核实表单 -->
          <div v-if="canHandle && verifyForm.open && detail.workflow_state < 3" class="rk-verify">
            <p class="rk-detail__group-t">填写核实结论</p>
            <USelect v-model="verifyForm.result" :options="VERIFY_OPTS" placeholder="核实结论" width="100%" />
            <UInput v-model="verifyForm.note" placeholder="核实依据与处置建议（必填）" width="100%" />
            <div class="rk-verify__acts">
              <UButton variant="ghost" size="sm" @click="verifyForm.open = false">取消</UButton>
              <UButton variant="primary" size="sm" :disabled="!verifyForm.result || !verifyForm.note.trim() || wfBusy" @click="submitVerify">提交核实</UButton>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="rk-footer">
          <UButton variant="ghost" @click="detailOpen = false">关闭</UButton>
          <UButton variant="primary" @click="router.push(`/student/${detail.student_id}`)">查看该生画像</UButton>
          <template v-if="canHandle && detail.id">
            <span class="rk-footer__sep" />
            <template v-if="detail.workflow_state < 3">
              <UButton size="sm" :loading="wfBusy" @click="doAssign(detail)">分配</UButton>
              <UButton v-if="detail.workflow_state !== 2" size="sm" :loading="wfBusy" @click="confirmWorkflow(detail, 'start', '开始核实该预警？')">开始核实</UButton>
              <UButton v-if="!verifyForm.open" variant="primary" size="sm" @click="openVerify">核实</UButton>
              <UButton size="sm" :loading="wfBusy" @click="confirmWorkflow(detail, 'close', '关闭该预警（不产生支持结论）？')">关闭</UButton>
            </template>
            <template v-else>
              <UButton size="sm" :loading="wfBusy" @click="confirmWorkflow(detail, 'reopen', '重新打开并回到待核实？')">重新打开</UButton>
              <UButton size="sm" @click="doAppeal(detail)">申诉纠正</UButton>
            </template>
          </template>
        </div>
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

.rk-signal {
  font-size: 12px;
  color: var(--ci-text-2);
}

.rk-detail__group {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rk-detail__group-t {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--ci-text-3);
  letter-spacing: 0.02em;
}

.rk-warn {
  color: var(--ci-warning);
  font-size: 12px;
}

.rk-verify {
  margin-top: 12px;
  padding: 12px;
  border: 1px dashed var(--ci-border-strong);
  border-radius: var(--r-md);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rk-verify__acts {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.rk-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.rk-footer__sep {
  flex: 1;
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
