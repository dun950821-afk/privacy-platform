<template>
  <div class="page-container" v-loading="loading">
    <!-- 页头 -->
    <PageHeader title="检测报告" :subtitle="headerSubtitle">
      <StatusTag v-if="task.status" :value="task.status" :map="TASK_STATUS" size="default" />
      <StatusTag v-if="isDegraded" value="DEGRADED" :map="ANALYSIS_COVERAGE" size="default" />
      <el-button :icon="ArrowLeft" @click="router.push(`/tasks/${taskId}`)">返回</el-button>
    </PageHeader>

    <!-- 分析没覆盖到应用时，本报告的任何「无风险」表述都不成立 -->
    <el-alert v-if="isDegraded" type="error" :closable="false" show-icon class="mb16"
      title="本次分析未覆盖应用代码，本报告不能用于判断是否存在风险"
      :description="degradedReason" />

    <el-tabs v-model="activeTab">
      <!-- ① 概览 -->
      <el-tab-pane label="概览" name="overview">
        <div class="stat-grid">
          <StatCard title="高风险" :value="riskCounts.high" :icon="Warning" color="#D03050" />
          <StatCard title="中风险" :value="riskCounts.medium" :icon="Warning" color="#F0A020" />
          <StatCard title="低风险" :value="riskCounts.low" :icon="Warning" color="#6B7A99" />
          <StatCard title="待确认" :value="riskCounts.needs_review" :icon="Warning" color="#2B5AED" />
        </div>

        <el-card shadow="never" class="mb16">
          <template #header><span class="card-title">各引擎产出</span></template>
          <div class="engine-summary">
            <div v-for="e in engineChapters" :key="e.type" class="engine-summary-item">
              <div class="es-name">{{ e.name }}</div>
              <div class="es-role">{{ e.role }}</div>
              <div class="es-metrics">
                <span v-for="m in e.metrics" :key="m.label" class="es-metric">
                  {{ m.label }} <b>{{ m.value }}</b>
                </span>
              </div>
            </div>
          </div>
          <EmptyBox v-if="!engineChapters.length" description="本次未启用任何引擎" :image-size="60" />
        </el-card>

        <el-card shadow="never" class="mb16">
          <template #header><span class="card-title">检测覆盖</span></template>
          <el-table :data="engines" size="small" stripe>
            <el-table-column label="引擎" min-width="160">
              <template #default="{ row }">{{ row.engine_name || row.engine_type || '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="EXEC_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="阶段" min-width="150">
              <template #default="{ row }">
                <span class="mono">{{ row.stage_message || row.stage || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="100">
              <template #default="{ row }">{{ fmtDuration(row.duration_ms) }}</template>
            </el-table-column>
            <el-table-column label="产出" width="150">
              <template #default="{ row }">
                事件 {{ row.event_count ?? 0 }} / 证据 {{ row.artifact_count ?? 0 }}
              </template>
            </el-table-column>
            <el-table-column label="错误" min-width="170" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.error_code || row.error_message" class="error-text">
                  {{ row.error_code || row.error_message }}
                </span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无引擎执行记录" /></template>
          </el-table>
        </el-card>

        <el-card shadow="never">
          <template #header><span class="card-title">重点发现</span></template>
          <ul v-if="platformFindings.length" class="highlight-list">
            <li v-for="f in platformFindings" :key="f.id">{{ f.title }}</li>
          </ul>
          <EmptyBox v-else description="暂无平台风险结论" />
        </el-card>
      </el-tab-pane>

      <!-- ② 风险 -->
      <el-tab-pane :label="`风险 (${platformFindings.length})`" name="risk">
        <el-card shadow="never" class="mb16">
          <template #header><span class="card-title">平台风险结论</span></template>
          <el-table :data="platformFindings" size="small" stripe>
            <el-table-column prop="title" label="风险" min-width="240" show-overflow-tooltip />
            <el-table-column prop="category" label="类别" width="110" />
            <el-table-column label="严重性" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.severity" :map="SEVERITY" />
              </template>
            </el-table-column>
            <el-table-column label="研判状态" width="110">
              <template #default="{ row }">{{ triageLabel(row.triage_status) }}</template>
            </el-table-column>
            <el-table-column label="证据来源" width="100" align="center">
              <template #default="{ row }">{{ row.observation_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="标准映射" min-width="200">
              <template #default="{ row }">
                <el-tag v-for="id in row.maswe_ids || []" :key="id" size="small" effect="plain" class="info-tag">{{ id }}</el-tag>
                <span v-if="!(row.maswe_ids || []).length">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="recommendation" label="整改建议" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.recommendation || '-' }}</template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无平台风险结论" /></template>
          </el-table>
        </el-card>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-card shadow="never">
              <template #header><span class="card-title">严重度分布</span></template>
              <VChart v-if="severityChartData.length" :option="severityOption" height="260px" />
              <EmptyBox v-else :description="isDegraded ? '本次分析未生效，不能据此判断' : '未发现风险'" />
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never">
              <template #header><span class="card-title">事件类型分布</span></template>
              <VChart v-if="eventChartData.length" :option="eventOption" height="260px" />
              <EmptyBox v-else description="暂无事件数据" />
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never">
              <template #header><span class="card-title">组件类型分布</span></template>
              <VChart v-if="componentChartData.length" :option="componentOption" height="260px" />
              <EmptyBox v-else description="暂无组件数据" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 分引擎结果：复用工作台那套面板；报告是交付物，按引擎分章、指标在前、明细默认展开 -->
      <el-tab-pane label="分引擎结果" name="engines">
        <el-alert v-if="leadCount" type="info" :closable="false" show-icon class="mb16"
          :title="`另有 ${leadCount} 条引擎判定为弱点的线索未经平台核实，未列入本报告结论；详见工作台「未核实线索」`" />

        <el-card v-for="e in engineChapters" :key="e.type" shadow="never" class="chapter-card">
          <template #header>
            <div class="chapter-head">
              <span class="chapter-name">{{ e.name }}</span>
              <span class="chapter-role">{{ e.role }}</span>
              <div class="chapter-metrics">
                <el-tag v-for="m in e.metrics" :key="m.label" size="small" effect="plain"
                        :type="m.value ? 'primary' : 'info'">
                  {{ m.label }} <b>{{ m.value }}</b>
                </el-tag>
              </div>
            </div>
          </template>
          <AppSharkPanel v-if="e.type === 'appshark'" :task-id="taskId" />
          <AndroguardPanel v-else-if="e.type === 'androguard'" :task-id="taskId"
                           :execution-summary="e.resultSummary" />
          <MobSFPanel v-else :task-id="taskId" />
        </el-card>
      </el-tab-pane>


      <!-- ⑥ 证据 -->
      <el-tab-pane :label="`证据 (${artifacts.length})`" name="evidence">
        <el-card shadow="never" class="mb16">
          <template #header><span class="card-title">原始产物</span></template>
          <el-table :data="artifacts" size="small" stripe>
            <el-table-column prop="execution_id" label="执行" width="90" align="center" />
            <el-table-column prop="artifact_type" label="类型" width="140" />
            <el-table-column label="存储" min-width="280" show-overflow-tooltip>
              <template #default="{ row }"><span class="mono">{{ row.artifact_uri }}</span></template>
            </el-table-column>
            <el-table-column label="大小" width="100" align="right">
              <template #default="{ row }">{{ fmtSize(row.size) }}</template>
            </el-table-column>
            <el-table-column label="SHA256" min-width="200" show-overflow-tooltip>
              <template #default="{ row }"><span class="mono">{{ row.sha256 }}</span></template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无原始产物" /></template>
          </el-table>
        </el-card>

        <el-card shadow="never">
          <template #header><span class="card-title">检测引擎执行</span></template>
          <el-table :data="engines" size="small" stripe>
            <el-table-column prop="engine_name" label="引擎" min-width="130">
              <template #default="{ row }">{{ row.engine_name || row.engine_type || '-' }}</template>
            </el-table-column>
            <el-table-column prop="engine_version" label="版本" width="100">
              <template #default="{ row }">{{ row.engine_version || '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="EXEC_STATUS" />
              </template>
            </el-table-column>
            <el-table-column prop="event_count" label="事件数" width="90" align="center">
              <template #default="{ row }">{{ row.event_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column prop="artifact_count" label="产出数" width="90" align="center">
              <template #default="{ row }">{{ row.artifact_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="耗时" width="100">
              <template #default="{ row }">{{ fmtDuration(row.duration_ms) }}</template>
            </el-table-column>
            <el-table-column prop="error_message" label="错误信息" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无引擎执行记录" /></template>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { ArrowLeft, Warning } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatCard from '@/components/StatCard.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import VChart from '@/components/VChart.vue'
