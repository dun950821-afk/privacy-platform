<template>
  <div class="engine-panel" v-loading="loading">
    <EmptyBox v-if="!hasAny" description="本任务未启用 MobSF，或该引擎未产出结果" />

    <template v-else>
      <!-- 端点：MobSF 的主体。按来源分组并去重——同一域名的多条 URL 归一处 -->
      <div class="section-head">
        <span class="section-title">端点</span>
        <span class="section-sub">
          {{ endpointCount }} 条 URL，按来源归为 {{ endpointGroups.length }} 组
        </span>
      </div>
      <div v-if="endpointGroups.length" class="group-list">
        <div v-for="group in endpointGroups" :key="group.path" class="group">
          <div class="group-head" @click="toggle(group.path)">
            <el-icon><component :is="expanded.has(group.path) ? 'ArrowDown' : 'ArrowRight'" /></el-icon>
            <span class="group-name">{{ group.path }}</span>
            <span class="dim">（{{ group.urls.length }}）</span>
          </div>
          <div v-show="expanded.has(group.path)" class="url-list">
            <div v-for="url in group.urls" :key="url" class="url-row mono">{{ url }}</div>
          </div>
        </div>
      </div>
      <EmptyBox v-else description="未检出端点" :image-size="60" />

      <!-- 跟踪器 -->
      <div class="section-head">
        <span class="section-title">跟踪器</span>
        <span class="section-sub">{{ trackers.length }} 个（MobSF 指纹识别）</span>
      </div>
      <div v-if="trackers.length" class="perm-wrap">
        <el-tag v-for="t in trackers" :key="t.id" type="warning" size="small">
          {{ t.subject || t.payload?.name || '未命名' }}
        </el-tag>
      </div>
      <div v-else class="dim">无</div>

      <!-- 导出组件：安全暴露面 -->
      <div class="section-head">
        <span class="section-title">导出组件</span>
        <span class="section-sub">{{ exported.length }} 个 —— 可被其他应用唤起，属暴露面</span>
      </div>
      <el-table v-if="exported.length" :data="exported" size="small" stripe max-height="300">
        <el-table-column label="组件" min-width="420">
          <template #default="{ row }">
            <span class="mono break-all">{{ row.payload?.component || row.subject }}</span>
          </template>
        </el-table-column>
        <template #empty><EmptyBox description="无导出组件" /></template>
      </el-table>
      <div v-else class="dim">无</div>

      <!-- 权限 -->
      <div class="section-head">
        <span class="section-title">权限</span>
        <span class="section-sub">{{ permissions.length }} 项</span>
      </div>
      <div v-if="permissions.length" class="perm-wrap">
        <el-tag v-for="p in permissions" :key="p.id" size="small" class="perm-tag">
          {{ p.payload?.permission || p.subject }}
        </el-tag>
      </div>
      <div v-else class="dim">无</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { taskApi } from '@/api/tasks'

const props = defineProps<{ taskId: number }>()

const loading = ref(false)
const observations = ref<any[]>([])
const expanded = ref(new Set<string>())

const byType = (t: string) => observations.value.filter(o => o.observation_type === t)
const trackers = computed(() => byType('security.tracker'))
const exported = computed(() => byType('security.exported_component'))
const permissions = computed(() => byType('security.permission'))
const endpoints = computed(() => byType('security.endpoint'))
const hasAny = computed(() => observations.value.length > 0)

/**
 * MobSF 的端点 payload 与其他引擎不同：`url` 是对象套数组
 * `{path: "Android String Resource", urls: [...]}`，不是字符串。
 * 这里按 path 分组并把 URL 去重——同一来源的几十条 URL 平铺没有意义。
 */
const endpointGroups = computed(() => {
  const groups = new Map<string, Set<string>>()
  for (const o of endpoints.value) {
    const payload = o.payload || {}
    const urlField = payload.url
    if (urlField && typeof urlField === 'object') {
      const path = urlField.path || '未标注来源'
      if (!groups.has(path)) groups.set(path, new Set())
      for (const u of urlField.urls || []) groups.get(path)!.add(u)
    } else if (typeof urlField === 'string') {
      if (!groups.has('未标注来源')) groups.set('未标注来源', new Set())
      groups.get('未标注来源')!.add(urlField)
    } else if (o.subject) {
      if (!groups.has('未标注来源')) groups.set('未标注来源', new Set())
      groups.get('未标注来源')!.add(o.subject)
    }
  }
  return [...groups.entries()]
    .map(([path, urls]) => ({ path, urls: [...urls].sort() }))
    .sort((a, b) => b.urls.length - a.urls.length)
})

const endpointCount = computed(() =>
  endpointGroups.value.reduce((sum, g) => sum + g.urls.length, 0))

function toggle(path: string) {
  const next = new Set(expanded.value)
  next.has(path) ? next.delete(path) : next.add(path)
  expanded.value = next
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    const res = await taskApi.observations(props.taskId, { engine_type: 'mobsf', page_size: 5000 })
    observations.value = res.data?.items || []
    // 默认展开最大的那组，否则一片折叠看不出有没有数据
    const first = endpointGroups.value[0]?.path
    if (first) expanded.value = new Set([first])
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.taskId, load)
</script>

<style scoped>
.engine-panel { font-size: 13px; }
.section-head { display: flex; align-items: baseline; gap: 10px; margin: 18px 0 8px; }
.section-head:first-child { margin-top: 0; }
.section-title { font-weight: 600; font-size: 14px; }
.section-sub { color: #6B7A99; font-size: 12px; }
.group-list { border: 1px solid #EEF1F6; border-radius: 4px; }
.group + .group { border-top: 1px solid #EEF1F6; }
.group-head { display: flex; align-items: center; gap: 6px; padding: 6px 10px; cursor: pointer; }
.group-head:hover { background: #FAFBFD; }
.group-name { font-weight: 500; }
.url-list { padding: 0 10px 8px 30px; }
.url-row { color: #6B7A99; word-break: break-all; }
.perm-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
.dim { color: #6B7A99; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.break-all { word-break: break-all; }
</style>
