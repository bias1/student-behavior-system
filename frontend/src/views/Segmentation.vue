<script setup>
/**
 * 分群工作台（/segmentation）
 *
 * 功能：
 *   - K-Means 群体分布柱状图（可点击柱子看成员）
 *   - 簇画像卡片列表（带伦理声明）
 *   - PCA 散点图 + 手肘曲线（质量评估 Modal）
 *   - 成员 Drawer（分页表格）
 *   - 工具栏：时间窗口、K 值、特征集切换、刷新
 *
 * 数据来源：ClusteringApi（/clustering/result、/elbow、/members）
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Layers, Maximize2, RefreshCw } from 'lucide-vue-next'
import { ClusteringApi } from '@/api'
import { dataSpan, windowOptions } from '@/utils/window'
import { PALETTE } from '@/styles/palette'
import BaseChart from '@/components/BaseChart.vue'
import UCard from '@/components/ui/UCard.vue'
import USegmented from '@/components/ui/USegmented.vue'
import USelect from '@/components/ui/USelect.vue'
import UButton from '@/components/ui/UButton.vue'
import UBadge from '@/components/ui/UBadge.vue'
import UModal from '@/components/ui/UModal.vue'
import UDrawer from '@/components/ui/UDrawer.vue'
import UTable from '@/components/ui/UTable.vue'
import USkeleton from '@/components/ui/USkeleton.vue'
import UEmptyState from '@/components/ui/UEmptyState.vue'

const router = useRouter()

// 窗口选项按真实数据跨度生成（“全部”不再是硬编码 90 天）
const span = ref(0)
const DAYS_OPTS = computed(() => windowOptions(span.value))
const K_OPTS = [3, 4, 5, 6].map((v) => ({ value: v, label: `K=${v}` }))
const FEATURE_OPTS = [
  { value: 'core', label: 'core 4 特征' },
  { value: 'full', label: 'full 11 特征' },
]

const days = ref(30)
const k = ref(4)
const featureSet = ref('core')
const loading = ref(false)
const clu = ref({})
const elbow = ref({})

async function load() {
  loading.value = true
  try {
    const params = { k: k.value, days: days.value, features: featureSet.value }
    const [r, e] = await Promise.all([
      ClusteringApi.result(params, { timeout: 60000 }),
      ClusteringApi.elbow({ ...params, k_min: 2, k_max: 8 }, { timeout: 60000 }),
    ])
    if (r) clu.value = r
    if (e) elbow.value = e
  } finally { loading.value = false }
}

watch([k, featureSet], load)
watch(days, load)
onMounted(async () => {
  span.value = await dataSpan()
  if (span.value > 0 && days.value > span.value) {
    days.value = span.value
    return                     // watch(days) 会触发 load，不重复算一轮聚类
  }
  load()
})

/* ---------------- 群体分布柱状图 ---------------- */
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
    series: [{
      type: 'bar', barMaxWidth: 74, data: cs.map((c) => c.size),
      label: { show: true, position: 'top', formatter: (p) => `${p.value}人/${cs[p.dataIndex].pct}%` },
      itemStyle: { color: (p) => PALETTE[p.dataIndex % PALETTE.length], borderRadius: [5, 5, 0, 0] },
    }],
  }
})

function onClusterClick(p) {
  if (p.componentType === 'series') openMembers(p.dataIndex)
}

/* ---------------- 质量评估 Modal ---------------- */
const qualityOpen = ref(false)

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
      { name: '轮廓系数', type: 'line', yAxisIndex: 1, data: e.silhouette || [], lineStyle: { color: '#ffb454' }, itemStyle: { color: '#ffb454' } },
    ],
  }
})

/* ---------------- 成员 Drawer ---------------- */
const membersOpen = ref(false)
const drawerData = ref({})

async function openMembers(idx) {
  const c = (clu.value.clusters || [])[idx]
  if (!c) return
  membersOpen.value = true
  drawerData.value = { cluster: c, items: [] }
  const d = await ClusteringApi.members({ cluster: c.cluster, k: k.value, features: featureSet.value, limit: 50 })
  if (d) drawerData.value = { cluster: c, ...d }
}

