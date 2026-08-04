<template>
  <div class="page-container">
    <PageHeader title="综合看板" subtitle="平台运行与隐私合规风险总览">
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </PageHeader>

    <!-- 统计卡片 -->
    <div class="stat-grid">
      <StatCard title="项目数" :value="dash.project_count" :icon="Folder" color="#2B5AED" to="/workspace" />
      <StatCard title="App资产" :value="dash.app_count" :icon="Cellphone" color="#18A058" to="/workspace" />
      <StatCard title="检测任务" :value="dash.task_count" :icon="List" color="#F0A020" to="/workspace" />
      <StatCard title="问题总数" :value="dash.finding_count" :icon="Warning" color="#2080F0" to="/findings" />
      <StatCard title="高风险问题" :value="dash.high_finding_count" :icon="WarningFilled" color="#D03050"
                value-color="#D03050" to="/findings" />
      <StatCard title="在线节点" :value="dash.node_count" :icon="Monitor" color="#7B61FF" />
      <StatCard title="设备数" :value="dash.device_count" :icon="Iphone" color="#13C2C2" />
    </div>

    <!-- 图表行 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :sm="24" :md="8">
        <el-card shadow="never" class="chart-card">
          <div class="chart-card-title">风险等级分布</div>
          <VChart :option="severityOption" height="260px" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="8">
        <el-card shadow="never" class="chart-card">
          <div class="chart-card-title">问题状态分布</div>
          <VChart :option="findingStatusOption" height="260px" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="8">
        <el-card shadow="never" class="chart-card">
          <div class="chart-card-title">近30天任务趋势</div>
          <VChart :option="trendOption" height="260px" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 底部两列 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :sm="24" :md="12">
        <el-card shadow="never" class="list-card">
          <div class="chart-card-title">最新高风险问题</div>
          <template v-if="recentFindings.length">
            <div v-for="f in recentFindings" :key="f.id" class="risk-item" @click="goFinding(f.id)">
              <StatusTag :value="f.severity" :map="SEVERITY" />
              <span class="risk-title" :title="f.title">{{ f.title }}</span>
              <span class="risk-time">{{ fmtDateTime(f.created_at) }}</span>
            </div>
          </template>
          <EmptyBox v-else description="暂无高风险问题" :image-size="90" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="12">
        <el-card shadow="never" class="list-card">
          <div class="chart-card-title">最近检测任务</div>
          <template v-if="recentTasks.length">
            <div v-for="t in recentTasks" :key="t.id" class="task-item" @click="goTask(t.id)">
              <div class="task-main">
                <span class="task-code">{{ t.task_code }}</span>
                <span class="task-app" :title="t.app_name || ''">{{ t.app_name || '-' }}</span>
                <span class="task-type">{{ dictLabel(DETECTION_TYPE, t.detection_type) }}</span>
              </div>
              <div class="task-side">
                <StatusTag :value="t.status" :map="TASK_STATUS" />
                <span class="task-time">{{ fmtDateTime(t.created_at) }}</span>
              </div>
            </div>
          </template>
          <EmptyBox v-else description="暂无检测任务" :image-size="90" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import {
  Refresh, Folder, Cellphone, List, Warning, WarningFilled, Monitor, Iphone,
} from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import VChart from '@/components/VChart.vue'
import { systemApi } from '@/api/system'
import { taskApi } from '@/api/tasks'
import { fmtDateTime } from '@/utils/format'
import {
  SEVERITY, FINDING_STATUS, TASK_STATUS, DETECTION_TYPE, dictItem, dictLabel,
} from '@/utils/dict'

interface RecentFinding {
  id: number
  title: string
  severity: string
  status: string
  task_id: number
  created_at: string
}

interface TaskItem {
  id: number
  task_code: string
  status: string
  detection_type: string
  app_name: string | null
  version_name: string | null
  created_at: string
}

interface DashboardData {
  project_count: number
  app_count: number
  task_count: number
  finding_count: number
  high_finding_count: number
  node_count: number
  device_count: number
  severity_distribution: Record<string, number>
  finding_status_distribution: Record<string, number>
  task_status_distribution: Record<string, number>
  task_trend: { date: string; count: number }[]
  recent_findings: RecentFinding[]
}

