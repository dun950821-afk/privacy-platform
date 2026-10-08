<template>
  <div class="net-evidence" v-loading="loading">
    <div class="ev-head">
      <span class="ev-title">网络证据</span>
      <span v-if="hosts.length" class="ev-count t-num">{{ hosts.length }} 个 host · {{ data?.total_urls }} 个 URL</span>
    </div>

    <!-- 必须标注：端点级归属已能推，但「哪个端点对应哪条规则」还没有建立。
         只在**真的取到端点数据**时标注：否则「以上为 App 全部端点」会与下面
         「该任务没有端点数据」同时出现，语义自相矛盾（T7-M3）。 -->
    <p v-if="available" class="net-note">端点与规则的精确关联暂未建立，以上为 App 全部端点</p>

    <div v-if="error" class="ev-error">
      <span class="ev-error-text">{{ error }}</span>
      <el-button size="small" link type="primary" @click="$emit('retry')">重试</el-button>
    </div>

    <!-- 「没有数据」与「没有端点」是两件事：available:false 是后者，不是一个空列表 -->
    <div v-else-if="!available" class="net-absent">该任务没有端点数据</div>

    <template v-else>
      <div v-if="!hosts.length" class="net-absent">该任务没有端点数据</div>
      <div v-for="h in hosts" :key="h.host" class="host" :class="{ 'is-test': h.is_test_residue }">
        <div class="host-head">
          <span class="host-name mono">{{ h.host }}</span>
          <span class="host-count t-num">{{ h.url_count }}</span>
          <span v-if="h.is_test_residue" class="host-flag is-test-flag">测试服务器残留</span>
          <span v-if="h.is_privacy_policy" class="host-flag is-pp-flag">隐私政策</span>
          <span class="host-fill"></span>
          <span class="host-src">{{ (h.observed_by || []).map((e: string) => ENGINE_CN[e] || e).join(' / ') }}</span>
          <el-button v-if="h.urls?.length" link type="primary" size="small"
                     @click="toggle(h.host)">
            {{ expanded.has(h.host) ? '收起 URL' : `${h.urls.length} 个 URL` }}
          </el-button>
        </div>

        <ul v-if="expanded.has(h.host)" class="host-urls">
          <li v-for="u in h.urls" :key="u" class="mono">{{ u }}</li>
        </ul>

        <!-- 归属：有断语才显示。三样（组件 / 厂商 / label）全空就留空——
             按错误归属去查隐私政策是白查；渲染一个空的归属盒同样没意义（T7-M7）。
             非代码归属（平台命名空间 / 应用自研）没有组件或厂商，断语落在 label 上。 -->
        <div v-if="hasVerdict(h.attribution)" class="attr"
             :class="isLow(h.attribution) ? 'is-lead' : 'is-solid'">
          <span class="attr-label">{{ isLow(h.attribution) ? '归属线索' : '归属' }}</span>
          <span class="attr-name">{{ attributionName(h.attribution) }}</span>
          <span v-if="h.attribution.component_name && h.attribution.vendor" class="attr-vendor">
            · {{ h.attribution.vendor }}
          </span>
          <span class="attr-conf">{{ CONF_CN[h.attribution.confidence] || h.attribution.confidence }}</span>
          <span v-if="h.attribution.via" class="attr-via">
            依据：{{ VIA_CN[h.attribution.via] || h.attribution.via }}
          </span>
          <span v-if="sourcesOf(h.attribution).length" class="attr-sources">
            <span v-for="s in sourcesOf(h.attribution)" :key="s" class="src mono">{{ s }}</span>
          </span>
          <!-- low 的疑虑必须随行显示：它是线索不是结论，审计人员要能自己判断 -->
          <span v-if="h.attribution.note" class="attr-note">{{ h.attribution.note }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ data: any; loading?: boolean; error?: string }>()
defineEmits<{ retry: [] }>()

const ENGINE_CN: Record<string, string> = { androguard: 'Androguard', appshark: 'AppShark' }
const CONF_CN: Record<string, string> = { high: '高确信', medium: '中确信', low: '低确信' }
const VIA_CN: Record<string, string> = { derived: '推导', curated: '人工查证' }

const expanded = ref<Set<string>>(new Set())

const hosts = computed<any[]>(() => props.data?.hosts || [])
/** 只有接口明确说 available 才认为「查过了」；缺字段按未取到处理，不默认成「没有端点」 */
const available = computed(() => props.data?.available === true)

function isLow(a: any): boolean {
  return a?.confidence === 'low'
}

/** 归属盒只在真有断语时渲染：组件名 / 厂商 / label 三样全空 = 一个空盒子（T7-M7） */
function hasVerdict(a: any): boolean {
  return !!(a && (a.component_name || a.vendor || a.label))
}

