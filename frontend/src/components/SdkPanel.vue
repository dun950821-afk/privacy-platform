<template>
  <div class="sdk-panel" v-loading="loading">
    <!-- ① 已识别：知识库匹配到的第三方组件 -->
    <el-card shadow="never" class="block">
      <template #header>
        <div class="head">
          <span class="title">已识别第三方组件</span>
          <span class="count">{{ hits.length }}</span>
          <span class="sub">点名称看证据；「涉及信息」与「合规备注」来自平台知识库</span>
        </div>
      </template>

      <el-table :data="hits" size="small" row-key="hit_id" class="data-table">
        <el-table-column label="组件名称" min-width="230">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.sdk_name }}</el-button>
            <div class="sub-line">{{ row.primary_package || (row.package_prefixes || [])[0] || '' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="厂商" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.vendor || '—' }}</template>
        </el-table-column>
        <el-table-column label="分类" width="110">
          <template #default="{ row }">{{ row.category || '—' }}</template>
        </el-table-column>
        <el-table-column label="涉及个人信息" min-width="220">
          <template #default="{ row }">
            <span v-if="row.involved_info?.length">{{ row.involved_info.join('、') }}</span>
            <span v-else class="dim">知识库未标注</span>
          </template>
        </el-table-column>
        <el-table-column label="敏感权限" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sensitive_permission" type="danger" size="small">涉及</el-tag>
            <span v-else class="dim">否</span>
          </template>
        </el-table-column>
        <el-table-column label="匹配度" width="150">
          <template #default="{ row }">
            <el-progress :percentage="row.total_score" :stroke-width="6"
                         :color="scoreColor(row.total_score)" :show-text="false" />
            <span class="sub-line">{{ row.total_score }} · 证据 {{ row.evidence_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.hit_status)" size="small">{{ statusLabel(row.hit_status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ② 暂时无法识别：两个层面，分开说清楚是哪一层没认出来 -->
    <el-card shadow="never" class="block">
      <template #header>
        <div class="head">
          <span class="title">暂时无法识别</span>
          <span class="sub">
            知识库指纹未覆盖 —— 这些不是「应用自身」，是「还不知道是谁」
          </span>
        </div>
      </template>

      <!-- 0 值折叠成一行：此前一个 0 要占「标题行 + 无数据行」两行 -->
      <div v-if="!unattributed.length" class="zero-line">
        采集调用点里认不出归属的包：0 处
      </div>
      <template v-else>
        <div class="group-head">
          <span class="group-name">采集调用点里认不出归属的包</span>
          <span class="group-count">{{ unattributedSum }} 处 · {{ unattributed.length }} 个包</span>
          <span class="group-hint">按调用点的包前缀聚合</span>
        </div>
        <el-table :data="unattributed" size="small" max-height="320" class="data-table">
          <el-table-column label="包前缀" min-width="280">
            <template #default="{ row }"><span class="mono">{{ row.package_prefix }}</span></template>
          </el-table-column>
          <el-table-column label="采集点" width="90" align="center">
            <template #default="{ row }"><b class="t-num">{{ row.call_site_count }}</b></template>
          </el-table-column>
          <el-table-column label="涉及个人信息" min-width="240">
            <template #default="{ row }">
              <span class="dim">{{ row.categories.map(cn).join('、') }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <div v-if="!clusters.length" class="zero-line">
        清单里没匹配上知识库的三方包：0 个 —— 本次的调用点都已归属到具体组件
      </div>
      <template v-else>
        <div class="group-head">
          <span class="group-name">识别不出归属的包</span>
          <span class="group-count">{{ clusters.length }} 个</span>
          <span class="group-hint">来自调用点与清单里的类名，按包前缀聚类</span>
        </div>
        <el-table :data="clusters" size="small" max-height="320" class="data-table">
          <el-table-column label="包名前缀" min-width="260">
            <template #default="{ row }"><span class="mono">{{ row.package_prefix }}</span></template>
          </el-table-column>
          <el-table-column prop="class_count" label="类数量" width="90" align="center" />
          <el-table-column label="组件分布" min-width="200">
            <template #default="{ row }">
              <span class="dim">{{ typeStatText(row.component_type_stat) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="推测属性" width="140">
            <template #default="{ row }">{{ row.identified_name || '待分析' }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <el-drawer v-model="detailVisible" :title="detail?.sdk_name || '组件详情'" size="720px">
      <template v-if="detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="厂商">{{ detail.vendor || '—' }}</el-descriptions-item>
          <el-descriptions-item label="分类">{{ detail.category || '—' }}</el-descriptions-item>
          <el-descriptions-item label="敏感级别">{{ detail.sensitivity_level || '—' }}</el-descriptions-item>
          <el-descriptions-item label="包名前缀">
            <span class="mono">{{ (detail.package_prefixes || []).join('  ') || detail.primary_package || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="涉及个人信息">
            {{ detail.involved_info?.length ? detail.involved_info.join('、') : '知识库未标注' }}
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.compliance_note" class="note">
          <div class="note-title">合规备注（知识库）</div>
          <div>{{ detail.compliance_note }}</div>
        </div>
        <div class="note">
          <div class="note-title">命中证据（{{ detail.evidence?.length || 0 }}）</div>
          <div v-for="(ev, i) in detail.evidence || []" :key="i" class="ev-row mono">
            {{ ev.evidence_value || ev.value || ev }}
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import api from '@/api'
import { DATA_CATEGORY_CN } from '@/utils/complianceDict'

const props = defineProps<{ taskId: number; unattributed?: any[] }>()

const loading = ref(false)
const hits = ref<any[]>([])
const clusters = ref<any[]>([])
const detail = ref<any>(null)
const detailVisible = ref(false)

const unattributed = computed(() => props.unattributed || [])
const unattributedSum = computed(() =>
  unattributed.value.reduce((n: number, i: any) => n + i.call_site_count, 0))

const cn = (key: string) => DATA_CATEGORY_CN[key] || key

/** 阈值与后端 _confidence() 一致：>=70 CONFIRMED、>=40 PROBABLE、其余 CANDIDATE。
 *  此前前端是 80/50，会出现进度条显示「高」而状态标签显示「大概率」的自相矛盾。
 *  配色也一并纠正：匹配度高是**确定**，不是危险，此前用红色（danger）读起来像报警，
 *  8 个组件全红等于没有红色。 */
function scoreColor(score: number) {
  if (score >= 70) return '#18A058'
  if (score >= 40) return '#F0A020'
  return '#B4BDCC'
}

const STATUS_CN: Record<string, [string, string]> = {
  CONFIRMED: ['已确认', 'success'],
  PROBABLE: ['大概率', 'warning'],
  CANDIDATE: ['候选', 'info'],
  REJECTED: ['已驳回', 'info'],
  WHITELISTED: ['已白名单', 'success'],
}
const statusLabel = (s: string) => (STATUS_CN[s] || [s, 'info'])[0] as string
const statusType = (s: string) => (STATUS_CN[s] || [s, 'info'])[1] as any

function typeStatText(stat: any) {
  if (!stat || typeof stat !== 'object') return '—'
  return Object.entries(stat).map(([k, v]) => `${k} ${v}`).join(' · ')
}

async function openDetail(row: any) {
  detailVisible.value = true
  detail.value = row
  try {
    const res: any = await api.get(`/tasks/${props.taskId}/sdk-hits/${row.hit_id}`)
    detail.value = { ...row, ...(res.data || {}) }
  } catch { /* 详情取不到就展示列表里的字段 */ }
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    const [hitsRes, clustersRes] = await Promise.allSettled([
      api.get(`/tasks/${props.taskId}/sdk-hits`),
      api.get(`/tasks/${props.taskId}/package-clusters`),
    ])
    if (hitsRes.status === 'fulfilled') hits.value = (hitsRes.value as any).data || []
    if (clustersRes.status === 'fulfilled') clusters.value = (clustersRes.value as any).data || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.taskId, load)
</script>

<style scoped>
.sdk-panel { font-size: var(--text-body); }
.block { margin-bottom: var(--space-4); }
.head { display: flex; align-items: baseline; gap: var(--space-2); flex-wrap: wrap; }
.title { font-size: var(--text-section); font-weight: 600; }
.count {
  display: inline-block; min-width: 22px; padding: 0 6px; border-radius: 10px;
  background: var(--surface-line-soft); color: var(--el-color-primary);
  font-size: var(--text-label); text-align: center; font-weight: 600;
}
.sub { color: var(--ink-3); font-size: var(--text-label); }
.group-head {
  display: flex; align-items: baseline; gap: var(--space-2);
  margin: var(--space-4) 0 var(--space-1); flex-wrap: wrap;
}
.group-head:first-child { margin-top: 0; }
.group-name { font-weight: 600; }
.group-count { color: var(--ink-3); font-size: var(--text-label); }
.group-hint { color: var(--el-color-primary); font-size: var(--text-label); }
.sub-line { color: var(--ink-3); font-size: var(--text-micro); }
.note { margin-top: var(--space-3); }
.note-title { color: var(--ink-3); font-size: var(--text-label); margin-bottom: var(--space-1); }
.ev-row { padding: 2px 0; border-bottom: 1px dashed var(--surface-line-soft); word-break: break-all; }
.dim { color: var(--ink-3); }
.mono {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", "JetBrains Mono",
    Menlo, Consolas, "Liberation Mono", monospace;
}
</style>
