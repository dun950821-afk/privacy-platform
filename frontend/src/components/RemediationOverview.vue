<template>
  <div class="remediation" v-loading="loading">
    <!-- ① 按整改状态汇总：四态计数。数据来自 platform-findings 的 items -->
    <div class="tri-row">
      <div v-for="s in states" :key="s.key" class="tri-item" :class="{ 'is-zero': !s.count }">
        <span class="tri-num t-num">{{ s.count }}</span>
        <span class="tri-cap">{{ s.label }}</span>
      </div>
      <span class="tri-fill"></span>
      <span v-if="loadError" class="tri-err">
        问题清单读取失败：{{ loadError }}
        <el-button size="small" link type="primary" @click="loadFindings">重试</el-button>
      </span>
      <span v-else class="tri-total">共 <b class="t-num">{{ items.length }}</b> 项结论</span>
    </div>

    <!-- ② 复检记录：两个方向分开显示，它们回答的是不同的问题 -->
    <!-- 取数失败必须是错误态，不能落成「尚无复检记录」——把请求挂了说成一句结论，
         和本页其它两处（问题清单的失败态、面板的错误态）就不一致了。 -->
    <div v-if="retestError" class="retest-error">
      <span class="retest-error-text">复检记录读取失败：{{ retestError }}</span>
      <el-button size="small" link type="primary" @click="loadRetest">重试</el-button>
    </div>
    <div v-else class="retest-grid">
      <div class="retest-col">
        <div class="col-head">
          <span class="col-title">本任务的结论被复检</span>
          <span class="col-count t-num">{{ own.length }}</span>
        </div>
        <div class="col-desc">本任务产出的结论后来被复检了吗、结果如何</div>
        <table v-if="own.length" class="mini">
          <thead><tr><th>结论</th><th>结果</th><th>复检任务</th><th>复检人 / 时间</th></tr></thead>
          <tbody>
            <tr v-for="r in own" :key="r.id">
              <td class="t-mono">#{{ r.original_finding_id }}</td>
              <td>{{ r.result || '—' }}</td>
              <td class="t-mono">{{ r.retest_task_id != null ? '#' + r.retest_task_id : '—' }}</td>
              <td>{{ userName(r.tested_by) }}<span v-if="r.tested_at" class="dim"> · {{ fmtDateTime(r.tested_at) }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="col-empty">本任务的结论尚无复检记录</div>
      </div>

      <div class="retest-col">
        <div class="col-head">
          <span class="col-title">本任务作为复检任务</span>
          <span class="col-count t-num">{{ asRetest.length }}</span>
        </div>
        <div class="col-desc">本任务自己是某条结论的复检任务</div>
        <table v-if="asRetest.length" class="mini">
          <thead><tr><th>被复检结论</th><th>结果</th><th>复检人 / 时间</th></tr></thead>
          <tbody>
            <tr v-for="r in asRetest" :key="r.id">
              <td class="t-mono">#{{ r.original_finding_id }}</td>
              <td>{{ r.result || '—' }}</td>
              <td>{{ userName(r.tested_by) }}<span v-if="r.tested_at" class="dim"> · {{ fmtDateTime(r.tested_at) }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="col-empty">本任务不是任何结论的复检任务</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import api from '@/api'
import { taskApi } from '@/api/tasks'
import { TRIAGE_STATUS } from '@/utils/dict'
import { fmtDateTime } from '@/utils/format'

const props = defineProps<{ taskId: number }>()

const loading = ref(false)
const loadError = ref('')
const retestError = ref('')
const items = ref<any[]>([])
const own = ref<any[]>([])
const asRetest = ref<any[]>([])
const users = ref<any[]>([])

/** 四态的展示顺序固定（与 TRIAGE_STATUS 同源），0 值也要出现——「都是 0」本身是信息 */
const states = computed(() =>
  ['needs_review', 'fixing', 'fixed', 'ignored'].map((key) => ({
    key,
    label: TRIAGE_STATUS[key]?.label || key,
    count: items.value.filter((f) => (f.triage_status || 'needs_review') === key).length,
  })),
)

function userName(id?: number | null): string {
  if (id == null) return '—'
  const u = users.value.find((x) => x.id === id)
  return u ? (u.full_name || u.username) : `#${id}`
}

async function loadFindings() {
  loadError.value = ''
  try {
    const res: any = await taskApi.platformFindings(props.taskId)
    items.value = res.data?.items || []
  } catch (e: any) {
    // 失败不能冒充「0 条待整改」：清空计数并明确报错
    items.value = []
    loadError.value = e?.message || e?.detail || '无法获取问题清单'
  }
}

async function loadRetest() {
  retestError.value = ''
  try {
    const res: any = await taskApi.retestRecords(props.taskId)
    own.value = res.data?.items || []
    asRetest.value = res.data?.as_retest || []
  } catch (e: any) {
    // 清空 + 明确报错：失败不能被渲染成「本任务的结论尚无复检记录」
    own.value = []
    asRetest.value = []
    retestError.value = e?.message || e?.detail || '无法获取复检记录'
  }
}

async function loadUsers() {
  try {
    const res: any = await api.get('/system/users', { params: { page_size: 100 }, silent: true })
    users.value = res.data || []
  } catch {
    users.value = []
  }
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    await Promise.all([loadFindings(), loadRetest(), loadUsers()])
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.taskId, load)
</script>

<style scoped>
.remediation { font-size: var(--text-body); }

/* 四态汇总条：与问题清单的结论条同一套表面语言 */
.tri-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-4);
  padding: var(--card-pad) var(--space-4);
  margin-bottom: var(--space-3);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  flex-wrap: wrap;
}
.tri-item { display: flex; align-items: baseline; gap: var(--space-2); }
.tri-num { font-size: 20px; font-weight: 600; line-height: 1.1; color: var(--brand-700); letter-spacing: -0.3px; }
.tri-item.is-zero .tri-num { color: var(--ink-4); font-weight: 400; }
.tri-cap { font-size: var(--text-label); color: var(--ink-3); }
.tri-fill { flex: 1; }
.tri-total { font-size: var(--text-label); color: var(--ink-3); }
.tri-err { font-size: var(--text-label); color: var(--el-color-danger); }

