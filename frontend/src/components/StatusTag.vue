<template>
  <el-tag :type="item.type" :size="size" :effect="effect" disable-transitions>
    {{ item.label }}
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { dictItem } from '@/utils/dict'
import type { DictItem } from '@/utils/dict'

const props = withDefaults(defineProps<{
  value?: string | null
  map: Record<string, DictItem>
  size?: 'large' | 'default' | 'small'
  effect?: 'dark' | 'light' | 'plain'
}>(), {
  size: 'small',
  effect: 'light',
})

const item = computed(() => dictItem(props.map, props.value))
</script>
