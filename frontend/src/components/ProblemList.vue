<template>
  <div class="problems" v-loading="loading">
    <!-- 结论条：主视图先回答「有几件事、有多急」，再给逐条清单 -->
    <div v-if="items.length" class="digest">
      <div class="digest-stat">
        <span class="digest-num is-high">{{ counts.high }}</span>
        <span class="digest-cap">高危</span>
      </div>
      <span class="digest-div"></span>
      <div class="digest-stat">
        <span class="digest-num is-medium">{{ counts.medium }}</span>
        <span class="digest-cap">中危</span>
      </div>
      <span class="digest-div"></span>
      <span class="digest-total">共 <b class="t-num">{{ items.length }}</b> 项结论</span>
    </div>

    <!-- 折叠态卡片：一条结论一张，按严重度排序，high 在前 -->
    <el-collapse v-if="items.length" v-model="openIds" class="cards">
      <el-collapse-item v-for="f in items" :key="f.id" :name="f.id">
        <template #title>
          <div class="card-head">
            <StatusTag :value="f.severity" :map="SEVERITY" />
            <span class="card-title">{{ f.title || f.finding_code || '-' }}</span>
            <span v-if="composition(f)" class="card-composition">{{ composition(f) }}</span>
            <span class="card-fill"></span>
            <span class="card-evidence">证据 <b class="t-num">{{ f.observation_count ?? 0 }}</b> 处</span>
            <StatusTag :value="f.triage_status" :map="TRIAGE_STATUS" />
          </div>
        </template>

        <div class="card-body">
          <div class="card-field">
            <span class="card-key">规则标识</span>
            <span class="card-val t-mono">{{ f.finding_code || '-' }}</span>
          </div>
          <div class="card-field">
            <span class="card-key">维度</span>
            <span class="card-val">{{ CATEGORY_CN[f.category] || f.category || '-' }}</span>
          </div>
          <div class="card-field">
            <span class="card-key">置信度</span>
            <span class="card-val">{{ dictLabel(CONFIDENCE, f.confidence) }}</span>
          </div>
          <div v-if="f.recommendation" class="card-field">
            <span class="card-key">建议</span>
            <span class="card-val">{{ f.recommendation }}</span>
          </div>
          <div class="card-field">
            <span class="card-key">负责人</span>
            <span class="card-val">{{ f.assigned_to != null ? userName(f.assigned_to) : '未指派' }}</span>
          </div>
          <div class="card-field">
            <span class="card-key">截止日期</span>
            <span class="card-val t-num">{{ f.due_date || '未设置' }}</span>
          </div>

          <template v-if="isOpen(f.id)">
            <!-- 整改操作放在证据之上：证据可能上百条，把操作沉到列表末尾等于藏起来。
                 只改 triage_status / assigned_to / due_date（不动计数与严重度） -->
            <div v-if="drafts[f.id]" class="card-actions">
              <div class="act">
                <span class="act-key">整改状态</span>
                <el-select v-model="drafts[f.id].triage_status" size="small" style="width: 118px">
                  <el-option v-for="(v, k) in TRIAGE_STATUS" :key="k" :label="v.label" :value="k" />
                </el-select>
              </div>
              <div class="act">
                <span class="act-key">负责人</span>
                <el-select v-model="drafts[f.id].assigned_to" size="small" clearable filterable
                           placeholder="未指派" style="width: 160px">
                  <el-option v-for="u in users" :key="u.id" :value="u.id"
                             :label="u.full_name || u.username" />
                </el-select>
              </div>
              <div class="act">
                <span class="act-key">截止日期</span>
                <el-date-picker v-model="drafts[f.id].due_date" type="date" size="small"
                                value-format="YYYY-MM-DD" placeholder="未设置" style="width: 150px" />
              </div>
              <span class="act-fill"></span>
              <el-button type="primary" size="small" :loading="savingId === f.id"
                         @click="saveStatus(f)">保存</el-button>
            </div>

            <!-- 证据块只在卡片展开时挂载：否则每张卡一进页面就各自打接口。
                 网络证据是任务级数据，已搬到 App 背景面板，这里只留代码证据。 -->
            <CodeEvidenceBlock :task-id="taskId" :finding-id="f.id" />
          </template>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 失败态必须与「确实没有结论」分开：接口挂了不等于「本次未形成平台结论」——
         在合规产品里「没有问题」是一句有结论意义的话，不能由失败冒充 -->
    <div v-else-if="loadError" class="load-error">
      <div class="load-error-body">
        <span class="load-error-title">问题清单加载失败</span>
        <span class="load-error-reason">{{ loadError }}</span>
      </div>
      <el-button size="small" :icon="RefreshRight" :loading="loading" @click="load">重试</el-button>
    </div>

    <EmptyBox v-else-if="!loading" description="本次未形成平台结论" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshRight } from '@element-plus/icons-vue'
