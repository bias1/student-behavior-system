<script setup>
/**
 * 命令面板（Ctrl+K / Cmd+K 呼出）
 *
 * 数据源：
 *   1. 静态路由命令（快速跳转页面）
 *   2. 学生搜索（防抖 300ms 调 /student/list?size=6）
 *
 * 键盘：↑↓ 选择，Enter 跳转，Esc 关闭
 * 复用 UModal 底座，不独立渲染遮罩
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CornerDownLeft, Search, User } from 'lucide-vue-next'
import { StudentApi } from '@/api'
import UModal from './ui/UModal.vue'

const emit = defineEmits(['close'])

const router = useRouter()
const open = defineModel('open', { type: Boolean, default: false })

const query = ref('')
const selected = ref(0)
const inputEl = ref(null)

/* ---------------- 静态命令 ---------------- */
const PAGE_COMMANDS = [
  { id: 'overview', label: '群体概览', hint: 'Overview', action: () => router.push({ name: 'overview' }) },
  { id: 'students', label: '学生列表', hint: 'Students', action: () => router.push({ name: 'students' }) },
  { id: 'profile', label: '个体画像', hint: 'Student Profile', action: () => router.push({ name: 'student-profile' }) },
  { id: 'risk', label: '风险中心', hint: 'Risk Center', action: () => router.push({ name: 'risk' }) },
  { id: 'seg', label: '分群工作台', hint: 'Segmentation', action: () => router.push({ name: 'segmentation' }) },
]

/* ---------------- 学生搜索结果 ---------------- */
const stuResults = ref([])
const stuLoading = ref(false)
let debounce = null

async function searchStudents(q) {
  if (!q.trim()) { stuResults.value = []; return }
  stuLoading.value = true
  try {
    const d = await StudentApi.list({ keyword: q, size: 6 })
    stuResults.value = (d.items || []).map((s) => ({
      id: s.student_id,
      label: `${s.name} (${s.student_id})`,
      hint: [s.college, s.major].filter(Boolean).join(' · '),
      action: () => router.push({ name: 'student-profile', params: { id: s.student_id } }),
    }))
  } finally { stuLoading.value = false }
}

watch(query, (v) => {
  clearTimeout(debounce)
  debounce = setTimeout(() => searchStudents(v), 300)
})

/* ---------------- 合并列表 ---------------- */
const filteredPages = computed(() => {
  const q = query.value.toLowerCase()
  if (!q) return PAGE_COMMANDS
  return PAGE_COMMANDS.filter((c) => c.label.includes(q) || c.hint.toLowerCase().includes(q))
})

const items = computed(() => [
  ...filteredPages.value.map((c) => ({ ...c, type: 'page' })),
  ...stuResults.value.map((c) => ({ ...c, type: 'student' })),
])

// 重置选中索引
watch(items, () => { selected.value = 0 })

/* ---------------- 键盘导航 ---------------- */
function onKeydown(e) {
  if (!open.value) return
  if (e.key === 'ArrowDown') { e.preventDefault(); selected.value = Math.min(selected.value + 1, items.value.length - 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); selected.value = Math.max(selected.value - 1, 0) }
  else if (e.key === 'Enter') { e.preventDefault(); run(items.value[selected.value]) }
}

function run(item) {
  if (!item) return
  item.action()
  close()
}

function close() {
  open.value = false
  query.value = ''
  stuResults.value = []
  selected.value = 0
}

/* ---------------- 焦点管理 ---------------- */
watch(open, async (v) => {
  if (v) {
    await nextTick()
    inputEl.value?.focus()
  }
})

/* ---------------- 全局快捷键 ---------------- */
function globalKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    open.value = !open.value
  }
}
onMounted(() => document.addEventListener('keydown', globalKey))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', globalKey)
  clearTimeout(debounce)
})
</script>

