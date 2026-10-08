<template>
  <!-- 480px 侧滑面板：App 背景。任务级数据（端点/画像/SDK/权限）只在这里出现一次，
       不再随每张问题卡片重复渲染。 -->
  <el-drawer v-model="open" direction="rtl" size="480px" :with-header="false" class="bg-panel">
    <div class="panel">
      <div class="panel-head">
        <div class="panel-head-main">
          <span class="panel-title">App 背景</span>
          <span v-if="app.name" class="panel-app">{{ app.name }}</span>
        </div>
        <el-button link :icon="Close" title="关闭" aria-label="关闭" @click="open = false" />
      </div>

      <div class="panel-body">
        <!-- ① App 基本信息 -->
        <section class="bg-block" data-block="basic">
          <div class="bg-title">App 基本信息</div>
          <el-descriptions :column="1" size="small" border class="bg-desc">
            <el-descriptions-item label="包名">
              <span class="t-mono">{{ app.package_name || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="版本">
              {{ version.version_name || '-' }}
              <span v-if="version.version_code != null" class="dim">（code {{ version.version_code }}）</span>
            </el-descriptions-item>
            <el-descriptions-item label="SHA256">
              <span class="t-mono" :title="version.sha256 || ''">{{ sha16 }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ fmtSize(version.file_size) }}</el-descriptions-item>
            <el-descriptions-item label="min / target SDK">{{ sdkRange }}</el-descriptions-item>
          </el-descriptions>
        </section>

        <!-- ② 安全加固：L4 安全缺陷归这里，不进问题卡片的构成说明（决策 A） -->
        <section class="bg-block" data-block="security" v-loading="secLoading">
          <div class="bg-title">
            安全加固
            <span class="bg-hint">安全缺陷（L4）/ 应用安全 / 清单 / 密钥 / 证书 / 依赖</span>
          </div>

          <div v-if="secError" class="bg-error">
            <span>{{ secError }}</span>
            <el-button size="small" link type="primary" @click="loadSecurity">重试</el-button>
          </div>

          <template v-else>
            <div v-for="s in SECURITY_SECTIONS" :key="s.path" class="sec-seg" :data-section="s.path">
              <div class="sec-head">
                <span class="sec-label">{{ s.label }}</span>
                <span v-if="secItem(s.path)" class="sec-count t-num">{{ secCountText(secItem(s.path)) }}</span>
              </div>

              <!-- 「没有数据」与「数据是空的」是两件事：missing 里的段落要说「没有这段数据」 -->
              <div v-if="!secItem(s.path)" class="sec-missing">本任务没有这段数据</div>
              <div v-else class="sec-body raw-body">
                <template v-if="isArr(secItem(s.path)!.payload)">
                  <ol v-if="secItem(s.path)!.payload.length" class="raw-list">
                    <li v-for="(v, i) in shown(s.path, secItem(s.path)!.payload)" :key="i" class="raw-item">
                      <div v-if="isObj(v)" class="raw-kv-wrap">
                        <div v-for="(val, k) in v" :key="k" class="raw-kv">
                          <span class="raw-k">{{ k }}</span>
                          <span class="raw-v">{{ fmtVal(val) }}</span>
                        </div>
                      </div>
                      <span v-else class="raw-v">{{ fmtVal(v) }}</span>
                    </li>
                  </ol>
                  <div v-else class="sec-missing">这段数据为空（引擎产出过，但内容为空）</div>
                </template>
                <div v-else-if="isObj(secItem(s.path)!.payload)" class="raw-kv-wrap">
                  <div v-for="(val, k) in secItem(s.path)!.payload" :key="k" class="raw-kv">
                    <span class="raw-k">{{ k }}</span>
                    <span class="raw-v">{{ fmtVal(val) }}</span>
                  </div>
                </div>
                <div v-else class="raw-v">{{ fmtVal(secItem(s.path)!.payload) }}</div>
              </div>

              <!-- secrets 实测 414 条（含私钥），首屏只渲染 RAW_LIMIT 条，其余点开 -->
              <button v-if="overflowCount(s.path) > 0" class="raw-more" @click="toggleSec(s.path)">
                {{ expanded.has(s.path) ? `收起（仅显示前 ${RAW_LIMIT} 条）` : `显示全部 ${rawLen(s.path)} 条` }}
              </button>
            </div>
          </template>

          <!-- L4 安全缺陷结论（决策 A：不进卡片构成说明，归这里）。
               数据源是 platform-findings，与上面 MobSF 五段不同，所以单独成块、
               不参与 .sec-seg 的五段顺序。 -->
          <div class="l4-seg" data-section="l4" v-loading="l4Loading">
            <div class="sec-head">
              <span class="sec-label">安全缺陷结论（L4）</span>
              <span v-if="l4Items.length" class="sec-count t-num">{{ l4Items.length }} 条</span>
            </div>
            <div v-if="l4Error" class="bg-error">
              <span>{{ l4Error }}</span>
              <el-button size="small" link type="primary" @click="loadL4">重试</el-button>
            </div>
            <div v-else-if="!l4Items.length" class="sec-missing">本任务没有安全缺陷结论</div>
            <ul v-else class="l4-list">
              <li v-for="f in l4Items" :key="f.id" class="l4-item">
                <StatusTag :value="f.severity" :map="SEVERITY" />
                <span class="l4-title">{{ f.title || f.finding_code || '-' }}</span>
                <span class="l4-meta t-num">{{ f.observation_count ?? 0 }} 处证据</span>
              </li>
            </ul>
          </div>
        </section>

        <!-- ③ 端点与网络：任务级数据，只在这里出现一次 -->
        <section class="bg-block" data-block="network">
          <div class="bg-title">端点与网络</div>
          <NetworkEvidenceBlock :data="endpoints" :loading="epLoading" :error="epError"
                                @retry="loadEndpoints" />
        </section>

        <!-- ④⑤⑥ 合规画像 / SDK / 权限 共用**同一次** `/compliance-profile` 取数
             （F2：此前取了 3 次）。失败时只有一个错误态、一个重试——绝不把
             一次请求失败渲染成一排全 0 结论。 -->
        <section v-if="profError" class="bg-block" data-block="profile">
          <div class="bg-title">合规画像</div>
          <div class="bg-error">
            <span>{{ profError }}</span>
            <el-button size="small" link type="primary" @click="loadProfile">重试</el-button>
          </div>
        </section>

        <template v-else>
          <!-- ④ 合规画像（采集主体）：权限与 SDK 在下面各自成块，这里不再重复 -->
          <section class="bg-block" data-block="profile">
            <div class="bg-title">合规画像</div>
            <div class="bg-embed">
              <ComplianceProfile :task-id="taskId" :sections="['collect', 'gaps']"
                                 :profile="profileData" :profile-loading="profLoading"
                                 :profile-error="profError" @retry="loadProfile" />
            </div>
          </section>

          <!-- ⑤ SDK 组件。unattributed 来自同一次 compliance-profile 取数 -->
          <section class="bg-block" data-block="sdk" v-loading="profLoading">
            <div class="bg-title">SDK 组件</div>
            <div class="bg-embed">
              <SdkPanel :task-id="taskId" :unattributed="unattributed" />
            </div>
          </section>

          <!-- ⑥ 权限：直接复用 ComplianceProfile 的 #sec-permission 卡片。
               简报 §一 对该块的要求是「沿用现成展示」——手写一张窄表会丢掉
               筛选栏（含「申请但未见使用」）、compliance_focus、method_count
               与「N 项权限的映射未覆盖」披露条，并让权限表的列定义在仓库里出现两份。 -->
          <section class="bg-block" data-block="permission">
            <div class="bg-title">权限</div>
            <div class="bg-embed">
              <ComplianceProfile :task-id="taskId" :sections="['permission']"
                                 :profile="profileData" :profile-loading="profLoading"
                                 :profile-error="profError" @retry="loadProfile" />
            </div>
          </section>
        </template>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import NetworkEvidenceBlock from '@/components/NetworkEvidenceBlock.vue'
import ComplianceProfile from '@/components/ComplianceProfile.vue'
import SdkPanel from '@/components/SdkPanel.vue'
import StatusTag from '@/components/StatusTag.vue'
import { taskApi } from '@/api/tasks'
import { SEVERITY } from '@/utils/dict'
import { fmtSize } from '@/utils/format'

const props = defineProps<{ modelValue: boolean; taskId: number; task?: any }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const open = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const app = computed<any>(() => props.task?.app || {})
const version = computed<any>(() => props.task?.version || {})
// 包名、版本、sha256 前 16 位、文件大小、min/target SDK（简报 §一）
const sha16 = computed(() => (version.value.sha256 || '').slice(0, 16) || '-')
const sdkRange = computed(() => {
  const min = version.value.min_sdk
  const target = version.value.target_sdk
  if (min == null && target == null) return '-'
  return `${min ?? '-'} / ${target ?? '-'}`
})

// ── 安全加固 ───────────────────────────────────────────────────────────────
// 五段固定顺序（与后端 SECURITY_SECTIONS 一致）；missing 只有 path，label 得在这边兜住。
const SECURITY_SECTIONS = [
  { path: 'appsec', label: '应用安全评分' },
  { path: 'manifest_analysis.manifest_findings', label: '清单问题' },
  { path: 'secrets', label: '硬编码密钥' },
  { path: 'certificate_analysis', label: '签名与证书' },
  { path: 'sbom', label: '依赖清单' },
]
/** 大列表首屏只渲染这么多条：secrets 实测 414 条（含私钥），全量渲染会把面板撑爆 */
const RAW_LIMIT = 50

const secLoading = ref(false)
const secError = ref('')
const secItems = ref<Record<string, any>>({})
const expanded = ref<Set<string>>(new Set())

const secItem = (path: string) => secItems.value[path]

/** payload 原样展示，不做语义解析：仅按类型分派「数组 / 对象 / 标量」三种排版 */
const isArr = (v: any) => Array.isArray(v)
const isObj = (v: any) => v !== null && typeof v === 'object' && !Array.isArray(v)
function fmtVal(v: any): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  try { return JSON.stringify(v) } catch { return String(v) }
}

