<template>
  <div class="page-container">
    <PageHeader title="AppShark规则" subtitle="污点分析引擎的检测规则集, 改动即时生效(下次扫描加载)">
      <el-button type="primary" :icon="Plus" @click="openCreate">新增规则</el-button>
    </PageHeader>

    <el-alert type="info" :closable="false" class="mb16">
      <p><b>APIMode</b>：只查找敏感 API 调用点(有没有调用、在哪里调用)；
         <b>SliceMode</b>：Source → Sink 污点路径追踪(敏感数据流去了哪)。</p>
      <p>函数签名使用 Jimple 格式，如 <span class="mono">&lt;android.telephony.TelephonyManager: * getDeviceId(*)&gt;</span>，
         类名和方法签名必须与 APK 中实际调用一致，写错将匹配不到。</p>
    </el-alert>

    <el-card shadow="never">
      <el-table :data="rows" size="small" stripe v-loading="loading">
        <el-table-column label="规则名称" min-width="180">
          <template #default="{ row }">
            <div>{{ row.name }}</div>
            <div class="sub-text mono">{{ row.filename }}</div>
          </template>
        </el-table-column>
        <el-table-column label="模式" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.mode === 'APIMode' ? 'warning' : 'primary'" effect="plain">
              {{ row.mode }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="合规分类" min-width="200">
          <template #default="{ row }">
            <div>{{ row.category_detail || row.category || '-' }}</div>
            <div v-if="row.category_detail && row.category" class="sub-text mono">{{ row.category }}</div>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="70" align="center">
          <template #default="{ row }">{{ row.level || '-' }}</template>
        </el-table-column>
        <el-table-column label="Source / Sink" width="120" align="center">
          <template #default="{ row }">
            {{ row.mode === 'APIMode' ? '-' : row.source_count }} / {{ row.sink_count }}
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="说明" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.detail || '-' }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="toggleFile(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeFile(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty><EmptyBox description="暂无规则" /></template>
      </el-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isCreate ? '新增规则' : `编辑规则 · ${editingFile}`"
               width="720px" top="4vh">
      <!-- 多规则文件只能编辑原始 JSON -->
      <template v-if="rawMode">
        <el-alert type="warning" :closable="false" class="mb16"
                  title="该文件包含多条规则, 请直接编辑 JSON" />
        <el-input v-model="rawJson" type="textarea" :rows="20" class="mono" />
      </template>

      <el-form v-else label-width="110px" label-position="left">
        <el-form-item label="规则文件名" v-if="isCreate">
          <el-input v-model="form.filename" placeholder="如 device_id_to_log.json" class="mono">
            <template #append>.json</template>
          </el-input>
        </el-form-item>
        <el-form-item label="规则标识">
          <el-input v-model="form.key" placeholder="如 DeviceId_Log(规则内部名称)" class="mono" />
        </el-form-item>
        <el-form-item label="模式">
          <el-radio-group v-model="form.mode">
            <el-radio-button value="APIMode">APIMode(调用点)</el-radio-button>
            <el-radio-button value="SliceMode">SliceMode(污点路径)</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="form.level" style="width: 120px">
            <el-option v-for="l in ['L1', 'L2', 'L3', 'L4']" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="合规分类">
          <el-input v-model="form.category" placeholder="如 PersonalDeviceInformation_APICall" class="mono" />
        </el-form-item>
        <el-form-item label="分类中文">
          <el-input v-model="form.categoryDetail" placeholder="如 个人设备信息_API调用" />
        </el-form-item>
        <el-form-item label="规则说明">
          <el-input v-model="form.detail" placeholder="这条规则检测什么" />
        </el-form-item>
        <template v-if="form.mode === 'SliceMode'">
          <el-form-item label="追踪深度">
            <el-input-number v-model="form.traceDepth" :min="1" :max="64" />
          </el-form-item>
          <el-form-item label="Source方法">
            <el-input v-model="form.sourceReturn" type="textarea" :rows="5" class="mono"
                      placeholder="返回值为污点的API签名, 每行一条" />
          </el-form-item>
          <el-form-item label="Source字段">
            <el-input v-model="form.sourceField" type="textarea" :rows="2" class="mono"
                      placeholder="字段签名(可选), 每行一条, 如 <android.os.Build: * SERIAL>" />
          </el-form-item>
        </template>
        <el-form-item :label="form.mode === 'APIMode' ? 'API签名' : 'Sink签名'">
          <el-input v-model="form.sinks" type="textarea" :rows="6" class="mono"
                    :placeholder="form.mode === 'APIMode' ? '要检测调用点的API签名, 每行一条' : '污点汇聚点API签名, 每行一条'" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { appsharkRuleApi, type AppsharkRuleFile } from '@/api/appsharkRules'

interface RuleRow {
  filename: string
  enabled: boolean
  key: string
  name: string
  mode: string
  detail: string
  category: string
  category_detail: string
  level: string
  source_count: number
  sink_count: number
}

const loading = ref(false)
const files = ref<AppsharkRuleFile[]>([])
const rows = ref<RuleRow[]>([])

// ============ 对话框状态 ============
const dialogVisible = ref(false)
const saving = ref(false)
const isCreate = ref(true)
const editingFile = ref('')
const rawMode = ref(false)
const rawJson = ref('')