/* 复检取数失败：与面板 .bg-error / 清单 .load-error 同一套告警语言 */
.retest-error {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: #FEF0F0; border: 1px solid #FECACA; border-radius: 8px;
  font-size: var(--text-label);
}
.retest-error-text { color: var(--el-color-danger); word-break: break-all; }

/* 两个方向并排：左边「我的结论被复检」，右边「我在复检别人」 */
.retest-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-4); }
@media (max-width: 900px) { .retest-grid { grid-template-columns: minmax(0, 1fr); } }
.retest-col { min-width: 0; }
.col-head { display: flex; align-items: baseline; gap: var(--space-2); }
.col-title { font-size: var(--text-body); font-weight: 600; color: var(--ink-body); }
.col-count {
  padding: 0 6px; border-radius: 999px; background: var(--brand-50); color: var(--brand-700);
  border: 1px solid var(--brand-100); font-size: var(--text-micro); font-weight: 600;
}
.col-desc { font-size: var(--text-micro); color: var(--ink-4); margin-bottom: var(--space-2); }
.col-empty {
  padding: var(--space-2) var(--space-3);
  background: var(--surface-subtle); border: 1px dashed var(--line); border-radius: 6px;
  color: var(--ink-3); font-size: var(--text-label);
}
.mini { width: 100%; border-collapse: collapse; }
.mini th {
  text-align: left; font-weight: 600; color: var(--ink-3); font-size: var(--text-micro);
  padding: 4px 6px; border-bottom: 1px solid var(--line);
}
.mini td { padding: 5px 6px; border-bottom: 1px solid var(--line-soft); font-size: var(--text-label); word-break: break-all; }
.dim { color: var(--ink-3); }
</style>