const rawLen = (path: string): number => {
  const p = secItem(path)?.payload
  return Array.isArray(p) ? p.length : 0
}
const overflowCount = (path: string) => Math.max(0, rawLen(path) - RAW_LIMIT)
function shown(path: string, arr: any[]): any[] {
  return expanded.value.has(path) ? arr : arr.slice(0, RAW_LIMIT)
}
function toggleSec(path: string) {
  const next = new Set(expanded.value)
  next.has(path) ? next.delete(path) : next.add(path)
  expanded.value = next
}

function secCountText(it: any): string {
  const n = it.item_count
  if (typeof n === 'number') return `${n} 条`
  const p = it.payload
  if (Array.isArray(p)) return `${p.length} 条`
  if (isObj(p)) return `${Object.keys(p).length} 项`
  return ''
}

// ── 端点与网络 ─────────────────────────────────────────────────────────────
const endpoints = ref<any>(null)
const epLoading = ref(false)
const epError = ref('')

// ── 合规画像 / SDK / 权限：同一次 `/compliance-profile` 取数（F2）。
//    结果作为 prop 传给两块内嵌的 ComplianceProfile，它们自己不再取数。
const profileData = ref<any>(null)
const unattributed = ref<any[]>([])
const profLoading = ref(false)
const profError = ref('')