/** 展示名：组件优先，其次厂商，最后落到 label（平台命名空间 / 应用自研） */
function attributionName(a: any): string {
  return a?.component_name || a?.vendor || a?.label || ''
}

/** sources 是空格分隔的混合串（IR 路径 / URL），拆开逐条展示才便于核对。
    语料里「无依据」写作 `none`，那不是一条依据，不展示。 */
function sourcesOf(a: any): string[] {
  return String(a?.sources || '').split(/\s+/).filter((s) => s && s !== 'none')
}

function toggle(host: string) {
  const next = new Set(expanded.value)
  next.has(host) ? next.delete(host) : next.add(host)
  expanded.value = next
}
</script>

<style scoped>
.net-evidence { margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--line-soft); }

.ev-head { display: flex; align-items: baseline; gap: var(--space-2); margin-bottom: var(--space-2); flex-wrap: wrap; }
.ev-title { font-size: var(--text-section); font-weight: 600; color: var(--ink); }
.ev-count {
  padding: 0 7px; border-radius: 999px; background: var(--brand-50); color: var(--brand-700);
  border: 1px solid var(--brand-100); font-size: var(--text-label); font-weight: 600;
}
.net-note {
  margin-bottom: var(--space-2);
  padding: var(--space-1) var(--space-2);
  background: var(--brand-50);
  border-left: 2px solid var(--brand-200);
  color: var(--ink-3);
  font-size: var(--text-micro);
}

.ev-error {
  display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--accent-50); border: 1px solid var(--accent-600); border-radius: 8px;
}
.ev-error-text { font-size: var(--text-label); color: var(--accent-600); }
.net-absent {
  padding: var(--space-2) var(--space-3);
  background: var(--brand-50); border: 1px dashed var(--line);
  border-radius: 8px; color: var(--ink-3); font-size: var(--text-label);
}

.host { padding: var(--space-2) 0; border-bottom: 1px solid var(--line-soft); }
.host:last-child { border-bottom: none; }
/* 测试服务器残留：现成的合规信号，整行上琥珀底（既有 token --accent-*） */
.host.is-test { background: var(--accent-50); border-radius: 6px; padding-left: var(--space-2); padding-right: var(--space-2); }
.host-head { display: flex; align-items: baseline; gap: var(--space-2); flex-wrap: wrap; }
.host-name { font-size: var(--text-body); color: var(--ink-body); word-break: break-all; }
.host-count {
  min-width: 20px; text-align: center; padding: 0 6px; border-radius: 999px;
  background: var(--surface); border: 1px solid var(--line); color: var(--ink-3);
  font-size: var(--text-micro);
}
.host-flag { padding: 0 6px; border-radius: 4px; font-size: var(--text-micro); font-weight: 600; }
.is-test-flag { background: var(--accent-600); color: #fff; }
.is-pp-flag { background: var(--brand-50); color: var(--brand-700); border: 1px solid var(--brand-100); }
.host-fill { flex: 1; }
.host-src { font-size: var(--text-micro); color: var(--ink-4); }
.host-urls { margin: var(--space-1) 0 var(--space-1) var(--space-3); padding-left: var(--space-3); border-left: 1px solid var(--line); }
.host-urls li { font-size: var(--text-micro); color: var(--ink-3); list-style: none; word-break: break-all; }

/* 归属：high/medium 是结论（实底品牌色），low 是线索（虚线琥珀 + 疑虑随行） */
.attr {
  display: flex; align-items: baseline; gap: var(--space-2); flex-wrap: wrap;
  margin-top: var(--space-1); padding: 2px var(--space-2); border-radius: 6px;
  font-size: var(--text-micro);
}
.attr.is-solid { background: var(--brand-50); border: 1px solid var(--brand-100); }
.attr.is-lead { background: var(--accent-50); border: 1px dashed var(--accent-600); }
.attr-label { font-weight: 600; flex-shrink: 0; }
.attr.is-solid .attr-label { color: var(--brand-700); }
.attr.is-lead .attr-label { color: var(--accent-600); }
.attr-name { font-weight: 600; color: var(--ink-body); }
.attr-vendor { color: var(--ink-3); }
.attr-conf, .attr-via { color: var(--ink-3); }
.attr.is-lead .attr-conf { color: var(--accent-600); font-weight: 600; }
.attr-sources { display: inline-flex; gap: var(--space-1); flex-wrap: wrap; }
.src { padding: 0 4px; border-radius: 3px; background: var(--surface); border: 1px solid var(--line); color: var(--ink-3); }
.attr-note { flex-basis: 100%; color: var(--ink-3); }
.attr.is-lead .attr-note { color: var(--accent-600); }
</style>
