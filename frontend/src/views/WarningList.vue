<script setup>
/**
 * 异常行为预警页（/warning）
 *
 * 顶部：4 个统计卡（总数/未处理/高危/今日新增）+ 规则分布 + 近 N 日趋势
 * 主体：筛选条（大类 / 规则 / 级别 / 状态 / 关键词 / 日期）+ 表格 + 分页
 *
 * 注意后端 list 接口的 level 是"大于等于"语义（level=2 表示中及以上），
 * 所以筛选器用"最低级别"而不是"级别等于"，与辅导员"先看严重的"的用法一致。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WARNING_TYPE_TEXT, WarningApi } from '@/api'
import { fmtInt } from '@/utils/format'
import PanelBox from '@/components/PanelBox.vue'
import BaseChart from '@/components/BaseChart.vue'
import StatCard from '@/components/StatCard.vue'

const route = useRoute()
const router = useRouter()

const LEVEL_TEXT = { 1: '低', 2: '中', 3: '高' }
const LEVEL_TAG = { 3: 'danger', 2: 'warning', 1: 'info' }

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
  status: '0',           // 默认只看未处理：打开页面就是待办清单
  keyword: route.query.keyword || '',
  range: null,
})

function queryParams(withPage = true) {
  const p = { ...filters }
  delete p.range
  if (filters.range?.length === 2) {
    p.start = filters.range[0]
    p.end = filters.range[1]
  }
  Object.keys(p).forEach((k) => (p[k] === '' || p[k] === null ? delete p[k] : null))
  if (withPage) Object.assign(p, { page: page.value, size: size.value })
  return p
}

async function loadList() {
  loading.value = true
  try {
    const d = await WarningApi.list(queryParams())
    tableData.value = d.items || []
    total.value = d.total || 0
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  stats.value = await WarningApi.stats()
}

async function loadRules() {
  rules.value = await WarningApi.rules()
}

function search() {
  page.value = 1
  loadList()
}

function reset() {
  Object.assign(filters, { type: '', rule_code: '', level: '', status: '0', keyword: '', range: null })
  search()
}

async function rescan() {
  scanning.value = true
  try {
    // scope=all：总纲四大规则（带失效预警清理）+ 扩展细粒度规则，一次跑完两套引擎
    const d = await WarningApi.refresh({ scope: 'all' })
    ElMessage.success(
      `重算完成：写入/更新 ${d.written} 条，清理失效 ${d.removed_stale} 条` +
      `（参与环比的自然周：${(d.weeks_compared || []).join('、') || '不足两个完整周'}）`
    )
    await Promise.all([loadStats(), loadList()])
  } finally {
    scanning.value = false
  }
}

async function handle(row, status) {
  await ElMessageBox.confirm(
    `确认将该预警标记为「${{ 1: '已处理', 2: '已忽略', 0: '未处理' }[status]}」？`,
    '处置确认',
    { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
  )
  await WarningApi.handle(row.id, { status, handled_by: 'admin' })
  ElMessage.success('处置成功')
  loadList()
  loadStats()
}

/** 详情弹窗：把 detail JSON 摊平成人能读的句子 */
const detail = ref({})
const detailVisible = ref(false)
function showDetail(row) {
  detail.value = row
  detailVisible.value = true
}

const cards = computed(() => {
  const s = stats.value
  const high = (s.by_level || []).find((x) => x.level === 3)?.count || 0
  const pending = (s.by_status || []).find((x) => x.status === 0)?.count || 0
  const trend = s.trend || []
  return [
    { label: '预警总数', value: fmtInt(s.total ?? 0), unit: '条', icon: 'Bell', color: '#4ea1ff' },
    { label: '未处理', value: fmtInt(pending), unit: '条', icon: 'Clock', color: '#ffd166' },
    { label: '高危（级别=高）', value: fmtInt(high), unit: '条', icon: 'CircleClose', color: '#ff6b81' },
    { label: '涉及规则', value: fmtInt((s.by_rule || []).length), unit: '条', icon: 'SetUp', color: '#7ee787', hint: (s.by_rule || []).map((r) => r.rule_name).join('、') },
  ]
})

