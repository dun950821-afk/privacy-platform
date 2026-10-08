<template>
  <div class="page-container" v-loading="loading">
    <!-- 首屏主语是「哪个 App」，不是任务号。任务号降到副行，仍可复制 -->
    <div class="task-head">
      <div class="task-head-main">
        <div class="task-title-row">
          <h1 class="t-h1">{{ task.app?.name || '任务详情' }}</h1>
          <span v-if="task.version?.version_name" class="task-version t-num">
            {{ task.version.version_name }}
          </span>
        </div>
        <div class="task-meta">
          <button v-if="task.task_code" class="task-code t-mono"
                  :title="`复制任务号 ${task.task_code}`" @click="copyTaskCode">
            {{ task.task_code }}
            <el-icon><CopyDocument /></el-icon>
          </button>
          <span v-if="task.task_code" class="sep">·</span>
          <span>{{ dictLabel(DETECTION_TYPE, task.detection_type) }}</span>
          <span class="sep">·</span>
          <span>{{ task.completed_at ? fmtDateTime(task.completed_at) + ' 完成'
                                     : dictLabel(TASK_STATUS, task.status) }}</span>
        </div>
      </div>

      <div class="task-head-actions">
        <StatusTag v-if="task.status" :value="task.status" :map="TASK_STATUS" size="default" />
        <StatusTag v-if="task.analysis_coverage" :value="task.analysis_coverage"
                   :map="ANALYSIS_COVERAGE" size="default" />
        <!-- App 背景（包/安全加固/端点/画像/SDK/权限）收进右侧面板，不占正文首屏 -->
        <el-button :icon="Notebook" @click="panelVisible = true">App 背景</el-button>
        <!-- 主位只有一个动作；查看报告、重试、取消、返回都是次级，收进溢出菜单 -->
        <el-button v-if="task.status === 'completed'" type="primary" :icon="Document"
                   :loading="generating" @click="handleGenerateReport">
          生成检测报告
        </el-button>
        <el-dropdown trigger="click" @command="onHeadCommand">
          <el-button :icon="MoreFilled" title="更多操作" aria-label="更多操作" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="report" :icon="DataAnalysis">查看检测报告</el-dropdown-item>
              <el-dropdown-item command="retry" :icon="RefreshRight" :disabled="!canRetry">
                重试任务
              </el-dropdown-item>
              <el-dropdown-item command="cancel" :icon="CircleClose" :disabled="!canCancel" divided>
                取消任务
              </el-dropdown-item>
              <el-dropdown-item command="back" :icon="ArrowLeft" divided>返回工作台</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 进度条只在「正在跑 / 跑挂了」时出场：任务已完成时它是纯冗余 -->
    <el-card v-if="showSteps" shadow="never" class="steps-card">
      <el-steps :active="stepActive" align-center
                :process-status="processStatus" :finish-status="finishStatus">
        <el-step v-for="s in steps" :key="s" :title="s" />
      </el-steps>
    </el-card>

    <!-- 主视图：问题清单。原 tab 里的引擎细节整体降为下方折叠区，
         主视图不再罗列引擎结果，只回答「有哪些问题」 -->
    <ProblemList :task-id="taskId" />

    <el-card shadow="never" class="secondary-card">
      <el-collapse v-model="openSections">
        <!-- 合规画像已搬进「App 背景」右侧面板（§5.1）；这里不再重复 -->

        <!-- 运维排查用：任务明细 + 阶段 + 场景 + 引擎队列，合并成一个折叠区 -->
        <el-collapse-item name="execution">
          <template #title>
            <span class="sec-title">执行信息</span>
            <span v-if="execFailed" class="sec-badge is-danger">{{ execFailed }}</span>
            <span v-else-if="subTasks.length" class="sec-badge">{{ subTasks.length }}</span>
          </template>

          <!-- 原本在首屏折叠条里的字段挪到这里：它对排查有用，但不该占首屏 -->
          <div class="sub-group mb16">
            <div class="t-section mb12">任务信息</div>
            <el-descriptions :column="3" size="small">
              <el-descriptions-item label="包名">
                <span class="t-mono">{{ task.app?.package_name || '-' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="版本">
                {{ task.version?.version_name || '-' }}（code {{ task.version?.version_code ?? '-' }}）
              </el-descriptions-item>
              <el-descriptions-item label="文件大小">
                {{ fmtSize(task.version?.file_size) }}
              </el-descriptions-item>
              <el-descriptions-item label="SHA256" :span="2">
                <span class="t-mono">{{ task.version?.sha256 || '-' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="规则包版本">{{ task.rule_pack_version || '-' }}</el-descriptions-item>
              <el-descriptions-item label="优先级">{{ task.priority ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="创建人">{{ task.created_by_name || task.created_by || '-' }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ fmtDateTime(task.created_at) }}</el-descriptions-item>
              <el-descriptions-item label="开始时间">{{ fmtDateTime(task.started_at) }}</el-descriptions-item>
              <el-descriptions-item label="完成时间">{{ fmtDateTime(task.completed_at) }}</el-descriptions-item>
            </el-descriptions>
            <div v-if="task.failed_reason" class="failed-reason">
              <span class="failed-label">失败原因：</span>{{ task.failed_reason }}
            </div>
          </div>

          <div class="t-section mb12">检测阶段</div>
          <el-table :data="subTasks" size="small" class="data-table">
            <el-table-column prop="sub_task_code" label="子任务编号" width="180">
              <template #default="{ row }"><span class="t-mono">{{ row.sub_task_code }}</span></template>
            </el-table-column>
            <el-table-column label="引擎" width="140">
              <template #default="{ row }">{{ engineNames(row) }}</template>
            </el-table-column>
            <el-table-column prop="stage" label="阶段" width="110" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="EXEC_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="开始时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="完成时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.completed_at) }}</template>
            </el-table-column>
            <el-table-column label="结果摘要" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ summaryText(row.result_summary) }}</template>
            </el-table-column>
            <el-table-column prop="error_message" label="错误信息" min-width="140"
                             show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无检测阶段" /></template>
          </el-table>

          <div class="t-section mb12 mt20">检测场景</div>
          <el-table :data="scenarios" size="small" class="data-table">
            <el-table-column label="场景类型" width="150">
              <template #default="{ row }">{{ dictLabel(SCENARIO_TYPE, row.scenario_type) }}</template>
            </el-table-column>
            <el-table-column label="同意状态" width="110">
              <template #default="{ row }">
                <StatusTag :value="row.consent_status" :map="CONSENT_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="执行状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="EXEC_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="设备" width="140">
              <template #default="{ row }">{{ row.device || row.device_id || '-' }}</template>
            </el-table-column>
            <el-table-column label="开始时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="完成时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.completed_at) }}</template>
            </el-table-column>
            <el-table-column prop="notes" label="备注" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.notes || '-' }}</template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无检测场景" /></template>
          </el-table>

          <div class="t-section mb12 mt20">引擎队列</div>
          <el-timeline v-if="engineQueue.items?.length">
            <el-timeline-item v-for="item in engineQueue.items" :key="item.id"
                              :type="engineStatusType(item.status)"
                              :timestamp="fmtDateTime(item.started_at || item.completed_at)">
              <strong>{{ item.engine_name }}</strong>
              <span class="t-sub"> · {{ engineStatusLabel(item.status) }} · {{ item.stage_message || item.stage || '-' }}</span>
              <el-progress v-if="item.progress != null" :percentage="item.progress" :stroke-width="6" />
              <div v-if="item.error_message" class="error-text">{{ item.error_message }}</div>
              <div v-if="item.error_code" class="t-sub">
                错误码：{{ item.error_code }} · 可重试：{{ item.retryable ? '是' : '否' }}
              </div>
              <el-button v-if="canRetryEngine(item)" size="small" type="warning" plain
                         :loading="retryingId === item.id" @click="handleEngineRetry(item)">
                重新执行本引擎
              </el-button>
            </el-timeline-item>
          </el-timeline>
          <EmptyBox v-else description="暂无引擎执行记录" />
        </el-collapse-item>

        <el-collapse-item name="evidence">
          <template #title>
            <span class="sec-title">证据</span>
            <span v-if="evidenceList.length" class="sec-badge">{{ evidenceList.length }}</span>
          </template>
          <el-table :data="evidenceList" size="small" class="data-table">
            <el-table-column label="类型" width="180">
              <template #default="{ row }">
                {{ evidenceTypeLabel(row.evidence_type) }}
                <span v-if="row.metadata_json?.engine" class="t-sub"> · {{ row.metadata_json.engine }}</span>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ fmtSize(row.artifact_size) }}</template>
            </el-table-column>
            <el-table-column label="哈希" width="140">
              <template #default="{ row }">
                <span class="t-mono">{{ row.artifact_hash ? row.artifact_hash.slice(0, 12) : '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" :icon="View"
                           @click.stop="openPreview(row)">预览</el-button>
                <el-button link type="primary" size="small" :icon="Download"
                           @click.stop="downloadEvidence(row)">下载</el-button>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无证据" /></template>
          </el-table>
        </el-collapse-item>

        <el-collapse-item name="leads">
          <template #title><span class="sec-title">引擎判定与未核实线索</span></template>
          <RiskFindings :task-id="taskId" hide-findings />
        </el-collapse-item>

        <!-- 整改概览折叠在底部：四态汇总 + 复检记录（两个方向）。
             v-if 让它展开时才挂载取数——卡片上的整改是就地改的，若这里常驻挂载，
             计数会停留在上一次进页面时的快照。 -->
        <el-collapse-item name="remediation">
          <template #title><span class="sec-title">整改概览</span></template>
          <RemediationOverview v-if="openSections.includes('remediation')" :task-id="taskId" />
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <!-- App 背景：480px 侧滑面板。任务级数据（端点/画像/SDK/权限）只在这里出现一次 -->
    <AppBackgroundPanel v-model="panelVisible" :task-id="taskId" :task="task" />

    <!-- 证据预览对话框（可拖拽调整大小） -->
    <el-dialog v-model="previewVisible" :title="previewTitle" :width="previewSize.w + 'px'" top="4vh">
      <div v-loading="previewLoading" class="preview-body" :style="{ height: previewSize.h + 'px' }">
        <img v-if="previewKind === 'image' && previewUrl" :src="previewUrl"
             class="preview-image" alt="证据预览" />
        <template v-else-if="previewKind === 'text'">
          <pre class="json-pre preview-text">{{ previewContent }}</pre>
          <div v-if="previewTruncated" class="preview-truncated">
            文件过大，仅显示前 512KB，完整内容请下载查看
          </div>
        </template>
        <EmptyBox v-else-if="previewKind === 'unsupported'"
                  description="该文件类型暂不支持预览，请下载后查看">
          <el-button type="primary" :icon="Download" @click="downloadEvidence(previewRow)">
            下载文件
          </el-button>
        </EmptyBox>
        <div class="resize-grip" title="拖拽调整大小" @mousedown="startResize">
          <el-icon><Rank /></el-icon>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, RefreshRight, CircleClose, Document, Download, View, Rank,
  DataAnalysis, CopyDocument, MoreFilled, Notebook,
} from '@element-plus/icons-vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import ProblemList from '@/components/ProblemList.vue'
import AppBackgroundPanel from '@/components/AppBackgroundPanel.vue'
import RemediationOverview from '@/components/RemediationOverview.vue'
import RiskFindings from '@/components/RiskFindings.vue'
import api from '@/api'
import { taskApi } from '@/api/tasks'
import { reportApi } from '@/api/reports'
import { engineApi } from '@/api/engines'
import { fmtDateTime, fmtSize } from '@/utils/format'
import {
  dictLabel, TASK_STATUS, EXEC_STATUS, SCENARIO_TYPE, CONSENT_STATUS,
  DETECTION_TYPE, ANALYSIS_COVERAGE,
} from '@/utils/dict'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => Number(route.params.id))