import AppSharkPanel from '@/components/AppSharkPanel.vue'
import AndroguardPanel from '@/components/AndroguardPanel.vue'
import MobSFPanel from '@/components/MobSFPanel.vue'
import { taskApi } from '@/api/tasks'
import { fmtSize, fmtDateTime, fmtDuration } from '@/utils/format'
import {
  dictLabel, TASK_STATUS, EXEC_STATUS, SEVERITY, EVENT_TYPE, DETECTION_TYPE, SENSITIVITY,
  ANALYSIS_COVERAGE,
} from '@/utils/dict'

const route = useRoute()
const router = useRouter()
const taskId = Number(route.params.id)

const loading = ref(true)
const report = ref<any>({})
const activeTab = ref('overview')
const platformFindings = ref<any[]>([])
const observations = ref<any[]>([])
const artifacts = ref<any[]>([])

const task = computed<any>(() => report.value.task || {})
const isDegraded = computed(() => task.value.analysis_coverage === 'DEGRADED')
const degradedReason = computed(() => {
  const detail = task.value.coverage_detail?.artifact_detail || {}
  if (detail.criterion === 'component_classes_all_missing') {
    return `依据：manifest 声明的 ${detail.component_class_total} 个组件类，在 DEX 声明的 `
      + `${detail.class_count} 个类里一个都找不到——应用代码不在 DEX 中（加固/壳）。`
  }
  return '部分引擎未能分析到应用代码，详见任务详情的引擎执行记录。'
})
const app = computed<any>(() => report.value.app || {})
const basicInfo = computed<Record<string, any>>(() => report.value.basic_info || {})
const engines = computed<any[]>(() => report.value.engines || [])
const components = computed<any>(() => report.value.components || {})
interface PermDetail { name: string; capability?: string; risk_level?: string; category?: string }
const permissions = computed<{ declared: PermDetail[]; sensitive: PermDetail[] }>(() => ({
  declared: report.value.permissions?.declared || [],
  sensitive: report.value.permissions?.sensitive || [],
}))
const eventsByType = computed<Record<string, number>>(() => report.value.events_by_type || {})
const dataFlows = computed<any[]>(() => report.value.data_flows || [])