const clusterMeta = computed(() => ({
  silhouette: clu.value.silhouette,
  sse: clu.value.sse,
  pca: clu.value.pca_explained,
  n: clu.value.n_students,
}))

/* Drawer 成员表格列（含动态特征列）*/
const memberColumns = computed(() => [
  { key: 'student_id', label: '学号', width: '110px' },
  { key: 'name', label: '姓名', width: '80px' },
  { key: 'college', label: '学院', width: '160px' },
  ...(clu.value.feature_keys || []).map((key) => ({
    key, label: clu.value.features?.[key]?.label || key, width: '100px', align: 'right',
    formatter: (_v, row) => row.features?.[key] ?? '--',
  })),
])
</script>

<template>
  <div class="seg-page">
    <!-- 工具栏 -->
    <div class="sg-bar">
      <USegmented v-model="days" :options="DAYS_OPTS" size="sm" />
      <USelect v-model="k" :options="K_OPTS" placeholder="K 值" width="80px" />
      <USelect v-model="featureSet" :options="FEATURE_OPTS" placeholder="特征集" width="136px" />
      <div class="sg-bar__right">
        <UButton variant="ghost" size="sm" :loading="loading" @click="load">
          <RefreshCw :size="13" /> 重新计算
        </UButton>
        <UButton variant="ghost" size="sm" @click="qualityOpen = true">
          <Maximize2 :size="13" /> 质量评估
        </UButton>
      </div>
    </div>

    <!-- 指标摘要 -->
    <div v-if="clusterMeta.silhouette != null" class="sg-meta">
      <span>轮廓系数 <b>{{ clusterMeta.silhouette }}</b></span>
      <span>SSE <b>{{ clusterMeta.sse }}</b></span>
      <span>PCA 解释度 <b>{{ clusterMeta.pca }}%</b></span>
      <span>样本 <b>{{ clusterMeta.n }}</b> 人</span>
    </div>

    <!-- 群体分布图 -->
    <UCard title="K-Means 群体分布" :subtitle="`K=${k} · ${featureSet} 特征集 · 点击柱子查看成员`" padded>
      <USkeleton v-if="loading && !clu.clusters" :lines="6" />
      <BaseChart v-else :option="clusterOption" :loading="loading" height="280px" @click="onClusterClick" />
    </UCard>

    <!-- 簇画像卡片列表 -->
    <UCard title="簇画像解读" subtitle="点击查看详情" padded>
      <p class="sg-ethics">
        群体画像仅用于教学服务与资助帮扶参考，不构成对学生的评价或定性。
      </p>
      <div class="sg-clusters">
        <div
          v-for="(c, i) in clu.clusters || []" :key="c.cluster"
          class="sg-cc"
          @click="openMembers(i)"
        >
          <div class="sg-cc__head">
            <i class="sg-cc__dot" :style="{ background: PALETTE[i % PALETTE.length] }" />
            <b class="sg-cc__label">{{ c.label }}</b>
            <span class="sg-cc__size">{{ c.size }} 人 / {{ c.pct }}%</span>
          </div>
          <div class="sg-cc__bar">
            <i :style="{ width: c.pct + '%', background: PALETTE[i % PALETTE.length] }" />
          </div>
          <p class="sg-cc__desc">{{ c.desc }}</p>
        </div>
        <UEmptyState v-if="!(clu.clusters || []).length && !loading" title="暂无聚类结果" hint="尝试调整 K 值或特征集" />
      </div>
    </UCard>

    <!-- 质量评估 Modal -->
    <UModal v-model:open="qualityOpen" title="聚类质量评估" width="1080px">
      <div class="sg-quality">
        <div class="sg-quality__box">
          <p class="sg-quality__label">PCA 散点图（前两主成分）</p>
          <BaseChart :option="scatterOption" height="400px" />
        </div>
        <div class="sg-quality__box">
          <p class="sg-quality__label">手肘曲线（SSE + 轮廓系数）</p>
          <BaseChart :option="elbowOption" height="400px" />
        </div>
      </div>
      <p class="sg-note">
        左图：标准化特征经 PCA 降到前两主成分后的散点（解释度 {{ clu.pca_explained || '--' }}%），
        仅用于观察簇分离程度，不参与聚类计算。右图：K=2~8 的 SSE 与轮廓系数，
        最优 K 值按"SSE 边际收益明显下降 + 簇可解释性"确定。
      </p>
    </UModal>

    <!-- 成员 Drawer -->
    <UDrawer v-model:open="membersOpen" :title="`簇 ${drawerData.cluster?.cluster ?? ''}：${drawerData.cluster?.label ?? ''}`" width="680px">
      <div v-if="drawerData.cluster" class="sg-drawer">
        <div class="sg-drawer__info">
          <p class="sg-drawer__def">{{ drawerData.cluster.desc }}</p>
          <p class="sg-drawer__definition">{{ drawerData.cluster.definition }}</p>
        </div>
        <div v-if="drawerData.cluster.features" class="sg-drawer__features">
          <div v-for="(v, key) in drawerData.cluster.features" :key="key" class="sg-drawer__feat">
            <span class="sg-drawer__fname">{{ clu.features?.[key]?.label || key }}</span>
            <b>{{ v }} <small>{{ clu.features?.[key]?.unit }}</small></b>
          </div>
        </div>
        <UTable
          :columns="memberColumns"
          :items="drawerData.items || []"
          row-key="student_id"
          clickable
          dense
          @row-click="(row) => router.push(`/student/${row.student_id}`)"
        />
      </div>
    </UDrawer>
  </div>
