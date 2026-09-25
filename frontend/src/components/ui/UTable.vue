<script setup>
/**
 * 数据表：列定义 + 前端排序 + 自定义单元格插槽（cell-<key>）。
 * columns: [{ key, label, width?, align?, sortable?, formatter? }]
 * 只覆盖本项目三张明细表的诉求（无固定列/无树形），刻意不做 EP 全家桶。
 */
import { computed, ref } from 'vue'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-vue-next'

const props = defineProps({
  columns: { type: Array, required: true },
  items: { type: Array, default: () => [] },
  rowKey: { type: String, default: 'id' },
  clickable: Boolean,
  dense: { type: Boolean, default: true },
})
const emit = defineEmits(['row-click'])

const sort = ref({ key: '', dir: 1 })

function toggleSort(col) {
  if (!col.sortable) return
  if (sort.value.key !== col.key) sort.value = { key: col.key, dir: 1 }
  else if (sort.value.dir === 1) sort.value = { key: col.key, dir: -1 }
  else sort.value = { key: '', dir: 1 }               // 三态：升 → 降 → 恢复原序
}

const sorted = computed(() => {
  const { key, dir } = sort.value
  if (!key) return props.items
  return [...props.items].sort((a, b) => {
    const va = a[key]
    const vb = b[key]
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
    return String(va).localeCompare(String(vb), 'zh-CN') * dir
  })
})

function cellText(col, row) {
  const v = row[col.key]
  if (col.formatter) return col.formatter(v, row)
  return v ?? '--'
}
</script>

<template>
  <div class="ci-table-wrap">
    <table class="ci-table" :class="{ dense }">
      <thead>
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            :style="{ width: col.width ? col.width + 'px' : undefined, textAlign: col.align || 'left' }"
            :class="{ sortable: col.sortable }"
            @click="toggleSort(col)"
          >
            {{ col.label }}
            <component
              :is="col.sortable ? (sort.key === col.key ? (sort.dir === 1 ? ArrowUp : ArrowDown) : ChevronsUpDown) : null"
              v-if="col.sortable"
              :size="12"
              class="ci-th__icon"
            />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in sorted"
          :key="row[rowKey] ?? i"
          :class="{ clickable }"
          @click="clickable && emit('row-click', row)"
        >
          <td v-for="col in columns" :key="col.key" :style="{ textAlign: col.align || 'left' }">
            <!-- 列自定义插槽：<template #cell-status="{ row }">；无插槽走 formatter/原值 -->
            <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]" :index="i">
              <span :class="{ 'ci-num': col.numeric }">{{ cellText(col, row) }}</span>
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="!items.length" class="ci-table__none">暂无数据</div>
  </div>
</template>

<style scoped>
.ci-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--ci-border);
  border-radius: var(--r-md);
}
.ci-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.ci-table th {
  position: sticky;
  top: 0;
  background: var(--ci-surface-2);
  color: var(--ci-text-2);
  font-weight: 600;
  font-size: 12px;
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--ci-border);
  white-space: nowrap;
  user-select: none;
}
.ci-table th.sortable {
  cursor: pointer;
}
.ci-table th.sortable:hover {
  color: var(--ci-text);
}
.ci-th__icon {
  vertical-align: -2px;
  margin-left: 3px;
  opacity: 0.7;
}
.ci-table td {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.045);
  color: var(--ci-text);
  white-space: nowrap;
}
.ci-table.dense td {
  padding: 5px 12px;
}
.ci-table tbody tr {
  transition: background var(--dur-fast) var(--ease);
}
.ci-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.03);
}
.ci-table tbody tr:last-child td {
  border-bottom: 0;
}
.ci-table tr.clickable {
  cursor: pointer;
}
.ci-table__none {
  padding: 24px;
  text-align: center;
  color: var(--ci-text-3);
  font-size: 12.5px;
}
</style>
