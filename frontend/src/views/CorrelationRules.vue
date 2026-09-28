<template>
  <div class="page-container">
    <PageHeader title="关联规则" subtitle="跨引擎观察事实的关联检测规则，受控编辑 + 版本化发布">
      <el-button :icon="Refresh" :loading="loading" @click="loadData">刷新</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建规则</el-button>
    </PageHeader>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="mb16"
      title="保存新版本会把规则置为「停用」，需在版本历史中发布后才会生效；命中预览始终基于已发布版本。"
    />

    <el-card shadow="never">
      <el-table :data="rules" v-loading="loading" stripe>
        <el-table-column prop="rule_key" label="规则编号" width="200" />
        <el-table-column label="名称" min-width="200">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.name }}</el-button>
            <div v-if="row.description" class="sub-text">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="RULE_STATUS" />
          </template>
        </el-table-column>
        <el-table-column label="当前版本" width="100">
          <template #default="{ row }">{{ row.current_version || '-' }}</template>
        </el-table-column>
        <el-table-column prop="hit_count" label="命中数" width="90" align="center" />
        <el-table-column label="最近变更" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无关联规则" />
        </template>
      </el-table>
    </el-card>

    <!-- 新建 / 查看抽屉 -->
    <el-drawer v-model="drawerVisible" :title="drawerTitle" size="760px" destroy-on-close>
      <div v-loading="detailLoading">
        <!-- 基本信息 -->
        <div class="section-title">基本信息</div>
        <el-form
          v-if="isCreate"
          ref="createFormRef"
          :model="basic"
          :rules="createRules"
          label-width="90px"
        >
          <el-form-item label="规则编号" prop="rule_key">
            <el-input v-model="basic.rule_key" placeholder="如 PRIVACY_CONTACTS_NETWORK，唯一标识" class="mono" />
          </el-form-item>
          <el-form-item label="名称" prop="name">
            <el-input v-model="basic.name" placeholder="规则名称" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="basic.description" type="textarea" :rows="2" placeholder="规则用途与判定逻辑说明" />
          </el-form-item>
        </el-form>
        <el-descriptions v-else :column="2" border size="small">
          <el-descriptions-item label="规则编号">
            <span class="mono">{{ rule.rule_key || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusTag :value="rule.status" :map="RULE_STATUS" />
          </el-descriptions-item>
          <el-descriptions-item label="名称">{{ rule.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前版本">{{ rule.current_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="命中数">{{ rule.hit_count ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="最近变更">{{ fmtDateTime(rule.updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ rule.description || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 规则形态：决定编辑器长什么样，也决定保存出去的 schema_version -->
        <div class="section-title">规则形态</div>
        <el-radio-group v-model="form.mode" class="mb8">
          <el-radio-button value="match">字面匹配（1.0）</el-radio-button>
          <el-radio-button value="join">共享键增强（2.0）</el-radio-button>
        </el-radio-group>
        <el-alert
          v-if="form.mode === 'match'"
          type="info"
          :closable="false"
          class="mb16"
          title="按字面值匹配观察字段，命中后新建结论。新增一个数据类目就要新增一条规则。"
        />
        <el-alert
          v-else
          type="success"
          :closable="false"
          class="mb16"
          title="按共享语义键（data_category）连接同类目的证据，给已有结论补充证据并提升置信度，不新建结论。规则内不要写具体类目名。"
        />

        <!-- 增强规则的锚点与连接 -->
        <template v-if="form.mode === 'join'">
          <div class="section-title">锚点（被增强的结论所依赖的观察）</div>
          <div class="cond-row">
            <el-input v-model="form.anchorType" placeholder="观察类型，如 dataflow.privacy" />
              <el-select v-model="form.action" style="width: 160px">
                <el-option label="enrich（增强）" value="enrich" />
              </el-select>
          </div>
          <div class="field-label mt8">锚点筛选（可留空；键写错只会静默不命中，请核对）</div>
          <div v-for="(row, idx) in form.anchorWhere" :key="`aw${idx}`" class="cond-row">
            <el-input v-model="row.key" placeholder="字段，如 sink_type" />
            <el-input v-model="row.value" placeholder="值，如 network" />
            <el-button link type="danger" :icon="Delete" @click="form.anchorWhere.splice(idx, 1)" />
          </div>
          <el-button link type="primary" :icon="Plus" @click="form.anchorWhere.push({ key: '', value: '' })">
            添加锚点筛选
          </el-button>

          <div class="section-title">连接（证据侧）</div>
          <div v-for="(item, idx) in form.joins" :key="`j${idx}`" class="join-block">
            <div class="cond-row">
              <el-input v-model="item.type" placeholder="证据观察类型，如 security.sensitive_api" />
              <el-select v-model="item.on" multiple placeholder="连接键" style="width: 220px">
                <el-option v-for="key in JOIN_KEYS" :key="key" :label="key" :value="key" />
              </el-select>
              <el-button link type="danger" :icon="Delete" @click="form.joins.splice(idx, 1)" />
            </div>
            <div v-for="(row, widx) in item.where" :key="`jw${idx}-${widx}`" class="cond-row indent">
              <el-input v-model="row.key" placeholder="筛选字段（可选）" />
              <el-input v-model="row.value" placeholder="值" />
              <el-button link type="danger" :icon="Delete" @click="item.where.splice(widx, 1)" />
            </div>
            <el-button link type="primary" size="small" class="indent"
                       @click="item.where.push({ key: '', value: '' })">添加筛选</el-button>
          </div>
          <EmptyBox v-if="!form.joins.length" description="至少需要一个连接" :image-size="60" />
          <el-button link type="primary" :icon="Plus" @click="addJoin">添加连接</el-button>
          <div class="vocab-warn">
            作用范围固定为 app_version_id（同一次扫描内的观察）；增强规则不产出结论，因此没有产出定义与标准映射。
          </div>
        </template>

        <!-- 匹配条件 -->
        <template v-if="form.mode === 'match'">
        <div class="section-title">匹配条件</div>
        <div class="logic-row">
          <span class="field-label">条件组合</span>
          <el-select v-model="form.logic" style="width: 200px">
            <el-option v-for="opt in LOGIC_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
          <el-button link type="primary" :icon="Plus" @click="addCondition">添加条件</el-button>
        </div>
        <div v-for="(cond, idx) in form.conditions" :key="idx" class="cond-row">
          <el-input v-model="cond.observation_type" placeholder="观察类型，如 fact.permission" />
          <el-select v-model="cond.field" placeholder="字段">
            <el-option v-for="f in FIELD_OPTIONS" :key="f" :label="f" :value="f" />
          </el-select>
          <el-select v-model="cond.operator" placeholder="操作符">
            <el-option v-for="op in OPERATOR_OPTIONS" :key="op" :label="op" :value="op" />
          </el-select>
          <el-input v-if="cond.operator !== 'exists'" v-model="cond.value" placeholder="匹配值" />
          <span v-else class="no-value">exists 无需值</span>
          <el-button link type="danger" :icon="Delete" @click="removeCondition(idx)" />
        </div>
        <EmptyBox v-if="!form.conditions.length" description="至少需要一个匹配条件" :image-size="60" />
        <div v-if="hasUnknownField" class="vocab-warn">
          存在受控词表之外的字段，保存时将原样保留；建议改为下拉列表中的字段。
        </div>

        <!-- 产出定义 -->
        <div class="section-title">产出定义</div>
        <el-form label-width="90px">
          <el-form-item label="问题编号">
            <el-input v-model="form.produce.finding_code" class="mono" :maxlength="MAX_FINDING_CODE_LEN"
                      show-word-limit placeholder="大写字母/数字/下划线，如 PRIVACY_CONTACTS_NETWORK" />
          </el-form-item>
          <el-form-item label="标题">
            <el-input v-model="form.produce.title" :maxlength="MAX_TITLE_LEN" show-word-limit
                      placeholder="命中后生成的问题标题" />
          </el-form-item>
          <el-form-item label="类别">
            <el-input v-model="form.produce.category" class="mono" :maxlength="MAX_CATEGORY_LEN"
                      show-word-limit placeholder="如 privacy" />
          </el-form-item>
          <el-form-item label="严重性">
            <el-select v-model="form.produce.severity" style="width: 160px">
              <el-option v-for="key in SEVERITY_KEYS" :key="key" :label="dictLabel(SEVERITY, key)" :value="key" />
            </el-select>
          </el-form-item>
          <el-form-item label="置信度">
            <el-select v-model="form.produce.confidence" style="width: 160px">
              <el-option v-for="key in PRODUCE_CONFIDENCE_KEYS" :key="key"
                         :label="dictLabel(CONFIDENCE, key)" :value="key" />
            </el-select>
          </el-form-item>
          <el-form-item label="整改建议">
            <el-input v-model="form.produce.recommendation" type="textarea" :rows="2"
                      :maxlength="MAX_RECOMMENDATION_LEN" show-word-limit />
          </el-form-item>
        </el-form>

        <!-- 标准映射 -->
        <div class="section-title">标准映射</div>
        <el-form label-width="90px">
          <el-form-item v-for="std in STANDARD_FIELDS" :key="std.key" :label="std.label">
            <el-select
              v-model="form.standards[std.key]"
              multiple
              filterable
              allow-create
              default-first-option
              :reserve-keyword="false"
              :placeholder="std.placeholder"
              style="width: 100%"
            />
          </el-form-item>
        </el-form>
        </template>

        <template v-if="!isCreate">
          <!-- 版本历史 -->
          <div class="section-title">版本历史</div>
          <el-table :data="rule.versions || []" size="small" stripe>
            <el-table-column prop="version" label="版本" width="90" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="RULE_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="变更说明" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.changelog || '-' }}</template>
            </el-table-column>
            <el-table-column label="创建时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.id !== rule.current_version_id"
                  link
                  type="primary"
                  size="small"
                  :loading="publishingId === row.id"
                  @click="publishVersion(row)"
                >发布</el-button>
                <span v-else class="sub-text">当前版本</span>
              </template>
            </el-table-column>
            <template #empty>
              <EmptyBox description="暂无版本" />
            </template>
          </el-table>

          <!-- 命中预览 -->
          <div class="section-title">命中预览</div>
          <el-alert
            type="info"
            :closable="false"
            class="mb12"
            title="预览基于该规则已发布版本的内容做只读评估，不会预览未保存的修改。"
          />
          <div class="preview-row">
            <el-input-number v-model="previewTaskId" :min="1" :controls="false" placeholder="任务 ID" style="width: 160px" />
            <el-button
              type="primary"
              :loading="previewing"
              :disabled="!rule.current_version_id"
              @click="runPreview"
            >命中预览（基于已发布版本）</el-button>
            <span v-if="!rule.current_version_id" class="sub-text">该规则尚未发布任何版本，无法预览</span>
          </div>
          <el-descriptions v-if="previewResult" :column="1" border size="small" class="mt12">
            <el-descriptions-item label="是否命中">
              <el-tag :type="previewResult.would_match ? 'danger' : 'info'" size="small">
                {{ previewResult.would_match ? '命中' : '未命中' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="previewResult.action === 'enrich' ? '锚点 Observation 数' : '命中 Observation 数'">
              {{ previewResult.matched_observation_ids?.length || 0 }}
              <span v-if="previewResult.matched_observation_ids?.length" class="sub-text mono">
                （ID: {{ previewResult.matched_observation_ids.join(', ') }}）
              </span>
            </el-descriptions-item>
            <el-descriptions-item v-if="previewResult.action === 'enrich'" label="可补充的证据数">
              {{ previewResult.evidence_observation_ids?.length || 0 }}
              <span v-if="previewResult.evidence_observation_ids?.length" class="sub-text mono">
                （ID: {{ previewResult.evidence_observation_ids.join(', ') }}）
              </span>
            </el-descriptions-item>
            <el-descriptions-item v-if="previewResult.action !== 'enrich'" label="产出问题编号">
              {{ previewResult.finding_code || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="previewResult.action === 'enrich' ? '会被增强的问题' : '该任务已有问题'">
              {{ previewResult.existing_findings?.length ? previewResult.existing_findings.join(', ') : '无' }}
            </el-descriptions-item>
            <el-descriptions-item label="是否写库">
              {{ previewResult.writes ? '会写库' : '不会写库（仅预览）' }}
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </div>

      <template #footer>
        <el-button @click="drawerVisible = false">关闭</el-button>
        <el-button
          v-if="!isCreate && rule.status === 'active'"
          type="danger"
          plain
          :loading="disabling"
          @click="disableRule"
        >停用规则</el-button>
        <el-button v-if="isCreate" type="primary" :loading="saving" @click="submitCreate">创建</el-button>
        <el-button v-else type="primary" :loading="saving" @click="openVersionDialog">保存为新版本</el-button>
      </template>
    </el-drawer>

    <!-- 保存新版本 -->
    <el-dialog v-model="versionVisible" title="保存新版本" width="520px" destroy-on-close>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        class="mb16"
        title="保存后规则将置为「停用」，需在版本历史中发布该版本才会重新生效。"
      />
      <el-form ref="versionFormRef" :model="versionForm" :rules="versionRules" label-width="90px">
        <el-form-item label="版本号" prop="version">
          <el-input v-model="versionForm.version" placeholder="如 1.1" style="width: 180px" />
        </el-form-item>
        <el-form-item label="变更说明">
          <el-input v-model="versionForm.changelog" type="textarea" :rows="2" placeholder="本次版本的变更内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="versionVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitVersion">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Refresh, Delete } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { correlationRuleApi } from '@/api/correlationRules'
import type { CorrelationRuleDetail, CorrelationRulePreviewResult, CorrelationRuleSummary } from '@/api/correlationRules'
import { RULE_STATUS, SEVERITY, CONFIDENCE, dictLabel } from '@/utils/dict'
import { fmtDateTime } from '@/utils/format'
// 表单 ⇄ 规则内容的映射抽在 correlationRuleForm.ts，便于直接对真实规则内容跑往返校验
import {
  JOIN_KEYS, MAX_CATEGORY_LEN, MAX_FINDING_CODE_LEN, MAX_RECOMMENDATION_LEN, MAX_TITLE_LEN,
  buildContent as buildRuleContent, emptyCondition, emptyForm, emptyJoin, parseContent,
  validateForm as validateRuleForm,
} from './correlationRuleForm'
import type { RuleForm } from './correlationRuleForm'

/** 受控词表：条件字段与操作符固定，不提供自由编辑或原始 JSON 编辑 */
// 受控字段词表：取值必须能在真实引擎产物里解析出来。
// 注意 payload.sink / payload.source 是**方法签名数组**（不是对象），
// 因此 payload.sink.category 这类路径永远解析不到值，不能作为可选字段。
const FIELD_OPTIONS = ['subject', 'location', 'payload.category', 'payload.rule', 'payload.detail',
                       'payload.section', 'payload.level']
const OPERATOR_OPTIONS = ['equals', 'contains', 'exists']
const LOGIC_OPTIONS = [
  { label: '全部满足 (all)', value: 'all' },
  { label: '任一满足 (any)', value: 'any' },
]
const STANDARD_FIELDS = [
  { key: 'masvs', label: 'MASVS', placeholder: '如 MASVS-PRIVACY-1，回车添加' },
  { key: 'maswe', label: 'MASWE', placeholder: '如 MASWE-0001，回车添加' },
  { key: 'mastg', label: 'MASTG', placeholder: '如 MASTG-TEST-PRIVACY-1，回车添加' },
  { key: 'cwe', label: 'CWE', placeholder: '如 CWE-359，回车添加' },
] as const
const SEVERITY_KEYS = Object.keys(SEVERITY)
// 1.0 的 produce.confidence 仍是旧词表（后端 ALLOWED_CONFIDENCES 未变）；
// CONFIDENCE 里新增的 high/medium_high/medium 属于平台结论的置信度（设计 §8），
// 由增强规则按证据来源算出来，不是手填的，因此不出现在这里。
const PRODUCE_CONFIDENCE_KEYS = ['confirmed', 'probable', 'possible']
function addJoin() {
  form.value.joins.push(emptyJoin())
}

// ============ 列表 ============
const loading = ref(false)
const rules = ref<CorrelationRuleSummary[]>([])

async function loadData() {
  loading.value = true
  try {
    const res = await correlationRuleApi.list()
    rules.value = res.data || []
  } finally {
    loading.value = false
  }
}

// ============ 抽屉状态 ============
const drawerVisible = ref(false)
const isCreate = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const disabling = ref(false)
const publishingId = ref<number | null>(null)
const ruleId = ref<number | null>(null)
const rule = ref<Partial<CorrelationRuleDetail>>({})
const form = ref<RuleForm>(emptyForm())

const createFormRef = ref<FormInstance>()
const basic = ref({ rule_key: '', name: '', description: '' })
const createRules: FormRules = {
  rule_key: [{ required: true, message: '请输入规则编号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }],
}

const drawerTitle = computed(() =>
  isCreate.value ? '新建关联规则' : `关联规则 · ${rule.value.name || rule.value.rule_key || ''}`)

function addCondition() {
  form.value.conditions.push(emptyCondition())
}

function removeCondition(idx: number) {
  form.value.conditions.splice(idx, 1)
}

const hasUnknownField = computed(() => form.value.conditions.some(c => !FIELD_OPTIONS.includes(c.field)))

/** 详情请求序号：丢弃被后一次请求或新建操作取代的过期响应 */
let detailSeq = 0

function openCreate() {
  isCreate.value = true
  ruleId.value = null
  // 作废在途的详情/预览请求，并清掉它们的加载态，避免新建抽屉出现假加载
  detailSeq += 1
  detailLoading.value = false
  previewSeq += 1
  previewing.value = false
  rule.value = {}
  basic.value = { rule_key: '', name: '', description: '' }
  form.value = emptyForm()
  previewTaskId.value = undefined
  previewResult.value = null
  drawerVisible.value = true
}

async function openDetail(row: CorrelationRuleSummary) {
  isCreate.value = false
  ruleId.value = row.id
  // 先用列表行占位，避免上一规则的详情与预览结果残留到新打开的抽屉
  rule.value = { ...row, versions: [] }
  // 作废在途的预览请求，否则它的响应会落到新规则的抽屉里
  previewSeq += 1
  previewing.value = false
  previewTaskId.value = undefined
  previewResult.value = null
  drawerVisible.value = true
  await loadDetail()
}

/** keepForm=true 时只刷新状态/版本/命中数，保留编辑器中的工作副本 */
async function loadDetail(keepForm = false) {
  if (ruleId.value == null) return
  const seq = ++detailSeq
  detailLoading.value = true
  try {
    const res = await correlationRuleApi.get(ruleId.value)
    if (seq !== detailSeq) return
    rule.value = res.data || {}
    if (!keepForm) form.value = parseContent(rule.value.current_content)
  } finally {
    if (seq === detailSeq) detailLoading.value = false
  }
}

async function submitCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return
  const err = validateRuleForm(form.value)
  if (err) { ElMessage.warning(err); return }
  saving.value = true
  try {
    const res = await correlationRuleApi.create({
      rule_key: basic.value.rule_key.trim(),
      name: basic.value.name.trim(),
      description: basic.value.description.trim() || undefined,
      content: buildRuleContent(form.value),
    })
    ElMessage.success('规则已创建，初始版本为草稿，发布后生效')
    isCreate.value = false
    ruleId.value = res.data.id
    // 新建的规则没有当前版本，重新解析会清空刚填写的内容，这里保留工作副本
    await loadDetail(true)
    loadData()
  } finally {
    saving.value = false
  }
}

// ============ 保存新版本 ============
const versionVisible = ref(false)
const versionFormRef = ref<FormInstance>()
const versionForm = ref({ version: '', changelog: '' })
const versionRules: FormRules = {
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
}

function openVersionDialog() {
  const err = validateRuleForm(form.value)
  if (err) { ElMessage.warning(err); return }
  versionForm.value = { version: '', changelog: '' }
  versionVisible.value = true
}

async function submitVersion() {
  const valid = await versionFormRef.value?.validate().catch(() => false)
  if (!valid) return
  if (ruleId.value == null) return
  saving.value = true
  try {
    await correlationRuleApi.saveVersion(ruleId.value, {
      version: versionForm.value.version.trim(),
      content: buildRuleContent(form.value),
      changelog: versionForm.value.changelog.trim() || undefined,
    })
    ElMessage.success('新版本已保存，规则已置为停用，发布后生效')
    versionVisible.value = false
    await loadDetail(true)
    loadData()
  } finally {
    saving.value = false
  }
}

async function publishVersion(row: { id: number; version: string }) {
  if (ruleId.value == null) return
  try {
    await ElMessageBox.confirm(
      `确定发布版本 ${row.version} 吗？发布后该版本成为当前生效版本，规则状态变为启用。`,
      '发布确认',
      { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  publishingId.value = row.id
  try {
    await correlationRuleApi.publish(ruleId.value, row.id)
    ElMessage.success(`版本 ${row.version} 已发布`)
    // 已发布内容可能已改变，之前的预览结果不再代表当前生效版本
    previewResult.value = null
    await loadDetail(true)
    loadData()
  } finally {
    publishingId.value = null
  }
}

async function disableRule() {
  if (ruleId.value == null) return
  try {
    await ElMessageBox.confirm(
      '停用后该规则不再参与关联检测，可随时重新发布版本启用。',
      '停用规则',
      { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  disabling.value = true
  try {
    await correlationRuleApi.disable(ruleId.value)
    ElMessage.success('规则已停用')
    await loadDetail(true)
    loadData()
  } finally {
    disabling.value = false
  }
}

// ============ 命中预览（基于已发布版本） ============
const previewTaskId = ref<number | undefined>()
const previewing = ref(false)
const previewResult = ref<CorrelationRulePreviewResult | null>(null)
/** 预览请求序号：丢弃被后一次预览或切换规则取代的过期响应 */
let previewSeq = 0

async function runPreview() {
  if (ruleId.value == null) return
  const taskId = Number(previewTaskId.value)
  if (!taskId || taskId <= 0) { ElMessage.warning('请输入有效的任务 ID'); return }
  const seq = ++previewSeq
  previewing.value = true
  // 先清空旧结果，避免请求期间还显示上一次的预览
  previewResult.value = null
  try {
    const res = await correlationRuleApi.preview(ruleId.value, taskId)
    if (seq !== previewSeq) return
    previewResult.value = res.data
  } finally {
    if (seq === previewSeq) previewing.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.mb12 { margin-bottom: 12px; }
.mb16 { margin-bottom: 16px; }
.mt12 { margin-top: 12px; }
.mono { font-family: monospace; font-size: 12px; }
.sub-text { font-size: 12px; color: var(--el-text-color-secondary); }
.logic-row { display: flex; align-items: center; gap: 12px; }
.field-label { font-size: 13px; color: var(--el-text-color-regular); }
.cond-row {
  display: grid;
  grid-template-columns: 1.4fr 1.4fr 1fr 1.4fr 32px;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.no-value {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-left: 8px;
}
.vocab-warn {
  font-size: 12px;
  color: var(--el-color-warning);
  line-height: 1.6;
}
.preview-row { display: flex; align-items: center; gap: 12px; }
</style>
