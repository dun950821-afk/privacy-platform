<template>
  <div class="page-container">
    <PageHeader :title="sdk.name || '组件详情'" subtitle="组件隐私合规档案与识别指纹">
      <el-button @click="$router.back()">返回</el-button>
      <el-button type="primary" plain :icon="Edit" @click="openEdit">编辑</el-button>
      <el-button type="primary" :icon="Plus" @click="openFingerprint">添加指纹</el-button>
    </PageHeader>

    <el-card shadow="never" v-loading="loading">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="名称">{{ sdk.name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="英文名">{{ sdk.english_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="厂商">{{ sdk.vendor || '-' }}</el-descriptions-item>
        <el-descriptions-item label="类型">
          <StatusTag :value="sdk.component_kind" :map="COMPONENT_KIND" />
        </el-descriptions-item>
        <el-descriptions-item label="分类">
          <template v-if="sdk.category_l1">
            {{ sdk.category_l1 }}<span v-if="sdk.category_l2"> / {{ sdk.category_l2 }}</span>
          </template>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="敏感度">
          <StatusTag :value="sdk.sensitivity_level" :map="SENSITIVITY" />
        </el-descriptions-item>
        <el-descriptions-item label="置信度">
          <StatusTag :value="sdk.confidence_level" :map="SENSITIVITY" />
        </el-descriptions-item>
        <el-descriptions-item label="核验状态">
          <StatusTag :value="sdk.verification_status" :map="VERIFICATION_STATUS" />
        </el-descriptions-item>
        <el-descriptions-item label="许可证">{{ sdk.license_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="官网">
          <el-link v-if="sdk.vendor_website" :href="sdk.vendor_website" target="_blank" type="primary">
            {{ sdk.vendor_website }}
          </el-link>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="用途" :span="2">{{ sdk.primary_purpose || '-' }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ sdk.description || '-' }}</el-descriptions-item>
        <el-descriptions-item label="合规说明" :span="2">{{ sdk.compliance_note || '-' }}</el-descriptions-item>
      </el-descriptions>

      <template v-if="sdk.aliases?.length">
        <h3 class="section-title">别名</h3>
        <el-tag v-for="a in sdk.aliases" :key="a.id" size="small" style="margin-right:8px">
          {{ a.alias_name }}
        </el-tag>
      </template>

      <h3 class="section-title">识别指纹（{{ sdk.fingerprints?.length || 0 }}）</h3>
      <el-table :data="sdk.fingerprints || []" size="small" max-height="360" stripe>
        <el-table-column label="类型" width="170">
          <template #default="{ row }">
            <StatusTag :value="row.fingerprint_type" :map="FP_TYPE" />
          </template>
        </el-table-column>
        <el-table-column prop="value" label="值" min-width="220" show-overflow-tooltip />
        <el-table-column label="匹配方式" width="100">
          <template #default="{ row }">{{ dictLabel(MATCH_MODE, row.match_mode) }}</template>
        </el-table-column>
        <el-table-column prop="weight" label="权重" width="70" align="center" />
        <el-table-column label="证据角色" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.evidence_role" :map="EVIDENCE_ROLE" />
          </template>
        </el-table-column>
        <el-table-column label="适用版本" width="140">
          <template #default="{ row }">
            <span v-if="row.version_from || row.version_to">
              {{ row.version_from || '∞' }} ~ {{ row.version_to || '∞' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无指纹，点击右上角添加" />
        </template>
      </el-table>

      <template v-if="sdk.data_claims?.length">
        <h3 class="section-title">个人信息处理（{{ sdk.data_claims.length }}）</h3>
        <el-table :data="sdk.data_claims" size="small" max-height="360" stripe>
          <el-table-column prop="data_item" label="数据项" width="140" show-overflow-tooltip />
          <el-table-column prop="data_description" label="数据描述" min-width="180" show-overflow-tooltip />
          <el-table-column prop="personal_info_category" label="个人信息类别" width="140" show-overflow-tooltip />
          <el-table-column label="敏感度" width="90">
            <template #default="{ row }">
              <StatusTag :value="row.sensitivity_level" :map="SENSITIVITY" />
            </template>
          </el-table-column>
          <el-table-column prop="collection_mode" label="收集方式" width="110" />
          <el-table-column prop="purpose" label="目的" min-width="160" show-overflow-tooltip />
        </el-table>
      </template>

      <template v-if="sdk.permissions?.length">
        <h3 class="section-title">权限（{{ sdk.permissions.length }}）</h3>
        <el-table :data="sdk.permissions" size="small" max-height="300" stripe>
          <el-table-column prop="permission_name" label="权限" min-width="220" show-overflow-tooltip />
          <el-table-column prop="risk_level" label="风险等级" width="100" />
          <el-table-column prop="relation_type" label="关系" width="110" />
        </el-table>
      </template>
    </el-card>

    <el-dialog v-model="editVisible" title="编辑组件" width="560px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="英文名">
          <el-input v-model="editForm.english_name" />
        </el-form-item>
        <el-form-item label="厂商">
          <el-input v-model="editForm.vendor" placeholder="厂商名称（按名称自动关联或创建）" />
        </el-form-item>
        <el-form-item label="类型" prop="component_kind">
          <el-select v-model="editForm.component_kind" style="width:100%">
            <el-option v-for="(item, value) in COMPONENT_KIND" :key="value" :label="item.label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="一级分类">
          <el-input v-model="editForm.category_l1" />
        </el-form-item>
        <el-form-item label="二级分类">
          <el-input v-model="editForm.category_l2" />
        </el-form-item>
        <el-form-item label="敏感度">
          <el-select v-model="editForm.sensitivity_level" clearable style="width:100%">
            <el-option v-for="(item, value) in SENSITIVITY" :key="value" :label="item.label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="许可证">
          <el-input v-model="editForm.license_name" placeholder="如 Apache-2.0 / MIT" />
        </el-form-item>
        <el-form-item label="用途">
          <el-input v-model="editForm.primary_purpose" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="合规说明">
          <el-input v-model="editForm.compliance_note" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="fpVisible" title="添加指纹" width="520px" @closed="resetFpForm">
      <el-form ref="fpFormRef" :model="fpForm" :rules="fpRules" label-width="90px">
        <el-form-item label="指纹类型" prop="fingerprint_type">
          <el-select v-model="fpForm.fingerprint_type" filterable style="width:100%">
            <el-option v-for="(item, value) in FP_TYPE" :key="value" :label="item.label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="指纹值" prop="value">
          <el-input v-model="fpForm.value" placeholder="如 com.squareup.okhttp3" />
        </el-form-item>
        <el-form-item label="匹配方式" prop="match_mode">
          <el-select v-model="fpForm.match_mode" style="width:100%">
            <el-option v-for="(item, value) in MATCH_MODE" :key="value" :label="item.label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="权重" prop="weight">
          <el-input-number v-model="fpForm.weight" :min="1" :max="100" style="width:160px" />
          <span class="form-tip">1-100，权重越高命中贡献越大</span>
        </el-form-item>
        <el-form-item label="证据角色" prop="evidence_role">
          <el-select v-model="fpForm.evidence_role" style="width:100%">
            <el-option v-for="(item, value) in EVIDENCE_ROLE" :key="value" :label="item.label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="版本范围">
          <div class="version-range">
            <el-input v-model="fpForm.version_from" placeholder="起始版本，可空" />
            <span class="version-sep">~</span>
            <el-input v-model="fpForm.version_to" placeholder="结束版本，可空" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fpVisible = false">取消</el-button>
        <el-button type="primary" :loading="fpSaving" @click="handleAddFingerprint">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Edit, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { sdkApi } from '@/api/sdks'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { COMPONENT_KIND, SENSITIVITY, VERIFICATION_STATUS, dictLabel } from '@/utils/dict'
import type { DictItem } from '@/utils/dict'

/** 指纹类型（全局字典未覆盖，页面级定义） */
const FP_TYPE: Record<string, DictItem> = {
  PACKAGE_PREFIX: { label: '包名前缀', type: 'primary' },
  CLASS: { label: '类名', type: 'primary' },
  MANIFEST_ACTIVITY: { label: 'Activity', type: 'info' },
  MANIFEST_SERVICE: { label: 'Service', type: 'info' },
  MANIFEST_RECEIVER: { label: 'Receiver', type: 'info' },
  MANIFEST_PROVIDER: { label: 'Provider', type: 'info' },
  MAVEN_COORDINATE: { label: 'Maven坐标', type: 'primary' },
  NATIVE_SO: { label: 'Native库', type: 'info' },
  RESOURCE: { label: '资源', type: 'info' },
  PERMISSION: { label: '权限', type: 'warning' },
  API_SIGNATURE: { label: 'API签名', type: 'primary' },
  DOMAIN: { label: '域名', type: 'warning' },
  URL: { label: 'URL', type: 'warning' },
  STRING: { label: '字符串', type: 'info' },
  OTHER: { label: '其他', type: 'info' },
}
const MATCH_MODE: Record<string, DictItem> = {
  EXACT: { label: '精确', type: 'primary' },
  PREFIX: { label: '前缀', type: 'info' },
  SUFFIX: { label: '后缀', type: 'info' },
  CONTAINS: { label: '包含', type: 'info' },
  REGEX: { label: '正则', type: 'warning' },
}
const EVIDENCE_ROLE: Record<string, DictItem> = {
  PRIMARY: { label: '主要', type: 'success' },
  SUPPORTING: { label: '辅助', type: 'info' },
  NEGATIVE: { label: '反向', type: 'danger' },
}

interface SdkDetail {
  id: number
  name?: string
  english_name?: string | null
  vendor?: string | null
  vendor_website?: string | null
  component_kind?: string
  category_l1?: string | null
  category_l2?: string | null
  sensitivity_level?: string | null
  confidence_level?: string | null
  verification_status?: string | null
  license_name?: string | null
  primary_purpose?: string | null
  description?: string | null
  compliance_note?: string | null
  aliases?: Array<{ id: number; alias_name: string; alias_type?: string }>
  fingerprints?: Array<{
    id: number; fingerprint_type: string; value: string; match_mode: string
    weight: number; evidence_role: string; version_from?: string | null; version_to?: string | null
  }>
  data_claims?: Array<{
    id: number; data_item?: string | null; data_description?: string | null
    personal_info_category?: string | null; sensitivity_level?: string | null
    collection_mode?: string | null; purpose?: string | null
  }>
  permissions?: Array<{ id: number; permission_name: string; risk_level?: string; relation_type?: string }>
}

const route = useRoute()
const sdkId = Number(route.params.id)
const loading = ref(false)
const sdk = ref<SdkDetail>({ id: sdkId })

async function loadDetail() {
  loading.value = true
  try {
    const res: any = await sdkApi.get(sdkId)
    sdk.value = res.data
  } finally { loading.value = false }
}

/* ---------- 编辑 ---------- */
const editVisible = ref(false)
const saving = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({
  name: '',
  english_name: '',
  vendor: '',
  component_kind: 'SDK',
  category_l1: '',
  category_l2: '',
  sensitivity_level: '',
  license_name: '',
  primary_purpose: '',
  description: '',
  compliance_note: '',
})
const editRules: FormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  component_kind: [{ required: true, message: '请选择类型', trigger: 'change' }],
}

function openEdit() {
  editForm.name = sdk.value.name || ''
  editForm.english_name = sdk.value.english_name || ''
  editForm.vendor = sdk.value.vendor || ''
  editForm.component_kind = sdk.value.component_kind || 'SDK'
  editForm.category_l1 = sdk.value.category_l1 || ''
  editForm.category_l2 = sdk.value.category_l2 || ''
  editForm.sensitivity_level = sdk.value.sensitivity_level || ''
  editForm.license_name = sdk.value.license_name || ''
  editForm.primary_purpose = sdk.value.primary_purpose || ''
  editForm.description = sdk.value.description || ''
  editForm.compliance_note = sdk.value.compliance_note || ''
  editVisible.value = true
}

async function handleSave() {
  if (!editFormRef.value) return
  await editFormRef.value.validate()
  saving.value = true
  try {
    await sdkApi.update(sdkId, {
      name: editForm.name,
      english_name: editForm.english_name || null,
      vendor: editForm.vendor,
      component_kind: editForm.component_kind,
      category_l1: editForm.category_l1 || null,
      category_l2: editForm.category_l2 || null,
      sensitivity_level: editForm.sensitivity_level || null,
      license_name: editForm.license_name || null,
      primary_purpose: editForm.primary_purpose || null,
      description: editForm.description || null,
      compliance_note: editForm.compliance_note || null,
    })
    ElMessage.success('保存成功')
    editVisible.value = false
    loadDetail()
  } finally { saving.value = false }
}

/* ---------- 添加指纹 ---------- */
const fpVisible = ref(false)
const fpSaving = ref(false)
const fpFormRef = ref<FormInstance>()
const fpForm = reactive({
  fingerprint_type: 'PACKAGE_PREFIX',
  value: '',
  match_mode: 'EXACT',
  weight: 10,
  evidence_role: 'SUPPORTING',
  version_from: '',
  version_to: '',
})
const fpRules: FormRules = {
  fingerprint_type: [{ required: true, message: '请选择指纹类型', trigger: 'change' }],
  value: [{ required: true, message: '请输入指纹值', trigger: 'blur' }],
  match_mode: [{ required: true, message: '请选择匹配方式', trigger: 'change' }],
  weight: [{ required: true, message: '请设置权重', trigger: 'change' }],
  evidence_role: [{ required: true, message: '请选择证据角色', trigger: 'change' }],
}

function openFingerprint() {
  fpVisible.value = true
}

function resetFpForm() {
  fpForm.fingerprint_type = 'PACKAGE_PREFIX'
  fpForm.value = ''
  fpForm.match_mode = 'EXACT'
  fpForm.weight = 10
  fpForm.evidence_role = 'SUPPORTING'
  fpForm.version_from = ''
  fpForm.version_to = ''
  fpFormRef.value?.clearValidate()
}

async function handleAddFingerprint() {
  if (!fpFormRef.value) return
  await fpFormRef.value.validate()
  fpSaving.value = true
  try {
    await sdkApi.addFingerprint(sdkId, {
      fingerprint_type: fpForm.fingerprint_type,
      value: fpForm.value,
      match_mode: fpForm.match_mode,
      weight: fpForm.weight,
      evidence_role: fpForm.evidence_role,
      version_from: fpForm.version_from || undefined,
      version_to: fpForm.version_to || undefined,
    })
    ElMessage.success('指纹已添加')
    fpVisible.value = false
    loadDetail()
  } finally { fpSaving.value = false }
}

onMounted(loadDetail)
</script>

<style scoped>
.form-tip { margin-left: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.version-range { display: flex; align-items: center; gap: 8px; width: 100%; }
.version-sep { color: var(--el-text-color-secondary); }
</style>
