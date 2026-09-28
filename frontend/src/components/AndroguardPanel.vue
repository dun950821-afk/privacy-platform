<template>
  <div class="engine-panel" v-loading="loading">
    <!-- 应用档案：Androguard 的主体就是「这个应用是什么」，不是流水 -->
    <div class="section-head">
      <span class="section-title">应用档案</span>
      <span class="section-sub">包名/版本/SDK/签名，来自 manifest 解析</span>
    </div>
    <div class="fact-grid">
      <div v-for="item in appFacts" :key="item.label" class="fact-card">
        <div class="fact-label">{{ item.label }}</div>
        <div class="fact-value mono" :title="item.value">{{ item.value }}</div>
      </div>
    </div>

    <!-- DEX 统计：兼作「这次分析覆盖到多少」的提示 -->
    <div class="section-head">
      <span class="section-title">代码规模</span>
      <span class="section-sub">解析自 DEX 头部；组件类缺失是判断「分析有没有覆盖到应用」的依据</span>
    </div>
    <div class="fact-grid">
      <div v-for="item in dexStats" :key="item.label" class="fact-card">
        <div class="fact-label">{{ item.label }}</div>
        <div class="fact-value mono" :class="{ warn: item.warn }">{{ item.value }}</div>
      </div>
    </div>

    <!-- 组件：按类型分组，量最大但结构最规整 -->
    <div class="section-head">
      <span class="section-title">组件</span>
      <span class="section-sub">{{ components.length }} 个，按类型分组</span>
    </div>
    <div class="comp-toolbar">
      <el-radio-group v-model="componentType" size="small">
        <el-radio-button v-for="t in componentTypes" :key="t.type" :value="t.type">
          {{ t.label }} ({{ t.count }})
        </el-radio-button>
      </el-radio-group>
      <el-input v-model="componentKeyword" placeholder="搜索类名" clearable size="small"
                style="width: 220px" />
    </div>
    <el-table v-if="visibleComponents.length" :data="visibleComponents" size="small" stripe
              max-height="360">
      <el-table-column label="组件类" min-width="420">
        <template #default="{ row }"><span class="mono break-all">{{ row.subject }}</span></template>
      </el-table-column>
      <template #empty><EmptyBox description="没有匹配的组件" /></template>
    </el-table>
    <EmptyBox v-else description="没有匹配的组件" :image-size="60" />

    <!-- 权限：声明的与命中的分开 -->
    <div class="section-head">
      <span class="section-title">权限</span>
      <span class="section-sub">命中的敏感权限优先，声明权限单独列</span>
    </div>
    <div class="perm-block">
      <div class="perm-title">敏感权限（{{ sensitivePermissions.length }}）</div>
      <div v-if="sensitivePermissions.length" class="perm-wrap">
        <el-tag v-for="p in sensitivePermissions" :key="p.id" type="warning" size="small">
          {{ p.subject }} · {{ p.data_category || '未归类' }}
        </el-tag>
      </div>
      <div v-else class="dim">无</div>
    </div>
    <div class="perm-block">
      <div class="perm-title">声明权限（{{ declaredPermissions.length }}）</div>
      <div v-if="declaredPermissions.length" class="perm-wrap">
        <el-tag v-for="p in declaredPermissions" :key="p.id" size="small" class="perm-tag">
          {{ p.subject }}
        </el-tag>
      </div>
      <div v-else class="dim">无（该引擎只上报被判为危险的权限）</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { taskApi } from '@/api/tasks'

const props = defineProps<{ taskId: number; executionSummary?: Record<string, any> }>()

const loading = ref(false)
const observations = ref<any[]>([])
const componentType = ref('ACTIVITY')
const componentKeyword = ref('')

const TYPE_LABELS: Record<string, string> = {
  ACTIVITY: 'Activity', SERVICE: 'Service', RECEIVER: 'Receiver', PROVIDER: 'Provider',
}