const loading = ref(true)
const generating = ref(false)
// 落地即看问题清单：主视图回答「有哪些问题」，引擎细节收进下方折叠区
const openSections = ref<string[]>([])
// App 背景侧滑面板（右上角按钮触发）
const panelVisible = ref(false)

const task = ref<any>({})
const subTasks = computed<any[]>(() => task.value.sub_tasks || [])
const engineQueue = computed<any>(() => task.value.engine_queue || { items: [] })
const retryingId = ref<number | null>(null)
const ENGINE_RETRYABLE = ['failed', 'timed_out', 'canceled']
function canRetryEngine(item: any) {
  return ENGINE_RETRYABLE.includes(item.status) && item.retryable
}
async function handleEngineRetry(item: any) {
  retryingId.value = item.id
  try {
    await engineApi.retryExecution(item.id)
    ElMessage.success(`已重新排队：${item.engine_name}`)
    await loadTask()
  } finally {
    retryingId.value = null
  }
}
const engineStatusLabel = (status: string) => ({ pending: '等待执行', running: '执行中', completed: '已完成', failed: '失败', canceled: '已取消' }[status] || status)
const engineStatusType = (status: string) => ({ pending: 'info', running: 'primary', completed: 'success', failed: 'danger', canceled: 'warning' }[status] || 'info') as any

