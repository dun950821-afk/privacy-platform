<template>
  <div class="workspace">
    <!-- ① 平台结论：跨引擎的，Direct Finding 与证据增强 -->
    <el-card shadow="never" class="block">
      <template #header>
        <div class="block-head">
          <span class="block-title">平台结论</span>
          <span class="block-count">{{ findings.length }}</span>
          <span class="block-sub">由具备完整语义的观察直接形成，或经跨引擎证据增强</span>
        </div>
      </template>
      <el-table v-if="findings.length" :data="findings" size="small" stripe>
        <el-table-column label="结论" min-width="300">
          <template #default="{ row }">
            <div class="mono finding-code">{{ row.finding_code }}</div>
            <div class="finding-title">{{ row.title }}</div>
          </template>
        </el-table-column>
        <el-table-column label="严重性" width="90">
          <template #default="{ row }"><StatusTag :value="row.severity" :map="SEVERITY" /></template>
        </el-table-column>
        <el-table-column label="置信度" width="110">
          <template #default="{ row }"><StatusTag :value="row.confidence" :map="CONFIDENCE" /></template>
        </el-table-column>
        <el-table-column label="依据" min-width="240">
          <template #default="{ row }">
            <span class="dim">{{ evidenceText(row) }}</span>
          </template>
        </el-table-column>
        <template #empty><EmptyBox description="无平台结论" /></template>
      </el-table>
      <EmptyBox v-else description="本次未形成平台结论" :image-size="60" />
    </el-card>

    <!-- ② 未核实线索 -->
    <el-card shadow="never" class="block">
      <UnverifiedLeadsPanel :task-id="taskId" />
    </el-card>

    <!-- ③ 引擎原始结果：按各自输出特点分区 -->
    <el-card shadow="never" class="block">
      <template #header>
        <div class="block-head">
          <span class="block-title">引擎原始结果</span>
          <span class="block-sub">按各引擎自己的输出形态展示</span>
        </div>
      </template>
      <el-tabs v-model="activeEngine" class="engine-tabs">
        <el-tab-pane v-for="e in engines" :key="e.type" :name="e.type" :disabled="!e.enabled">
          <template #label>
            <span :class="{ 'engine-off': !e.enabled }">
              {{ e.name }}<span v-if="e.count !== null" class="dim"> ({{ e.count }})</span>
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <div v-if="!engines.some(e => e.enabled)" class="dim">
        本次任务未启用任何可展示结果的引擎
      </div>
      <AppSharkPanel v-else-if="activeEngine === 'appshark'" :task-id="taskId" />
      <AndroguardPanel v-else-if="activeEngine === 'androguard'" :task-id="taskId"
                       :execution-summary="androguardSummary" />
      <MobSFPanel v-else-if="activeEngine === 'mobsf'" :task-id="taskId" />
    </el-card>

    <!-- 原始事件：降为下钻视图，不再是并列的一等页面 -->
    <el-card shadow="never" class="block">
      <el-collapse v-model="rawOpen">
        <el-collapse-item name="raw">
          <template #title>
            <span class="block-title">原始事件流</span>
            <span class="block-sub">排查与核对管道用；日常阅读看上面的分区即可</span>
          </template>
          <div class="raw-toolbar">
            <el-select v-model="eventTypeFilter" placeholder="事件类型" clearable size="small"
                       style="width: 200px" @change="loadEvents">
              <el-option v-for="t in EVENT_TYPE_OPTIONS" :key="t.value"
                         :label="t.label" :value="t.value" />
            </el-select>
            <el-input v-model="eventKeyword" placeholder="搜 API / 调用方" clearable size="small"
                      style="width: 240px" @change="loadEvents" />
            <span class="dim">共 {{ eventTotal }} 条</span>
          </div>
          <el-table :data="events" size="small" stripe v-loading="loadingEvents" max-height="420"
                    :row-class-name="eventRowClass">
            <el-table-column label="类型" width="170">
              <template #default="{ row }">
                <StatusTag :value="row.event_type" :map="EVENT_TYPE" />
              </template>
            </el-table-column>
            <el-table-column label="API / 组件" min-width="300">
              <template #default="{ row }"><span class="mono break-all">{{ row.api || '-' }}</span></template>
            </el-table-column>
            <el-table-column label="调用方" min-width="280" show-overflow-tooltip>
              <template #default="{ row }"><span class="mono dim">{{ row.caller || '-' }}</span></template>
            </el-table-column>
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ fmtDateTimeFull(row.timestamp) }}</template>
            </el-table-column>
            <template #empty><EmptyBox description="无事件" /></template>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyBox from '@/components/EmptyBox.vue'
import StatusTag from '@/components/StatusTag.vue'
import AppSharkPanel from '@/components/AppSharkPanel.vue'
import AndroguardPanel from '@/components/AndroguardPanel.vue'
import MobSFPanel from '@/components/MobSFPanel.vue'
import UnverifiedLeadsPanel from '@/components/UnverifiedLeadsPanel.vue'
import { taskApi } from '@/api/tasks'
import { fmtDateTimeFull } from '@/utils/format'
import { CONFIDENCE, EVENT_TYPE, SEVERITY } from '@/utils/dict'

