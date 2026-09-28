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

    <el-table v-if="groups.length" :data="groups" size="small" row-key="key">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="hit-list">
            <div v-for="(hit, i) in row.items" :key="i" class="hit-row">
              <span class="mono dim">{{ compact(hit.payload?.caller) || hit.subject || '—' }}</span>
              <el-button link type="primary" size="small" @click="openCode(hit)"
                         :disabled="!hit.payload?.url">查看代码</el-button>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="引擎判定" width="260">
        <template #default="{ row }"><span class="mono">{{ row.rule }}</span></template>
      </el-table-column>
      <el-table-column label="风险类型" width="150">
        <template #default="{ row }">{{ riskLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="命中" width="90" align="center">
        <template #default="{ row }"><b>{{ row.items.length }}</b></template>
      </el-table-column>
      <el-table-column label="涉及方法" width="100" align="center">
        <template #default="{ row }">{{ row.methods }}</template>
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
  return SINK_LABELS[row.sink_type] || row.rule || '—'
}

/** 同一规则可能命中几十上百次（实测 PendingIntentMutable 65 处），
    平铺是一堵重复墙；按「规则+风险类型」合并，展开再看具体位置 */
const groups = computed(() => {
  const map = new Map<string, any>()
  for (const hit of leads.value) {
    const rule = hit.provider_rule_id || hit.payload?.rule || '(未登记规则)'
    const key = `${rule}|${hit.sink_type || ''}`
    if (!map.has(key)) map.set(key, { key, rule, sink_type: hit.sink_type, items: [] })
    map.get(key).items.push(hit)
  }
  return [...map.values()]
    .map(g => ({ ...g, methods: new Set(g.items.map((i: any) => i.payload?.caller).filter(Boolean)).size }))
    .sort((a, b) => b.items.length - a.items.length)
})

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
.hit-list { padding: 4px 12px; }
.hit-row { display: flex; align-items: center; justify-content: space-between; gap: 12px;
           padding: 3px 0; border-bottom: 1px dashed #EEF1F6; }
.hit-row:last-child { border-bottom: none; }
</style>
