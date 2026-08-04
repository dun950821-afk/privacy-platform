<template>
  <div class="page-container" v-loading="loading">
    <!-- 页头 -->
    <PageHeader title="检测报告" :subtitle="headerSubtitle">
      <StatusTag v-if="task.status" :value="task.status" :map="TASK_STATUS" size="default" />
      <el-button :icon="ArrowLeft" @click="router.push(`/tasks/${taskId}`)">返回</el-button>
    </PageHeader>

    <!-- 概览统计 -->
    <div class="stat-grid">
      <StatCard title="检测组件总数" :value="components.total ?? 0" :icon="Grid" color="#2B5AED" />
      <StatCard title="声明权限（含敏感）"
                :value="`${permissions.declared.length} / ${permissions.sensitive.length} 敏感`"
                :icon="Key" color="#F0A020" />
      <StatCard title="已识别SDK / 未识别包簇"
                :value="`${sdk.identified_count ?? 0} / ${sdk.unidentified_count ?? 0}`"
                :icon="Box" color="#7B61FF" />
      <StatCard title="事件总数" :value="eventTotal" :icon="Histogram" color="#2080F0" />
      <StatCard title="问题数" :value="findings.total ?? 0" :icon="Warning"
                :color="findings.total ? '#D03050' : '#18A058'"
                :value-color="findings.total ? '#D03050' : undefined" />
      <StatCard title="证据数" :value="evidenceCount" :icon="Folder" color="#13C2C2" />
    </div>

    <!-- App 基础信息 -->
    <el-card shadow="never" class="mb16">
      <template #header><span class="card-title">App 基础信息</span></template>
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item label="App名称">{{ app.name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="包名">
          <span class="mono">{{ app.package_name || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="版本">
          {{ app.version_name || '-' }}（code {{ app.version_code ?? '-' }}）
        </el-descriptions-item>
        <el-descriptions-item label="文件大小">{{ fmtSize(app.file_size) }}</el-descriptions-item>
        <el-descriptions-item label="minSdk / targetSdk">
          {{ app.min_sdk ?? '-' }} / {{ app.target_sdk ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="检测类型">
          <StatusTag :value="task.detection_type" :map="DETECTION_TYPE" />
        </el-descriptions-item>
        <el-descriptions-item label="规则包版本">{{ task.rule_pack_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ fmtDateTime(task.started_at) }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ fmtDateTime(task.completed_at) }}</el-descriptions-item>
        <el-descriptions-item label="SHA256" :span="3">
          <span class="mono">{{ app.sha256 || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item v-for="item in basicInfoExtra" :key="item.key" :label="item.key">
          <span class="mono">{{ item.value }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 图表行 -->
    <el-row :gutter="16" class="mb16">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span class="card-title">组件类型分布</span></template>
          <VChart v-if="componentChartData.length" :option="componentOption" height="260px" />
          <EmptyBox v-else description="暂无组件数据" />
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
          <template #header><span class="card-title">问题严重度分布</span></template>
          <VChart v-if="severityChartData.length" :option="severityOption" height="260px" />
          <EmptyBox v-else description="未发现问题" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 权限明细 -->
    <el-card shadow="never" class="mb16">
      <template #header><span class="card-title">权限明细</span></template>
      <template v-if="permissions.sensitive.length || permissions.declared.length">
        <div class="sub-title">敏感权限（{{ permissions.sensitive.length }}）</div>
        <div class="perm-list">
          <div v-for="p in permissions.sensitive" :key="p.name" class="perm-item">
            <span class="mono perm-name danger">{{ p.name }}</span>
            <span class="perm-cap">{{ p.capability || '知识库未收录该权限' }}</span>
          </div>
          <span v-if="!permissions.sensitive.length" class="no-data">-</span>
        </div>
        <div class="sub-title">声明权限（{{ permissions.declared.length }}）</div>
        <div class="perm-list">
          <div v-for="p in permissions.declared" :key="p.name" class="perm-item">
            <span class="mono perm-name">{{ p.name }}</span>
            <span class="perm-cap">{{ p.capability || '知识库未收录该权限' }}</span>
          </div>
          <span v-if="!permissions.declared.length" class="no-data">-</span>
        </div>
      </template>
      <EmptyBox v-else description="暂无权限数据" />
    </el-card>

    <!-- SDK 识别 -->
    <el-row :gutter="16" class="mb16">
      <el-col :span="14">
        <el-card shadow="never" class="sdk-card">
          <template #header>
            <span class="card-title">已识别 SDK（{{ sdk.identified.length }}）</span>
          </template>
          <el-table :data="sdk.identified" size="small" stripe max-height="420">
            <el-table-column prop="sdk_name" label="SDK名称" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.sdk_name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="vendor" label="厂商" width="100" show-overflow-tooltip>
              <template #default="{ row }">{{ row.vendor || '-' }}</template>
            </el-table-column>
            <el-table-column prop="category" label="类别" width="110" show-overflow-tooltip>
              <template #default="{ row }">{{ row.category || '-' }}</template>
            </el-table-column>
            <el-table-column label="置信度" width="80">
              <template #default="{ row }">
                <StatusTag :value="row.confidence_level" :map="SENSITIVITY" />
              </template>
            </el-table-column>
            <el-table-column prop="total_score" label="得分" width="70" align="center">
              <template #default="{ row }">{{ row.total_score ?? '-' }}</template>
            </el-table-column>
            <el-table-column prop="evidence_count" label="证据数" width="80" align="center">
              <template #default="{ row }">{{ row.evidence_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="涉及信息" min-width="140">
              <template #default="{ row }">
                <template v-if="row.involved_info?.length">
                  <el-tag v-for="info in row.involved_info" :key="info" size="small"
                          effect="plain" class="info-tag">{{ info }}</el-tag>
                </template>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="敏感权限" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.sensitive_permission" type="danger" size="small">涉及</el-tag>
                <el-tag v-else type="info" size="small" effect="plain">否</el-tag>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="未识别到SDK" /></template>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never" class="sdk-card">
          <template #header>
            <span class="card-title">未识别包簇（{{ sdk.unidentified.length }}）</span>
          </template>
          <el-table :data="sdk.unidentified" size="small" stripe max-height="420">
            <el-table-column label="包前缀" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.package_prefix || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="class_count" label="类数量" width="90" align="center">
              <template #default="{ row }">{{ row.class_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="初步判断" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.guess_attr" size="small" effect="plain"
                        :type="row.guess_attr.includes('加固') ? 'danger'
                              : row.guess_attr.includes('自研') ? 'success' : 'info'">
                  {{ row.guess_attr }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="无未识别包簇" /></template>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 敏感 API 与数据流 -->
    <el-card v-if="hasFlowData" shadow="never" class="mb16">
      <template #header><span class="card-title">敏感 API 与数据流</span></template>
      <el-alert v-if="appshark" type="info" :closable="false" class="mb16"
                :title="appsharkSummary" />
      <el-row :gutter="16">
        <el-col :span="10">
          <div class="sub-title">数据流（{{ dataFlows.length }}）</div>
          <el-table :data="dataFlows" size="small" stripe max-height="380">
            <el-table-column prop="category" label="合规分类" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.category || '-' }}</template>
            </el-table-column>
            <el-table-column prop="rule" label="规则" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.rule || '-' }}</template>
            </el-table-column>
            <el-table-column prop="count" label="路径数" width="90" align="center">
              <template #default="{ row }">{{ row.count ?? 0 }}</template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无数据流" /></template>
          </el-table>
        </el-col>
        <el-col :span="14">
          <div class="sub-title">敏感 API（{{ sensitiveApis.length }}）</div>
          <el-table :data="sensitiveApis" size="small" stripe max-height="380">
            <el-table-column prop="category" label="分类" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.category || '-' }}</template>
            </el-table-column>
            <el-table-column prop="api" label="API" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.api || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="调用点数" width="90" align="center">
              <template #default="{ row }">{{ row.count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="调用方" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.callers?.length" class="mono">{{ row.callers.join('、') }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无敏感API" /></template>
          </el-table>
        </el-col>
      </el-row>
    </el-card>

    <!-- 检测引擎执行 -->
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
        <el-table-column prop="event_count" label="产出事件数" width="110" align="center">
          <template #default="{ row }">{{ row.event_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column prop="artifact_count" label="证据数" width="90" align="center">
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import {
  ArrowLeft, Grid, Key, Box, Histogram, Warning, Folder,
} from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatCard from '@/components/StatCard.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import VChart from '@/components/VChart.vue'
import { taskApi } from '@/api/tasks'
import { fmtSize, fmtDateTime, fmtDuration } from '@/utils/format'
import {
  dictLabel, TASK_STATUS, EXEC_STATUS, SEVERITY, EVENT_TYPE, DETECTION_TYPE, SENSITIVITY,
} from '@/utils/dict'

const route = useRoute()
const router = useRouter()
const taskId = Number(route.params.id)

const loading = ref(true)
const report = ref<any>({})

const task = computed<any>(() => report.value.task || {})
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
const eventTotal = computed<number>(() => report.value.event_total ?? 0)
const dataFlows = computed<any[]>(() => report.value.data_flows || [])
const sensitiveApis = computed<any[]>(() => report.value.sensitive_apis || [])
const appshark = computed<any>(() => report.value.appshark_overview || null)
const sdk = computed<any>(() => ({
  identified: report.value.sdk?.identified || [],
  unidentified: report.value.sdk?.unidentified || [],
  identified_count: report.value.sdk?.identified_count ?? 0,
  unidentified_count: report.value.sdk?.unidentified_count ?? 0,
}))
const findings = computed<any>(() => report.value.findings || {})
const evidenceCount = computed<number>(() => report.value.evidence_count ?? 0)

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
    // 基础信息只是扫描概要，对分布分析没有意义，排除
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
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
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
</style>
