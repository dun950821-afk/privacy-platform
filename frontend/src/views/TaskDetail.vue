<template>
  <div class="task-detail" v-loading="loading">
    <!-- 顶部信息栏 -->
    <div class="detail-header">
      <div class="header-left">
        <el-button :icon="ArrowLeft" text @click="$router.push('/workspace')">返回工作台</el-button>
        <el-divider direction="vertical" />
        <span class="task-code">{{ task.task_code }}</span>
        <el-tag :type="statusType(task.status)" size="small" effect="dark">{{ statusLabel(task.status) }}</el-tag>
      </div>
      <div class="header-right">
        <el-button v-if="task.status === 'failed'" type="warning" @click="handleRetry">重试</el-button>
        <el-button v-if="['queued','running_static','waiting_dynamic'].includes(task.status)" @click="handleCancel">取消任务</el-button>
        <el-button type="primary" @click="generateReport" :disabled="task.status !== 'completed'">生成报告</el-button>
      </div>
    </div>

    <!-- 状态进度条 -->
    <div class="status-bar" v-if="task.status">
      <div class="step" v-for="(s, i) in steps" :key="s.key"
           :class="{ done: stepIndex > i, active: stepIndex === i, pending: stepIndex < i }">
        <div class="step-dot">{{ i + 1 }}</div>
        <div class="step-label">{{ s.label }}</div>
      </div>
    </div>

    <!-- 主体内容 -->
    <div class="detail-body">
      <el-row :gutter="16">
        <!-- 左侧：基本信息 -->
        <el-col :span="6">
          <el-card shadow="never" class="info-card">
            <template #header><span class="card-title">检测对象</span></template>
            <el-descriptions :column="1" size="small">
              <el-descriptions-item label="App">{{ task.app?.name }}</el-descriptions-item>
              <el-descriptions-item label="包名">{{ task.app?.package_name }}</el-descriptions-item>
              <el-descriptions-item label="版本">{{ task.version?.version_name }} ({{ task.version?.version_code }})</el-descriptions-item>
              <el-descriptions-item label="安装包大小">{{ task.version?.file_size ? formatSize(task.version.file_size) : '-' }}</el-descriptions-item>
              <el-descriptions-item label="SDK版本" v-if="task.version?.min_sdk || task.version?.target_sdk">
                {{ task.version?.min_sdk || '?' }} - {{ task.version?.target_sdk || '?' }}
              </el-descriptions-item>
              <el-descriptions-item label="SHA256">{{ task.version?.sha256 }}</el-descriptions-item>
              <el-descriptions-item label="检测类型">{{ detectionTypeLabel(task.detection_type) }}</el-descriptions-item>
              <el-descriptions-item label="规则包">{{ task.rule_pack_version }}</el-descriptions-item>
              <el-descriptions-item label="开始">{{ fmtDate(task.started_at) }}</el-descriptions-item>
              <el-descriptions-item label="完成">{{ fmtDate(task.completed_at) }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-card shadow="never" class="info-card" v-if="task.failed_reason">
            <template #header><span class="card-title" style="color:#D03050">失败原因</span></template>
            <p style="font-size:13px;color:#D03050">{{ task.failed_reason }}</p>
          </el-card>

          <el-card shadow="never" class="info-card">
            <template #header><span class="card-title">统计</span></template>
            <div class="stat-grid">
              <div class="stat-item">
                <div class="stat-num">{{ task.event_count || 0 }}</div>
                <div class="stat-text">事件</div>
              </div>
              <div class="stat-item">
                <div class="stat-num" style="color:#D03050">{{ task.finding_count || 0 }}</div>
                <div class="stat-text">问题</div>
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 右侧：Tab详情 -->
        <el-col :span="18">
          <el-card shadow="never">
            <el-tabs v-model="activeTab" @tab-change="handleTabChange">
              <!-- 子任务 -->
              <el-tab-pane label="检测阶段" name="subtasks">
                <el-table :data="task.sub_tasks || []" size="small" stripe>
                  <el-table-column prop="engine_type" label="引擎" width="100" />
                  <el-table-column prop="stage" label="阶段" width="100" />
                  <el-table-column prop="status" label="状态" width="100">
                    <template #default="{ row }">
                      <el-tag :type="subStatusType(row.status)" size="small">{{ subStatusLabel(row.status) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="started_at" label="开始" width="160">
                    <template #default="{ row }">{{ fmtDate(row.started_at) }}</template>
                  </el-table-column>
                  <el-table-column prop="completed_at" label="完成" width="160">
                    <template #default="{ row }">{{ fmtDate(row.completed_at) }}</template>
                  </el-table-column>
                  <el-table-column prop="error_message" label="错误" show-overflow-tooltip />
                </el-table>
              </el-tab-pane>

              <!-- 检测场景 -->
              <el-tab-pane v-if="(task.scenarios?.length ?? 0) > 0" label="检测场景" name="scenarios">
                <el-table :data="task.scenarios || []" size="small" stripe>
                  <el-table-column prop="scenario_type" label="场景" width="120">
                    <template #default="{ row }">{{ scenarioLabel(row.scenario_type) }}</template>
                  </el-table-column>
                  <el-table-column prop="consent_status" label="同意状态" width="120" />
                  <el-table-column prop="status" label="执行状态" width="100">
                    <template #default="{ row }">
                      <el-tag :type="subStatusType(row.status)" size="small">{{ subStatusLabel(row.status) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="started_at" label="开始" width="160">
                    <template #default="{ row }">{{ fmtDate(row.started_at) }}</template>
                  </el-table-column>
                  <el-table-column prop="completed_at" label="完成" width="160">
                    <template #default="{ row }">{{ fmtDate(row.completed_at) }}</template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>

              <!-- 事件时间线 -->
              <el-tab-pane :label="`事件流 (${eventTotal})`" name="events">
                <div class="filter-bar">
                  <el-select v-model="eventFilter" placeholder="事件类型" clearable size="small"
                             @change="loadEvents" style="width:180px">
                    <el-option label="基础信息" value="static_basic_info" />
                    <el-option label="权限声明" value="static_permission" />
                    <el-option label="敏感权限" value="static_sensitive_permission" />
                    <el-option label="组件" value="static_component" />
                    <el-option label="静态数据流" value="static_data_flow" />
                    <el-option label="跟踪器" value="static_tracker" />
                    <el-option label="URL" value="static_url" />
                    <el-option label="敏感API调用" value="sensitive_api_call" />
                    <el-option label="网络请求" value="network_request" />
                    <el-option label="权限申请" value="permission_request" />
                    <el-option label="页面浏览" value="page_view" />
                    <el-option label="同意状态变更" value="consent_state_change" />
                    <el-option label="SDK初始化" value="sdk_init" />
                  </el-select>
                </div>
                <el-table :data="events" size="small" stripe border @row-click="showEventDetail">
                  <el-table-column prop="timestamp" label="时间" width="160">
                    <template #default="{ row }">{{ fmtDate(row.timestamp) }}</template>
                  </el-table-column>
                  <el-table-column prop="event_type" label="类型" width="130">
                    <template #default="{ row }">
                      <el-tag :type="eventTypeColor(row.event_type)" size="small" effect="plain">
                        {{ eventTypeLabel(row.event_type) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="consent_status" label="同意状态" width="80" />
                  <el-table-column prop="data_type" label="数据类型" width="100" />
                  <el-table-column prop="api" label="API/路径" show-overflow-tooltip />
                  <el-table-column prop="caller" label="调用者" show-overflow-tooltip />
                  <el-table-column label="详情" width="60" align="center">
                    <template #default><el-icon><View /></el-icon></template>
                  </el-table-column>
                </el-table>
                <el-pagination class="pager" v-model:current-page="eventPage" :page-size="50"
                  :total="eventTotal" layout="total, prev, pager, next" @current-change="loadEvents" />
              </el-tab-pane>

              <!-- 问题 -->
              <el-tab-pane :label="`问题 (${findings.length})`" name="findings">
                <el-table :data="findings" size="small" stripe
                          @row-click="(r:any) => $router.push(`/findings/${r.id}`)">
                  <el-table-column prop="severity" label="等级" width="70">
                    <template #default="{ row }">
                      <el-tag :type="severityType(row.severity)" size="small" effect="dark">
                        {{ severityLabel(row.severity) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="title" label="标题" show-overflow-tooltip />
                  <el-table-column prop="data_type" label="数据类型" width="100" />
                  <el-table-column prop="status" label="状态" width="90" />
                  <el-table-column prop="created_at" label="发现时间" width="160">
                    <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>

              <!-- 证据 -->
              <el-tab-pane :label="`证据 (${evidenceList.length})`" name="evidence">
                <el-table :data="evidenceList" size="small" stripe>
                  <el-table-column prop="evidence_type" label="类型" width="120">
                    <template #default="{ row }">{{ evidenceLabel(row.evidence_type) }}</template>
                  </el-table-column>
                  <el-table-column prop="evidence_uid" label="UID" width="180" />
                  <el-table-column label="引擎" width="100">
                    <template #default="{ row }">{{ row.metadata_json?.engine || '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="artifact_size" label="大小" width="80">
                    <template #default="{ row }">{{ row.artifact_size ? (row.artifact_size/1024).toFixed(1)+'KB' : '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="created_at" label="时间" width="160">
                    <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="120">
                    <template #default="{ row }">
                      <el-button link size="small" @click="viewEvidence(row)">查看</el-button>
                      <el-button link size="small" @click="downloadEvidence(row)">下载</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 事件详情对话框 -->
    <el-dialog v-model="showEventDialog" title="事件详情" width="640px">
      <el-descriptions :column="1" border size="small" v-if="currentEvent">
        <el-descriptions-item label="事件ID">{{ currentEvent.event_uid }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ eventTypeLabel(currentEvent.event_type) }}</el-descriptions-item>
        <el-descriptions-item label="时间">{{ fmtDate(currentEvent.timestamp) }}</el-descriptions-item>
        <el-descriptions-item label="同意状态" v-if="currentEvent.consent_status">{{ currentEvent.consent_status }}</el-descriptions-item>
        <el-descriptions-item label="数据类型" v-if="currentEvent.data_type">{{ currentEvent.data_type }}</el-descriptions-item>
        <el-descriptions-item label="API" v-if="currentEvent.api">{{ currentEvent.api }}</el-descriptions-item>
        <el-descriptions-item label="调用者" v-if="currentEvent.caller">{{ currentEvent.caller }}</el-descriptions-item>
        <el-descriptions-item label="Trace ID" v-if="currentEvent.trace_id">{{ currentEvent.trace_id }}</el-descriptions-item>
      </el-descriptions>
      <div v-if="currentEvent?.event_data" class="event-data-block">
        <div class="event-data-title">事件数据 (JSON)</div>
        <pre class="event-data-json">{{ JSON.stringify(currentEvent.event_data, null, 2) }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, View } from '@element-plus/icons-vue'
import { taskApi } from '@/api/tasks'
import { reportApi } from '@/api/reports'
import api from '@/api/index'

const route = useRoute()
const taskId = Number(route.params.id)
const loading = ref(true)
const activeTab = ref('subtasks')

const task = ref<any>({})
const events = ref<any[]>([])
const eventPage = ref(1)
const eventTotal = ref(0)
const eventFilter = ref('')
const findings = ref<any[]>([])
const evidenceList = ref<any[]>([])

// 进度步骤
const stepsStatic = [
  { key: 'queued', label: '排队' },
  { key: 'running_static', label: '静态分析' },
  { key: 'completed', label: '完成' },
]
const stepsFull = [
  { key: 'queued', label: '排队' },
  { key: 'running_static', label: '静态分析' },
  { key: 'waiting_dynamic', label: '等待动态' },
  { key: 'running_dynamic', label: '动态检测' },
  { key: 'analyzing', label: '规则判定' },
  { key: 'completed', label: '完成' },
]

const steps = computed(() => {
  const t = task.value
  if (!t) return stepsFull
  // 有动态场景 → 完整流程；否则 → 纯静态流程
  const hasDynamic = (t.scenarios && t.scenarios.length > 0) ||
    ['full', 'consent_pre', 'sdk_audit'].includes(t.detection_type)
  return hasDynamic ? stepsFull : stepsStatic
})

const stepIndex = computed(() => {
  const status = task.value.status
  if (!status) return 0
  const s = steps.value
  const hasDynamic = s.length > 3

  if (hasDynamic) {
    const order = ['draft', 'queued', 'preparing', 'running_static', 'waiting_dynamic', 'running_dynamic', 'analyzing', 'reviewing', 'completed']
    const idx = order.indexOf(status)
    if (idx <= 1) return 0
    if (status === 'completed') return s.length
    if (status === 'failed' || status === 'canceled') return s.length
    if (idx <= 3) return 1
    if (idx === 4) return 2
    if (idx === 5) return 3
    if (idx === 6) return 4
    return 5
  } else {
    // 纯静态: queued → running_static → completed
    if (['draft', 'queued', 'preparing'].includes(status)) return 0
    if (['running_static', 'analyzing'].includes(status)) return 1
    return 2 // completed / failed / canceled
  }
})

async function loadTask() {
  loading.value = true
  try {
    const res: any = await taskApi.get(taskId)
    task.value = res.data
    // 并行加载初始数据
    loadFindings()
    loadEvents()
    loadEvidence()
  } finally {
    loading.value = false
  }
}

async function loadEvents() {
  const res: any = await taskApi.events(taskId, {
    event_type: eventFilter.value || undefined,
    page: eventPage.value, page_size: 50
  })
  events.value = res.data.items
  eventTotal.value = res.data.total
}

async function loadFindings() {
  const res: any = await taskApi.findings(taskId)
  findings.value = res.data
}

async function loadEvidence() {
  const res: any = await taskApi.evidence(taskId)
  evidenceList.value = res.data
}

function handleTabChange(name: any) {
  if (name === 'events' && !events.value.length) loadEvents()
  if (name === 'findings' && !findings.value.length) loadFindings()
  if (name === 'evidence' && !evidenceList.value.length) loadEvidence()
}

async function handleRetry() {
  await taskApi.retry(taskId)
  ElMessage.success('任务已重新提交')
  loadTask()
}

async function handleCancel() {
  await taskApi.cancel(taskId)
  ElMessage.success('任务已取消')
  loadTask()
}

async function generateReport() {
  await reportApi.generate(taskId)
  ElMessage.success('报告已生成')
}

// 事件详情
const showEventDialog = ref(false)
const currentEvent = ref<any>(null)
function showEventDetail(row: any) {
  currentEvent.value = row
  showEventDialog.value = true
}

// 证据操作
async function viewEvidence(row: any) {
  try {
    const res = await api.get(`/evidence/${row.id}/download`, { responseType: 'blob' })
    const blob = new Blob([res as any])
    const url = window.URL.createObjectURL(blob)
    const meta = row.metadata_json || {}

    if (meta.engine_type || row.evidence_type === 'engine_output') {
      // 引擎输出JSON → 新窗口展示
      const text = await blob.text()
      const w = window.open('', '_blank')
      if (w) {
        w.document.write(`<pre style="font-size:13px;white-space:pre-wrap;word-break:break-all;">${escapeHtml(text)}</pre>`)
        w.document.title = `${row.evidence_uid || 'evidence'}`
      }
    } else if (row.evidence_type === 'screenshot') {
      // 截图 → 新窗口展示图片
      window.open(url, '_blank')
    } else {
      // 其他 → 下载
      const link = document.createElement('a')
      link.href = url
      link.download = row.evidence_uid || 'evidence'
      link.click()
      window.URL.revokeObjectURL(url)
    }
  } catch (e) {
    ElMessage.error('查看证据失败')
  }
}

async function downloadEvidence(row: any) {
  try {
    const res = await api.get(`/evidence/${row.id}/download`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res as any]))
    const link = document.createElement('a')
    link.href = url
    link.download = row.evidence_uid || 'evidence'
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch {
    ElMessage.error('下载失败')
  }
}

function escapeHtml(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

// 工具函数
function fmtDate(d: string) {
  if (!d) return '-'
  return d.substring(0, 19).replace('T', ' ')
}
function formatSize(bytes: number) {
  if (!bytes) return '-'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}
function detectionTypeLabel(t: string) {
  const m: Record<string, string> = {
    full: '完整检测', static_only: '静态专项', consent_pre: '同意前专项', sdk_audit: 'SDK审计'
  }
  return m[t] || t
}
function statusType(s: string) {
  const m: Record<string, string> = { draft: 'info', queued: 'warning', completed: 'success', failed: 'danger' }
  return m[s] || ''
}
function statusLabel(s: string) {
  const m: Record<string, string> = {
    draft: '草稿', queued: '队列中', preparing: '准备中', running_static: '静态检测',
    running_dynamic: '动态检测', waiting_dynamic: '等待动态', analyzing: '分析中',
    reviewing: '复核中', completed: '已完成', failed: '失败', canceled: '已取消'
  }
  return m[s] || s
}
function subStatusType(s: string) {
  const m: Record<string, string> = { completed: 'success', failed: 'danger', running: '', pending: 'info' }
  return m[s] || 'info'
}
function subStatusLabel(s: string) {
  const m: Record<string, string> = { pending: '待执行', running: '执行中', completed: '已完成', failed: '失败' }
  return m[s] || s
}
function scenarioLabel(s: string) {
  const m: Record<string, string> = {
    first_launch: '首次启动', rejected: '拒绝同意', consented: '同意政策',
    function_trigger: '功能触发', revoked: '撤回同意', account_cancel: '账号注销'
  }
  return m[s] || s
}
function severityType(s: string) {
  const m: Record<string, string> = { critical: 'danger', high: 'danger', medium: 'warning', low: 'info' }
  return m[s] || ''
}
function severityLabel(s: string) {
  const m: Record<string, string> = { critical: '严重', high: '高', medium: '中', low: '低', info: '提示' }
  return m[s] || s
}
function eventTypeColor(t: string) {
  const m: Record<string, string> = {
    sensitive_api_call: 'danger', network_request: 'warning',
    permission_request: 'warning', consent_state_change: 'success',
    static_data_flow: 'info', page_view: '', sdk_init: 'warning',
    static_basic_info: '', static_permission: 'warning',
    static_sensitive_permission: 'danger', static_component: 'info',
    static_url: 'warning', static_tracker: 'info'
  }
  return m[t] || 'info'
}
function eventTypeLabel(t: string) {
  const m: Record<string, string> = {
    sensitive_api_call: '敏感API', network_request: '网络请求',
    permission_request: '权限申请', consent_state_change: '状态变更',
    static_data_flow: '数据流', page_view: '页面', sdk_init: 'SDK初始化',
    static_basic_info: '基础信息', static_permission: '权限声明',
    static_sensitive_permission: '敏感权限', static_component: '组件',
    static_url: 'URL', static_tracker: '跟踪器'
  }
  return m[t] || t
}
function evidenceLabel(t: string) {
  const m: Record<string, string> = {
    screenshot: '截图', api_call_stack: '调用栈', network_request: '报文',
    traffic_capture: '抓包', log_file: '日志', engine_output: '引擎输出',
    human_note: '人工说明', screen_recording: '录屏'
  }
  return m[t] || t
}

onMounted(loadTask)
</script>

<style scoped>
.task-detail { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.detail-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; background: #fff; border-bottom: 1px solid #E8EAEC;
}
.header-left { display: flex; align-items: center; gap: 8px; }
.task-code { font-size: 14px; font-weight: 600; color: #1F2329; }
.header-right { display: flex; gap: 8px; }

/* 状态进度条 */
.status-bar {
  display: flex; align-items: center; justify-content: center;
  gap: 0; padding: 16px 20px; background: #fff; border-bottom: 1px solid #E8EAEC;
}
.step {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  flex: 1; position: relative;
}
.step:not(:last-child)::after {
  content: ''; position: absolute; top: 11px; left: 50%; width: 100%; height: 2px;
  background: #E8EAEC; z-index: 0;
}
.step.done:not(:last-child)::after { background: #18A058; }
.step-dot {
  width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; z-index: 1;
  background: #E8EAEC; color: #8F959E;
}
.step.done .step-dot { background: #18A058; color: #fff; }
.step.active .step-dot { background: #2B5AED; color: #fff; box-shadow: 0 0 0 4px #EEF3FE; }
.step-label { font-size: 12px; color: #8F959E; }
.step.done .step-label { color: #18A058; }
.step.active .step-label { color: #2B5AED; font-weight: 600; }

/* 主体 */
.detail-body { flex: 1; overflow-y: auto; padding: 16px; background: #F7F8FA; }
.info-card { margin-bottom: 12px; }
.card-title { font-size: 14px; font-weight: 600; color: #1F2329; }
.stat-grid { display: flex; gap: 20px; }
.stat-item { text-align: center; }
.stat-num { font-size: 24px; font-weight: 700; color: #1F2329; }
.stat-text { font-size: 12px; color: #8F959E; }
.filter-bar { margin-bottom: 12px; }
.pager { margin-top: 12px; justify-content: flex-end; }
.event-data-block { margin-top: 12px; }
.event-data-title { font-size: 13px; font-weight: 600; color: #1F2329; margin-bottom: 6px; }
.event-data-json {
  background: #F7F8FA; border: 1px solid #E8EAEC; border-radius: 6px;
  padding: 12px; font-size: 12px; max-height: 300px; overflow-y: auto;
  white-space: pre-wrap; word-break: break-all;
}
</style>
