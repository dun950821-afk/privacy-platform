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

      <!-- ③ 隐私数据流 -->
      <el-tab-pane :label="`隐私数据流 (${dataFlows.length})`" name="dataflow">
        <el-card shadow="never" class="mb16">
          <template #header><span class="card-title">数据流分析</span></template>
          <el-alert v-if="appshark" type="info" :closable="false" class="mb16" :title="appsharkSummary" />
          <el-row v-if="hasFlowData" :gutter="16">
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
                  <template #default="{ row }"><span class="mono">{{ row.api || '-' }}</span></template>
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
          <EmptyBox v-else description="暂无数据流结果" />
          <div class="evidence-note">
            证据等级：潜在（potential）。第三方与加密状态在无运行时证据时保持未知。
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header><span class="card-title">数据流观察（{{ dataflowObservations.length }}）</span></template>
          <el-table :data="dataflowObservations" size="small" stripe>
            <el-table-column prop="rule_code" label="规则" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.rule_code || '-' }}</template>
            </el-table-column>
            <el-table-column label="Source" min-width="180" show-overflow-tooltip>
              <template #default="{ row }"><span class="mono">{{ sourceOf(row) }}</span></template>
            </el-table-column>
            <el-table-column label="Sink" min-width="180" show-overflow-tooltip>
              <template #default="{ row }"><span class="mono">{{ sinkOf(row) }}</span></template>
            </el-table-column>
            <el-table-column label="证据等级" width="110">
              <template #default="{ row }">{{ row.evidence_level || 'potential' }}</template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无数据流观察" /></template>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ④ 应用事实 -->
      <el-tab-pane label="应用事实" name="facts">
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

        <el-card shadow="never">
          <template #header><span class="card-title">应用事实观察（{{ factObservations.length }}）</span></template>
          <el-table :data="factObservations" size="small" stripe>
            <el-table-column prop="observation_type" label="类型" width="190" />
            <el-table-column prop="subject" label="对象" min-width="240" show-overflow-tooltip>
              <template #default="{ row }"><span class="mono">{{ row.subject || '-' }}</span></template>
            </el-table-column>
            <el-table-column prop="engine_type" label="来源引擎" width="110" />
            <template #empty><EmptyBox description="暂无事实观察" /></template>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ⑤ SDK 与第三方 -->
      <el-tab-pane label="SDK 与第三方" name="sdk">
        <el-row :gutter="16">
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
                  <template #default="{ row }"><span class="mono">{{ row.package_prefix || '-' }}</span></template>
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
    const [findingsRes, observationsRes, artifactsRes] = await Promise.allSettled([
      taskApi.platformFindings(taskId),
      taskApi.observations(taskId, { page_size: 200 }),
      taskApi.artifacts(taskId),
    ])
    if (findingsRes.status === 'fulfilled') platformFindings.value = findingsRes.value.data?.items || []
    if (observationsRes.status === 'fulfilled') observations.value = observationsRes.value.data?.items || []
    if (artifactsRes.status === 'fulfilled') artifacts.value = artifactsRes.value.data || []
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
.highlight-list { margin: 0; padding-left: 18px; }
.highlight-list li { padding: 3px 0; color: var(--el-text-color-regular); }
.evidence-note {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