// ── L4 安全缺陷结论（决策 A：归「安全加固」块，不进问题卡片的构成说明） ────────
const l4Items = ref<any[]>([])
const l4Loading = ref(false)
const l4Error = ref('')

/**
 * 是不是一条「L4 结论」：带 L4 观测、且**没有** L2/L3 的隐私维度成分。
 * 隐私结论即便含 L4 观测也留在问题清单（它的主体是 L2/L3）；纯安全缺陷才归这里。
 * summary 为 null 的历史结论用 category 兜底。
 */
function isL4(f: any): boolean {
  const s = f?.provider_level_summary || {}
  if (s.L2 || s.L3) return false
  return !!s.L4 || f?.category === 'security'
}

async function loadSecurity() {
  secLoading.value = true
  secError.value = ''
  try {
    const res: any = await taskApi.securityFindings(props.taskId)
    const items = res.data?.items || []
    secItems.value = Object.fromEntries(items.map((it: any) => [it.section, it]))
  } catch (e: any) {
    // 失败必须与「没有这段数据」区分开：接口挂了不等于引擎没产出
    secItems.value = {}
    secError.value = e?.message || e?.detail || '安全加固数据读取失败'
  } finally {
    secLoading.value = false
  }
}

async function loadEndpoints() {
  epLoading.value = true
  epError.value = ''
  try {
    const res: any = await taskApi.endpoints(props.taskId)
    endpoints.value = res.data || null
  } catch (e: any) {
    endpoints.value = null
    epError.value = e?.message || e?.detail || '网络证据读取失败'
  } finally {
    epLoading.value = false
  }
}

async function loadProfile() {
  profLoading.value = true
  profError.value = ''
  try {
    const res = await taskApi.complianceProfile(props.taskId)
    const d: any = res.data || {}
    profileData.value = d
    unattributed.value = d.unattributed_packages || []
  } catch (e: any) {
    // 失败必须与「确实是 0」分开：合规画像块 / SDK 块 / 权限块共用这一次取数，
    // 失败时只出**一个**错误态，绝不把全 0 渲染成结论（F2）。
    profileData.value = null
    unattributed.value = []
    profError.value = e?.message || e?.detail || '合规画像读取失败'
  } finally {
    profLoading.value = false
  }
}

