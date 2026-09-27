<script setup>
/**
 * ECharts 通用容器
 * 负责最容易出问题的三件事：初始化时机、尺寸自适应、销毁。
 * - 用 ResizeObserver 而不是 window.resize：面板宽度受栅格影响，父容器变化时才会真正需要重绘
 * - setOption 用 notMerge=true：切换特征集/指标时 series 数量会变，合并旧配置会残留上一次的线
 * - 主题名随全局深/浅模式切换（insight-dark / insight-light，均在 plugins/echarts.js 注册），
 *   切换时销毁重建实例：注册主题在 init 时一次性注入，无法热替换，只能重建
 */
import { computed, onBeforeUnmount, onMounted, shallowRef, ref, watch, nextTick } from 'vue'
import echarts from '@/plugins/echarts'
import { useTheme } from '@/composables/useTheme'

const props = defineProps({
  option: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  height: { type: String, default: '100%' },
})
const emit = defineEmits(['click'])

const el = ref(null)
const chart = shallowRef(null)   // shallowRef：实例不需要被 Vue 深度代理，否则内部遍历极慢还易报警
let ro = null

const theme = useTheme()
const themeName = computed(() => (theme.isLight.value ? 'insight-light' : 'insight-dark'))

// loading 遮罩文案/底色的中性色跟随主题：深色半透明深底、浅色半透明白底
function loadingOpt() {
  return theme.isLight.value
    ? { text: '加载中', color: '#0e8fc4', textColor: '#4a5563', maskColor: 'rgba(255,255,255,0.6)' }
    : { text: '加载中', color: '#4fd1ff', textColor: '#8b96a5', maskColor: 'rgba(11,15,20,0.55)' }
}

function render() {
  if (!chart.value || !props.option) return
  chart.value.setOption(props.option, true)
}

function createChart() {
  if (!el.value) return
  chart.value = echarts.init(el.value, themeName.value, { renderer: 'canvas' })
  chart.value.on('click', (p) => emit('click', p))
  render()
  if (props.loading) chart.value.showLoading('default', loadingOpt())
}

function destroyChart() {
  chart.value && chart.value.dispose()
  chart.value = null
}

onMounted(async () => {
  await nextTick()
  // el 为空 = 在 nextTick 间隙已被父组件的 v-if/v-else 切换卸掉
  // （首屏数据秒回时很容易撞上：先 mount 空图、loading 翻真又被换下，此时 init 会抛 invalid dom）
  createChart()
  ro = new ResizeObserver(() => chart.value && chart.value.resize())
  if (el.value) ro.observe(el.value)
})

onBeforeUnmount(() => {
  ro && ro.disconnect()
  destroyChart()
})

watch(() => props.option, render, { deep: true })
watch(
  () => props.loading,
  (v) => {
    if (!chart.value) return
    v ? chart.value.showLoading('default', loadingOpt()) : chart.value.hideLoading()
  }
)
// 主题切换：销毁旧实例、按新主题名重建，图表配色整体翻转
watch(themeName, () => {
  destroyChart()
  createChart()
})
</script>

<template>
  <div ref="el" :style="{ width: '100%', height }" class="sb-chart" />
</template>

<style scoped>
.sb-chart {
  min-height: 120px;
}
</style>