/** 引擎队列里失败/超时的条数——比阶段数更值得在 tab 上提示 */
const execFailed = computed(() =>
  (engineQueue.value.items || []).filter((i: any) => ['failed', 'timed_out'].includes(i.status)).length)

const scenarios = ref<any[]>([])
const evidenceList = ref<any[]>([])

/** 运行中状态（触发轮询 / 允许取消） */
const RUNNING_STATUSES = ['queued', 'running_static', 'running_dynamic', 'waiting_dynamic', 'analyzing']

const canRetry = computed(() => ['failed', 'canceled'].includes(task.value.status))
const canCancel = computed(() => RUNNING_STATUSES.includes(task.value.status))

/** 进度条只在运行中或异常结束时才有信息量 */
const showSteps = computed(() =>
  RUNNING_STATUSES.includes(task.value.status) || ['failed', 'canceled'].includes(task.value.status))

function onHeadCommand(cmd: string) {
  if (cmd === 'report') router.push(`/tasks/${taskId.value}/report`)
  else if (cmd === 'retry') handleRetry()
  else if (cmd === 'cancel') handleCancel()
  else if (cmd === 'back') router.push('/workspace')
}

async function copyTaskCode() {
  const code = task.value.task_code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success('任务号已复制')
  } catch {
    // 非安全上下文（http 访问）下 clipboard 可能不可用，退回到选中提示
    ElMessage.info(code)
  }
}

