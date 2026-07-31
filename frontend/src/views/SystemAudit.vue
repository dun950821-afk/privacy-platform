<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar"><span class="page-title">审计日志</span></div>
      <el-table :data="logs" v-loading="loading" stripe size="small">
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column prop="actor_name" label="操作者" width="100" />
        <el-table-column prop="action" label="操作" />
        <el-table-column prop="target_type" label="对象类型" width="100" />
        <el-table-column prop="source_ip" label="IP" width="120" />
      </el-table>
      <el-pagination class="pager" v-model:current-page="page" :page-size="50"
        :total="total" layout="total, prev, pager, next" @current-change="loadData" />
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { systemApi } from '@/api/system'
const loading = ref(false)
const logs = ref<any[]>([])
const page = ref(1); const total = ref(0)
async function loadData() {
  loading.value = true
  try { const res: any = await systemApi.auditLogs(page.value, 50); logs.value = res.data.items; total.value = res.data.total } finally { loading.value = false }
}
onMounted(loadData)
</script>
<style scoped>
.header-bar { margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
.pager { margin-top:16px; justify-content:flex-end; }
</style>