const emptyForm = () => ({
  filename: '',
  key: '',
  mode: 'APIMode',
  level: 'L2',
  category: '',
  categoryDetail: '',
  detail: '',
  traceDepth: 10,
  sourceReturn: '',
  sourceField: '',
  sinks: '',
})
const form = ref(emptyForm())
/** 编辑时保留原有 sink body(TaintCheck/LibraryOnly 等), 避免结构化编辑丢配置 */
let sinkBodies: Record<string, any> = {}

async function load() {
  loading.value = true
  try {
    const res = await appsharkRuleApi.list()
    files.value = res.data || []
    rows.value = files.value.flatMap(f =>
      f.rules.map(r => ({ filename: f.filename, enabled: f.enabled, ...r })))
  } finally {
    loading.value = false
  }
}

function lines(text: string): string[] {
  return text.split('\n').map(s => s.trim()).filter(Boolean)
}

function openCreate() {
  isCreate.value = true
  editingFile.value = ''
  rawMode.value = false
  rawJson.value = ''
  form.value = emptyForm()
  sinkBodies = {}
  dialogVisible.value = true
}

async function openEdit(row: RuleRow) {
  isCreate.value = false
  editingFile.value = row.filename
  const res = await appsharkRuleApi.get(row.filename)
  const content = res.data.content
  const entries = Object.entries(content)
  if (entries.length !== 1) {
    // 多规则文件: 退化为原始 JSON 编辑
    rawMode.value = true
    rawJson.value = JSON.stringify(content, null, 2)
    dialogVisible.value = true
    return
  }
  rawMode.value = false
  const [key, rule] = entries[0] as [string, any]
  const desc = rule.desc || {}
  sinkBodies = rule.sink || {}
  form.value = {
    ...emptyForm(),
    key,
    mode: rule.APIMode ? 'APIMode' : 'SliceMode',
    level: String(desc.level || 'L2'),
    category: desc.complianceCategory || desc.category || '',
    categoryDetail: desc.complianceCategoryDetail || '',
    detail: desc.detail || '',
    traceDepth: rule.traceDepth ?? 10,
    sourceReturn: (rule.source?.Return || []).join('\n'),
    sourceField: (rule.source?.Field || []).join('\n'),
    sinks: Object.keys(rule.sink || {}).join('\n'),
  }
  dialogVisible.value = true
}

function buildContent(): any {
  const f = form.value
  const sinkMap: Record<string, any> = {}
  for (const sig of lines(f.sinks)) {
    sinkMap[sig] = sinkBodies[sig] ?? (f.mode === 'APIMode' ? {} : { TaintCheck: ['p*'] })
  }
  const rule: any = {
    desc: {
      name: f.key,
      detail: f.detail,
      category: 'ComplianceInfo',
      complianceCategory: f.category,
      complianceCategoryDetail: f.categoryDetail,
      level: f.level,
    },
    sink: sinkMap,
  }
  if (f.mode === 'APIMode') {
    rule.APIMode = true
  } else {
    rule.SliceMode = true
    rule.traceDepth = f.traceDepth
    rule.PrimTypeAsTaint = true
    const source: Record<string, string[]> = {}
    if (lines(f.sourceReturn).length) source.Return = lines(f.sourceReturn)
    if (lines(f.sourceField).length) source.Field = lines(f.sourceField)
    rule.source = source
  }
  return { [f.key]: rule }
}

async function save() {
  if (rawMode.value) {
    let content: any
    try {
      content = JSON.parse(rawJson.value)
    } catch {
      ElMessage.error('JSON 格式错误')
      return
    }
    saving.value = true
    try {
      await appsharkRuleApi.update(editingFile.value, content)
      ElMessage.success('已保存')
      dialogVisible.value = false
      await load()
    } finally {
      saving.value = false
    }
    return
  }

  const f = form.value
  if (!f.key.trim()) { ElMessage.warning('请填写规则标识'); return }
  if (!lines(f.sinks).length) { ElMessage.warning('至少填写一条签名'); return }
  const bad = lines(f.sinks).find(s => !/^<.*>$/.test(s))
  if (bad) { ElMessage.warning(`签名格式应为 <类名: 返回类型 方法(参数)>: ${bad}`); return }

  let filename = editingFile.value
  if (isCreate.value) {
    const base = f.filename.trim().replace(/\.json$/, '')
    if (!/^[a-z0-9_]+$/.test(base)) {
      ElMessage.warning('文件名仅支持小写字母/数字/下划线')
      return
    }
    filename = `${base}.json`
  }

  saving.value = true
  try {
    const content = buildContent()
    if (isCreate.value) {
      await appsharkRuleApi.create({ filename, content })
    } else {
      await appsharkRuleApi.update(filename, content)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function toggleFile(row: RuleRow) {
  await appsharkRuleApi.toggle(row.filename)
  ElMessage.success(row.enabled ? '已禁用' : '已启用')
  await load()
}

async function removeFile(row: RuleRow) {
  try {
    await ElMessageBox.confirm(
      `确认删除规则文件 ${row.filename}？删除后下次扫描不再加载。`, '删除规则',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch {
    return
  }
  await appsharkRuleApi.remove(row.filename)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
.mono { font-family: monospace; font-size: 12px; }
.sub-text { font-size: 12px; color: var(--el-text-color-secondary); }
.mono :deep(textarea), .mono :deep(input) { font-family: monospace; font-size: 12px; }
</style>