<template>
  <UModal v-model:open="open" title="" width="580px" :show-header="false" @close="close">
    <template #default>
      <!-- 搜索框 -->
      <div class="cmd-input-wrap">
        <Search :size="15" class="cmd-icon" />
        <input
          ref="inputEl"
          v-model="query"
          class="cmd-input"
          placeholder="搜索页面 / 学生学号姓名..."
          @keydown="onKeydown"
        />
        <span class="cmd-kbd">ESC 关闭</span>
      </div>

      <!-- 结果列表 -->
      <div class="cmd-list">
        <!-- 页面命令 -->
        <template v-if="filteredPages.length">
          <p class="cmd-group">导航</p>
          <div
            v-for="item in filteredPages" :key="item.id"
            class="cmd-item"
            :class="{ 'is-selected': items[selected]?.id === item.id }"
            @click="run(item)"
            @mouseenter="selected = items.findIndex(x => x.id === item.id)"
          >
            <span class="cmd-item__label">{{ item.label }}</span>
            <span class="cmd-item__hint">{{ item.hint }}</span>
          </div>
        </template>

        <!-- 学生搜索 -->
        <template v-if="query.trim()">
          <p class="cmd-group">学生</p>
          <div v-if="stuLoading" class="cmd-loading">搜索中...</div>
          <div
            v-for="item in stuResults" :key="item.id"
            class="cmd-item"
            :class="{ 'is-selected': items[selected]?.id === item.id }"
            @click="run(item)"
            @mouseenter="selected = items.findIndex(x => x.id === item.id)"
          >
            <User :size="13" class="cmd-item__icon" />
            <span class="cmd-item__label">{{ item.label }}</span>
            <span class="cmd-item__hint">{{ item.hint }}</span>
          </div>
          <div v-if="!stuResults.length && !stuLoading && query.trim()" class="cmd-empty">
            未找到匹配学生
          </div>
        </template>

        <div v-if="!items.length" class="cmd-empty">无匹配结果</div>
      </div>

      <!-- 底部提示 -->
      <div class="cmd-footer">
        <span><CornerDownLeft :size="11" /> 确认</span>
        <span>↑↓ 导航</span>
        <span v-if="items.length">共 {{ items.length }} 项</span>
      </div>
    </template>
  </UModal>
</template>

<style scoped>
.cmd-input-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ci-border);
}

.cmd-icon {
  color: var(--ci-text-3);
  flex-shrink: 0;
}

.cmd-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-size: 15px;
  color: var(--ci-text);
  font-family: var(--font-sans);
}

.cmd-input::placeholder {
  color: var(--ci-text-3);
}

.cmd-kbd {
  font-size: 10px;
  padding: 2px 6px;
  border: 1px solid var(--ci-border);
  border-radius: 4px;
  color: var(--ci-text-3);
  white-space: nowrap;
}

.cmd-list {
  max-height: 360px;
  overflow-y: auto;
  padding: 8px 0;
}

.cmd-group {
  margin: 0;
  padding: 6px 16px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--ci-text-3);
  text-transform: uppercase;
}

.cmd-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.12s;
  font-size: 13px;
  color: var(--ci-text);
}

.cmd-item:hover,
.cmd-item.is-selected {
  background: var(--ci-surface-2);
}

.cmd-item.is-selected {
  background: var(--ci-primary-dim, rgba(124,108,255,0.12));
}

.cmd-item__icon {
  color: var(--ci-text-3);
  flex-shrink: 0;
}

.cmd-item__label {
  flex: 1;
}

.cmd-item__hint {
  font-size: 11px;
  color: var(--ci-text-3);
  white-space: nowrap;
}

.cmd-loading,
.cmd-empty {
  padding: 12px 16px;
  font-size: 12px;
  color: var(--ci-text-3);
}

.cmd-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  border-top: 1px solid var(--ci-border);
  font-size: 11px;
  color: var(--ci-text-3);
}

.cmd-footer span {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