import EmptyBox from '@/components/EmptyBox.vue'
import StatusTag from '@/components/StatusTag.vue'
import CodeEvidenceBlock from '@/components/CodeEvidenceBlock.vue'
import api from '@/api'
import { taskApi } from '@/api/tasks'
import { CONFIDENCE, SEVERITY, TRIAGE_STATUS, dictLabel } from '@/utils/dict'

const props = defineProps<{ taskId: number }>()

const loading = ref(false)
const findings = ref<any[]>([])
const openIds = ref<number[]>([])
/** 取数失败的原因。与「确实没有结论」是两回事，见模板里的失败态 */
const loadError = ref('')

/** el-collapse 的 v-model 就是展开中的 finding id 列表 */
function isOpen(id: number): boolean {
  return openIds.value.includes(id)
}

/**
 * 构成说明的词面。L2/L3/L4 是三个规则族，不是严重度阶梯（同一规则不跨 level）。
 * L4（安全缺陷）与隐私合规是两个维度，归 App 背景面板的「安全加固」块，
 * 所以卡片只列 L2 + L3。
 */
const LEVEL_CN: Record<string, string> = {
  L2: '敏感 API 调用',
  L3: '数据流',
  L4: '安全缺陷',
}
/** 卡片构成说明只体现隐私维度；顺序固定 L2 → L3，避免同一 finding 每次渲染顺序不同 */
const CARD_LEVELS = ['L2', 'L3']
const CATEGORY_CN: Record<string, string> = { privacy: '隐私', security: '安全' }
/** high 在前。同一严重度保持接口返回顺序（sort 稳定） */
const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }

const items = computed(() =>
  [...findings.value].sort(
    (a, b) => (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9),
  ),
)

/** 结论条只聚合 high / medium —— 与卡片主标签同一套词面 */
const counts = computed(() => {
  const c = { high: 0, medium: 0 }
  for (const f of findings.value) {
    const s = String(f.severity || '').toLowerCase()
    if (s === 'high') c.high += 1
    else if (s === 'medium') c.medium += 1
  }
  return c
})

/**
 * 无 provider_level_summary（历史结论可能没有 provider_level）时返回 null，
 * 卡片上整行不渲染 —— 不显示「由 构成」，也不显示「0 条」。
 */
function composition(f: any): string | null {
  const summary = f?.provider_level_summary
  const parts = CARD_LEVELS
    .filter((k) => summary?.[k])
    .map((k) => `${summary[k]} 条${LEVEL_CN[k]}`)
  return parts.length ? `由 ${parts.join(' + ')}构成` : null
}

// ============ 整改操作 ============
interface Draft { triage_status: string; assigned_to: number | null; due_date: string | null }

const users = ref<any[]>([])
const drafts = reactive<Record<number, Draft>>({})
const savingId = ref<number | null>(null)

const userName = (id: number) => {
  const u = users.value.find((x) => x.id === id)
  return u ? (u.full_name || u.username) : `#${id}`
}

/** 编辑态取自列表项；只在缺失时播种，避免刷新列表把用户正在改的草稿冲掉 */
function seedDrafts() {
  for (const f of findings.value) {
    if (!drafts[f.id]) {
      drafts[f.id] = {
        triage_status: f.triage_status || 'needs_review',
        assigned_to: f.assigned_to ?? null,
        due_date: f.due_date || null,
      }
    }
  }
}

async function loadUsers() {
  try {
    const res: any = await api.get('/system/users', { params: { page_size: 100 }, silent: true })
    users.value = res.data || []
  } catch {
    users.value = [] // 取不到就只影响下拉里的名字，不阻塞整改
  }
}

/** 后端 400 的 detail 是可读文案；两种 reject 形状都要兜住 */
function errorText(e: any): string {
  return e?.response?.data?.detail || e?.detail || e?.message || '保存失败'
}