</template>

<style scoped>
.seg-page {
  padding: 16px 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
}

.sg-bar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sg-bar__right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.sg-meta {
  display: flex;
  gap: 20px;
  padding: 8px 14px;
  background: var(--ci-surface);
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  font-size: 12px;
  color: var(--ci-text-2);
}

.sg-meta b {
  color: var(--ci-text);
  font-weight: 600;
}

/* 伦理声明 */
.sg-ethics {
  margin: 0 0 12px;
  padding: 6px 10px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--ci-text-3);
  border-left: 2px solid var(--ci-warning);
  background: rgba(255, 180, 84, 0.06);
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
}

/* 簇卡片列表 */
.sg-clusters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}

.sg-cc {
  padding: 10px 12px;
  border-radius: var(--r-md);
  background: var(--ci-surface-2);
  border: 1px solid var(--ci-border);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.sg-cc:hover {
  border-color: var(--ci-primary-dim, rgba(124,108,255,0.4));
  background: var(--ci-surface-3);
}

.sg-cc__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.sg-cc__dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.sg-cc__label { font-size: 13px; color: var(--ci-text); }
.sg-cc__size { margin-left: auto; font-size: 11px; color: var(--ci-text-3); }

.sg-cc__bar {
  height: 3px;
  margin-bottom: 6px;
  border-radius: 2px;
  background: rgba(255,255,255,0.06);
  overflow: hidden;
}

.sg-cc__bar i { display: block; height: 100%; }

.sg-cc__desc {
  margin: 0;
  font-size: 11px;
  color: var(--ci-text-3);
  line-height: 1.5;
}

/* 质量 Modal */
.sg-quality {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.sg-quality__box {
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
  padding: 8px;
}

.sg-quality__label {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--ci-text-3);
}

.sg-note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--ci-text-3);
  line-height: 1.7;
}

/* Drawer */
.sg-drawer {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sg-drawer__info {
  padding: 10px 12px;
  background: var(--ci-surface-2);
  border-radius: var(--r-md);
  border: 1px solid var(--ci-border);
}

.sg-drawer__def { margin: 0 0 4px; font-size: 13px; color: var(--ci-text); }
.sg-drawer__definition { margin: 0; font-size: 12px; color: var(--ci-text-3); line-height: 1.5; }

.sg-drawer__features {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px;
}

.sg-drawer__feat {
  padding: 6px 10px;
  background: var(--ci-surface-2);
  border-radius: var(--r-sm);
  font-size: 12px;
}

.sg-drawer__fname { display: block; color: var(--ci-text-3); margin-bottom: 2px; }

@media (max-width: 900px) {
  .sg-quality { grid-template-columns: 1fr; }
}
</style>
