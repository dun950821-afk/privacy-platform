<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar"><span class="page-title">问题管理</span></div>
      <div class="filter-bar">
        <el-select v-model="filterSeverity" placeholder="等级" clearable @change="loadData" style="width:100px">
          <el-option label="严重" value="critical" /><el-option label="高" value="high" />
          <el-option label="中" value="medium" /><el-option label="低" value="low" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable @change="loadData" style="width:120px">
          <el-option label="待处理" value="open" /><el-option label="已分派" value="assigned" />
          <el-option label="已修复" value="closed_fixed" /><el-option label="误报" value="closed_false_positive" />
        </el-select>
      </div>
      <el-table :data="findings" v-loading="loading" stripe @row-click="(r:any) => $router.push(`/findings/${r.id}`)">
        <el-table-column prop="title" label="标题" show-overflow-tooltip />
        <el-table-column prop="severity" label="等级" width="80">
          <template #default="{ row }">
            <el-tag :type="severityType(row.severity)" size="small">{{ severityLabel(row.severity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="app_name" label="App" width="120" />
        <el-table-column prop="data_type" label="数据类型" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
      </el-table>
      <el-pagination class="pager" v-model:current-page="page" :page-size="20"
        :total="total" layout="total, prev, pager, next" @current-change="loadData" />
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { findingApi } from '@/api/findings'

const loading = ref(false)
const findings = ref<any[]>([])
const page = ref(1); const total = ref(0)
const filterSeverity = ref(''); const filterStatus = ref('')

async function loadData() {
  loading.value = true
  try {
    const res: any = await findingApi.list({ severity: filterSeverity.value || undefined, status: filterStatus.value || undefined, page: page.value, page_size: 20 })
    findings.value = res.data.items; total.value = res.data.total
  } finally { loading.value = false }
}
function severityType(s:string){const m:Record<string,string>={critical:'danger',high:'danger',medium:'warning',low:'info'};return m[s]||''}
function severityLabel(s:string){const m:Record<string,string>={critical:'严重',high:'高',medium:'中',low:'低',info:'提示'};return m[s]||s}
onMounted(loadData)
</script>
<style scoped>
.header-bar { margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
.filter-bar { display:flex; gap:8px; margin-bottom:12px; }
.pager { margin-top:16px; justify-content:flex-end; }
</style>
