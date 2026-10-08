<template>
  <div class="profile" v-loading="loading">
    <!-- 关键数字：一眼看出这个 App 采集了什么、谁在采集、权限用得怎么样。
         每个数字都可点击 —— 它同时是导航，不是装饰。 -->
    <div class="metric-row mb14">
      <button class="metric" :class="{ 'is-zero': !totalCollect }" @click="goTo('sec-collect')">
        <div class="metric-value">{{ totalCollect }}</div>
        <div class="metric-label">个人信息采集点</div>
      </button>
      <button class="metric" :class="{ 'is-zero': !thirdPartyOwners }" @click="goTo('sec-collect')">
        <div class="metric-value">{{ thirdPartyOwners }}</div>
        <div class="metric-label">涉及第三方厂商</div>
      </button>
      <button class="metric" :class="{ 'is-zero': !appSelfCount }" @click="goTo('sec-collect')">
        <div class="metric-value">{{ appSelfCount }}</div>
        <div class="metric-label">应用自身代码中的采集</div>
      </button>
      <!-- 敏感类目 >0 才是「需要注意」，0 用中性色。此前 0 反而标了警告色 -->
      <button class="metric" :class="sensitiveCount ? 'is-alert' : 'is-zero'"
              @click="goTo('sec-collect')">
        <div class="metric-value">{{ sensitiveCount }}</div>
        <div class="metric-label">敏感个人信息类目</div>
      </button>
      <button v-if="has('permission')" class="metric" :class="{ 'is-zero': !permissionCount }"
              @click="goTo('sec-permission')">
        <div class="metric-value">{{ permissionCount }}</div>
        <div class="metric-label">申请权限</div>
      </button>
    </div>

    <div class="body-grid">
      <div class="body-main">
        <!-- ── 个人信息收集 ─────────────────────────────────── -->
        <el-card v-if="has('collect')" id="sec-collect" shadow="never" class="block anchor-section">
          <template #header>
            <div class="block-head">
              <span class="t-section">个人信息收集</span>
              <span class="block-count">{{ totalCollect }}</span>
              <span class="t-sub">按「谁在采集」分组 —— 第三方 SDK 的采集需在隐私政策中逐一声明</span>
            </div>
          </template>

          <template v-for="group in collectGroups" :key="group.key">
            <!-- 0 值折叠成一行，不再占「标题行 + 空态」两行 -->
            <div v-if="!group.items.length" class="zero-line">
              {{ group.label }}：0 处 —— {{ group.emptyText }}
            </div>
            <template v-else>
              <div class="group-head">
                <span class="group-name">{{ group.label }}</span>
                <span class="t-sub">{{ group.sum }} 处 · {{ group.items.length }} 类</span>
                <span v-if="group.hint" class="group-hint">{{ group.hint }}</span>
              </div>
              <el-table :data="group.items" size="small" row-key="rowKey" class="data-table">
                <el-table-column type="expand">
                  <template #default="{ row }">
                    <div class="loc-list">
                      <div v-for="(loc, i) in row.code_locations" :key="i" class="loc-row">
                        <span class="t-mono dim">{{ loc.location }}</span>
                        <el-button v-if="loc.has_code" link type="primary" size="small"
                                   @click="openCode(loc)">查看代码</el-button>
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="个人信息" min-width="200">
                  <template #default="{ row }">
                    <span>{{ row.data_category_cn }}</span>
                    <el-tag v-if="row.sensitive" type="danger" size="small" effect="plain" class="ml6">敏感</el-tag>
                    <!-- 反转语义：只有「需要权限」才值得标。此前 6/6 行都挂着「无需权限」 -->
                    <el-tag v-if="row.requires_permission" size="small" effect="plain" class="ml6">需权限</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="归属" min-width="220">
                  <template #default="{ row }">
                    <div class="owner-name">{{ row.owner.name }}</div>
                    <div v-if="row.owner.vendor" class="owner-vendor">{{ row.owner.vendor }}</div>
                    <el-tag v-if="row.owner.match_status === 'CANDIDATE'" size="small" type="info"
                            effect="plain" class="ml6">候选匹配</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="收集方式" min-width="180">
                  <template #default="{ row }">
                    <span class="dim">{{ row.collect_modes.join(' · ') || '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="采集点" width="90" align="center">
                  <template #default="{ row }"><b class="t-num">{{ row.call_site_count }}</b></template>
                </el-table-column>
                <el-table-column label="方法" width="80" align="center">
                  <template #default="{ row }"><span class="t-num">{{ row.method_count }}</span></template>
                </el-table-column>
                <!-- 「隐私政策」列只在真有数据时出现；全为 null 时降级成下方一条说明 -->
                <el-table-column v-if="hasPolicyData" label="隐私政策" width="100" align="center">
                  <template #default="{ row }">
                    <span v-if="row.declared_in_policy === null" class="dim">无数据</span>
                    <span v-else>{{ row.declared_in_policy ? '已声明' : '未声明' }}</span>
                  </template>
                </el-table-column>
                <template #empty><EmptyBox description="无" /></template>
              </el-table>
            </template>
          </template>

          <div v-if="!hasPolicyData && totalCollect" class="column-note">
            「是否在隐私政策中声明」本页无法判定：平台尚无隐私政策数据（0 条政策、0 个任务关联），
            一律不推断，故不单独占一列。
          </div>
        </el-card>

        <!-- ── 权限使用 ─────────────────────────────────────── -->
        <el-card v-if="has('permission')" id="sec-permission" shadow="never" class="block anchor-section">
          <template #header>
            <div class="block-head">
              <span class="t-section">权限使用</span>
              <span class="block-count">{{ permissionCount }}</span>
              <span class="t-sub">
                申请 vs 实际调用点 —— 申请了却找不到使用处的，是权限过量的线索
              </span>
            </div>
          </template>

          <div class="filter-bar">
            <el-radio-group v-model="permFilter" size="small">
              <el-radio-button value="all">全部 ({{ judgeable.length }})</el-radio-button>
              <el-radio-button value="risky">有风险等级 ({{ riskyCount }})</el-radio-button>
              <el-radio-button value="used">实际有用 ({{ usedCount }})</el-radio-button>
              <!-- 计数为 0 的筛选点了必然是空的，直接不渲染 -->
              <el-radio-button v-if="unusedCount" value="unused">
                申请但未见使用 ({{ unusedCount }})
              </el-radio-button>
            </el-radio-group>
            <el-input v-model="permKeyword" placeholder="搜权限名" clearable size="small" style="width: 220px" />
          </div>

          <el-table :data="visiblePermissions" size="small" row-key="permission" class="data-table">
            <el-table-column label="权限" min-width="230">
              <template #default="{ row }">
                <span class="t-mono">{{ row.permission }}</span>
                <el-tag v-if="row.risk_level" size="small"
                        :type="row.risk_level === 'CRITICAL' ? 'danger' : 'warning'"
                        effect="plain" class="ml6">{{ row.risk_level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="300">
              <template #default="{ row }">
                <span v-if="row.category_cn">{{ row.category_cn }}</span>
                <span v-if="row.capability" class="dim"> · {{ row.capability }}</span>
                <span v-if="!row.kb_available" class="dim">（知识库暂无说明）</span>
                <div v-if="row.compliance_focus" class="sub-line">{{ row.compliance_focus }}</div>
              </template>
            </el-table-column>
            <el-table-column label="实际使用" width="150" align="center">
              <template #default="{ row }">
                <template v-if="row.call_site_count === 0">
                  <span class="warn-text">未发现调用点</span>
                </template>
                <template v-else>
                  <b class="t-num">{{ row.call_site_count }}</b> 处
                  <div class="sub-line t-num">{{ row.method_count }} 个方法</div>
                </template>
              </template>
            </el-table-column>
            <el-table-column label="申请来源" width="130">
              <template #default="{ row }">
                <span class="dim">{{ row.declared_by.join(' · ') }}</span>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="无权限记录" /></template>
          </el-table>

          <!-- 9/14 行写着同一句「无法判定」：折叠成一组 + 一条说明，不再逐行重复 -->
          <div v-if="unmappedFiltered.length" class="unmapped">
            <button class="unmapped-head" @click="showUnmapped = !showUnmapped"
                    :aria-expanded="showUnmapped">
              <el-icon><component :is="showUnmapped ? ArrowDown : ArrowRight" /></el-icon>
              <span>{{ unmappedFiltered.length }} 项权限的映射未覆盖，平台暂时无法判定是否被调用</span>
            </button>
            <p v-if="showUnmapped" class="unmapped-body">
              <span v-for="(p, i) in unmappedFiltered" :key="p.permission" class="unmapped-chip t-mono">
                {{ p.permission }}<span v-if="i < unmappedFiltered.length - 1">、</span>
              </span>
            </p>
          </div>
        </el-card>

        <!-- ── SDK 与第三方组件 ──────────────────────────────── -->
        <div v-if="has('components')" id="sec-components" class="anchor-section">
          <SdkPanel :task-id="taskId" :unattributed="profile?.unattributed_packages || []" />
        </div>

        <!-- ── 缺口说明：不假装有数据 ───────────────────────── -->
        <el-card v-if="has('gaps')" id="sec-gaps" shadow="never" class="block anchor-section">
          <template #header>
            <div class="block-head">
              <span class="t-section">以下字段平台尚无数据</span>
              <span class="t-sub">一律显示「无数据」，不推断</span>
            </div>
          </template>
          <ul class="gap-list">
            <li><b>是否在隐私政策中声明</b> —— 隐私政策解析模块结构已就绪但尚无数据（0 条政策、0 个任务关联）</li>
            <li><b>必要 / 非必要</b> —— 需要隐私政策 + 业务功能清单才能判定</li>
            <li><b>调用时机</b>（启动时 / 用户点击 / 后台）—— 静态检测看不到时机，需要动态检测</li>
            <li><b>未识别三方包</b> {{ unidentifiedSum }} 处 —— 知识库指纹未覆盖，属「待分析」而非「应用自身」</li>
          </ul>
        </el-card>
      </div>

      <!-- 锚点目录：3275px 的长页，让人不用滚也能跳 -->
      <nav class="toc" aria-label="页内导航">
        <div class="toc-title">本页内容</div>
        <button v-for="s in sections" :key="s.id" class="toc-item"
                :class="{ 'is-active': activeSection === s.id }" @click="goTo(s.id)">
          {{ s.label }}
        </button>
      </nav>
    </div>

    <el-drawer v-model="codeVisible" :title="codeTitle" size="720px">
      <EngineReportViewer v-if="codeObservationId" :task-id="taskId"
                          :observation-id="codeObservationId" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import EmptyBox from '@/components/EmptyBox.vue'
import EngineReportViewer from '@/components/EngineReportViewer.vue'
import SdkPanel from '@/components/SdkPanel.vue'
import { taskApi } from '@/api/tasks'

/**
 * `sections` 让消费方按需剪裁：App 背景侧滑面板把「权限」与「SDK 组件」拆成独立块，
 * 这里就只渲染「个人信息收集」与「数据缺口」，否则同一面板里 SDK 会连出两遍。
 * 不传 = 全渲染，TaskReport 等既有用法行为不变。
 */
const props = withDefaults(defineProps<{ taskId: number; sections?: string[] }>(), {
  // 默认全渲染（TaskReport 等既有用法行为不变）；defineProps 的默认值会被提升，
  // 所以这里必须写字面量，不能引用本地 const。
  sections: () => ['collect', 'permission', 'components', 'gaps'],
})
const emit = defineEmits<{ (e: 'count', n: number): void }>()

const has = (key: string) => props.sections.includes(key)

const loading = ref(false)
const profile = ref<any>(null)
const permFilter = ref('all')
const permKeyword = ref('')
const showUnmapped = ref(false)
const codeVisible = ref(false)
const codeObservationId = ref<number | null>(null)
const codeTitle = ref('引擎报告')

const collect = (key: string) => profile.value?.[key] || []
const sum = (items: any[]): number => items.reduce((n: number, i: any) => n + i.call_site_count, 0)

const appSelf = computed(() => collect('collect_app_self'))
const thirdParty = computed(() => collect('collect_third_party'))
const unidentified = computed(() => collect('collect_unidentified'))
const permissions = computed<any[]>(() => profile.value?.permissions || [])

const appSelfCount = computed(() => sum(appSelf.value))
const unidentifiedSum = computed(() => sum(unidentified.value))
const totalCollect = computed(() => appSelfCount.value + sum(thirdParty.value) + unidentifiedSum.value)
const thirdPartyOwners = computed(() => new Set(thirdParty.value.map((i: any) => i.owner.name)).size)
const sensitiveCount = computed(() =>
  new Set([...appSelf.value, ...thirdParty.value, ...unidentified.value]
    .filter(i => i.sensitive).map(i => i.data_category)).size)

const permissionCount = computed(() => permissions.value.length)

/** 能判定「实际用没用」的权限：映射覆盖到的 */
const judgeable = computed(() => permissions.value.filter(p => p.guard_mapped))
/** 映射未覆盖的：平台给不出判断，单独折叠展示 */
const unmapped = computed(() => permissions.value.filter(p => !p.guard_mapped))

const riskyCount = computed(() => judgeable.value.filter(p => p.risk_level).length)
const usedCount = computed(() => judgeable.value.filter(p => p.call_site_count > 0).length)
const unusedCount = computed(() => judgeable.value.filter(p => p.call_site_count === 0).length)

/** 隐私政策列是否有任何一行有数据；全为 null 时整列不渲染 */
const hasPolicyData = computed(() =>
  [...appSelf.value, ...thirdParty.value, ...unidentified.value]
    .some(i => i.declared_in_policy !== null && i.declared_in_policy !== undefined))

const visiblePermissions = computed(() => {
  const key = permKeyword.value.trim().toLowerCase()
  return judgeable.value.filter(p => {
    if (key && !p.permission.toLowerCase().includes(key)) return false
    if (permFilter.value === 'risky') return !!p.risk_level
    if (permFilter.value === 'used') return p.call_site_count > 0
    if (permFilter.value === 'unused') return p.call_site_count === 0
    return true
  })
})

const unmappedFiltered = computed(() => {
  const key = permKeyword.value.trim().toLowerCase()
  return unmapped.value.filter(p => !key || p.permission.toLowerCase().includes(key))
})

const collectGroups = computed(() => [
  { key: 'self', label: 'App 自身代码', items: appSelf.value, sum: appSelfCount.value,
    hint: '', emptyText: '应用自身代码中未发现敏感个人信息采集' },
  { key: 'third_party', label: '第三方组件', items: thirdParty.value, sum: sum(thirdParty.value),
    hint: '这些组件的采集行为需在隐私政策中逐一声明',
    emptyText: '未识别到第三方组件的采集' },
  { key: 'unidentified', label: '未识别三方包（待分析）', items: unidentified.value,
    sum: unidentifiedSum.value,
    hint: '知识库指纹未覆盖，无法判断归属 —— 不是「应用自身」',
    emptyText: '无未识别采集' },
])

// ============ 锚点导航 ============
const ALL_TOC = [
  { id: 'sec-collect', key: 'collect', label: '个人信息收集' },
  { id: 'sec-permission', key: 'permission', label: '权限使用' },
  { id: 'sec-components', key: 'components', label: '第三方组件' },
  { id: 'sec-gaps', key: 'gaps', label: '数据缺口' },
]
const sections = computed(() => ALL_TOC.filter((s) => has(s.key)))
const activeSection = ref('sec-collect')

/** 页面内容滚在 .el-main 里（不是 window），得先找到真正的滚动容器 */
function scroller(): HTMLElement | Window {
  let el: HTMLElement | null = document.getElementById('sec-collect')
  while (el && el !== document.body) {
    const oy = getComputedStyle(el).overflowY
    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) return el
    el = el.parentElement
  }
  return window
}

function goTo(id: string) {
  activeSection.value = id
  const el = document.getElementById(id)
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// 激活线必须**大于** .anchor-section 的 scroll-margin-top(96px)：
// 点击锚点后目标会停在 96px 处，激活线若是 80px 就永远够不到，高亮会卡在上一节。
const ACTIVE_LINE = 110

function onScroll() {
  const list = sections.value
  if (!list.length) return
  const box = scroller()
  if (box instanceof Window) {
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
      activeSection.value = list[list.length - 1].id
      return
    }
  } else if (box.scrollTop + box.clientHeight >= box.scrollHeight - 4) {
    // 滚到底时最后一节可能到不了激活线，直接判定为最后一节
    activeSection.value = list[list.length - 1].id
    return
  }
  const boxTop = box instanceof Window ? 0 : box.getBoundingClientRect().top
  // 取最后一个「已经越过激活线」的分区
  let current = list[0].id
  for (const s of list) {
    const el = document.getElementById(s.id)
    if (!el) continue
    if (el.getBoundingClientRect().top - boxTop <= ACTIVE_LINE) current = s.id
  }
  activeSection.value = current
}

let box: HTMLElement | Window | null = null

function bindScroll() {
  box = scroller()
  box.addEventListener('scroll', onScroll, { passive: true })
}

function openCode(loc: any) {
  codeObservationId.value = loc.observation_id
  codeTitle.value = '引擎报告'
  codeVisible.value = true
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    const res = await taskApi.complianceProfile(props.taskId)
    profile.value = res.data || {}
    emit('count', totalCollect.value)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  bindScroll()
})

onBeforeUnmount(() => {
  box?.removeEventListener('scroll', onScroll)
})

watch(() => props.taskId, load)
</script>

<style scoped>
.profile { font-size: var(--text-body); }

/* 内容 + 右侧锚点目录 */
.body-grid { display: grid; grid-template-columns: minmax(0, 1fr) 132px; gap: var(--space-5); }
.body-main { min-width: 0; }
@media (max-width: 1280px) {
  .body-grid { grid-template-columns: minmax(0, 1fr); }
  .toc { display: none; }
}

.mb14 { margin-bottom: var(--space-4); }
.block { margin-bottom: var(--space-4); }

.group-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin: var(--space-4) 0 var(--space-1);
  flex-wrap: wrap;
}
.group-head:first-child { margin-top: 0; }
.group-name { font-weight: 600; }
.group-hint { color: var(--el-color-primary); font-size: var(--text-label); }

.filter-bar {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.sub-line { color: var(--ink-3); font-size: var(--text-micro); }
.warn-text { color: #E6A23C; }

/* 归属：主名一行，厂商降为次行 —— 此前两者挤在一行，换行把行高撑到 2-3 行 */
.owner-name { line-height: 1.35; }
.owner-vendor {
  font-size: var(--text-micro);
  color: var(--ink-3);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

/* 列被降级成一条说明 */
.column-note {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--surface-subtle);
  border-radius: 6px;
  font-size: var(--text-label);
  color: var(--ink-3);
}

/* 无法判定的权限折叠区 */
.unmapped { margin-top: var(--space-3); border-top: 1px dashed var(--surface-line); padding-top: var(--space-2); }
.unmapped-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 2px 0;
  background: none;
  border: none;
  font: inherit;
  font-size: var(--text-label);
  color: var(--ink-3);
  cursor: pointer;
  text-align: left;
}
.unmapped-head:hover { color: var(--el-color-primary); }
.unmapped-body {
  margin: var(--space-1) 0 0;
  font-size: var(--text-micro);
  color: var(--ink-3);
  line-height: 1.9;
}
.unmapped-chip { word-break: break-all; }

.gap-list { margin: 0; padding-left: 18px; line-height: 1.9; color: var(--ink-2); }

.ml6 { margin-left: 6px; }
/* 表格缩进/表头/悬停统一由全局 .data-table 提供，这里只管本页特有的 */
.dim { color: var(--ink-3); }
.t-mono {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", "JetBrains Mono",
    Menlo, Consolas, "Liberation Mono", monospace;
}
</style>