const router = useRouter()
const loading = ref(false)
const dash = ref<Partial<DashboardData>>({})
const recentFindings = ref<RecentFinding[]>([])
const recentTasks = ref<TaskItem[]>([])

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#D03050',
  high: '#E8553A',
  medium: '#F0A020',
  low: '#2080F0',
}

/** el-tag type → 图表配色 */
const TYPE_COLORS: Record<string, string> = {
  primary: '#2B5AED',
  success: '#18A058',
  warning: '#F0A020',
  danger: '#D03050',
  info: '#909399',
}

const severityOption = computed<EChartsOption>(() => {
  const dist = dash.value.severity_distribution || {}
  const data = Object.entries(dist).map(([key, value]) => {
    const k = key.toLowerCase()
    return {
      name: dictLabel(SEVERITY, k),
      value,
      itemStyle: { color: SEVERITY_COLORS[k] || '#909399' },
    }
  })
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: '62%',
      center: ['50%', '44%'],
      label: { show: false },
      labelLine: { show: false },
      emphasis: { scaleSize: 6 },
      data,
    }],
  }
})

const findingStatusOption = computed<EChartsOption>(() => {
  const dist = dash.value.finding_status_distribution || {}
  const data = Object.entries(dist).map(([key, value]) => {
    const item = dictItem(FINDING_STATUS, key)
    return {
      name: item.label,
      value,
      itemStyle: { color: TYPE_COLORS[item.type] || '#909399' },
    }
  })
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['42%', '62%'],
      center: ['50%', '44%'],
      label: { show: false },
      labelLine: { show: false },
      emphasis: { scaleSize: 6 },
      data,
    }],
  }
})

const trendOption = computed<EChartsOption>(() => {
  const trend = dash.value.task_trend || []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: trend.map((t) => t.date.slice(5)),
      axisLine: { lineStyle: { color: '#E5E6EB' } },
      axisTick: { show: false },
      axisLabel: { color: '#8F959E', fontSize: 11, interval: 4 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#F0F1F3' } },
      axisLabel: { color: '#8F959E', fontSize: 11 },
    },
    series: [{
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      showSymbol: false,
      data: trend.map((t) => t.count),
      lineStyle: { color: '#2B5AED', width: 2 },
      itemStyle: { color: '#2B5AED' },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(43, 90, 237, 0.25)' },
            { offset: 1, color: 'rgba(43, 90, 237, 0.02)' },
          ],
        },
      },
    }],
  }
})

async function loadDashboard() {
  const res: any = await systemApi.dashboard()
  dash.value = res.data || {}
  recentFindings.value = res.data?.recent_findings || []
}

async function loadTasks() {
  const res: any = await taskApi.list({ page: 1, page_size: 6 })
  recentTasks.value = res.data?.items || []
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.allSettled([loadDashboard(), loadTasks()])
  } finally {
    loading.value = false
  }
}

function goFinding(id: number) {
  router.push(`/findings/${id}`)
}

function goTask(id: number) {
  router.push(`/tasks/${id}`)
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  loadAll()
  timer = setInterval(loadDashboard, 60_000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.chart-row {
  margin-bottom: 16px;
}
.chart-card {
  border-radius: 8px;
}
.list-card {
  border-radius: 8px;
  min-height: 320px;
}
.risk-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 4px;
  border-bottom: 1px solid #F0F1F3;
  cursor: pointer;
  transition: background 0.15s;
}
.risk-item:last-child {
  border-bottom: none;
}
.risk-item:hover {
  background: #F7F8FA;
}
.risk-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: #1F2329;
}
.risk-time {
  flex-shrink: 0;
  font-size: 12px;
  color: #8F959E;
}
.task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 4px;
  border-bottom: 1px solid #F0F1F3;
  cursor: pointer;
  transition: background 0.15s;
}
.task-item:last-child {
  border-bottom: none;
}
.task-item:hover {
  background: #F7F8FA;
}
.task-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.task-code {
  font-size: 13px;
  font-weight: 600;
  color: #2B5AED;
  white-space: nowrap;
}
.task-app {
  font-size: 13px;
  color: #1F2329;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-type {
  flex-shrink: 0;
  font-size: 12px;
  color: #8F959E;
}
.task-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.task-time {
  font-size: 12px;
  color: #8F959E;
}
</style>
