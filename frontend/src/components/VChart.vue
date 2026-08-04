<template>
  <div ref="el" class="v-chart" :style="{ height }" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption, ECharts } from 'echarts'

const props = withDefaults(defineProps<{
  option: EChartsOption
  height?: string
}>(), {
  height: '300px',
})

const el = ref<HTMLDivElement>()
let chart: ECharts | null = null
let observer: ResizeObserver | null = null

function render() {
  if (!chart || !props.option) return
  chart.setOption(props.option, true)
}

onMounted(() => {
  chart = echarts.init(el.value!)
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(el.value!)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.v-chart {
  width: 100%;
}
</style>
