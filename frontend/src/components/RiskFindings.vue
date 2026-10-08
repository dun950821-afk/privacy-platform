<template>
  <div class="risk" v-loading="loading">
    <!-- ① 平台结论：具备完整语义的观察直接形成，或经跨引擎证据增强
         任务详情页改用「问题清单」做主视图后，同一批结论不再在这里重复渲染 -->
    <el-card v-if="!hideFindings" shadow="never" class="block">
      <template #header>
        <div class="head">
          <span class="title">平台结论</span>
          <span class="count">{{ findings.length }}</span>
          <span class="sub">由具备完整语义的观察直接形成，或经跨引擎证据增强 —— 引用前看「依据」</span>
        </div>
      </template>
      <el-table v-if="findings.length" :data="findings" size="small">
        <el-table-column label="结论" min-width="300">
          <template #default="{ row }">
            <div class="code mono">{{ row.finding_code }}</div>
            <div class="sub-line">{{ row.title }}</div>
          </template>
        </el-table-column>
        <el-table-column label="严重性" width="90">
          <template #default="{ row }"><StatusTag :value="row.severity" :map="SEVERITY" /></template>
        </el-table-column>
        <el-table-column label="置信度" width="100">
          <template #default="{ row }"><StatusTag :value="row.confidence" :map="CONFIDENCE" /></template>
        </el-table-column>
        <el-table-column label="依据" min-width="260">
          <template #default="{ row }"><span class="dim">{{ evidenceText(row) }}</span></template>
        </el-table-column>
        <el-table-column label="证据" width="80" align="center">
          <template #default="{ row }">{{ row.observation_count ?? 0 }}</template>
        </el-table-column>
      </el-table>
      <EmptyBox v-else description="本次未形成平台结论" :image-size="60" />
    </el-card>

    <!-- ② 未核实线索：引擎报出的弱点模式，平台未核实真伪 -->
    <el-card shadow="never" class="block">
      <template #header>
        <div class="head">
          <span class="title">未核实线索</span>
          <span class="count">{{ leadSum }}</span>
          <span class="sub">
            引擎报出了弱点模式，<b>平台未核实真伪</b> —— 污点分析看不穿接口/多态调用，
            校验可能就在被调用方的实现里。这些是线索不是结论
          </span>
        </div>
      </template>
      <el-table v-if="leadsGrouped.length" :data="leadsGrouped" size="small">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="loc-list">
              <div v-for="(hit, i) in row.items" :key="i" class="loc-row">
                <span class="mono dim">{{ compact(hit.payload?.caller) || hit.subject || '—' }}</span>
                <el-button link type="primary" size="small" @click="openCode(hit)"
                           :disabled="!hit.payload?.url">查看代码</el-button>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="引擎判定" width="240">
          <template #default="{ row }"><span class="mono">{{ row.rule }}</span></template>
        </el-table-column>
        <el-table-column label="风险类型" width="150">
          <template #default="{ row }">{{ riskLabel(row) }}</template>
        </el-table-column>
        <el-table-column label="命中" width="80" align="center">
          <template #default="{ row }"><b>{{ row.items.length }}</b></template>
        </el-table-column>
        <el-table-column label="涉及方法" width="100" align="center">
          <template #default="{ row }">{{ row.methods }}</template>
        </el-table-column>
      </el-table>
      <EmptyBox v-else description="本次没有引擎判定为弱点的线索" :image-size="60" />
    </el-card>

    <el-drawer v-model="codeVisible" :title="codeTitle" size="720px">
      <EngineReportViewer v-if="codeObservationId" :task-id="taskId"
                          :observation-id="codeObservationId" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import EmptyBox from '@/components/EmptyBox.vue'
import StatusTag from '@/components/StatusTag.vue'
import EngineReportViewer from '@/components/EngineReportViewer.vue'
import { taskApi } from '@/api/tasks'
import { CONFIDENCE, SEVERITY } from '@/utils/dict'

