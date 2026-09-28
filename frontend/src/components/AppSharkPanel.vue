<template>
  <div class="engine-panel" v-loading="loading">
    <!-- 数据流：结论级。按「类目→流向 + 规则」合并——128 条里大半是同一条规则的重复，
         逐条平铺会把关键信息（哪类数据流向哪里、多少处）埋掉 -->
    <div class="section-head">
      <span class="section-title">数据流</span>
      <span class="section-sub">
        source→sink 路径 {{ flows.length }} 条，归为 {{ flowGroups.length }} 类 —— 每条都是完整结论
      </span>
    </div>
    <el-table v-if="flowGroups.length" :data="flowGroups" size="small" row-key="key">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="hit-list">
            <div v-for="(hit, i) in row.items" :key="i" class="hit-row">
              <span class="mono dim">{{ compact(hit.payload?.caller) || hit.subject }}</span>
              <el-button link type="primary" size="small" @click="openCode(hit)"
                         :disabled="!hit.payload?.url">查看代码</el-button>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="类目 → 流向" min-width="230">
        <template #default="{ row }">
          <span class="mono">{{ row.data_category || '—' }}</span>
          <span class="arrow">→</span>
          <span class="mono">{{ row.sink_type || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="规则" width="210">
        <template #default="{ row }"><span class="mono">{{ row.rule || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="命中" width="90" align="center">
        <template #default="{ row }"><b>{{ row.items.length }}</b></template>
      </el-table-column>
      <el-table-column label="涉及方法" width="100" align="center">
        <template #default="{ row }">{{ row.methods }}</template>
      </el-table-column>
      <template #empty><EmptyBox description="未检出数据流" /></template>
    </el-table>
    <EmptyBox v-else description="未检出数据流" :image-size="60" />

    <!-- 敏感 API 调用：事实级，同类合并 -->
    <div class="section-head">
      <span class="section-title">敏感 API 调用</span>
      <span class="section-sub">
        事实层证据，共 {{ apiHits.length }} 处 —— 同一规则合并展示，展开看调用点
      </span>
    </div>
    <el-table v-if="apiGroups.length" :data="apiGroups" size="small" row-key="key">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="hit-list">
            <div v-for="(hit, i) in row.items" :key="i" class="hit-row">
              <span class="mono dim">{{ compact(hit.payload?.caller) || hit.subject }}</span>
              <el-button link type="primary" size="small" @click="openCode(hit)"
                         :disabled="!hit.payload?.url">查看代码</el-button>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="规则" width="220">
        <template #default="{ row }"><span class="mono">{{ row.rule }}</span></template>
      </el-table-column>
      <el-table-column label="数据类目" width="180">
        <template #default="{ row }"><span class="mono">{{ row.data_category || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="命中" width="90" align="center">
        <template #default="{ row }">{{ row.items.length }}</template>
      </el-table-column>
      <el-table-column label="等级" width="80" align="center">
        <template #default="{ row }"><span class="mono dim">{{ row.level || '—' }}</span></template>
      </el-table-column>
      <template #empty><EmptyBox description="未检出敏感 API 调用" /></template>
    </el-table>
    <EmptyBox v-else description="未检出敏感 API 调用" :image-size="60" />

    <!-- 声明权限 -->
    <div class="section-head">
      <span class="section-title">声明权限</span>
      <span class="section-sub">{{ permissions.length }} 项（AppShark 从 manifest 解析）</span>
    </div>
    <div v-if="permissions.length" class="perm-wrap">
      <el-tag v-for="p in permissions" :key="p.subject" size="small" class="perm-tag">
        {{ p.subject }}
      </el-tag>
    </div>
    <EmptyBox v-else description="未解析到权限" :image-size="60" />

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

const loading = ref(false)
const observations = ref<any[]>([])
const codeVisible = ref(false)
const codeObservationId = ref<number | null>(null)
const codeTitle = ref('引擎报告')

const byType = (t: string) => observations.value.filter(o => o.observation_type === t)
const flows = computed(() => byType('dataflow.privacy'))
const apiHits = computed(() => byType('security.sensitive_api'))
const permissions = computed(() => byType('fact.permission'))

/** 数据流按「类目+流向+规则」合并，并数出涉及多少个不同的调用方法 */
const flowGroups = computed(() => groupBy(flows.value))

/** 敏感 API 调用按规则+类目合并：988 条平铺就是噪音 */
const apiGroups = computed(() => groupBy(apiHits.value))

/** 同一类结论往往命中几十上百次，合并后按命中数排——多的地方才值得先看 */
function groupBy(items: any[]) {
  const groups = new Map<string, any>()
  for (const hit of items) {
    const rule = hit.provider_rule_id || hit.payload?.rule || ''
    const key = `${hit.data_category || ''}|${hit.sink_type || ''}|${rule}`
    if (!groups.has(key)) {
      groups.set(key, { key, rule, data_category: hit.data_category,
                        sink_type: hit.sink_type, level: hit.provider_level, items: [] })
    }
    groups.get(key).items.push(hit)
  }
  return [...groups.values()]
    .map(g => ({ ...g, methods: new Set(g.items.map((i: any) => i.payload?.caller).filter(Boolean)).size }))
    .sort((a, b) => b.items.length - a.items.length)
}

function compact(signature?: string) {
  if (!signature) return ''
  // Jimple 方法签名太长，只留类名与方法名
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
    // 一次取全：AppShark 单任务可达上千条观察，前端聚合需要完整集合
    const res = await taskApi.observations(props.taskId, { engine_type: 'appshark', page_size: 5000 })
    observations.value = res.data?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.taskId, load)
</script>

<style scoped>
.engine-panel { font-size: 13px; }
.section-head { display: flex; align-items: baseline; gap: 10px; margin: 18px 0 8px; }
.section-head:first-child { margin-top: 0; }
.section-title { font-weight: 600; font-size: 14px; }
.section-sub { color: #6B7A99; font-size: 12px; }
.arrow { color: #B4BDCC; margin: 0 6px; }
.hit-list { padding: 4px 12px; }
.hit-row { display: flex; align-items: center; justify-content: space-between; gap: 12px;
           padding: 3px 0; border-bottom: 1px dashed #EEF1F6; }
.hit-row:last-child { border-bottom: none; }
.perm-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.dim { color: #6B7A99; }
</style>
