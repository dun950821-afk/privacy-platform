<template>
  <div class="page-container">
    <PageHeader title="检测队列" subtitle="检测任务的排队与执行状况">
      <el-switch v-model="autoRefresh" inline-prompt active-text="自动刷新" inactive-text="手动" />
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </PageHeader>

    <!-- 状态统计卡 -->
    <div class="stat-grid">
      <div v-for="c in statusCards" :key="c.key"
           :class="['queue-card', { active: filters.statuses.length && filters.statuses.every(s => c.statuses.includes(s)) && c.statuses.length === filters.statuses.length }]"
           @click="filterByCard(c)">
        <div class="queue-card-value" :style="{ color: c.color }">{{ c.count }}</div>
        <div class="queue-card-label">{{ c.label }}</div>
      </div>
    </div>

    <el-card shadow="never">
      <div class="filter-bar">
        <el-select v-model="filters.statuses" multiple collapse-tags collapse-tags-tooltip
                   placeholder="全部状态" clearable style="width: 280px" @change="loadTasks(1)">
          <el-option v-for="(item, value) in TASK_STATUS" :key="value" :label="item.label" :value="value" />
        </el-select>
        <el-select v-model="filters.projectId" placeholder="全部项目" clearable filterable
                   style="width: 200px" @change="loadTasks(1)">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column label="任务编号" min-width="210">
          <template #default="{ row }">
            <el-link type="primary" :underline="false" class="mono"
                     @click="router.push(`/tasks/${row.id}`)">{{ row.task_code }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="App / 版本" min-width="160">
          <template #default="{ row }">
            <div>{{ row.app_name || '-' }}</div>
            <div class="sub-text">{{ row.version_name ? 'v' + row.version_name : '' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="检测类型" width="110">
          <template #default="{ row }">{{ dictLabel(DETECTION_TYPE, row.detection_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="TASK_STATUS" />
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" align="center" />
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/tasks/${row.id}`)">详情</el-button>
            <el-button v-if="isActive(row.status)" link type="danger" @click="handleCancel(row)">取消</el-button>
            <el-button v-if="canRetry(row.status)" link type="warning" @click="handleRetry(row)">重试</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无检测任务" />
        </template>
      </el-table>

      <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                     :page-size="pageSize" :current-page="page" @current-change="loadTasks" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { fmtDateTime } from '@/utils/format'
import { dictLabel, TASK_STATUS, DETECTION_TYPE } from '@/utils/dict'
import { taskApi } from '@/api/tasks'
import { projectApi } from '@/api/projects'
import api from '@/api'

const router = useRouter()

/** 进行中（可取消）与可重试的状态 */
const ACTIVE_STATUSES = ['queued', 'running_static', 'running_dynamic', 'analyzing', 'waiting_dynamic']
const RETRY_STATUSES = ['failed', 'canceled']

const isActive = (s: string) => ACTIVE_STATUSES.includes(s)
const canRetry = (s: string) => RETRY_STATUSES.includes(s)

// ============ 数据 ============
const tasks = ref<any[]>([])
const projects = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const autoRefresh = ref(true)
const statusDist = ref<Record<string, number>>({})

const filters = reactive({
  statuses: [] as string[],
  projectId: null as number | null,
})

// ============ 状态统计卡 ============
const CARD_DEFS = [
  { key: 'queued', label: '排队中', statuses: ['queued'], color: '#6B7A99' },
  { key: 'running', label: '进行中', statuses: ['running_static', 'running_dynamic', 'analyzing'], color: '#2B5AED' },
  { key: 'waiting', label: '等待动态', statuses: ['waiting_dynamic'], color: '#F0A020' },
  { key: 'failed', label: '失败', statuses: ['failed'], color: '#D03050' },
  { key: 'completed', label: '已完成', statuses: ['completed'], color: '#18A058' },
  { key: 'canceled', label: '已取消', statuses: ['canceled'], color: '#8F959E' },
]

const statusCards = computed(() =>
  CARD_DEFS.map((c) => ({
    ...c,
    count: c.statuses.reduce((sum, s) => sum + (statusDist.value[s] || 0), 0),
  }))
)

function filterByCard(c: (typeof CARD_DEFS)[number]) {
  filters.statuses = [...c.statuses]
  loadTasks(1)
}

// ============ 加载 ============
async function loadTasks(p = 1) {
  page.value = p
  loading.value = true
  try {
    const res: any = await taskApi.list({
      status: filters.statuses.length ? filters.statuses.join(',') : undefined,
      project_id: filters.projectId || undefined,
      page: page.value,
      page_size: pageSize,
    })
    tasks.value = res.data?.items || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const res: any = await api.get('/system/dashboard')
  statusDist.value = res.data?.task_status_distribution || {}
}

async function loadProjects() {
  const res: any = await projectApi.list(1, 100)
  projects.value = res.data?.items || []
}

async function loadAll() {
  await Promise.all([loadTasks(page.value), loadStats()])
}

function resetFilters() {
  filters.statuses = []
  filters.projectId = null
  loadTasks(1)
}

// ============ 操作 ============
async function handleCancel(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认取消任务「${row.task_code}」？取消后可通过重试重新排队。`,
      '取消任务',
      { type: 'warning', confirmButtonText: '确认取消', cancelButtonText: '返回' }
    )
  } catch {
    return
  }
  await taskApi.cancel(row.id)
  ElMessage.success('任务已取消')
  loadAll()
}

async function handleRetry(row: any) {
  await taskApi.retry(row.id)
  ElMessage.success('任务已重新排队')
  loadAll()
}

// ============ 轮询 ============
let pollTimer: ReturnType<typeof setInterval> | undefined

function syncPolling() {
  if (autoRefresh.value && !pollTimer) {
    pollTimer = setInterval(loadAll, 5000)
  } else if (!autoRefresh.value && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
}

watch(autoRefresh, syncPolling)

onMounted(async () => {
  loadProjects()
  await loadAll()
  syncPolling()
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.queue-card {
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px 20px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: center;
}
.queue-card:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); }
.queue-card.active {
  border-color: #2B5AED;
  box-shadow: 0 0 0 2px #EEF3FE;
}
.queue-card-value {
  font-size: 26px;
  font-weight: 600;
  line-height: 32px;
  font-variant-numeric: tabular-nums;
}
.queue-card-label {
  margin-top: 2px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.mono { font-family: monospace; font-size: 13px; }
.sub-text { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