async function loadL4() {
  l4Loading.value = true
  l4Error.value = ''
  try {
    const res: any = await taskApi.platformFindings(props.taskId)
    l4Items.value = (res.data?.items || []).filter(isL4)
  } catch (e: any) {
    l4Items.value = []
    l4Error.value = e?.message || e?.detail || '安全缺陷结论读取失败'
  } finally {
    l4Loading.value = false
  }
}

/** 首次打开才取数：面板里的数据都是任务级的，没必要在详情页首屏就拉 */
let loaded = false
function loadAll() {
  if (loaded || !props.taskId) return
  loaded = true
  loadSecurity()
  loadEndpoints()
  loadProfile()
  loadL4()
}

watch(open, (v) => { if (v) loadAll() }, { immediate: true })
// 面板不关、但页面切到别的任务时，重新取数
watch(() => props.taskId, () => { loaded = false; if (props.modelValue) loadAll() })
</script>

<style scoped>
.panel { display: flex; flex-direction: column; height: 100%; }
.panel-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--line);
}
.panel-head-main { display: flex; align-items: baseline; gap: var(--space-2); min-width: 0; }
.panel-title { font-size: var(--text-section); font-weight: 600; color: var(--ink); }
.panel-app { font-size: var(--text-label); color: var(--ink-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.panel-body { flex: 1; overflow-y: auto; padding-top: var(--space-3); }

.bg-block { padding-bottom: var(--space-4); margin-bottom: var(--space-4); border-bottom: 1px solid var(--line-soft); }
.bg-block:last-child { border-bottom: none; }
.bg-title {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  font-size: var(--text-section);
  font-weight: 600;
  color: var(--ink);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.bg-hint { font-size: var(--text-micro); font-weight: 400; color: var(--ink-4); }
.bg-desc :deep(.el-descriptions__label) { width: 96px; }
.bg-embed { overflow-x: auto; }

.bg-error {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: #FEF0F0; border: 1px solid #FECACA; border-radius: 8px;
  color: var(--el-color-danger); font-size: var(--text-label);
}

/* 安全加固：每段一块 */
.sec-seg { margin-bottom: var(--space-3); }
.sec-seg:last-child { margin-bottom: 0; }
.sec-head { display: flex; align-items: baseline; gap: var(--space-2); margin-bottom: var(--space-1); }
.sec-label { font-size: var(--text-body); font-weight: 600; color: var(--ink-body); }
.sec-count {
  padding: 0 6px; border-radius: 999px; background: var(--surface-subtle); border: 1px solid var(--line);
  color: var(--ink-3); font-size: var(--text-micro);
}
/* L4 安全缺陷结论：与 MobSF 五段同一排版语言，但独立成块（不占 .sec-seg 的顺序） */
.l4-seg { margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px dashed var(--line); }
.l4-list { margin: 0; padding: 0; list-style: none; }
.l4-item { display: flex; align-items: baseline; gap: var(--space-2); padding: 2px 0; flex-wrap: wrap; }
.l4-title { font-size: var(--text-label); color: var(--ink-body); word-break: break-all; }
.l4-meta { font-size: var(--text-micro); color: var(--ink-4); }

/* 「没有这段数据」是结论，不是空列表：虚线框 + 一句说明 */
.sec-missing {
  padding: var(--space-1) var(--space-2);
  background: var(--surface-subtle);
  border: 1px dashed var(--line);
  border-radius: 6px;
  color: var(--ink-4);
  font-size: var(--text-label);
}

/* payload 原样排版 */
.raw-body { max-height: 340px; overflow: auto; background: var(--surface-subtle); border: 1px solid var(--line-soft); border-radius: 6px; padding: var(--space-2); }
.raw-list { margin: 0; padding-left: 18px; }
.raw-item { font-size: var(--text-label); color: var(--ink-body); padding: 2px 0; word-break: break-all; }
.raw-kv-wrap { display: flex; flex-direction: column; gap: 2px; }
.raw-kv { display: flex; gap: var(--space-2); font-size: var(--text-label); word-break: break-all; }
.raw-k { flex-shrink: 0; min-width: 96px; color: var(--ink-4); }
.raw-v { color: var(--ink-body); white-space: pre-wrap; }
.raw-more {
  margin-top: var(--space-1);
  padding: 0; background: none; border: none;
  color: var(--el-color-primary); font-size: var(--text-label); cursor: pointer;
}
.raw-more:hover { text-decoration: underline; }

.dim { color: var(--ink-3); }
</style>