const ruleBarOption = computed(() => {
  const rows = [...(stats.value.by_rule || [])].reverse()   // ECharts 条形图从下往上画，反转后最大值在顶部
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 6, right: 30, top: 8, bottom: 4, containLabel: true },
    xAxis: { type: 'value', name: '条' },
    yAxis: { type: 'category', data: rows.map((r) => r.rule_name), axisLabel: { fontSize: 11 } },
    series: [
      {
        type: 'bar', data: rows.map((r) => r.count), barMaxWidth: 16,
        label: { show: true, position: 'right', color: '#c8ddf7' },
        itemStyle: { color: (p) => (rows[p.dataIndex].level === 3 ? '#ff6b81' : rows[p.dataIndex].level === 2 ? '#ffd166' : '#4ea1ff'), borderRadius: [0, 4, 4, 0] },
      },
    ],
  }
})

const trendOption = computed(() => {
  const rows = stats.value.trend || []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 6, right: 10, top: 10, bottom: 2, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.date.slice(5)), boundaryGap: false },
    yAxis: { type: 'value', name: '条' },
    series: [{ type: 'line', data: rows.map((r) => r.count), areaStyle: { opacity: 0.18 }, smooth: true }],
  }
})

onMounted(() => {
  loadRules()
  loadStats()
  loadList()
})
</script>