const props = withDefaults(defineProps<{
  taskId: number
  /** 隐藏「平台结论」块：该数据已由问题清单主视图承载，避免同页重复 */
  hideFindings?: boolean
}>(), { hideFindings: false })
const emit = defineEmits<{ (e: 'count', n: number): void }>()

const SINK_LABELS: Record<string, string> = {
  file: '路径穿越（文件）', ipc: 'IPC / Intent', network: '网络', log: '日志',
}

const loading = ref(false)
const findings = ref<any[]>([])
const leads = ref<any[]>([])
const codeVisible = ref(false)
const codeObservationId = ref<number | null>(null)
const codeTitle = ref('引擎报告')

const leadSum = computed(() => leads.value.length)

/** 同一规则可能命中几十上百次（实测 PendingIntentMutable 64 处），按规则合并 */
const leadsGrouped = computed(() => {
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

function riskLabel(row: any) {
  return SINK_LABELS[row.sink_type] || row.rule || '—'
}

function evidenceText(row: any) {
  const snapshot = row.rule_snapshot || {}
  if (snapshot.source === 'direct_finding') {
    const parts = [snapshot.provider_rule_id, snapshot.data_category, snapshot.sink_type].filter(Boolean)
    return `直接结论：${parts.join(' · ') || row.finding_code}`
  }
  const enrichments = snapshot.enrichments || []
  if (enrichments.length) {
    const total = enrichments.reduce((n: number, e: any) => n + (e.evidence_observation_ids?.length || 0), 0)
    return `证据增强：+${total} 条同类目证据`
  }
  return row.correlation_rule_id ? '关联规则' : '—'
}

function compact(signature?: string) {
  if (!signature) return ''
  const m = /<([^:>]+):[^>]*?([A-Za-z0-9_$<>]+)\(/.exec(signature)
  return m ? `${m[1]}.${m[2]}` : signature
}

function openCode(row: any) {
  codeObservationId.value = row.id
  codeTitle.value = `引擎报告 · ${row.provider_rule_id || row.payload?.rule || ''}`
  codeVisible.value = true
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    const [findingsRes, leadsRes] = await Promise.allSettled([
      // hideFindings 时不请求平台结论：那块不渲染，请求它就是白发一次
      // （任务详情页已由问题清单主视图取同一份数据）
      props.hideFindings ? Promise.resolve(null) : taskApi.platformFindings(props.taskId),
      taskApi.observations(props.taskId, {
        result_semantics: 'supporting_evidence', observation_type: 'security.other', page_size: 1000,
      }),
    ])
    if (findingsRes.status === 'fulfilled' && findingsRes.value) {
      findings.value = (findingsRes.value as any).data?.items || []
    }
    if (leadsRes.status === 'fulfilled') {
      leads.value = (leadsRes.value as any).data?.items || []
    }
    emit('count', findings.value.length + leads.value.length)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.taskId, load)
</script>

<style scoped>
.block { margin-bottom: var(--space-4); }
.head { display: flex; align-items: baseline; gap: var(--space-2); flex-wrap: wrap; }
.title { font-size: var(--text-section); font-weight: 600; }
.count {
  display: inline-block; min-width: 22px; padding: 0 6px; border-radius: 10px;
  background: var(--surface-line-soft); color: var(--el-color-primary);
  font-size: var(--text-label); text-align: center; font-weight: 600;
}
.sub { color: var(--ink-3); font-size: var(--text-label); }
.code { font-weight: 600; }
.sub-line { color: var(--ink-3); font-size: var(--text-label); }
.loc-list { padding: var(--space-1) var(--space-3); }
.loc-row { display: flex; align-items: center; justify-content: space-between; gap: 12px;
           padding: 3px 0; border-bottom: 1px dashed #EEF1F6; }
.loc-row:last-child { border-bottom: none; }
.dim { color: #6B7A99; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
