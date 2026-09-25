<script setup>
/**
 * 学生列表（/students）
 *
 * 数据源：GET /api/student/list
 * 功能：关键词搜索（学号前缀/姓名）、学院/年级筛选、分页表格
 * 操作：点击学号或姓名 → 跳转个体画像
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Download, Search, User } from 'lucide-vue-next'
import { StudentApi } from '@/api'
import UCard from '@/components/ui/UCard.vue'
import UInput from '@/components/ui/UInput.vue'
import USelect from '@/components/ui/USelect.vue'
import UButton from '@/components/ui/UButton.vue'
import UBadge from '@/components/ui/UBadge.vue'
import UTable from '@/components/ui/UTable.vue'
import UPagination from '@/components/ui/UPagination.vue'
import USkeleton from '@/components/ui/USkeleton.vue'
import UEmptyState from '@/components/ui/UEmptyState.vue'

const router = useRouter()

const keyword = ref('')
const collegeFilter = ref('')
const gradeFilter = ref('')
const page = ref(1)
const size = ref(20)
const loading = ref(false)
const items = ref([])
const total = ref(0)

/* 学院列表（初始化时从后端拿，也可手动补充） */
const COLLEGES = ref([])
const GRADES = [
  { value: '2021', label: '2021 级' },
  { value: '2022', label: '2022 级' },
  { value: '2023', label: '2023 级' },
  { value: '2024', label: '2024 级' },
  { value: '2025', label: '2025 级' },
]

async function loadMeta() {
  // 从聚类表拿全量学院名称（后端没有专门的学院接口，利用聚类 table 接口）
  // 也可改为从 overview groups?dim=college 获取
  try {
    const { OverviewApi } = await import('@/api')
    const d = await OverviewApi.groups('college')
    COLLEGES.value = (d?.items || []).map((r) => ({ value: r.name, label: r.name }))
  } catch {
    COLLEGES.value = []
  }
}

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (keyword.value) params.keyword = keyword.value
    const d = await StudentApi.list(params)
    items.value = d.items || []
    total.value = d.total || 0
  } finally { loading.value = false }
}

function search() {
  page.value = 1
  loadList()
}

onMounted(() => { loadMeta(); loadList() })

const columns = [
  { key: 'student_id', label: '学号', width: '120px' },
  { key: 'name', label: '姓名', width: '80px' },
  { key: 'gender', label: '性别', width: '56px', align: 'center' },
  { key: 'college', label: '学院', width: '180px' },
  { key: 'major', label: '专业', width: '160px' },
  { key: 'class_name', label: '班级', width: '120px' },
  { key: 'grade_year', label: '年级', width: '70px', align: 'center' },
  { key: 'dorm_building', label: '宿舍', width: '120px' },
  { key: 'action', label: '操作', width: '80px' },
]

function goProfile(sid) {
  if (sid) router.push(`/student/${sid}`)
}
</script>

<template>
  <div class="students-page">
    <UCard title="学生列表" :subtitle="`共 ${total} 人`">
      <template #extra>
        <UButton variant="ghost" size="sm">
          <Download :size="13" /> 导出
        </UButton>
      </template>

      <!-- 搜索栏 -->
      <div class="st-filters">
        <UInput
          v-model="keyword"
          placeholder="学号前缀 / 姓名搜索"
          width="220px"
          @enter="search"
          @clear="search"
        >
          <template #prefix><Search :size="13" /></template>
        </UInput>
        <UButton variant="primary" size="sm" @click="search">查询</UButton>
        <UButton
          variant="ghost" size="sm"
          @click="keyword = ''; page = 1; loadList()"
        >重置</UButton>
      </div>

      <!-- 表格 -->
      <div class="st-table">
        <USkeleton v-if="loading && !items.length" :lines="8" />
        <UTable
          v-else-if="items.length"
          :columns="columns"
          :items="items"
          row-key="student_id"
          clickable
          @row-click="(row) => goProfile(row.student_id)"
        >
          <template #cell-student_id="{ row }">
            <a class="st-link" @click.stop="goProfile(row.student_id)">{{ row.student_id }}</a>
          </template>
          <template #cell-name="{ row }">
            <span class="st-name"><User :size="11" /> {{ row.name }}</span>
          </template>
          <template #cell-gender="{ row }">
            <UBadge :tone="row.gender === '男' ? 'primary' : 'neutral'">
              {{ row.gender || '--' }}
            </UBadge>
          </template>
          <template #cell-action="{ row }">
            <UButton variant="text" size="sm" @click.stop="goProfile(row.student_id)">画像</UButton>
          </template>
        </UTable>
        <UEmptyState v-else tone="search" title="暂无学生数据" hint="调整搜索条件重试" />
      </div>

      <UPagination
        v-if="total > 0"
        v-model:page="page"
        :size="size"
        :total="total"
        class="st-pager"
        @change="loadList"
      />
    </UCard>
  </div>
</template>

<style scoped>
.students-page {
  padding: 16px 18px 18px;
  min-height: 100%;
}

.st-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.st-table { min-height: 200px; }

.st-pager { margin-top: 10px; }

.st-link {
  color: var(--ci-primary);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 12px;
  &:hover { text-decoration: underline; }
}

.st-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}
</style>
