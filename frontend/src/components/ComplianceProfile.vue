<template>
  <div class="profile" v-loading="loading">
    <!-- 关键数字：一眼看出这个 App 采集了什么、谁在采集、权限用得怎么样 -->
    <div class="stat-row">
      <div class="stat">
        <div class="stat-num">{{ totalCollect }}</div>
        <div class="stat-label">个人信息采集点</div>
      </div>
      <div class="stat">
        <div class="stat-num">{{ thirdPartyOwners }}</div>
        <div class="stat-label">涉及的第三方组件</div>
      </div>
      <div class="stat">
        <div class="stat-num" :class="{ warn: appSelfCount === 0 }">{{ appSelfCount }}</div>
        <div class="stat-label">应用自身代码中的采集</div>
      </div>
      <div class="stat">
        <div class="stat-num">{{ sensitiveCount }}</div>
        <div class="stat-label">敏感个人信息类目</div>
      </div>
      <div class="stat">
        <div class="stat-num">{{ permissionCount }}</div>
        <div class="stat-label">申请权限</div>
      </div>
    </div>

    <!-- ── 4.1 个人信息收集详情 ────────────────────────────── -->
    <el-card shadow="never" class="block">
      <template #header>
        <div class="head">
          <span class="title">个人信息收集</span>
          <span class="sub">按「谁在采集」分组 —— 第三方 SDK 的采集需在隐私政策中逐一声明</span>
        </div>
      </template>

      <template v-for="group in collectGroups" :key="group.key">
        <div class="group-head">
          <span class="group-name">{{ group.label }}</span>
          <span class="group-count">{{ group.sum }} 处 · {{ group.items.length }} 类</span>
          <span v-if="group.hint" class="group-hint">{{ group.hint }}</span>
        </div>
        <el-table v-if="group.items.length" :data="group.items" size="small" row-key="rowKey">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="loc-list">
                <div v-for="(loc, i) in row.code_locations" :key="i" class="loc-row">
                  <span class="mono dim">{{ loc.location }}</span>
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
              <el-tag v-if="!row.requires_permission" size="small" effect="plain" class="ml6">无需权限</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="归属" min-width="240">
            <template #default="{ row }">
              <span>{{ row.owner.name }}</span>
              <span v-if="row.owner.vendor" class="dim ml6">{{ row.owner.vendor }}</span>
              <el-tag v-if="row.owner.match_status === 'CANDIDATE'" size="small" type="info"
                      effect="plain" class="ml6">候选匹配</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="收集方式" min-width="200">
            <template #default="{ row }">
              <span class="dim">{{ row.collect_modes.join(' · ') || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="采集点" width="90" align="center">
            <template #default="{ row }"><b>{{ row.call_site_count }}</b></template>
          </el-table-column>
          <el-table-column label="方法" width="80" align="center">
            <template #default="{ row }">{{ row.method_count }}</template>
          </el-table-column>
          <el-table-column label="隐私政策" width="100" align="center">
            <template #default="{ row }">
              <span v-if="row.declared_in_policy === null" class="dim">无数据</span>
              <span v-else>{{ row.declared_in_policy ? '已声明' : '未声明' }}</span>
            </template>
          </el-table-column>
          <template #empty><EmptyBox description="无" /></template>
        </el-table>
        <div v-else class="empty-line">{{ group.emptyText }}</div>
      </template>
    </el-card>

    <!-- ── 4.2 权限使用详情 ────────────────────────────────── -->
    <el-card shadow="never" class="block">
      <template #header>
        <div class="head">
          <span class="title">权限使用</span>
          <span class="sub">
            申请 vs 实际调用点 —— 申请了却找不到使用处的，是权限过量的线索；
            「映射未覆盖」的权限不会给出这个判断
          </span>
        </div>
      </template>
      <div class="filter-bar">
        <el-radio-group v-model="permFilter" size="small">
          <el-radio-button value="all">全部 ({{ permissions.length }})</el-radio-button>
          <el-radio-button value="risky">有风险等级 ({{ riskyCount }})</el-radio-button>
          <el-radio-button value="used">实际有用 ({{ usedCount }})</el-radio-button>
          <el-radio-button value="unused">申请但未见使用 ({{ unusedCount }})</el-radio-button>
        </el-radio-group>
        <el-input v-model="permKeyword" placeholder="搜权限名" clearable size="small" style="width: 220px" />
      </div>
      <el-table :data="visiblePermissions" size="small" row-key="permission">
        <el-table-column label="权限" min-width="230">
          <template #default="{ row }">
            <span class="mono">{{ row.permission }}</span>
            <el-tag v-if="row.risk_level" size="small" :type="row.risk_level === 'CRITICAL' ? 'danger' : 'warning'"
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
            <template v-if="!row.guard_mapped">
              <span class="dim">无法判定</span>
              <div class="sub-line">权限映射未覆盖</div>
            </template>
            <template v-else-if="row.call_site_count === 0">
              <span class="warn-text">未发现调用点</span>
            </template>
            <template v-else>
              <b>{{ row.call_site_count }}</b> 处
              <div class="sub-line">{{ row.method_count }} 个方法</div>
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
    </el-card>

    <!-- ── 缺口说明：不假装有数据 ───────────────────────────── -->
    <el-alert type="info" :closable="false" class="block">
      <template #title>以下字段平台尚无数据，一律显示「无数据」，不推断</template>
      <ul class="gap-list">
        <li><b>是否在隐私政策中声明</b> — 隐私政策解析模块结构已就绪但尚无数据（0 条政策、0 个任务关联）</li>
        <li><b>必要 / 非必要</b> — 需要隐私政策 + 业务功能清单才能判定</li>
        <li><b>调用时机</b>（启动时 / 用户点击 / 后台）— 静态检测看不到时机，需要动态检测</li>
        <li><b>未识别三方包</b> {{ unidentifiedSum }} 处 — 知识库指纹未覆盖，属「待分析」而非「应用自身」</li>
      </ul>
    </el-alert>

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
const profile = ref<any>(null)
const permFilter = ref('all')
const permKeyword = ref('')
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
const riskyCount = computed(() => permissions.value.filter(p => p.risk_level).length)
const usedCount = computed(() => permissions.value.filter(p => p.guard_mapped && p.call_site_count > 0).length)
const unusedCount = computed(() => permissions.value.filter(p => p.guard_mapped && p.call_site_count === 0).length)

const visiblePermissions = computed(() => {
  const key = permKeyword.value.trim().toLowerCase()
  return permissions.value.filter(p => {
    if (key && !p.permission.toLowerCase().includes(key)) return false
    if (permFilter.value === 'risky') return !!p.risk_level
    if (permFilter.value === 'used') return p.guard_mapped && p.call_site_count > 0
    if (permFilter.value === 'unused') return p.guard_mapped && p.call_site_count === 0
    return true
  })
})

const collectGroups = computed(() => [
  { key: 'self', label: 'App 自身代码', items: appSelf.value, sum: appSelfCount.value,
    hint: appSelfCount.value === 0 ? '应用自己的代码里没有敏感采集点，全部由下列组件完成' : '',
    emptyText: '应用自身代码中未发现敏感个人信息采集' },
  { key: 'third_party', label: '第三方组件', items: thirdParty.value, sum: sum(thirdParty.value),
    hint: '这些组件的采集行为需在隐私政策中逐一声明',
    emptyText: '未识别到第三方组件的采集' },
  { key: 'unidentified', label: '未识别三方包（待分析）', items: unidentified.value,
    sum: unidentifiedSum.value,
    hint: '知识库指纹未覆盖，无法判断归属 —— 不是「应用自身」',
    emptyText: '无未识别采集' },
])

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
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.taskId, load)
</script>

<style scoped>
.profile { font-size: 13px; }
.stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 14px; }
.stat { background: #FAFBFD; border: 1px solid #EEF1F6; border-radius: 6px; padding: 12px 14px; }
.stat-num { font-size: 22px; font-weight: 600; line-height: 1.2; }
.stat-num.warn { color: #2B5AED; }
.stat-label { color: #6B7A99; font-size: 12px; margin-top: 2px; }
.block { margin-bottom: 14px; }
.head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.title { font-size: 15px; font-weight: 600; }
.sub { color: #6B7A99; font-size: 12px; }
.group-head { display: flex; align-items: baseline; gap: 10px; margin: 14px 0 6px; flex-wrap: wrap; }
.group-head:first-child { margin-top: 0; }
.group-name { font-weight: 600; }
.group-count { color: #6B7A99; font-size: 12px; }
.group-hint { color: #2B5AED; font-size: 12px; }
.empty-line { color: #B4BDCC; padding: 6px 0 2px; }
.loc-list { padding: 4px 12px; }
.loc-row { display: flex; align-items: center; justify-content: space-between; gap: 12px;
           padding: 3px 0; border-bottom: 1px dashed #EEF1F6; }
.loc-row:last-child { border-bottom: none; }
.filter-bar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.sub-line { color: #6B7A99; font-size: 11px; }
.warn-text { color: #E6A23C; }
.gap-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.9; }
.ml6 { margin-left: 6px; }
.dim { color: #6B7A99; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