/** 各引擎的角色一句话说明：报告读者未必知道每个引擎负责什么 */
const ENGINE_ROLES: Record<string, string> = {
  appshark: '污点分析：source→sink 数据流与敏感 API 调用',
  androguard: 'APK 解析：应用信息、组件、权限、代码规模',
  mobsf: '静态扫描：第三方与暴露面（端点/跟踪器/导出组件）',
}

/** 引擎章节：名称 + 角色 + 关键指标 + 明细（复用工作台面板） */
const engineChapters = computed(() => {
  const queue = engineQueue.value
  const ran = new Set(queue.map((i: any) => i.engine_type))
  const summary = (type: string) => queue.find((i: any) => i.engine_type === type)?.result_summary || {}
  const n = (type: string, key: string) => engineStats.value[type]?.[key] ?? 0
  const chapters = [
    { type: 'appshark', name: 'AppShark', role: ENGINE_ROLES.appshark, resultSummary: summary('appshark'),
      enabled: ran.has('appshark'),
      metrics: [
        { label: '数据流', value: n('appshark', 'dataflow.privacy') },
        { label: '敏感 API 调用', value: n('appshark', 'security.sensitive_api') },
        { label: '声明权限', value: n('appshark', 'fact.permission') },
      ] },
    { type: 'androguard', name: 'Androguard', role: ENGINE_ROLES.androguard, resultSummary: summary('androguard'),
      enabled: ran.has('androguard'),
      metrics: [
        { label: '组件', value: summary('androguard').component_class_total ?? n('androguard', 'fact.component') },
        { label: '敏感权限', value: n('androguard', 'fact.sensitive_permission') },
        { label: 'DEX 类', value: summary('androguard').class_count ?? '—' },
        { label: 'DEX 方法', value: summary('androguard').method_count ?? '—' },
      ] },
    { type: 'mobsf', name: 'MobSF', role: ENGINE_ROLES.mobsf, resultSummary: summary('mobsf'),
      enabled: ran.has('mobsf'),
      metrics: [
        { label: '端点', value: n('mobsf', 'security.endpoint') },
        { label: '跟踪器', value: n('mobsf', 'security.tracker') },
        { label: '导出组件', value: n('mobsf', 'security.exported_component') },
        { label: '权限', value: n('mobsf', 'security.permission') },
      ] },
  ]
  return chapters.filter(c => c.enabled)
})

const engineQueue = ref<any[]>([])
const engineStats = ref<Record<string, Record<string, number>>>({})

