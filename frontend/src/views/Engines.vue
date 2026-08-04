<template>
  <div class="page-container">
    <PageHeader title="检测引擎" subtitle="静态/动态检测引擎运行状况">
      <el-button :icon="Refresh" :loading="loadingEngines" @click="loadAll">刷新</el-button>
    </PageHeader>

    <div class="stat-grid">
      <StatCard title="总执行次数" :value="stats.total_executions ?? 0" :icon="Histogram" color="#2B5AED" />
      <StatCard title="成功次数" :value="successCount" :icon="CircleCheck" color="#18A058" />
      <StatCard title="失败次数" :value="failedCount" :icon="CircleClose" color="#D03050" />
      <StatCard title="平均耗时" :value="avgDuration" :icon="Timer" color="#F0A020" />
    </div>

    <div class="section-title">引擎列表</div>
    <div v-if="engines.length" class="engine-grid" v-loading="loadingEngines">
      <el-card v-for="e in engines" :key="e.engine_type" shadow="never" class="engine-card">
        <div class="engine-header">
          <div class="engine-name-area">
            <span class="engine-name">{{ e.name }}</span>
            <el-tag size="small" type="info" effect="plain">v{{ e.version }}</el-tag>
          </div>
          <el-tag :type="e.env_ready ? 'success' : 'warning'" size="small">
            {{ e.env_ready ? '就绪' : '未配置' }}
          </el-tag>
        </div>
        <p class="engine-desc">{{ e.description || '-' }}</p>
        <div class="engine-caps">
          <el-tag v-for="cap in e.capabilities || []" :key="cap" size="small" effect="plain">
            {{ capLabel(cap) }}
          </el-tag>
        </div>
        <el-alert
          v-if="!e.env_ready"
          type="warning"
          :closable="false"
          show-icon
          title="环境未就绪"
          class="engine-alert"
        >
          <div class="guide-content">
            <span class="guide-label">安装方式：</span>
            <code class="guide-code">{{ e.install_guide || '请联系管理员配置' }}</code>
          </div>
        </el-alert>
        <div class="engine-actions">
          <el-button
            size="small"
            :icon="Monitor"
            :loading="checkingType === e.engine_type"
            @click="handleHealthCheck(e.engine_type)"
          >环境检查</el-button>
        </div>
      </el-card>
    </div>
    <el-card v-else shadow="never">
      <EmptyBox description="暂无已注册引擎" />
    </el-card>

    <div class="section-title">执行历史</div>
    <div class="filter-bar">
      <el-select v-model="filterEngine" placeholder="引擎类型" clearable style="width: 160px" @change="onFilter">
        <el-option v-for="e in engines" :key="e.engine_type" :label="e.name" :value="e.engine_type" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 120px" @change="onFilter">
        <el-option
          v-for="key in EXEC_FILTER_KEYS"
          :key="key"
          :label="dictLabel(EXEC_STATUS, key)"
          :value="key"
        />
      </el-select>
    </div>
    <el-card shadow="never">
      <el-table :data="executions" v-loading="loadingExec" stripe>
        <el-table-column label="任务ID" width="170">
          <template #default="{ row }">{{ row.task_code || row.task_id || '-' }}</template>
        </el-table-column>
        <el-table-column prop="engine_name" label="引擎" width="130">
          <template #default="{ row }">{{ row.engine_name || row.engine_type }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="EXEC_STATUS" />
          </template>
        </el-table-column>
        <el-table-column prop="event_count" label="事件数" width="80" align="right" />
        <el-table-column prop="artifact_count" label="产出数" width="80" align="right" />
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ fmtDuration(row.duration_ms) }}</template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误信息" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_message || '-' }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无执行记录" />
        </template>
      </el-table>
      <el-pagination
        class="pager"
        v-model:current-page="execPage"
        :page-size="execPageSize"
        :total="execTotal"
        layout="total, prev, pager, next"
        @current-change="loadExecutions"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Histogram, CircleCheck, CircleClose, Timer, Monitor } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { engineApi } from '@/api/engines'
import { EXEC_STATUS, dictLabel } from '@/utils/dict'
import { fmtDateTime, fmtDuration } from '@/utils/format'

const EXEC_FILTER_KEYS = ['pending', 'running', 'completed', 'failed']

const engines = ref<any[]>([])
const stats = ref<any>({})
const executions = ref<any[]>([])
const loadingEngines = ref(false)
const loadingExec = ref(false)
const checkingType = ref('')
const execPage = ref(1)
const execPageSize = 20
const execTotal = ref(0)
const filterEngine = ref('')
const filterStatus = ref('')

const successCount = computed(() => {
  const s = stats.value.by_status || {}
  return (s.success || 0) + (s.completed || 0)
})
const failedCount = computed(() => stats.value.by_status?.failed || 0)
const avgDuration = computed(() => {
  const list: any[] = stats.value.by_engine || []
  const total = list.reduce((sum, e) => sum + (e.total || 0), 0)
  if (!total) return fmtDuration(0)
  const weighted = list.reduce((sum, e) => sum + (e.avg_duration_ms || 0) * (e.total || 0), 0)
  return fmtDuration(Math.round(weighted / total))
})

const CAP_LABELS: Record<string, string> = {
  BASIC_INFO: '基础信息', PERMISSIONS: '权限', COMPONENTS: '组件',
  SIGNATURE: '签名', STRINGS: '字符串', DATA_FLOW: '数据流',
  TAINT_ANALYSIS: '污点分析', STATIC_SCAN: '静态扫描',
  MALWARE_CHECK: '恶意检测', TRACKER_DETECTION: '跟踪器',
}
function capLabel(cap: string) {
  return CAP_LABELS[cap] || cap
}

async function loadEngines() {
  loadingEngines.value = true
  try {
    const res: any = await engineApi.list()
    engines.value = res.data
  } finally {
    loadingEngines.value = false
  }
}

async function loadStats() {
  const res: any = await engineApi.stats()
  stats.value = res.data
}

async function loadExecutions() {
  loadingExec.value = true
  try {
    const res: any = await engineApi.executions({
      engine_type: filterEngine.value || undefined,
      status: filterStatus.value || undefined,
      page: execPage.value,
      page_size: execPageSize,
    })
    executions.value = res.data.items
    execTotal.value = res.data.total
  } finally {
    loadingExec.value = false
  }
}

function onFilter() {
  execPage.value = 1
  loadExecutions()
}

async function handleHealthCheck(engineType: string) {
  checkingType.value = engineType
  try {
    const res: any = await engineApi.healthCheck(engineType)
    const d = res.data
    if (d.env_ready) {
      ElMessage.success(`${d.name}: 环境就绪`)
    } else {
      ElMessage.warning(`${d.name}: 环境未配置`)
    }
    loadEngines()
  } finally {
    checkingType.value = ''
  }
}

function loadAll() {
  loadEngines()
  loadStats()
  execPage.value = 1
  loadExecutions()
}

onMounted(loadAll)
</script>

<style scoped>
.engine-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}
.engine-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.engine-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.engine-name-area {
  display: flex;
  align-items: center;
  gap: 8px;
}
.engine-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.engine-desc {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.engine-caps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.engine-alert :deep(.el-alert__content) {
  min-width: 0;
}
.guide-content {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  margin-top: 4px;
}
.guide-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.guide-code {
  font-size: 12px;
  word-break: break-all;
}
.engine-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
