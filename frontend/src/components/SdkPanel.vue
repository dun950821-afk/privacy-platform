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

      <el-table :data="hits" size="small" row-key="hit_id">
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

      <div class="group-head">
        <span class="group-name">采集调用点里认不出归属的包</span>
        <span class="group-count">{{ unattributedSum }} 处 · {{ unattributed.length }} 个包</span>
        <span class="group-hint">按调用点的包前缀聚合</span>
      </div>
      <el-table v-if="unattributed.length" :data="unattributed" size="small" max-height="320">
        <el-table-column label="包前缀" min-width="280">
          <template #default="{ row }"><span class="mono">{{ row.package_prefix }}</span></template>
        </el-table-column>
        <el-table-column label="采集点" width="90" align="center">
          <template #default="{ row }"><b>{{ row.call_site_count }}</b></template>
        </el-table-column>
        <el-table-column label="涉及个人信息" min-width="240">
          <template #default="{ row }">
            <span class="dim">{{ row.categories.map(cn).join('、') }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="dim">无</div>

      <div class="group-head">
        <span class="group-name">清单里没匹配上知识库的三方包</span>
        <span class="group-count">{{ clusters.length }} 个</span>
        <span class="group-hint">来自 manifest 组件匹配</span>
      </div>
      <el-table v-if="clusters.length" :data="clusters" size="small" max-height="320">
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
      <div v-else class="dim">无（本次清单中的三方包都匹配上了知识库）</div>
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

function scoreColor(score: number) {
  if (score >= 80) return '#F56C6C'
  if (score >= 50) return '#E6A23C'
  return '#909399'
}

const STATUS_CN: Record<string, [string, string]> = {
  CONFIRMED: ['已确认', 'danger'],
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
.sdk-panel { font-size: 13px; }
.block { margin-bottom: 14px; }
.head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.title { font-size: 15px; font-weight: 600; }
.count {
  display: inline-block; min-width: 22px; padding: 0 6px; border-radius: 10px;
  background: #EEF1F6; color: #2B5AED; font-size: 12px; text-align: center; font-weight: 600;
}
.sub { color: #6B7A99; font-size: 12px; }
.group-head { display: flex; align-items: baseline; gap: 10px; margin: 14px 0 6px; flex-wrap: wrap; }
.group-head:first-child { margin-top: 0; }
.group-name { font-weight: 600; }
.group-count { color: #6B7A99; font-size: 12px; }
.group-hint { color: #2B5AED; font-size: 12px; }
.sub-line { color: #6B7A99; font-size: 11px; }
.note { margin-top: 12px; }
.note-title { color: #6B7A99; font-size: 12px; margin-bottom: 4px; }
.ev-row { padding: 2px 0; border-bottom: 1px dashed #EEF1F6; word-break: break-all; }
.dim { color: #6B7A99; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
