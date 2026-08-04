<template>
  <div class="stat-card" :class="{ 'stat-card-clickable': !!to }" @click="go">
    <div class="stat-icon" :style="{ background: bg, color: color }">
      <el-icon :size="22"><component :is="icon" /></el-icon>
    </div>
    <div class="stat-body">
      <div class="stat-value" :style="{ color: valueColor || undefined }">{{ display }}</div>
      <div class="stat-title">{{ title }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { Component } from 'vue'

const props = defineProps<{
  title: string
  value: number | string | null | undefined
  icon: Component
  /** 图标主色 */
  color?: string
  /** 数值颜色 */
  valueColor?: string
  suffix?: string
  /** 点击跳转路径 */
  to?: string
}>()

const router = useRouter()

const display = computed(() => {
  const v = props.value ?? 0
  return props.suffix ? `${v}${props.suffix}` : v
})

const bg = computed(() => {
  const c = props.color || '#2B5AED'
  return `${c}14` // 8% 透明度底色
})

function go() {
  if (props.to) router.push(props.to)
}
</script>
