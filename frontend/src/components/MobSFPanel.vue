<template>
  <div class="engine-panel" v-loading="loading">
    <EmptyBox v-if="!hasAny" description="本任务未启用 MobSF，或该引擎未产出结果" />

    <template v-else>
      <!-- 端点：MobSF 的主体。按**域名**分组——它自带的 path 是内部产物路径
           （aptool_out/lib/.../libBaiduMapSDK.so），分组后看不出「这个应用在和谁通信」，
           而且同一来源能塞进 40 条混杂字符串 -->
      <div class="section-head">
        <span class="section-title">端点</span>
        <span class="section-sub">
          去重后 {{ endpointCount }} 条，归为 {{ domainGroups.length }} 个域名
        </span>
      </div>
      <div v-if="domainGroups.length" class="group-list">
        <div v-for="group in domainGroups" :key="group.host" class="group">
          <div class="group-head" @click="toggle(group.host)">
            <el-icon><component :is="expanded.has(group.host) ? ArrowDown : ArrowRight" /></el-icon>
            <span class="group-name mono">{{ group.host }}</span>
            <span class="dim">{{ group.urls.length }} 条</span>
          </div>
          <div v-show="expanded.has(group.host)" class="url-list">
            <div v-for="u in group.urls" :key="u" class="url-row mono">{{ u }}</div>
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
import { ArrowDown, ArrowRight } from '@element-plus/icons-vue'
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
 * 端点按域名分组。
 *
 * MobSF 的 payload 形状与其他引擎不同：`url` 是对象套数组
 * `{path: "Android String Resource", urls: [...]}`。按它给的 path 分组没有信息量
 * （那是内部产物路径），而按域名分组才回答「这个应用在和谁通信」。
 * 顺带把明显不是端点的抽取噪音（`Data:MergeLines...` 这类无协议头字符串）单列一组。
 */
const NOT_URL_HOST = '非 URL 字符串（抽取噪音）'

function hostOf(raw: string): string {
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw)
  if (!withScheme) return NOT_URL_HOST
  const rest = raw.replace(/^[a-z][a-z0-9+.-]*:\/\//i, '')
  const host = rest.split(/[/?#]/)[0].split('@').pop() || ''
  return host.replace(/:[0-9]+$/, '') || NOT_URL_HOST
}

const domainGroups = computed(() => {
  const urls = new Set<string>()
  for (const o of endpoints.value) {
    const payload = o.payload || {}
    const urlField = payload.url
    if (urlField && typeof urlField === 'object') {
      for (const u of urlField.urls || []) urls.add(u)
    } else if (typeof urlField === 'string') {
      urls.add(urlField)
    } else if (o.subject) {
      urls.add(o.subject)
    }
  }
  const groups = new Map<string, Set<string>>()
  for (const u of urls) {
    const host = hostOf(u)
    if (!groups.has(host)) groups.set(host, new Set())
    groups.get(host)!.add(u)
  }
  return [...groups.entries()]
    .map(([host, list]) => ({ host, urls: [...list].sort() }))
    .sort((a, b) => b.urls.length - a.urls.length)
})

const endpointCount = computed(() =>
  domainGroups.value.reduce((sum, g) => sum + g.urls.length, 0))

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
    const first = domainGroups.value[0]?.host
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
