<template>
  <div class="leads-panel" v-loading="loading">
    <div class="section-head">
      <span class="section-title">未核实线索</span>
      <span class="section-sub">
        引擎报告了弱点模式，<b>平台未核实真伪</b> ——
        污点分析看不穿接口/多态调用，校验可能就在被调用方的实现里
      </span>
    </div>

    <el-alert v-if="leads.length" type="info" :closable="false" show-icon class="mb12"
      title="这些是线索不是结论：引用前需下沉到代码核实（工作台可查看代码）" />

    <el-table v-if="leads.length" :data="leads" size="small" stripe>
      <el-table-column label="引擎判定" width="260">
        <template #default="{ row }"><span class="mono">{{ row.provider_rule_id }}</span></template>
      </el-table-column>
      <el-table-column label="风险类型" width="150">
        <template #default="{ row }">{{ riskLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="位置" min-width="280" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="mono dim">{{ compact(row.payload?.caller) || row.subject || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="110" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openCode(row)"
                     :disabled="!row.payload?.url">查看代码</el-button>
        </template>
      </el-table-column>
      <template #empty><EmptyBox description="无未核实线索" /></template>
    </el-table>
    <EmptyBox v-else description="本次没有引擎判定为弱点的线索" :image-size="60" />

    <el-drawer v-model="codeVisible" :title="codeTitle" size="720px">
      <EngineReportViewer v-if="codeObservationId" :task-id="taskId"
                          :observation-id="codeObservationId" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyBox from '@/components/EmptyBox.vue'
import EngineReportViewer from '@/components/EngineReportViewer.vue'
import { taskApi } from '@/api/tasks'

const props = defineProps<{ taskId: number }>()

const SINK_LABELS: Record<string, string> = {
  file: '路径穿越（文件）', ipc: 'IPC / Intent', network: '网络', log: '日志',
}

const loading = ref(false)
const leads = ref<any[]>([])
const codeVisible = ref(false)
const codeObservationId = ref<number | null>(null)
const codeTitle = ref('引擎报告')

function riskLabel(row: any) {
  return SINK_LABELS[row.sink_type] || row.provider_rule_id || '—'
}

function compact(signature?: string) {
  if (!signature) return ''
  const m = /<([^:>]+):[^>]*?([A-Za-z0-9_$<>]+)\(/.exec(signature)
  return m ? `${m[1]}.${m[2]}` : signature
}

function openCode(row: any) {
  codeObservationId.value = row.id
  codeTitle.value = `引擎报告 · ${row.provider_rule_id}`
  codeVisible.value = true
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    // 论断为「存在某个漏洞」的规则已降为 supporting_evidence（不再直接成结论），
    // 它们集中在这里展示，免得「检出来了却看不见」
    const res = await taskApi.observations(props.taskId, {
      result_semantics: 'supporting_evidence', observation_type: 'security.other',
      page_size: 1000,
    })
    leads.value = res.data?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.taskId, load)
</script>

<style scoped>
.section-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.section-title { font-weight: 600; font-size: 14px; }
.section-sub { color: #6B7A99; font-size: 12px; }
.mb12 { margin-bottom: 12px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.dim { color: #6B7A99; }
</style>
