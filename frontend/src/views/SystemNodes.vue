<template>
  <div class="page-container">
    <PageHeader title="节点设备" subtitle="检测 Agent 节点与 Android 设备池">
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </PageHeader>

    <!-- 节点卡片区 -->
    <div class="section-title">检测节点</div>
    <div v-loading="loading">
      <div v-if="nodes.length" class="node-grid">
        <div v-for="n in nodes" :key="n.id" class="node-card">
          <div class="node-head">
            <span class="node-name">{{ n.node_name || n.node_uid }}</span>
            <StatusTag :value="n.status" :map="NODE_STATUS" />
          </div>
          <div class="node-uid">{{ n.node_uid }}</div>
          <div class="node-meta">
            <span>类型：{{ n.node_type || '-' }}</span>
            <span>最近心跳：{{ fmtDateTime(n.last_heartbeat_at) }}</span>
          </div>
          <div v-if="capList(n.capabilities).length" class="node-caps">
            <el-tag
              v-for="c in capList(n.capabilities)"
              :key="c"
              size="small"
              effect="plain"
              class="cap-tag"
            >
              {{ c }}
            </el-tag>
          </div>
          <div v-if="toolEntries(n.tools_info).length" class="node-tools">
            <div v-for="t in toolEntries(n.tools_info)" :key="t.k" class="tool-row">
              <span class="tool-key">{{ t.k }}</span>
              <span class="tool-val">{{ t.v }}</span>
            </div>
          </div>
        </div>
      </div>
      <el-card v-else shadow="never" class="empty-card">
        <EmptyBox description="暂无节点" />
      </el-card>
    </div>

    <!-- 设备表格 -->
    <div class="section-title">设备池</div>
    <el-card shadow="never">
      <el-table :data="devices" v-loading="loading" stripe>
        <el-table-column prop="serial" label="序列号" min-width="160" show-overflow-tooltip />
        <el-table-column label="品牌 / 型号" min-width="160">
          <template #default="{ row }">
            {{ [row.brand, row.model].filter(Boolean).join(' ') || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Android 版本" width="120">
          <template #default="{ row }">{{ row.android_version || '-' }}</template>
        </el-table-column>
        <el-table-column label="Root" width="80">
          <template #default="{ row }">
            <StatusTag :value="String(!!row.is_rooted)" :map="BOOL_TAG" />
          </template>
        </el-table-column>
        <el-table-column label="Frida" width="80">
          <template #default="{ row }">
            <StatusTag :value="String(!!row.is_frida_ready)" :map="BOOL_TAG" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="NODE_STATUS" />
          </template>
        </el-table-column>
        <el-table-column label="最近在线" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.last_seen_at) }}</template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无设备" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { fmtDateTime } from '@/utils/format'
import { NODE_STATUS, BOOL_TAG } from '@/utils/dict'
import { systemApi } from '@/api/system'

interface NodeRow {
  id: number
  node_uid: string
  node_name: string | null
  node_type: string | null
  status: string | null
  capabilities: unknown
  tools_info: unknown
  last_heartbeat_at: string | null
}

interface DeviceRow {
  id: number
  serial: string
  brand: string | null
  model: string | null
  android_version: string | null
  is_rooted: boolean
  is_frida_ready: boolean
  status: string | null
  agent_id: number | null
  last_seen_at: string | null
}

const loading = ref(false)
const nodes = ref<NodeRow[]>([])
const devices = ref<DeviceRow[]>([])

/** capabilities 兼容数组或对象两种 JSON 结构 */
function capList(caps: unknown): string[] {
  if (Array.isArray(caps)) return caps.map(String)
  if (caps && typeof caps === 'object') return Object.keys(caps as Record<string, unknown>)
  return []
}

/** tools_info 展开为键值对，简要展示 */
function toolEntries(info: unknown): Array<{ k: string; v: string }> {
  if (!info || typeof info !== 'object' || Array.isArray(info)) return []
  return Object.entries(info as Record<string, unknown>).map(([k, v]) => ({
    k,
    v: v === null || v === undefined ? '-' : typeof v === 'object' ? JSON.stringify(v) : String(v),
  }))
}

async function loadAll() {
  loading.value = true
  try {
    const [nodeRes, deviceRes]: any[] = await Promise.all([
      systemApi.nodes(),
      systemApi.devices(),
    ])
    nodes.value = nodeRes.data || []
    devices.value = deviceRes.data || []
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}
.node-card {
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  transition: box-shadow 0.2s;
}
.node-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}
.node-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.node-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.node-uid {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.node-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.node-caps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.cap-tag {
  font-size: 11px;
}
.node-tools {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.tool-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  line-height: 22px;
}
.tool-key {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.tool-val {
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty-card {
  padding: 20px 0;
}
</style>
