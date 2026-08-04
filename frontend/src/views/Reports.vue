<template>
  <div class="page-container">
    <PageHeader title="报告中心" subtitle="检测报告查阅、生成与下载" />

    <el-card shadow="never">
      <el-table :data="reports" v-loading="loading" stripe>
        <el-table-column prop="task_code" label="任务编号" width="170" />
        <el-table-column label="App" min-width="200">
          <template #default="{ row }">
            <div class="app-name">{{ row.app_name || '-' }}</div>
            <div class="pkg-name">{{ row.package_name || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="version_name" label="版本" width="110">
          <template #default="{ row }">{{ row.version_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="检测类型" width="120">
          <template #default="{ row }">{{ dictLabel(DETECTION_TYPE, row.detection_type) }}</template>
        </el-table-column>
        <el-table-column prop="finding_count" label="问题数" width="90" align="center">
          <template #default="{ row }">{{ row.finding_count ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="严重度分布" min-width="220">
          <template #default="{ row }">
            <template v-if="hasSeverity(row.severity_distribution)">
              <el-tag v-for="key in SEVERITY_KEYS" :key="key"
                v-show="row.severity_distribution?.[key] > 0"
                :type="SEVERITY[key].type" size="small" effect="light" class="sev-tag">
                {{ SEVERITY[key].label }} × {{ row.severity_distribution[key] }}
              </el-tag>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="生成时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.generated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
            <el-button link type="primary" :loading="downloadingId === row.task_id"
              @click="downloadReport(row)">下载</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无已生成的报告" />
        </template>
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="page" :page-size="20" :total="total"
          layout="total, prev, pager, next" background @current-change="loadData" />
      </div>
    </el-card>

    <!-- 报告详情抽屉 -->
    <el-drawer v-model="drawerVisible" size="640px" :title="`检测报告 ${report?.task?.task_code || ''}`">
      <div v-loading="detailLoading" class="drawer-body">
        <template v-if="report">
          <div class="section-title" style="margin-top: 0">任务信息</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="任务编号">{{ report.task?.task_code }}</el-descriptions-item>
            <el-descriptions-item label="任务状态">
              <StatusTag :value="report.task?.status" :map="TASK_STATUS" />
            </el-descriptions-item>
            <el-descriptions-item label="检测类型">
              {{ dictLabel(DETECTION_TYPE, report.task?.detection_type) }}
            </el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ fmtDateTime(report.task?.completed_at) }}</el-descriptions-item>
            <el-descriptions-item label="App">{{ report.app?.name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="包名">{{ report.app?.package_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="版本">
              {{ report.version?.version_name || '-' }}
              <span v-if="report.version?.version_code">（{{ report.version.version_code }}）</span>
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ fmtDateTime(report.task?.created_at) }}</el-descriptions-item>
          </el-descriptions>

          <div class="section-title">统计概览</div>
          <div class="summary-grid">
            <div class="summary-item">
              <div class="summary-num">{{ report.summary?.finding_count ?? 0 }}</div>
              <div class="summary-text">问题</div>
            </div>
            <div class="summary-item">
              <div class="summary-num">{{ report.summary?.event_count ?? 0 }}</div>
              <div class="summary-text">事件</div>
            </div>
            <div class="summary-item">
              <div class="summary-num">{{ report.summary?.evidence_count ?? 0 }}</div>
              <div class="summary-text">证据</div>
            </div>
            <div class="summary-item">
              <div class="summary-num danger">{{ report.summary?.severity_distribution?.critical ?? 0 }}</div>
              <div class="summary-text">严重问题</div>
            </div>
          </div>

          <div class="section-title">问题清单</div>
          <el-table :data="report.findings || []" size="small" stripe max-height="320">
            <el-table-column label="严重度" width="80" align="center">
              <template #default="{ row }">
                <StatusTag :value="row.severity" :map="SEVERITY" />
              </template>
            </el-table-column>
            <el-table-column label="标题" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <el-button link type="primary" class="title-link"
                  @click="goFinding(row.id)">{{ row.title }}</el-button>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="FINDING_STATUS" />
              </template>
            </el-table-column>
            <template #empty>
              <EmptyBox description="该任务无问题记录" :image-size="80" />
            </template>
          </el-table>

          <div class="drawer-footer">
            <el-button type="primary" :loading="downloadingId === report.task?.id"
              @click="downloadReport({ task_id: report.task?.id, task_code: report.task?.task_code })">
              下载报告
            </el-button>
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { reportApi } from '@/api/reports'
import { fmtDateTime } from '@/utils/format'
import { dictLabel, SEVERITY, FINDING_STATUS, TASK_STATUS, DETECTION_TYPE } from '@/utils/dict'

const router = useRouter()
const SEVERITY_KEYS = ['critical', 'high', 'medium', 'low'] as const

const loading = ref(false)
const detailLoading = ref(false)
const downloadingId = ref<number | null>(null)
const reports = ref<any[]>([])
const page = ref(1)
const total = ref(0)
const drawerVisible = ref(false)
const report = ref<any>(null)

function hasSeverity(dist?: Record<string, number> | null): boolean {
  return !!dist && SEVERITY_KEYS.some((k) => (dist[k] ?? 0) > 0)
}

async function loadData() {
  loading.value = true
  try {
    const res: any = await reportApi.list(page.value, 20)
    reports.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function openDetail(row: any) {
  drawerVisible.value = true
  detailLoading.value = true
  report.value = null
  try {
    const res: any = await reportApi.get(row.task_id)
    report.value = res.data
  } finally {
    detailLoading.value = false
  }
}

function goFinding(id: number) {
  drawerVisible.value = false
  router.push(`/findings/${id}`)
}

async function downloadReport(row: { task_id?: number; task_code?: string }) {
  if (!row.task_id) return
  downloadingId.value = row.task_id
  try {
    const res: any = await reportApi.download(row.task_id)
    const blob = new Blob([res], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${row.task_code || row.task_id}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('报告已开始下载')
  } finally {
    downloadingId.value = null
  }
}

onMounted(loadData)
</script>

<style scoped>
.app-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.pkg-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.sev-tag {
  margin-right: 6px;
}
.drawer-body {
  padding-bottom: 16px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.summary-item {
  padding: 14px 0;
  text-align: center;
  background: #F7F8FA;
  border-radius: 8px;
}
.summary-num {
  font-size: 22px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.summary-num.danger {
  color: #D03050;
}
.summary-text {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.title-link {
  padding: 0;
}
.drawer-footer {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
