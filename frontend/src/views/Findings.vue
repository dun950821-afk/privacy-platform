<template>
  <div class="page-container">
    <PageHeader title="问题管理" subtitle="隐私合规问题的处置与跟踪" />

    <el-card shadow="never">
      <div class="filter-bar">
        <el-select v-model="filters.project_id" placeholder="所属项目" clearable filterable style="width: 200px">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-select v-model="filters.severity" placeholder="严重度" clearable style="width: 140px">
          <el-option v-for="(item, key) in SEVERITY" :key="key" :label="item.label" :value="key" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable style="width: 140px">
          <el-option v-for="(item, key) in FINDING_STATUS" :key="key" :label="item.label" :value="key" />
        </el-select>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>

      <el-table :data="findings" v-loading="loading" stripe>
        <el-table-column label="严重度" width="90" align="center">
          <template #default="{ row }">
            <StatusTag :value="row.severity" :map="SEVERITY" />
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button link type="primary" class="title-link" @click="goDetail(row.id)">
              {{ row.title }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="所属任务" width="170">
          <template #default="{ row }">{{ row.task_code || `#${row.task_id}` }}</template>
        </el-table-column>
        <el-table-column prop="data_type" label="数据类型" width="130">
          <template #default="{ row }">{{ row.data_type || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="FINDING_STATUS" />
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="110">
          <template #default="{ row }">{{ userName(row.assigned_to) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无问题，调整筛选条件试试" />
        </template>
      </el-table>

      <div class="pager">
        <el-pagination v-model:current-page="page" :page-size="20" :total="total"
          layout="total, prev, pager, next" background @current-change="loadData" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { findingApi } from '@/api/findings'
import { projectApi } from '@/api/projects'
import api from '@/api'
import { fmtDateTime } from '@/utils/format'
import { SEVERITY, FINDING_STATUS } from '@/utils/dict'

const router = useRouter()
const loading = ref(false)
const findings = ref<any[]>([])
const projects = ref<any[]>([])
const users = ref<any[]>([])
const page = ref(1)
const total = ref(0)
const filters = reactive({
  project_id: undefined as number | undefined,
  severity: '',
  status: '',
})

function userName(id?: number | null): string {
  if (!id) return '-'
  const u = users.value.find((x) => x.id === id)
  return u ? u.full_name || u.username : `#${id}`
}

function goDetail(id: number) {
  router.push(`/findings/${id}`)
}

async function loadData() {
  loading.value = true
  try {
    const res: any = await findingApi.list({
      project_id: filters.project_id || undefined,
      severity: filters.severity || undefined,
      status: filters.status || undefined,
      page: page.value,
      page_size: 20,
    })
    findings.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadData()
}

function handleReset() {
  filters.project_id = undefined
  filters.severity = ''
  filters.status = ''
  page.value = 1
  loadData()
}

onMounted(async () => {
  loadData()
  try {
    const res: any = await projectApi.list(1, 100)
    projects.value = res.data.items
  } catch { /* 项目筛选留空 */ }
  // 负责人 id -> 姓名映射（无权限时静默降级为 #id）
  try {
    const res: any = await api.get('/system/users', { params: { page_size: 100 }, silent: true })
    users.value = res.data
  } catch { /* 无用户读权限时显示 #id */ }
})
</script>

<style scoped>
.title-link {
  padding: 0;
  font-weight: 500;
}
</style>
