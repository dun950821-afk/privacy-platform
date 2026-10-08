<template>
  <div class="code-evidence" v-loading="loading">
    <div class="ev-head">
      <span class="ev-title">代码证据</span>
      <span v-if="observations.length" class="ev-count t-num">{{ observations.length }} 条观察</span>
      <span class="ev-fill"></span>
      <span class="ev-hint">「调用发生处」的方法签名原文</span>
    </div>

    <!-- 取数失败与「确实没有关联观察」是两回事：前者要能重试，后者是一句结论 -->
    <div v-if="error" class="ev-error">
      <span class="ev-error-text">{{ error }}</span>
      <el-button size="small" link type="primary" @click="load">重试</el-button>
    </div>

    <template v-else-if="observations.length">
      <div v-for="o in visible" :key="o.id" class="obs">
        <div class="obs-head">
          <StatusTag v-if="o.provider_level" :value="o.provider_level" :map="PROVIDER_LEVEL" />
          <span class="obs-loc mono" :class="{ 'is-missing': !o.location }">{{ locationOf(o) }}</span>
          <span class="obs-fill"></span>
          <!-- 后端按 payload.url 定位报告文件；没有 url 的观察（如权限声明类事实）
               本来就没有 IR 报告，按钮置灰而不是点了才弹「没有报告」 -->
          <el-button link type="primary" size="small" :disabled="!hasReport(o)"
                     :title="hasReport(o) ? '' : '该条观察没有对应的引擎报告'"
                     @click="openCode(o)">查看完整路径</el-button>
        </div>
        <div class="obs-foot">
          <span class="obs-sub mono">{{ o.subject || '-' }}</span>
          <span v-if="o.data_category" class="obs-meta">{{ o.data_category }}</span>
          <span v-if="o.sink_type" class="obs-meta">经 {{ o.sink_type }}</span>
          <span class="obs-meta">{{ ENGINE_CN[o.engine_type] || o.engine_type }}</span>
        </div>
      </div>

      <el-button v-if="observations.length > PAGE" link type="primary" size="small"
                 class="obs-more" @click="showAll = !showAll">
        {{ showAll ? '收起' : `展开其余 ${observations.length - PAGE} 条` }}
      </el-button>
    </template>

    <EmptyBox v-else-if="!loading" description="该结论没有关联观察" :image-size="60" />

    <el-drawer v-model="codeVisible" :title="codeTitle" size="720px">
      <p class="ir-note">以下为 IR 代码（smali 风格），非 Java 源码</p>
      <EngineReportViewer v-if="codeObservationId" :task-id="taskId"
                          :observation-id="codeObservationId" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EmptyBox from '@/components/EmptyBox.vue'
import EngineReportViewer from '@/components/EngineReportViewer.vue'
import StatusTag from '@/components/StatusTag.vue'
import { taskApi } from '@/api/tasks'
import type { DictItem } from '@/utils/dict'

const props = defineProps<{ taskId: number; findingId: number }>()

/** 长列表首屏只渲染这么多，其余点开——一个结论可关联 300+ 条观察 */
const PAGE = 20

/** 规则族，不是严重度阶梯（同一规则不跨 level），与 ProblemList 的构成说明同一套词面 */
const PROVIDER_LEVEL: Record<string, DictItem> = {
  L2: { label: '敏感 API', type: 'warning' },
  L3: { label: '数据流', type: 'primary' },
  L4: { label: '安全缺陷', type: 'danger' },
}
const ENGINE_CN: Record<string, string> = { appshark: 'AppShark', androguard: 'Androguard' }

const loading = ref(false)
const error = ref('')
const observations = ref<any[]>([])
const showAll = ref(false)
const codeVisible = ref(false)
const codeObservationId = ref<number | null>(null)
const codeTitle = ref('IR 代码')

const visible = computed(() => (showAll.value ? observations.value : observations.value.slice(0, PAGE)))

/** location 覆盖率实测 99.7%：缺失时写清楚是「没有」，不要渲染成空行 */
function locationOf(o: any): string {
  return o.location || '（该条观察无方法签名）'
}

/** 后端以 payload.url 定位该条命中的报告文件；没有 url 就没有报告可开 */
function hasReport(o: any): boolean {
  return !!o?.payload?.url
}

async function load() {
  if (!props.taskId || !props.findingId) return
  loading.value = true
  error.value = ''
  try {
    const res: any = await taskApi.platformFinding(props.taskId, props.findingId)
    observations.value = res.data?.observations || []
  } catch (e: any) {
    // 必须 catch：否则 unhandled rejection 会以 pageerror 出现在 console；
    // 同时清空，避免切换结论后把上一条的观察当成本条的
    observations.value = []
    error.value = e?.message || e?.detail || '代码证据读取失败'
  } finally {
    loading.value = false
  }
}

function openCode(o: any) {
  if (!hasReport(o)) return
  codeObservationId.value = o.id
  codeTitle.value = 'IR 代码 · ' + (o.location || o.subject || '')
  codeVisible.value = true
}

watch(() => props.findingId, () => { showAll.value = false; load() }, { immediate: true })
</script>

<style scoped>
.code-evidence { margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--line-soft); }

.ev-head { display: flex; align-items: baseline; gap: var(--space-2); margin-bottom: var(--space-2); flex-wrap: wrap; }
.ev-title { font-size: var(--text-section); font-weight: 600; color: var(--ink); }
.ev-count {
  padding: 0 7px; border-radius: 999px; background: var(--brand-50); color: var(--brand-700);
  border: 1px solid var(--brand-100); font-size: var(--text-label); font-weight: 600;
}
.ev-fill { flex: 1; }
.ev-hint { font-size: var(--text-micro); color: var(--ink-4); }

.ev-error {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--accent-50); border: 1px solid var(--accent-600); border-radius: 8px;
}
.ev-error-text { font-size: var(--text-label); color: var(--accent-600); }

/* 一条观察一行：方法签名原文是主角，API/类目/引擎是旁注 */
.obs { padding: var(--space-2) 0; border-bottom: 1px solid var(--line-soft); }
.obs:last-of-type { border-bottom: none; }
.obs-head { display: flex; align-items: baseline; gap: var(--space-2); min-width: 0; }
.obs-loc { font-size: var(--text-label); color: var(--ink-body); word-break: break-all; min-width: 0; }
.obs-loc.is-missing { color: var(--ink-4); font-style: italic; }
.obs-fill { flex: 1; }
.obs-foot { display: flex; align-items: baseline; gap: var(--space-3); margin-top: 2px; flex-wrap: wrap; }
.obs-sub { font-size: var(--text-micro); color: var(--ink-3); word-break: break-all; }
.obs-meta { font-size: var(--text-micro); color: var(--ink-4); flex-shrink: 0; }
.obs-more { margin-top: var(--space-2); }

.ir-note {
  margin-bottom: var(--space-3);
  padding: var(--space-1) var(--space-2);
  background: var(--accent-50);
  border-left: 2px solid var(--accent-600);
  color: var(--accent-600);
  font-size: var(--text-label);
}
</style>
