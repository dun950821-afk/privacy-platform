<template>
  <div class="page-container" v-loading="loading">
    <PageHeader :title="finding.title || '问题详情'" :subtitle="finding.finding_uid || ''">
      <el-button @click="$router.back()">返回</el-button>
      <el-button type="primary" @click="openAssign">分派</el-button>
      <el-button type="warning" @click="openRemediation">提交整改</el-button>
      <el-button type="success" @click="openClose">关闭问题</el-button>
    </PageHeader>

    <!-- 基本信息 -->
    <el-card shadow="never">
      <div class="section-title" style="margin-top: 0">基本信息</div>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="编号">{{ finding.finding_uid || '-' }}</el-descriptions-item>
        <el-descriptions-item label="严重度">
          <StatusTag :value="finding.severity" :map="SEVERITY" />
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <StatusTag :value="finding.status" :map="FINDING_STATUS" />
        </el-descriptions-item>
        <el-descriptions-item label="置信度">
          <StatusTag :value="finding.confidence" :map="CONFIDENCE" />
        </el-descriptions-item>
        <el-descriptions-item label="数据类型">{{ finding.data_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="网络域名">{{ finding.network_domain || '-' }}</el-descriptions-item>
        <el-descriptions-item label="API路径">{{ finding.api_path || '-' }}</el-descriptions-item>
        <el-descriptions-item label="所属任务">
          <el-button v-if="finding.task_id" link type="primary"
            @click="$router.push(`/tasks/${finding.task_id}`)">
            查看任务 #{{ finding.task_id }}
          </el-button>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="场景">
          <template v-if="finding.scenario">
            {{ dictLabel(SCENARIO_TYPE, finding.scenario.type) }} /
            <StatusTag :value="finding.scenario.consent_status" :map="CONSENT_STATUS" />
          </template>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="关联规则">
          <span v-if="finding.rule">{{ finding.rule.rule_key }} {{ finding.rule.name }}</span>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="关联SDK">
          <span v-if="finding.sdk">
            {{ finding.sdk.name }}<span v-if="finding.sdk.vendor">（{{ finding.sdk.vendor }}）</span>
          </span>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="负责人">{{ userName(finding.assigned_to) }}</el-descriptions-item>
        <el-descriptions-item label="期望完成日期">{{ fmtDate(finding.due_date) }}</el-descriptions-item>
        <el-descriptions-item label="关闭原因">{{ dictLabel(CLOSED_REASON, finding.closed_reason) }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ fmtDateTime(finding.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ fmtDateTime(finding.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="问题描述" :span="2">
          {{ finding.description || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="整改建议" :span="2">
          {{ finding.remediation_advice || '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 关联信息 Tabs -->
    <el-card shadow="never" style="margin-top: 16px">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="整改记录" name="remediations">
          <el-table :data="remediations" v-loading="tabLoading" stripe>
            <el-table-column label="整改类型" width="120">
              <template #default="{ row }">{{ dictLabel(REMEDIATION_TYPE, row.remediation_type) }}</template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
            <el-table-column label="提交人" width="110">
              <template #default="{ row }">{{ userName(row.submitted_by) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="REMEDIATION_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="提交时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.submitted_at) }}</template>
            </el-table-column>
            <template #empty>
              <EmptyBox description="暂无整改记录" />
            </template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="关联证据" name="evidence">
          <el-table :data="evidence" v-loading="tabLoading" stripe>
            <el-table-column prop="evidence_type" label="类型" width="140">
              <template #default="{ row }">{{ row.evidence_type || '-' }}</template>
            </el-table-column>
            <el-table-column label="哈希" min-width="180">
              <template #default="{ row }">
                <span class="mono">{{ row.artifact_hash || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ fmtSize(row.metadata_json?.size ?? row.metadata_json?.file_size) }}</template>
            </el-table-column>
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
            </el-table-column>
            <template #empty>
              <EmptyBox description="暂无关联证据" />
            </template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="关联事件" name="events">
          <el-table :data="events" v-loading="tabLoading" stripe>
            <el-table-column label="时间" width="170">
              <template #default="{ row }">{{ fmtDateTimeFull(row.timestamp) }}</template>
            </el-table-column>
            <el-table-column label="类型" width="130">
              <template #default="{ row }">
                <StatusTag :value="row.event_type" :map="EVENT_TYPE" />
              </template>
            </el-table-column>
            <el-table-column label="数据类型" width="130">
              <template #default="{ row }">{{ row.data_type || '-' }}</template>
            </el-table-column>
            <el-table-column label="API" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.api || '-' }}</span>
              </template>
            </el-table-column>
            <template #empty>
              <EmptyBox description="暂无关联事件" />
            </template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 分派对话框 -->
    <el-dialog v-model="assignVisible" title="分派问题" width="440px">
      <el-form label-width="100px">
        <el-form-item label="负责人" required>
          <el-select v-model="assignForm.assigned_to" placeholder="选择负责人" filterable style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :value="u.id"
              :label="`${u.full_name || u.username}（${dictLabel(USER_ROLE, u.role)}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="期望完成">
          <el-date-picker v-model="assignForm.due_date" type="date" value-format="YYYY-MM-DD"
            placeholder="选择日期" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAssign">确定</el-button>
      </template>
    </el-dialog>

    <!-- 提交整改对话框 -->
    <el-dialog v-model="remediationVisible" title="提交整改" width="520px">
      <el-form label-width="100px">
        <el-form-item label="整改类型" required>
          <el-select v-model="remediationForm.remediation_type" style="width: 100%">
            <el-option v-for="(item, key) in REMEDIATION_TYPE" :key="key" :label="item.label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="整改描述" required>
          <el-input v-model="remediationForm.description" type="textarea" :rows="4"
            placeholder="说明整改内容、涉及代码/配置位置等" />
        </el-form-item>
        <el-form-item label="附件说明">
          <el-input v-model="remediationForm.attachment" placeholder="如：修复补丁路径、截图说明（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="remediationVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitRemediation">提交</el-button>
      </template>
    </el-dialog>

    <!-- 关闭问题对话框 -->
    <el-dialog v-model="closeVisible" title="关闭问题" width="440px">
      <el-form label-width="100px">
        <el-form-item label="关闭原因" required>
          <el-select v-model="closeForm.closed_reason" style="width: 100%">
            <el-option v-for="(item, key) in CLOSED_REASON" :key="key" :label="item.label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="closeForm.notes" type="textarea" :rows="3" placeholder="补充说明（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="closeVisible = false">取消</el-button>
        <el-button type="success" :loading="submitting" @click="submitClose">确认关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { findingApi } from '@/api/findings'
import api from '@/api'
import { fmtDate, fmtDateTime, fmtDateTimeFull, fmtSize } from '@/utils/format'
import {
  dictLabel, SEVERITY, FINDING_STATUS, CONFIDENCE, CONSENT_STATUS,
  SCENARIO_TYPE, EVENT_TYPE, USER_ROLE,
} from '@/utils/dict'

/** 整改类型 */
const REMEDIATION_TYPE: Record<string, { label: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
  code_fix: { label: '代码修复', type: 'primary' },
  sdk_upgrade: { label: 'SDK升级', type: 'primary' },
  config_change: { label: '配置调整', type: 'warning' },
  policy_update: { label: '政策更新', type: 'info' },
  other: { label: '其他', type: 'info' },
}

/** 整改记录状态 */
const REMEDIATION_STATUS: Record<string, { label: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
  pending_retest: { label: '待复测', type: 'warning' },
  retesting: { label: '复测中', type: 'primary' },
  verified: { label: '复测通过', type: 'success' },
  rejected: { label: '复测未过', type: 'danger' },
}

/** 关闭原因 */
const CLOSED_REASON: Record<string, { label: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
  fixed: { label: '已修复', type: 'success' },
  false_positive: { label: '误报', type: 'info' },
  accepted: { label: '风险接受', type: 'warning' },
  duplicate: { label: '重复', type: 'info' },
  other: { label: '其他', type: 'info' },
}

const route = useRoute()
const findingId = Number(route.params.id)

const loading = ref(false)
const tabLoading = ref(false)
const submitting = ref(false)
const finding = ref<any>({})
const users = ref<any[]>([])
const remediations = ref<any[]>([])
const evidence = ref<any[]>([])
const events = ref<any[]>([])
const activeTab = ref('remediations')

const assignVisible = ref(false)
const remediationVisible = ref(false)
const closeVisible = ref(false)
const assignForm = reactive({ assigned_to: undefined as number | undefined, due_date: '' })
const remediationForm = reactive({ remediation_type: 'code_fix', description: '', attachment: '' })
const closeForm = reactive({ closed_reason: 'fixed', notes: '' })

function userName(id?: number | null): string {
  if (!id) return '-'
  const u = users.value.find((x) => x.id === id)
  return u ? u.full_name || u.username : `#${id}`
}

async function loadFinding() {
  loading.value = true
  try {
    const res: any = await findingApi.get(findingId)
    finding.value = res.data
  } finally {
    loading.value = false
  }
}

async function loadTabs() {
  tabLoading.value = true
  try {
    const [r, e, ev]: any[] = await Promise.all([
      findingApi.remediations(findingId),
      findingApi.evidence(findingId),
      findingApi.events(findingId),
    ])
    remediations.value = r.data
    evidence.value = e.data
    events.value = ev.data
  } finally {
    tabLoading.value = false
  }
}

async function loadUsers() {
  try {
    const res: any = await api.get('/system/users', { params: { page_size: 100 }, silent: true })
    users.value = res.data
  } catch { /* 无用户读权限时分派选人不可用 */ }
}

function openAssign() {
  if (!users.value.length) {
    ElMessage.warning('当前账号无用户列表权限，无法分派')
    return
  }
  assignForm.assigned_to = finding.value.assigned_to || undefined
  assignForm.due_date = finding.value.due_date || ''
  assignVisible.value = true
}

function openRemediation() {
  remediationForm.remediation_type = 'code_fix'
  remediationForm.description = ''
  remediationForm.attachment = ''
  remediationVisible.value = true
}

function openClose() {
  closeForm.closed_reason = 'fixed'
  closeForm.notes = ''
  closeVisible.value = true
}

async function submitAssign() {
  if (!assignForm.assigned_to) {
    ElMessage.warning('请选择负责人')
    return
  }
  submitting.value = true
  try {
    await findingApi.assign(findingId, {
      assigned_to: assignForm.assigned_to,
      due_date: assignForm.due_date || undefined,
    })
    ElMessage.success('分派成功')
    assignVisible.value = false
    loadFinding()
  } finally {
    submitting.value = false
  }
}

async function submitRemediation() {
  if (!remediationForm.description.trim()) {
    ElMessage.warning('请填写整改描述')
    return
  }
  submitting.value = true
  try {
    const desc = remediationForm.attachment.trim()
      ? `${remediationForm.description.trim()}\n附件说明：${remediationForm.attachment.trim()}`
      : remediationForm.description.trim()
    await findingApi.createRemediation(findingId, {
      remediation_type: remediationForm.remediation_type,
      description: desc,
    })
    ElMessage.success('整改已提交，等待复测')
    remediationVisible.value = false
    loadFinding()
    loadTabs()
  } finally {
    submitting.value = false
  }
}

async function submitClose() {
  submitting.value = true
  try {
    await findingApi.close(findingId, {
      closed_reason: closeForm.closed_reason,
      notes: closeForm.notes || undefined,
    })
    ElMessage.success('问题已关闭')
    closeVisible.value = false
    loadFinding()
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadFinding()
  loadTabs()
  loadUsers()
})
</script>

<style scoped>
.mono {
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
}
</style>
