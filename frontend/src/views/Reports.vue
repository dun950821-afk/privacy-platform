<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar"><span class="page-title">报告中心</span></div>
      <el-input v-model="taskId" placeholder="输入任务ID" style="width:200px;margin-bottom:12px" />
      <el-button type="primary" @click="loadReport">查看报告</el-button>
      <el-button @click="generateReport">生成报告</el-button>
      <div v-if="report" style="margin-top:20px">
        <el-descriptions :column="2" border size="small" title="报告概览">
          <el-descriptions-item label="任务编号">{{ report.task?.task_code }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ report.task?.status }}</el-descriptions-item>
          <el-descriptions-item label="App">{{ report.app?.name }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ report.version?.version_name }}</el-descriptions-item>
          <el-descriptions-item label="问题数">{{ report.summary?.finding_count }}</el-descriptions-item>
          <el-descriptions-item label="事件数">{{ report.summary?.event_count }}</el-descriptions-item>
        </el-descriptions>
        <h3 style="margin-top:20px">问题清单</h3>
        <el-table :data="report.findings || []" size="small">
          <el-table-column prop="title" label="标题" />
          <el-table-column prop="severity" label="等级" width="80" />
          <el-table-column prop="status" label="状态" width="100" />
        </el-table>
      </div>
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { reportApi } from '@/api/reports'

const taskId = ref('')
const report = ref<any>(null)

async function loadReport() {
  if (!taskId.value) { ElMessage.warning('请输入任务ID'); return }
  const res: any = await reportApi.get(Number(taskId.value))
  report.value = res.data
}
async function generateReport() {
  if (!taskId.value) return
  await reportApi.generate(Number(taskId.value))
  ElMessage.success('报告生成中')
  loadReport()
}
</script>
<style scoped>
.header-bar { margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
</style>