// ============ 进度步骤条 ============
const DYNAMIC_TYPES = ['full', 'consent_pre', 'sdk_audit']
const hasDynamic = computed(() => DYNAMIC_TYPES.includes(task.value.detection_type))

const steps = computed(() =>
  hasDynamic.value
    ? ['创建', '静态检测', '动态检测', '分析判定', '完成']
    : ['创建', '静态检测', '分析判定', '完成'])

const stepActive = computed(() => {
  const status = task.value.status
  const dyn = hasDynamic.value
  switch (status) {
    case 'draft': return 0
    case 'queued': return 1
    case 'running_static': return 1
    case 'waiting_dynamic':
    case 'running_dynamic': return dyn ? 2 : 1
    case 'analyzing': return dyn ? 3 : 2
    case 'completed': return steps.value.length
    case 'failed': {
      // 按已完成的子任务数推断失败发生的位置
      const done = (task.value.sub_tasks || [])
        .filter((s: any) => s.status === 'completed').length
      return Math.min(1 + done, steps.value.length - 1)
    }
    case 'canceled': return 1
    default: return 0
  }
})

const processStatus = computed<'process' | 'error' | 'wait'>(() => {
  if (task.value.status === 'failed') return 'error'
  if (task.value.status === 'canceled') return 'wait'
  return 'process'
})
const finishStatus = computed<'success' | 'wait'>(() =>
  task.value.status === 'canceled' ? 'wait' : 'success')

// ============ 数据加载 ============
async function loadTask() {
  const res: any = await taskApi.get(taskId.value)
  task.value = res.data
}

async function loadScenarios() {
  const res: any = await taskApi.scenarios(taskId.value)
  scenarios.value = res.data || []
}

async function loadEvidence() {
  const res: any = await taskApi.evidence(taskId.value)
  evidenceList.value = res.data || []
}

async function loadAll() {
  loading.value = true
  try {
    await loadTask()
    // 合规画像/风险结论由各自组件取数（它们才是数据的消费方），这里不重复请求
    await Promise.all([loadScenarios(), loadEvidence()])
  } finally {
    loading.value = false
  }
  syncPolling()
}

// ============ 运行中 5s 轮询（任务详情 + 场景） ============
let pollTimer: ReturnType<typeof setInterval> | undefined