/** 各引擎按观察类型计数：报告的指标要与本任务实际展示的内容一致 */
async function loadEngineStats() {
  const spec: Record<string, string[]> = {
    appshark: ['dataflow.privacy', 'security.sensitive_api', 'fact.permission'],
    androguard: ['fact.component', 'fact.sensitive_permission'],
    mobsf: ['security.endpoint', 'security.tracker', 'security.exported_component', 'security.permission'],
  }
  const out: Record<string, Record<string, number>> = {}
  await Promise.all(Object.entries(spec).map(async ([engine, types]) => {
    const counts: Record<string, number> = {}
    await Promise.all(types.map(async (t) => {
      try {
        const res = await taskApi.observations(taskId, { engine_type: engine, observation_type: t, page_size: 1 })
        counts[t] = res.data?.total || 0
      } catch { counts[t] = 0 }
    }))
    out[engine] = counts
  }))
  engineStats.value = out
}
const leadCount = ref(0)

/** 报告只统计「引擎判定为弱点但未经平台核实」的条数，不列条目（那是工作台的事） */
async function loadLeadCount() {
  try {
    const res = await taskApi.observations(taskId, {
      result_semantics: 'supporting_evidence', observation_type: 'security.other', page_size: 1,
    })
    leadCount.value = res.data?.total || 0
  } catch {
    leadCount.value = 0
  }
}
const sensitiveApis = computed<any[]>(() => report.value.sensitive_apis || [])
const appshark = computed<any>(() => report.value.appshark_overview || null)
const sdk = computed<any>(() => ({
  identified: report.value.sdk?.identified || [],
  unidentified: report.value.sdk?.unidentified || [],
  identified_count: report.value.sdk?.identified_count ?? 0,
  unidentified_count: report.value.sdk?.unidentified_count ?? 0,
}))
const findings = computed<any>(() => report.value.findings || {})

const riskCounts = computed(() => {
  const counts = { high: 0, medium: 0, low: 0, needs_review: 0 }
  for (const f of platformFindings.value) {
    const severity = String(f.severity || '').toLowerCase()
    if (severity in counts) counts[severity as keyof typeof counts] += 1
    if (f.triage_status === 'needs_review') counts.needs_review += 1
  }
  return counts
})

const dataflowObservations = computed(() =>
  observations.value.filter(o => o.observation_type === 'dataflow.privacy'))
const factObservations = computed(() =>
  observations.value.filter(o => String(o.observation_type).startsWith('fact.')))

const TRIAGE_LABELS: Record<string, string> = {
  needs_review: '待确认', confirmed: '已确认', false_positive: '误报',
  accepted: '已接受', suppressed: '已抑制', fixed: '已修复',
}
function triageLabel(status: string) {
  return TRIAGE_LABELS[status] || status || '-'
}

function sourceOf(row: any) {
  const source = row.payload?.source
  return Array.isArray(source) ? source.join(' → ') : (source || '-')
}
function sinkOf(row: any) {
  const sink = row.payload?.sink
  return Array.isArray(sink) ? sink.join(' → ') : (sink || '-')
}

const headerSubtitle = computed(() => {
  const parts = [
    task.value.task_code,
    [app.value.name, app.value.version_name].filter(Boolean).join(' '),
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : undefined
})

/** basic_info 中 app 字段未覆盖的补充键 */
const basicInfoExtra = computed(() => {
  const covered = new Set([
    'app_name', 'name', 'package_name', 'version_name', 'version_code',
    'sha256', 'file_size', 'min_sdk', 'target_sdk',
  ])
  return Object.entries(basicInfo.value)
    .filter(([k, v]) => !covered.has(k) && v !== null && v !== undefined && v !== '')
    .map(([key, v]) => ({
      key,
      value: typeof v === 'object' ? JSON.stringify(v) : String(v),
    }))
})

// ============ 图表 ============
const COMPONENT_TYPE_LABEL: Record<string, string> = {
  ACTIVITY: '活动 (Activity)',
  SERVICE: '服务 (Service)',
  RECEIVER: '广播接收器 (Receiver)',
  PROVIDER: '内容提供者 (Provider)',
}

const componentChartData = computed(() =>
  Object.entries(components.value.by_type || {})
    .map(([k, v]) => ({ name: COMPONENT_TYPE_LABEL[k] || k, value: Number(v) || 0 }))
    .filter(d => d.value > 0))

const componentOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: ['40%', '65%'],
    center: ['50%', '45%'],
    label: { formatter: '{b}: {c}' },
    data: componentChartData.value,
  }],
}))

