<script setup>
/**
 * ECharts 通用容器
 * 负责最容易出问题的三件事：初始化时机、尺寸自适应、销毁。
 * - 用 ResizeObserver 而不是 window.resize：面板宽度受栅格影响，父容器变化时才会真正需要重绘
 * - setOption 用 notMerge=true：切换特征集/指标时 series 数量会变，合并旧配置会残留上一次的线
 * - 主题名 'sb-dark' 在 src/plugins/echarts.js 里注册
 */
import { onBeforeUnmount, onMounted, shallowRef, ref, watch, nextTick } from 'vue'
import echarts from '@/plugins/echarts'

const props = defineProps({
  option: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  height: { type: String, default: '100%' },
})
const emit = defineEmits(['click'])

const el = ref(null)
const chart = shallowRef(null)   // shallowRef：实例不需要被 Vue 深度代理，否则内部遍历极慢还易报警
let ro = null

const LOPT = { text: '加载中', color: '#37e2f0', textColor: '#9fbadb', maskColor: 'rgba(6,16,32,0.35)' }

function render() {
  if (!chart.value || !props.option) return
  chart.value.setOption(props.option, true)
}

onMounted(async () => {
  await nextTick()
  chart.value = echarts.init(el.value, 'sb-dark', { renderer: 'canvas' })
  chart.value.on('click', (p) => emit('click', p))
  render()
  ro = new ResizeObserver(() => chart.value && chart.value.resize())
  ro.observe(el.value)
})

onBeforeUnmount(() => {
  ro && ro.disconnect()
  chart.value && chart.value.dispose()
  chart.value = null
})

watch(() => props.option, render, { deep: true })
watch(
  () => props.loading,
  (v) => {
    if (!chart.value) return
    v ? chart.value.showLoading('default', LOPT) : chart.value.hideLoading()
  }
)
</script>

<template>
  <div ref="el" :style="{ width: '100%', height }" class="sb-chart" />
</template>

<style scoped>
.sb-chart {
  min-height: 120px;
}
</style>