async function saveStatus(f: any) {
  const d = drafts[f.id]
  if (!d) return
  savingId.value = f.id
  try {
    const res: any = await taskApi.updateFindingStatus(props.taskId, f.id, {
      triage_status: d.triage_status,
      assigned_to: d.assigned_to ?? null,
      due_date: d.due_date || null,
    })
    // 以服务端返回为准回写：triage_status/assigned_to/due_date 这三个字段由它拍板
    Object.assign(f, res.data || {})
    drafts[f.id] = {
      triage_status: f.triage_status || 'needs_review',
      assigned_to: f.assigned_to ?? null,
      due_date: f.due_date || null,
    }
    ElMessage.success('整改信息已保存')
  } catch (e: any) {
    ElMessage.error(errorText(e))
  } finally {
    savingId.value = null
  }
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  loadError.value = ''
  try {
    const res: any = await taskApi.platformFindings(props.taskId)
    findings.value = res.data?.items || []
    seedDrafts()
  } catch (e: any) {
    // 必须 catch：否则 (a) 失败会落到 EmptyBox，把「请求挂了」渲染成「本次未形成平台结论」；
    // (b) onMounted 返回的 rejected promise 会被 Vue 生命周期捕获并 console.error。
    // 同时清空列表，避免切换 taskId 后把上一个任务的结论当成本次结果展示。
    findings.value = []
    loadError.value = e?.message || e?.detail || '无法获取问题清单'
  } finally {
    loading.value = false
  }
}

onMounted(() => { load(); loadUsers() })
watch(() => props.taskId, () => {
  // 换任务时收起所有卡片、清掉草稿：展开态里的证据与草稿都是上一个任务的，留着会张冠李戴
  openIds.value = []
  for (const k of Object.keys(drafts)) delete drafts[Number(k)]
  load()
  loadUsers()
})
</script>

<style scoped>
.problems { min-height: 80px; }

/* 结论条：与卡片同表面，只靠字号/字重分主次 */
.digest {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  padding: var(--card-pad) var(--space-4);
  margin-bottom: var(--space-3);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}
.digest-stat { display: flex; align-items: baseline; gap: var(--space-2); }
.digest-num {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: -0.4px;
  color: var(--ink-4);
  font-variant-numeric: tabular-nums;
}
.digest-num.is-high { color: var(--el-color-danger); }
.digest-num.is-medium { color: var(--el-color-warning); }
.digest-cap { font-size: var(--text-label); color: var(--ink-3); }
.digest-div { width: 1px; height: 16px; background: var(--line); align-self: center; }
.digest-total { margin-left: auto; font-size: var(--text-label); color: var(--ink-3); }

/* 卡片列表：每张卡自带边框圆角，彼此留 8px */
.cards { border-top: none; border-bottom: none; }
.cards :deep(.el-collapse-item) {
  margin-bottom: var(--space-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.cards :deep(.el-collapse-item__header) {
  height: auto;
  min-height: var(--row-h);
  padding: var(--space-2) var(--space-3);
  gap: var(--space-2);
  font-size: var(--text-body);
  background: transparent;
  border-bottom: none;
}
.cards :deep(.el-collapse-item__header.is-active) { border-bottom: 1px solid var(--line); }
.cards :deep(.el-collapse-item__arrow) { color: var(--ink-4); }
.cards :deep(.el-collapse-item__wrap) { border-bottom: none; }
.cards :deep(.el-collapse-item__content) {
  padding: var(--space-2) var(--space-3) var(--space-3);
  font-size: var(--text-body);
}

.card-head { display: flex; align-items: center; gap: var(--space-2); flex: 1; min-width: 0; }
.card-title { font-weight: 600; color: var(--ink); min-width: 0; }
.card-composition { font-size: var(--text-label); color: var(--ink-3); flex-shrink: 0; }
.card-fill { flex: 1; }
.card-evidence { font-size: var(--text-label); color: var(--ink-3); flex-shrink: 0; }
.card-evidence b { color: var(--ink-2); }

/* 失败态：沿用 TaskDetail 里 .failed-reason 的告警配色，不引入新色 */
.load-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--card-pad) var(--space-4);
  background: #FEF0F0;
  border: 1px solid #FECACA;
  border-radius: 8px;
}
.load-error-body { display: flex; align-items: baseline; gap: var(--space-2); min-width: 0; flex-wrap: wrap; }
.load-error-title { font-size: var(--text-body); font-weight: 600; color: var(--el-color-danger); }
.load-error-reason { font-size: var(--text-label); color: var(--ink-3); word-break: break-all; }

.card-body { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-6); }
/* 证据块要与上面的字段行整行并列，不跟字段挤在同一行 */
.card-body :deep(.code-evidence) { flex-basis: 100%; width: 100%; }
.card-field { display: flex; align-items: baseline; gap: var(--space-2); min-width: 0; }
.card-key { font-size: var(--text-label); color: var(--ink-4); flex-shrink: 0; }
.card-val { color: var(--ink-body); word-break: break-all; }

/* 整改操作行：整行独占，与证据块区分开 */
.card-actions {
  flex-basis: 100%;
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px dashed var(--surface-line);
}
.act { display: flex; align-items: center; gap: var(--space-2); }
.act-key { font-size: var(--text-label); color: var(--ink-4); flex-shrink: 0; }
.act-fill { flex: 1; }
</style>