<template>
  <div class="page">
    <div class="cards">
      <StatCard
        v-for="c in cards" :key="c.label" :label="c.label" :value="c.value" :unit="c.unit"
        :icon="c.icon" :color="c.color" :hint="c.hint"
      />
    </div>

    <div class="charts">
      <PanelBox class="cell" title="按规则分布" subtitle="颜色代表级别">
        <BaseChart :option="ruleBarOption" height="240px" />
      </PanelBox>
      <PanelBox class="cell" title="预警新增趋势">
        <BaseChart :option="trendOption" height="240px" />
      </PanelBox>
    </div>

    <PanelBox class="mt" title="预警明细" subtitle="默认展示未处理，级别高者优先">
      <template #extra>
        <el-button size="small" :loading="scanning" @click="rescan"><el-icon><Refresh /></el-icon>重新计算</el-button>
      </template>

      <div class="filters">
        <el-select v-model="filters.type" placeholder="预警大类" clearable size="small" style="width: 132px" @change="search">
          <el-option v-for="(text, key) in WARNING_TYPE_TEXT" :key="key" :value="key" :label="text" />
        </el-select>
        <el-select v-model="filters.rule_code" placeholder="具体规则" clearable filterable size="small" style="width: 190px" @change="search">
          <el-option v-for="r in rules" :key="r.rule_code" :value="r.rule_code" :label="r.rule_name" />
        </el-select>
        <el-select v-model="filters.level" placeholder="最低级别" clearable size="small" style="width: 122px" @change="search">
          <el-option :value="1" label="低及以上" />
          <el-option :value="2" label="中及以上" />
          <el-option :value="3" label="仅高危" />
        </el-select>
        <el-select v-model="filters.status" placeholder="处置状态" clearable size="small" style="width: 118px" @change="search">
          <el-option :value="'0'" label="未处理" />
          <el-option :value="'1'" label="已处理" />
          <el-option :value="'2'" label="已忽略" />
        </el-select>
        <el-date-picker
          v-model="filters.range" type="daterange" size="small" style="width: 226px"
          value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" @change="search"
        />
        <el-input v-model="filters.keyword" placeholder="学号 / 姓名" clearable size="small" style="width: 168px" @keyup.enter="search" @clear="search" />
        <el-button type="primary" size="small" @click="search">查询</el-button>
        <el-button size="small" @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="tableData" size="small" height="480" class="mt" row-key="id">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand">
              <div><b>规则：</b>{{ row.rule_name }}（{{ row.rule_code }}，{{ WARNING_TYPE_TEXT[row.warning_type] || row.warning_type }}）</div>
              <div><b>命中指标：</b>{{ row.metric_value ?? '--' }}</div>
              <div><b>详情：</b>{{ JSON.stringify(row.detail) }}</div>
              <div v-if="row.handled_at"><b>处置：</b>{{ row.handled_by }} 于 {{ row.handled_at }} 标记为 {{ row.status_text }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="warning_date" label="日期" width="112" sortable />
        <el-table-column label="学生" width="180">
          <template #default="{ row }">
            <a class="link" @click="router.push(`/student/${row.student_id}`)">{{ row.student_name }}</a>
            <span class="sb-muted"> {{ row.student_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="college" label="学院" min-width="150" show-overflow-tooltip />
        <el-table-column prop="class_name" label="班级" width="120" show-overflow-tooltip />
        <el-table-column label="大类" width="92">
          <template #default="{ row }">{{ WARNING_TYPE_TEXT[row.warning_type] || row.warning_type }}</template>
        </el-table-column>
        <el-table-column prop="rule_name" label="规则" width="150" show-overflow-tooltip />
        <el-table-column label="级别" width="76" align="center">
          <template #default="{ row }">
            <el-tag :type="LEVEL_TAG[row.warning_level] || 'info'" size="small" effect="dark">
              {{ LEVEL_TEXT[row.warning_level] || row.warning_level_text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="metric_value" label="指标值" width="88" align="right" sortable />
        <el-table-column prop="message" label="说明" min-width="280" show-overflow-tooltip />
        <el-table-column label="状态" width="86" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 0 ? 'danger' : row.status === 1 ? 'success' : 'info'" size="small" effect="plain">
              {{ row.status_text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="186" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="showDetail(row)">详情</el-button>
            <el-button v-if="row.status === 0" size="small" text type="success" @click="handle(row, 1)">已处理</el-button>
            <el-button v-if="row.status === 0" size="small" text @click="handle(row, 2)">忽略</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page" v-model:page-size="size" :total="total"
        :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next, jumper"
        size="small" class="mt" @current-change="loadList" @size-change="search"
      />
    </PanelBox>

    <el-dialog v-model="detailVisible" title="预警详情" width="620px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="学生">{{ detail.student_name }}（{{ detail.student_id }}）</el-descriptions-item>
        <el-descriptions-item label="学院班级">{{ detail.college }} / {{ detail.class_name }}</el-descriptions-item>
        <el-descriptions-item label="规则">{{ detail.rule_name }}（{{ detail.rule_code }}）</el-descriptions-item>
        <el-descriptions-item label="预警日期">{{ detail.warning_date }}</el-descriptions-item>
        <el-descriptions-item label="触发时间">{{ detail.triggered_at }}</el-descriptions-item>
        <el-descriptions-item label="级别">{{ detail.warning_level_text }}</el-descriptions-item>
        <el-descriptions-item label="说明">{{ detail.message }}</el-descriptions-item>
        <el-descriptions-item label="指标值">{{ detail.metric_value }}</el-descriptions-item>
        <el-descriptions-item label="计算明细">
          <pre class="json">{{ JSON.stringify(detail.detail, null, 2) }}</pre>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="router.push(`/student/${detail.student_id}`)">查看该生画像</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.mt {
  margin-top: 12px;
}

.cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.charts {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 12px;
  margin-top: 12px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.link {
  color: var(--sb-accent);
  cursor: pointer;
}

.link:hover {
  text-decoration: underline;
}

.expand,
.json {
  font-size: 12px;
  color: var(--sb-text-dim);
  line-height: 1.8;
}

.json {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow: auto;
}

@media (max-width: 1500px) {
  .cards,
  .charts {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
