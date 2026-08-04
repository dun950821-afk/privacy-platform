<template>
  <div class="page-container">
    <PageHeader title="审计日志" subtitle="平台操作审计追踪" />

    <el-card shadow="never">
      <div class="filter-bar">
        <el-input
          v-model="actorKeyword"
          placeholder="按操作者筛选（当前页）"
          clearable
          style="width: 220px"
        />
      </div>

      <el-table :data="filteredLogs" v-loading="loading" stripe>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="audit-detail">
              <div class="json-block">
                <div class="json-title">变更前 (before_json)</div>
                <pre class="json-pre">{{ fmtJson(row.before_json) }}</pre>
              </div>
              <div class="json-block">
                <div class="json-title">变更后 (after_json)</div>
                <pre class="json-pre">{{ fmtJson(row.after_json) }}</pre>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ fmtDateTimeFull(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作者" width="120">
          <template #default="{ row }">{{ row.actor_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="action" label="动作" min-width="140" show-overflow-tooltip />
        <el-table-column label="对象类型" width="120">
          <template #default="{ row }">{{ row.target_type || '-' }}</template>
        </el-table-column>
        <el-table-column label="对象ID" width="90">
          <template #default="{ row }">{{ row.target_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="来源IP" width="130">
          <template #default="{ row }">{{ row.source_ip || '-' }}</template>
        </el-table-column>
        <el-table-column label="请求ID" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.request_id || '-' }}</template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无审计日志" />
        </template>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          background
          @current-change="loadLogs"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { fmtDateTimeFull } from '@/utils/format'
import { systemApi } from '@/api/system'

interface AuditRow {
  id: number
  actor_name: string | null
  action: string
  target_type: string | null
  target_id: number | null
  source_ip: string | null
  request_id: string | null
  before_json?: unknown
  after_json?: unknown
  created_at: string | null
}

const loading = ref(false)
const logs = ref<AuditRow[]>([])
const page = ref(1)
const pageSize = 20
const total = ref(0)
const actorKeyword = ref('')

// 后端不支持操作者/时间过滤参数，操作者按当前页前端过滤
const filteredLogs = computed(() => {
  const kw = actorKeyword.value.trim().toLowerCase()
  if (!kw) return logs.value
  return logs.value.filter(l => (l.actor_name || '').toLowerCase().includes(kw))
})

function fmtJson(v: unknown): string {
  if (v === null || v === undefined || v === '') return '暂无数据'
  if (typeof v === 'string') {
    try {
      return JSON.stringify(JSON.parse(v), null, 2)
    } catch {
      return v
    }
  }
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

async function loadLogs() {
  loading.value = true
  try {
    const res: any = await systemApi.auditLogs(page.value, pageSize)
    logs.value = res.data.items || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

onMounted(loadLogs)
</script>

<style scoped>
.audit-detail {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 12px 24px;
}
.json-title {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
.json-pre {
  margin: 0;
  padding: 10px 12px;
  background: #f7f8fa;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow: auto;
}
</style>