const app = computed(() => observations.value.find(o => o.observation_type === 'fact.application'))
const components = computed(() => observations.value.filter(o => o.observation_type === 'fact.component'))
const sensitivePermissions = computed(() =>
  observations.value.filter(o => o.observation_type === 'fact.sensitive_permission'))
const declaredPermissions = computed(() =>
  observations.value.filter(o => o.observation_type === 'fact.permission'))

const appFacts = computed(() => {
  const p = app.value?.payload || {}
  return [
    { label: '包名', value: p.package_name || '—' },
    { label: '应用名', value: p.app_name || '—' },
    { label: '版本', value: p.version_name ? `${p.version_name}（${p.version_code ?? '-'}）` : '—' },
    { label: 'SDK', value: `min ${p.min_sdk ?? '-'} / target ${p.target_sdk ?? '-'}` },
    { label: 'APK 大小', value: p.file_size ? fmtSize(p.file_size) : '—' },
    { label: 'SHA256', value: p.sha256 ? `${p.sha256.slice(0, 16)}…` : '—' },
  ]
})

/** 代码规模 + 覆盖度线索：组件类全缺 = DEX 里没有应用代码 */
const dexStats = computed(() => {
  const s = props.executionSummary || {}
  const num = (v: any) => (v === null || v === undefined ? '—' : Number(v).toLocaleString())
  const total = s.component_class_total
  const missing = s.component_class_missing
  const allMissing = total > 0 && missing === total
  return [
    { label: 'DEX 声明类数', value: num(s.class_count) },
    { label: 'DEX 声明方法数', value: num(s.method_count) },
    { label: '组件类', value: total === undefined || total === null ? '—' : `${num(total)} 个` },
    { label: '组件类缺失', value: missing === undefined || missing === null ? '—' : `${num(missing)} 个`,
      warn: allMissing },
  ]
})

const componentTypes = computed(() => {
  const counts = new Map<string, number>()
  for (const c of components.value) {
    counts.set(c.payload?.type || c.data_type || 'OTHER',
               (counts.get(c.payload?.type || c.data_type || 'OTHER') || 0) + 1)
  }
  return [...counts.entries()]
    .map(([type, count]) => ({ type, count, label: TYPE_LABELS[type] || type }))
    .sort((a, b) => b.count - a.count)
})

const visibleComponents = computed(() => {
  const key = componentKeyword.value.trim().toLowerCase()
  return components.value.filter(c => {
    const type = c.payload?.type || c.data_type
    if (type !== componentType.value) return false
    return !key || (c.subject || '').toLowerCase().includes(key)
  })
})

function fmtSize(size: number) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${Math.round(size / 1024)} KB`
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    const res = await taskApi.observations(props.taskId, { engine_type: 'androguard', page_size: 5000 })
    observations.value = res.data?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  // 默认选中数量最多的组件类型，省一次点击
  const first = componentTypes.value[0]?.type
  if (first) componentType.value = first
})
watch(() => props.taskId, load)
watch(componentTypes, types => {
  if (types.length && !types.some(t => t.type === componentType.value)) {
    componentType.value = types[0].type
  }
})
</script>

<style scoped>
.engine-panel { font-size: 13px; }
.section-head { display: flex; align-items: baseline; gap: 10px; margin: 18px 0 8px; }
.section-head:first-child { margin-top: 0; }
.section-title { font-weight: 600; font-size: 14px; }
.section-sub { color: #6B7A99; font-size: 12px; }
.fact-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 8px; }
.fact-card { border: 1px solid #EEF1F6; border-radius: 4px; padding: 6px 10px; background: #FAFBFD; }
.fact-label { color: #6B7A99; font-size: 12px; }
.fact-value { word-break: break-all; }
.fact-value.warn { color: #C4361D; font-weight: 600; }
.comp-toolbar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.perm-block { margin-bottom: 10px; }
.perm-title { color: #6B7A99; font-size: 12px; margin-bottom: 4px; }
.perm-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
.dim { color: #6B7A99; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.break-all { word-break: break-all; }
</style>
