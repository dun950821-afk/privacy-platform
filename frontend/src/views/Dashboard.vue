<template>
  <div class="page-container">
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6" v-for="card in statCards" :key="card.label">
        <div class="stat-card" :style="{ borderTopColor: card.color }">
          <div class="stat-icon" :style="{ background: card.bg, color: card.color }">
            <el-icon :size="24"><component :is="card.icon" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ card.value }}</div>
            <div class="stat-label">{{ card.label }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <!-- 风险分布 -->
      <el-col :span="8">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">风险等级分布</span></template>
          <div ref="severityChartRef" class="chart"></div>
        </el-card>
      </el-col>
      <!-- 问题状态 -->
      <el-col :span="8">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">问题状态分布</span></template>
          <div ref="statusChartRef" class="chart"></div>
        </el-card>
      </el-col>
      <!-- 任务统计 -->
      <el-col :span="8">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="card-title">任务状态统计</span></template>
          <div ref="taskChartRef" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <!-- 最近任务 -->
      <el-col :span="16">
        <el-card shadow="never">
          <template #header><span class="card-title">最近检测任务</span></template>
          <el-table :data="recentTasks" size="small" stripe>
            <el-table-column prop="task_code" label="任务编号" width="180" />
            <el-table-column prop="app_name" label="App" />
            <el-table-column prop="version_name" label="版本" width="80" />
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180" />
          </el-table>
        </el-card>
      </el-col>
      <!-- 系统信息 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span class="card-title">系统信息</span></template>
          <div class="sys-info">
            <div class="sys-row"><span>在线节点</span><span>{{ dashboard.node_count || 0 }}</span></div>
            <div class="sys-row"><span>Android设备</span><span>{{ dashboard.device_count || 0 }}</span></div>
            <div class="sys-row"><span>活跃项目</span><span>{{ dashboard.project_count || 0 }}</span></div>
            <div class="sys-row"><span>高危问题</span>
              <span style="color:#D03050;font-weight:600">{{ dashboard.high_finding_count || 0 }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import { systemApi } from '@/api/system'
import { taskApi } from '@/api/tasks'
import { Cellphone, Folder, Warning, List } from '@element-plus/icons-vue'

const dashboard = ref<any>({})
const recentTasks = ref<any[]>([])

const severityChartRef = ref<HTMLElement>()
const statusChartRef = ref<HTMLElement>()
const taskChartRef = ref<HTMLElement>()
let severityChart: echarts.ECharts | null = null
let statusChart: echarts.ECharts | null = null
let taskChart: echarts.ECharts | null = null

const statCards = computed(() => [
  { label: '项目数', value: dashboard.value.project_count || 0, icon: Folder, color: '#2B5AED', bg: '#EEF3FE' },
  { label: 'App资产', value: dashboard.value.app_count || 0, icon: Cellphone, color: '#18A058', bg: '#E8F8EE' },
  { label: '检测任务', value: dashboard.value.task_count || 0, icon: List, color: '#F0A020', bg: '#FFF7E6' },
  { label: '风险问题', value: dashboard.value.finding_count || 0, icon: Warning, color: '#D03050', bg: '#FEF0F0' },
])

function initCharts() {
  if (severityChartRef.value) {
    severityChart = echarts.init(severityChartRef.value)
    severityChart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, icon: 'circle', textStyle: { fontSize: 12 } },
      series: [{
        type: 'pie', radius: ['40%', '65%'], center: ['50%', '40%'],
        label: { show: false }, labelLine: { show: false },
        data: [
          { value: 0, name: '严重', itemStyle: { color: '#D03050' } },
          { value: 0, name: '高', itemStyle: { color: '#E8553A' } },
          { value: 0, name: '中', itemStyle: { color: '#F0A020' } },
          { value: 0, name: '低', itemStyle: { color: '#2080F0' } },
        ]
      }]
    })
  }
  if (statusChartRef.value) {
    statusChart = echarts.init(statusChartRef.value)
    statusChart.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, icon: 'circle', textStyle: { fontSize: 12 } },
      series: [{
        type: 'pie', radius: ['40%', '65%'], center: ['50%', '40%'],
        label: { show: false }, labelLine: { show: false },
        data: [
          { value: 0, name: '待处理', itemStyle: { color: '#D03050' } },
          { value: 0, name: '已分派', itemStyle: { color: '#F0A020' } },
          { value: 0, name: '修复中', itemStyle: { color: '#2080F0' } },
          { value: 0, name: '已修复', itemStyle: { color: '#18A058' } },
        ]
      }]
    })
  }
  if (taskChartRef.value) {
    taskChart = echarts.init(taskChartRef.value)
    taskChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: '10%', right: '5%', bottom: '15%', top: '10%' },
      xAxis: { type: 'category', data: ['队列中', '执行中', '分析中', '已完成', '已失败'] },
      yAxis: { type: 'value' },
      series: [{
        type: 'bar', barWidth: '50%',
        itemStyle: { color: '#2B5AED', borderRadius: [4, 4, 0, 0] },
        data: [0, 0, 0, 0, 0]
      }]
    })
  }
}

function handleResize() {
  severityChart?.resize()
  statusChart?.resize()
  taskChart?.resize()
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    draft: 'info', queued: 'warning', preparing: 'warning',
    running_static: '', running_dynamic: '', waiting_dynamic: 'warning',
    analyzing: 'warning', reviewing: 'warning',
    completed: 'success', failed: 'danger', canceled: 'info'
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    draft: '草稿', queued: '队列中', preparing: '准备中',
    running_static: '静态检测', running_dynamic: '动态检测',
    waiting_dynamic: '等待动态', analyzing: '分析中',
    reviewing: '复核中', completed: '已完成', failed: '失败', canceled: '已取消'
  }
  return map[status] || status
}

onMounted(async () => {
  await nextTick()
  initCharts()
  window.addEventListener('resize', handleResize)
  
  try {
    const res: any = await systemApi.dashboard()
    dashboard.value = res.data
  } catch {}
  try {
    const res: any = await taskApi.list({ page: 1, page_size: 5 })
    recentTasks.value = res.data.items || []
  } catch {}
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  severityChart?.dispose()
  statusChart?.dispose()
  taskChart?.dispose()
})
</script>

<style scoped>
.stat-row { margin-bottom: 16px; }
.stat-card {
  background: #fff; border-radius: 8px; padding: 20px;
  display: flex; align-items: center; gap: 16px;
  border-top: 3px solid #2B5AED;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.stat-icon {
  width: 48px; height: 48px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
}
.stat-value { font-size: 28px; font-weight: 700; color: #1F2329; }
.stat-label { font-size: 13px; color: #8F959E; margin-top: 2px; }
.chart-row { margin-bottom: 16px; }
.chart-card { height: 300px; }
.chart { height: 240px; }
.card-title { font-size: 14px; font-weight: 600; color: #1F2329; }
.sys-info { padding: 8px 0; }
.sys-row {
  display: flex; justify-content: space-between;
  padding: 12px 0; border-bottom: 1px solid #F0F1F3;
  font-size: 14px; color: #646A73;
}
.sys-row:last-child { border-bottom: none; }
.sys-row span:last-child { font-weight: 600; color: #1F2329; }
</style>