function syncPolling() {
  if (RUNNING_STATUSES.includes(task.value.status) && !pollTimer) {
    pollTimer = setInterval(pollRunning, 5000)
  } else if (!RUNNING_STATUSES.includes(task.value.status) && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function pollRunning() {
  try {
    await loadTask()
    await loadScenarios()
  } catch {
    /* 轮询失败静默，等待下次 */
  }
  syncPolling()
}

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// ============ 操作 ============
async function handleRetry() {
  await taskApi.retry(taskId.value)
  ElMessage.success('任务已重新提交')
  await loadAll()
}

async function handleCancel() {
  try {
    await ElMessageBox.confirm('确认取消该检测任务？取消后可通过"重试"重新执行。', '取消任务', {
      confirmButtonText: '确认取消',
      cancelButtonText: '再想想',
      type: 'warning',
    })
  } catch {
    return // 用户放弃取消
  }
  await taskApi.cancel(taskId.value)
  ElMessage.success('任务已取消')
  await loadAll()
}

async function handleGenerateReport() {
  generating.value = true
  try {
    await reportApi.generate(taskId.value)
    ElMessage.success('报告已生成，可前往报告中心查看')
  } finally {
    generating.value = false
  }
}

// ============ 证据下载 ============
function evidenceTypeLabel(t: string): string {
  const m: Record<string, string> = {
    screenshot: '截图', api_call_stack: '调用栈', network_request: '报文',
    traffic_capture: '抓包', log_file: '日志', engine_output: '引擎输出',
    human_note: '人工说明', screen_recording: '录屏',
  }
  return m[t] || t || '-'
}

async function downloadEvidence(row: any) {
  try {
    const blob: any = await api.get(`/evidence/${row.id}/download`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    link.download = row.metadata_json?.filename || row.evidence_uid || `evidence-${row.id}`
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch {
    ElMessage.error('下载失败')
  }
}

// ============ 证据预览 ============
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewKind = ref<'' | 'image' | 'text' | 'unsupported'>('')
const previewUrl = ref('')
const previewContent = ref('')
const previewTruncated = ref(false)
const previewTitle = ref('证据预览')
const previewRow = ref<any>(null)

function clearPreviewUrl() {
  if (previewUrl.value) {
    window.URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

async function openPreview(row: any) {
  previewRow.value = row
  previewTitle.value = `证据预览 · ${evidenceTypeLabel(row.evidence_type)}`
  previewVisible.value = true
  previewLoading.value = true
  previewKind.value = ''
  previewContent.value = ''
  previewTruncated.value = false
  clearPreviewUrl()
  try {
    // 先按 JSON 请求；图片类型后端直接返回文件流（axios 会当文本解析，需按扩展名预判）
    const filename = (row.metadata_json?.filename || '').toLowerCase()
    const isImage = /\.(png|jpe?g|gif|webp|bmp)$/.test(filename) || row.evidence_type === 'screenshot'
    if (isImage) {
      const blob: any = await api.get(`/evidence/${row.id}/preview`, { responseType: 'blob' })
      previewUrl.value = window.URL.createObjectURL(new Blob([blob]))
      previewKind.value = 'image'
    } else {
      const res: any = await api.get(`/evidence/${row.id}/preview`)
      const d = res.data || {}
      if (d.kind === 'text') {
        previewKind.value = 'text'
        previewContent.value = d.content || ''
        previewTruncated.value = !!d.truncated
      } else {
        previewKind.value = 'unsupported'
      }
    }
  } catch {
    previewKind.value = 'unsupported'
  } finally {
    previewLoading.value = false
  }
}

watch(previewVisible, (v) => {
  if (!v) clearPreviewUrl()
})

// ============ 预览框拖拽调整大小 ============
const previewSize = reactive({ w: 880, h: 620 })

function startResize(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startY = e.clientY
  const startW = previewSize.w
  const startH = previewSize.h
  const onMove = (ev: MouseEvent) => {
    previewSize.w = Math.min(Math.max(startW + (ev.clientX - startX), 480), window.innerWidth - 60)
    previewSize.h = Math.min(Math.max(startH + (ev.clientY - startY), 240), window.innerHeight - 140)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ============ 工具 ============
function summaryText(summary: any): string {
  if (!summary) return '-'
  if (typeof summary === 'string') return summary
  try {
    return JSON.stringify(summary)
  } catch {
    return '-'
  }
}

/** 检测阶段Tab的引擎列：显示实际执行的引擎名（如 AppShark），而非子任务类型 static/dynamic */
function engineNames(subTask: any): string {
  const engines = subTask.result_summary?.engines
  if (Array.isArray(engines) && engines.length) {
    return engines.map((e: any) => e.engine || e.type).join('、')
  }
  return subTask.engine_type || '-'
}

// 同组件内切换任务 id 时重新加载
watch(taskId, (id, old) => {
  if (id && id !== old) {
    loadAll()
  }
})

onMounted(loadAll)
</script>

<style scoped>
.task-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.task-head-main { min-width: 0; }
.task-title-row { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
/* 版本做成一枚蓝调胶囊：比灰字更容易被扫到，也给标题行一点视觉重量 */
.task-version {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--brand-700);
  background: var(--brand-50);
  border: 1px solid var(--brand-100);
  border-radius: 999px;
  padding: 2px 10px;
  line-height: 18px;
}
.task-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
  font-size: var(--text-label);
  color: var(--ink-3);
  flex-wrap: wrap;
}
.sep { color: var(--ink-4); }
.task-code {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  background: none;
  border: none;
  font-size: var(--text-label);
  color: var(--ink-3);
  cursor: pointer;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  transition: color 0.15s;
}
.task-code:hover { color: var(--el-color-primary); }
.task-head-actions { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }

.steps-card { margin-bottom: var(--space-4); }

/* 折叠区：主视图之下，默认全收起；徽标让「哪个区有东西」不用点开就知道 */
.secondary-card { margin-top: var(--space-4); }
.secondary-card :deep(.el-collapse) { border-top: none; border-bottom: none; }
.secondary-card :deep(.el-collapse-item__header) {
  height: auto;
  min-height: var(--row-h);
  padding: var(--space-2) 0;
  gap: var(--space-2);
  background: transparent;
  border-bottom: 1px solid var(--line);
}
.secondary-card :deep(.el-collapse-item:last-child .el-collapse-item__header) { border-bottom: none; }
.secondary-card :deep(.el-collapse-item__arrow) { color: var(--ink-4); }
.secondary-card :deep(.el-collapse-item__wrap) { border-bottom: none; }
.secondary-card :deep(.el-collapse-item__content) {
  padding: var(--space-3) 0 var(--space-5);
  font-size: var(--text-body);
}

.sec-title { font-size: var(--text-section); font-weight: 600; color: var(--ink); }
.sec-badge {
  display: inline-block;
  min-width: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--brand-50);
  color: var(--brand-700);
  border: 1px solid var(--brand-100);
  font-size: var(--text-micro);
  font-weight: 600;
  line-height: 16px;
  text-align: center;
}
.sec-badge.is-danger {
  background: #FEF2F2;
  color: #DC2626;
  border-color: #FECACA;
}

.mb12 { margin-bottom: var(--space-3); }
.mb16 { margin-bottom: var(--space-4); }
.mt20 { margin-top: var(--space-5); }
.error-text { color: var(--el-color-danger); }
.failed-reason {
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: #FEF0F0;
  border-radius: 6px;
  font-size: var(--text-body);
  color: var(--el-color-danger);
}
.failed-label { font-weight: 600; }
/* 表格密度/表头/悬停由全局 .data-table 提供 */

/* 证据预览 */
.preview-body { position: relative; min-height: 200px; }
.preview-image {
  display: block;
  max-width: 100%;
  max-height: 100%;
  margin: 0 auto;
  border-radius: 6px;
  object-fit: contain;
}
.preview-body .preview-text { height: 100%; max-height: none; box-sizing: border-box; }
.preview-truncated {
  position: absolute;
  bottom: 8px;
  left: 12px;
  font-size: var(--text-label);
  color: var(--el-color-warning);
  background: #FFFBEB;
  padding: 2px 8px;
  border-radius: 4px;
}
.resize-grip {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: nwse-resize;
  color: var(--ink-4);
  border-radius: 4px;
}
.resize-grip:hover { color: #2B5AED; background: #EEF3FE; }
.json-pre {
  background: var(--surface-subtle);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: var(--space-3);
  font-size: var(--text-label);
  line-height: 1.6;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
