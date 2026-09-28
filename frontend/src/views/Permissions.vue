<template>
  <div class="page-container">
    <PageHeader title="权限知识库" subtitle="Android 平台权限与三方声明权限的合规档案">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建权限</el-button>
    </PageHeader>
    <el-card shadow="never">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" placeholder="搜索权限名 / 能力说明" clearable style="width:240px"
                  @keyup.enter="loadData(1)" @clear="loadData(1)" />
        <el-select v-model="filters.platform" placeholder="全部平台" clearable style="width:130px"
                   @change="onPlatformChange">
          <el-option v-for="p in meta.platforms" :key="p" :label="dictLabel(PLATFORM, p)" :value="p" />
        </el-select>
        <el-checkbox v-model="filters.applicable">只看应用可申请</el-checkbox>
        <el-select v-model="filters.category" placeholder="全部分类" clearable filterable style="width:170px">
          <el-option v-for="c in meta.categories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.permission_type" placeholder="全部类型" clearable style="width:170px">
          <el-option v-for="t in meta.permission_types" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filters.risk_level" placeholder="全部风险" clearable style="width:130px">
          <el-option v-for="r in meta.risk_levels" :key="r" :label="dictLabel(RISK_LEVEL, r)" :value="r" />
        </el-select>
        <el-select v-model="filters.is_active" placeholder="全部状态" clearable style="width:120px">
          <el-option label="启用" :value="true" />
          <el-option label="已停用" :value="false" />
        </el-select>
        <el-button type="primary" @click="loadData(1)">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
      <el-table :data="permissions" v-loading="loading" stripe>
        <el-table-column label="权限名" min-width="250" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.permission_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平台" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.platform" :map="PLATFORM" />
          </template>
        </el-table-column>
        <el-table-column label="分类" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.category || '-' }}</template>
        </el-table-column>
        <el-table-column label="类型" width="150">
          <template #default="{ row }">
            <StatusTag v-if="row.permission_type" :value="row.permission_type" :map="PERMISSION_TYPE" />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="80">
          <template #default="{ row }">
            <StatusTag v-if="row.risk_level" :value="row.risk_level" :map="RISK_LEVEL" />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small" disable-transitions>
              {{ row.is_active ? '启用' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="toggleActive(row)">
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无权限，点击右上角新建" />
        </template>
      </el-table>
      <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                     :page-size="pageSize" :current-page="page"
                     @current-change="loadData" />
    </el-card>

    <el-dialog v-model="showDialog" :title="editingId ? '编辑权限' : '新建权限'" width="600px"
               @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="权限名" prop="permission_name">
          <!-- 对外主键：扫描记录按名字匹配，建后不可改，所以编辑态只读 -->
          <el-input v-model="form.permission_name" :disabled="!!editingId"
                    placeholder="如 android.permission.ACCESS_FINE_LOCATION" />
          <div v-if="editingId" class="form-hint">权限名是扫描记录的匹配依据，不可修改</div>
        </el-form-item>
        <el-form-item label="平台" prop="platform">
          <el-select v-model="form.platform" :disabled="!!editingId" style="width:100%"
                     @change="loadMeta">
            <el-option v-for="p in meta.platforms" :key="p" :label="dictLabel(PLATFORM, p)" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" clearable filterable allow-create style="width:100%"
                     placeholder="如：位置信息 / 设备标识">
            <el-option v-for="c in meta.categories" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.permission_type" clearable style="width:100%">
            <el-option v-for="t in meta.permission_types" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险等级">
          <el-select v-model="form.risk_level" clearable style="width:100%">
            <el-option v-for="r in meta.risk_levels" :key="r" :label="dictLabel(RISK_LEVEL, r)" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="能力说明">
          <el-input v-model="form.capability" type="textarea" :rows="2" placeholder="该权限授予后能做什么" />
        </el-form-item>
        <el-form-item label="授予方式">
          <el-input v-model="form.grant_mode" type="textarea" :rows="2"
                    placeholder="如：运行时授权；Android 11+ 需先授予前台定位" />
        </el-form-item>
        <el-form-item label="合规要点">
          <el-input v-model="form.compliance_focus" type="textarea" :rows="3"
                    placeholder="收集该类信息的合规要求" />
        </el-form-item>
        <el-form-item label="官方参考">
          <el-input v-model="form.official_reference" placeholder="https://..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">
          {{ editingId ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { permissionApi } from '@/api/permissions'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { PERMISSION_TYPE, PLATFORM, RISK_LEVEL, dictLabel } from '@/utils/dict'

interface PermissionItem {
  id: number
  permission_name: string
  platform: string
  category: string | null
  permission_type: string | null
  risk_level: string | null
  is_active: boolean
}

const loading = ref(false)
const permissions = ref<PermissionItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const filters = reactive({
  keyword: '', platform: '', category: '', permission_type: '', risk_level: '',
  is_active: undefined as boolean | undefined,
  // 三态由后端定义：true = 只看可达、false = 只看不可达、不传 = 不筛。
  // 这里的勾选框只表达「只看可达」，取消勾选送 undefined（不筛），不送 false。
  applicable: true,
})

/** 受控词表由后端给，前端不抄一份——词表抄到前端正是它失控的起点 */
const meta = reactive({ platforms: [] as string[], permission_types: [] as string[],
                        risk_levels: [] as string[], categories: [] as string[] })

const showDialog = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  permission_name: '', platform: 'ANDROID', category: '', permission_type: '', risk_level: '',
  capability: '', grant_mode: '', compliance_focus: '', official_reference: '',
})
const formRules: FormRules = {
  permission_name: [{ required: true, message: '请输入权限名', trigger: 'blur' }],
}

/**
 * 受控词表按平台取。platform 缺省时跟随筛选栏的平台——词表必须与「当前平台」一致，
 * 否则用户会拿别的平台的取值去查/去存。
 * 弹窗的平台下拉直接把它挂在 @change 上（el-select 会把新值作为参数传来）。
 */
async function loadMeta(platform?: string) {
  const p = platform ?? filters.platform
  const res: any = await permissionApi.meta(p ? { platform: p } : undefined)
  meta.platforms = res.data.platforms
  meta.permission_types = res.data.permission_types
  meta.risk_levels = res.data.risk_levels
  meta.categories = res.data.categories
}

function onPlatformChange() {
  // 平台变了，受控词表跟着变；已选的类型可能不再合法，清掉
  filters.permission_type = ''
  loadMeta()
  loadData(1)
}

async function loadData(p = 1) {
  page.value = p
  loading.value = true
  try {
    const res: any = await permissionApi.list({
      keyword: filters.keyword || undefined,
      platform: filters.platform || undefined,
      category: filters.category || undefined,
      permission_type: filters.permission_type || undefined,
      risk_level: filters.risk_level || undefined,
      // 取消勾选送 undefined（不筛），不是 false（只看不可达）
      applicable: filters.applicable || undefined,
      is_active: filters.is_active,
      page: page.value, page_size: pageSize,
    })
    permissions.value = res.data.items
    total.value = res.data.total
  } finally { loading.value = false }
}

function resetFilters() {
  filters.keyword = ''
  filters.platform = ''
  filters.category = ''
  filters.permission_type = ''
  filters.risk_level = ''
  filters.is_active = undefined
  filters.applicable = true
  // 平台回到「全部」，词表要跟着回到三平台并集，否则留下的还是上一个平台的取值
  loadMeta()
  loadData(1)
}

function resetForm() {
  editingId.value = null
  Object.assign(form, {
    permission_name: '', platform: 'ANDROID', category: '', permission_type: '', risk_level: '',
    capability: '', grant_mode: '', compliance_focus: '', official_reference: '',
  })
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  showDialog.value = true
}

async function openEdit(row: PermissionItem) {
  resetForm()
  editingId.value = row.id
  const res: any = await permissionApi.get(row.id)
  Object.assign(form, {
    permission_name: res.data.permission_name || '',
    // 平台是这一行的身份，编辑态禁用；填进来是为了让禁用框显示的是这一行真实的平台
    platform: res.data.platform || 'ANDROID',
    category: res.data.category || '',
    permission_type: res.data.permission_type || '',
    risk_level: res.data.risk_level || '',
    capability: res.data.capability || '',
    grant_mode: res.data.grant_mode || '',
    compliance_focus: res.data.compliance_focus || '',
    official_reference: res.data.official_reference || '',
  })
  showDialog.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate()
  saving.value = true
  try {
    const payload: any = {
      category: form.category || undefined,
      permission_type: form.permission_type || undefined,
      risk_level: form.risk_level || undefined,
      capability: form.capability || undefined,
      grant_mode: form.grant_mode || undefined,
      compliance_focus: form.compliance_focus || undefined,
      official_reference: form.official_reference || undefined,
    }
    if (editingId.value) {
      // platform 不进 payload：后端 PUT 不接受它，平台和 permission_name 一样建后不可改
      await permissionApi.update(editingId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await permissionApi.create({ ...payload, permission_name: form.permission_name,
                                   platform: form.platform })
      ElMessage.success('创建成功')
    }
    showDialog.value = false
    await Promise.all([loadData(page.value), loadMeta()])
  } finally { saving.value = false }
}

async function toggleActive(row: PermissionItem) {
  await permissionApi.update(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '已停用' : '已启用')
  loadData(page.value)
}

async function handleDelete(row: PermissionItem) {
  // 停用和删除是两件事：停用只是下架、行还在；删除会断开扫描记录的外键引用
  await ElMessageBox.confirm(
    `确定删除「${row.permission_name}」？\n\n如果历史扫描记录引用过它，记录会保留、只断开关联；` +
    `这个权限的说明将从知识库中消失。若要保留说明、只是不再使用，请改用「停用」。`,
    '删除权限', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  await permissionApi.remove(row.id)
  ElMessage.success('已删除')
  loadData(page.value)
}

onMounted(async () => {
  await loadMeta()
  loadData(1)
})
</script>

<style scoped>
.form-hint { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.5; }
</style>