const props = defineProps<{
  taskId: number
  engineQueue?: any[]
  /** 从 SDK / 包簇抽屉跳进来时带上的定位条件：展开原始事件并高亮 */
  focus?: { sdkId?: number | null; keyword?: string } | null
}>()

const EVENT_TYPE_OPTIONS = [
  { value: 'static_data_flow', label: '数据流' },
  { value: 'static_sensitive_api', label: '敏感 API 调用' },
  { value: 'static_component', label: '组件' },
  { value: 'static_permission', label: '声明权限' },
  { value: 'static_sensitive_permission', label: '敏感权限' },
  { value: 'static_tracker', label: '跟踪器' },
  { value: 'static_url', label: '端点' },
  { value: 'static_basic_info', label: '应用信息' },
]

const findings = ref<any[]>([])
const events = ref<any[]>([])
const eventTotal = ref(0)
const eventTypeFilter = ref('')
const eventKeyword = ref('')
const loadingEvents = ref(false)
const activeEngine = ref('appshark')
const rawOpen = ref<string[]>([])

/** 从 SDK / 包簇抽屉跳进来时的定位关键词 */
const focusKeyword = ref('')

function eventRowClass({ row }: { row: any }): string {
  return focusKeyword.value && row.api === focusKeyword.value ? 'focus-row' : ''
}

const engineCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const item of props.engineQueue || []) {
    counts.set(item.engine_type, item.event_count ?? 0)
  }
  return counts
})

const engines = computed(() => {
  const ran = new Set((props.engineQueue || []).map(i => i.engine_type))
  return [
    { type: 'appshark', name: 'AppShark', enabled: ran.has('appshark'), count: engineCounts.value.get('appshark') ?? null },
    { type: 'androguard', name: 'Androguard', enabled: ran.has('androguard'), count: engineCounts.value.get('androguard') ?? null },
    { type: 'mobsf', name: 'MobSF', enabled: ran.has('mobsf'), count: engineCounts.value.get('mobsf') ?? null },
  ]
})

const androguardSummary = computed(() =>
  (props.engineQueue || []).find(i => i.engine_type === 'androguard')?.result_summary || {})

function evidenceText(row: any) {
  const snapshot = row.rule_snapshot || {}
  if (snapshot.source === 'direct_finding') {
    const parts = [snapshot.provider_rule_id, snapshot.data_category, snapshot.sink_type]
      .filter(Boolean)
    return `直接结论：${parts.join(' · ') || row.finding_code}`
  }
  const enrichments = snapshot.enrichments || []
  if (enrichments.length) {
    const total = enrichments.reduce((s: number, e: any) => s + (e.evidence_observation_ids?.length || 0), 0)
    return `证据增强：+${total} 条同类目证据`
  }
  return row.correlation_rule_id ? '关联规则' : '—'
}

async function loadFindings() {
  const res = await taskApi.platformFindings(props.taskId)
  findings.value = res.data?.items || res.data || []
}

async function loadEvents() {
  if (!rawOpen.value.includes('raw')) return
  loadingEvents.value = true
  try {
    const res = await taskApi.events(props.taskId, {
      event_type: eventTypeFilter.value || undefined,
      keyword: eventKeyword.value || undefined,
      page_size: 200,
    })
    events.value = res.data?.items || []
    eventTotal.value = res.data?.total ?? events.value.length
  } finally {
    loadingEvents.value = false
  }
}

function pickDefaultEngine() {
  const first = engines.value.find(e => e.enabled)
  if (first) activeEngine.value = first.type
}

onMounted(async () => {
  pickDefaultEngine()
  await loadFindings()
})
watch(() => props.taskId, async () => {
  pickDefaultEngine()
  await loadFindings()
})
watch(rawOpen, loadEvents)

// SDK / 包簇抽屉里的「查看事件」：展开原始事件区并按条件定位
watch(() => props.focus, async (focus) => {
  if (!focus) return
  focusKeyword.value = focus.keyword || ''
  eventKeyword.value = focus.keyword || ''
  rawOpen.value = ['raw']
  await loadEvents()
}, { deep: true })
</script>

<style scoped>
.workspace { font-size: 13px; }
.block { margin-bottom: 14px; }
.block-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.block-title { font-weight: 600; font-size: 15px; }
.block-count {
  display: inline-block; min-width: 22px; padding: 0 6px; border-radius: 10px;
  background: #EEF1F6; color: #2B5AED; font-size: 12px; text-align: center; font-weight: 600;
}
.block-sub { color: #6B7A99; font-size: 12px; }
.finding-code { font-weight: 600; }
.finding-title { color: #6B7A99; font-size: 12px; }
.engine-tabs { margin-bottom: 6px; }
.engine-off { color: #B4BDCC; }
.raw-toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
.dim { color: #6B7A99; }
:deep(.focus-row) { background: #FFF7E6; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.break-all { word-break: break-all; }
</style>