const eventChartData = computed(() =>
  Object.entries(eventsByType.value)
    .filter(([k]) => k !== 'static_basic_info')
    .map(([k, v]) => ({ name: dictLabel(EVENT_TYPE, k), value: Number(v) || 0 }))
    .filter(d => d.value > 0)
    .sort((a, b) => a.value - b.value))

const eventOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 8, right: 30, top: 8, bottom: 8, containLabel: true },
  xAxis: { type: 'value' },
  yAxis: { type: 'category', data: eventChartData.value.map(d => d.name) },
  series: [{
    type: 'bar',
    barMaxWidth: 18,
    itemStyle: { color: '#2B5AED', borderRadius: [0, 4, 4, 0] },
    label: { show: true, position: 'right' },
    data: eventChartData.value.map(d => d.value),
  }],
}))

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#8B0A2E',
  high: '#D03050',
  medium: '#F0A020',
  low: '#6B7A99',
}

const severityChartData = computed(() =>
  Object.entries(findings.value.by_severity || {})
    .map(([k, v]) => ({
      name: dictLabel(SEVERITY, k),
      value: Number(v) || 0,
      itemStyle: { color: SEVERITY_COLOR[k.toLowerCase()] || '#6B7A99' },
    }))
    .filter(d => d.value > 0))

const severityOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: ['40%', '65%'],
    center: ['50%', '45%'],
    label: { formatter: '{b}: {c}' },
    data: severityChartData.value,
  }],
}))

// ============ 敏感 API 与数据流 ============
const hasFlowData = computed(() =>
  dataFlows.value.length > 0 || sensitiveApis.value.length > 0 || !!appshark.value)

const appsharkSummary = computed(() => {
  const a = appshark.value
  if (!a) return ''
  const pms = a.process_method_statistics || {}
  const parts = [
    `AppShark 分析概要：规则 ${a.rules?.length ?? 0} 条`,
    `发现漏洞/风险 ${a.vulnerability_count ?? 0} 个`,
    `分析规模 ${pms.availableClasses ?? '-'} 类 / ${pms.availableMethods ?? '-'} 方法`,
  ]
  if (a.note) parts.push(a.note)
  return parts.join('；')
})

// ============ 数据加载 ============
async function load() {
  loading.value = true
  try {
    const res: any = await taskApi.reportOverview(taskId)
    report.value = res.data || {}
    const [findingsRes, observationsRes, artifactsRes, taskRes] = await Promise.allSettled([
      taskApi.platformFindings(taskId),
      taskApi.observations(taskId, { page_size: 200 }),
      taskApi.artifacts(taskId),
      taskApi.get(taskId),
    ])
    if (taskRes.status === 'fulfilled') {
      engineQueue.value = taskRes.value.data?.engine_queue?.items || []
    }
    if (findingsRes.status === 'fulfilled') platformFindings.value = findingsRes.value.data?.items || []
    if (observationsRes.status === 'fulfilled') observations.value = observationsRes.value.data?.items || []
    if (artifactsRes.status === 'fulfilled') artifacts.value = artifactsRes.value.data || []
    await Promise.all([loadLeadCount(), loadEngineStats()])
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
.chapter-card { margin-bottom: 14px; }
.chapter-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.chapter-name { font-size: 15px; font-weight: 600; }
.chapter-role { color: #6B7A99; font-size: 12px; }
.chapter-metrics { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; }
.engine-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.engine-summary-item { border: 1px solid #EEF1F6; border-radius: 6px; padding: 10px 12px; background: #FAFBFD; }
.es-name { font-weight: 600; }
.es-role { color: #6B7A99; font-size: 12px; margin: 2px 0 6px; }
.es-metrics { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: #6B7A99; }
.es-metric b { color: #1F2A44; }
.card-title { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.mono { font-family: monospace; font-size: 12px; }
.error-text { color: var(--el-color-danger); }
.no-data { color: var(--el-text-color-secondary); }
.sub-title {
  margin: 4px 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.perm-list { margin-bottom: 12px; }
.perm-item {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 5px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.perm-item:last-child { border-bottom: none; }
.perm-name { font-size: 12px; flex-shrink: 0; }
.perm-name.danger { color: var(--el-color-danger); }
.perm-cap { font-size: 12px; color: var(--el-text-color-secondary); }
.info-tag { margin-right: 4px; }
.sdk-card :deep(.el-card__body) { padding-top: 12px; }
.highlight-list { margin: 0; padding-left: 18px; }
.highlight-list li { padding: 3px 0; color: var(--el-text-color-regular); }
.evidence-note {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
