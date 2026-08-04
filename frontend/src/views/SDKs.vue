<template>
  <div class="page-container">
    <PageHeader title="SDK知识库" subtitle="SDK、开源库与组件的隐私合规档案">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建组件</el-button>
    </PageHeader>
    <el-card shadow="never">
      <div class="filter-bar">
        <el-input v-model="filters.keyword" placeholder="搜索名称 / 厂商" clearable style="width:220px"
                  @keyup.enter="loadData(1)" @clear="loadData(1)" />
        <el-select v-model="filters.kind" placeholder="全部类型" clearable style="width:150px">
          <el-option v-for="(item, value) in COMPONENT_KIND" :key="value" :label="item.label" :value="value" />
        </el-select>
        <el-select v-model="filters.category" placeholder="全部分类" clearable filterable allow-create
                   style="width:170px">
          <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
        </el-select>
        <el-button type="primary" @click="loadData(1)">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
      <el-table :data="sdks" v-loading="loading" stripe>
        <el-table-column label="名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="goDetail(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="vendor" label="厂商" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.vendor || '-' }}</template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <StatusTag :value="row.component_kind" :map="COMPONENT_KIND" />
          </template>
        </el-table-column>
        <el-table-column label="分类" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <template v-if="row.category_l1">
              {{ row.category_l1 }}
              <span v-if="row.category_l2" class="cat-l2">/ {{ row.category_l2 }}</span>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="敏感度" width="90">
          <template #default="{ row }">
            <StatusTag v-if="row.sensitivity_level" :value="row.sensitivity_level" :map="SENSITIVITY" />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="fingerprint_count" label="指纹数" width="80" align="center" />
        <el-table-column label="核验状态" width="110">
          <template #default="{ row }">
            <StatusTag :value="row.verification_status" :map="VERIFICATION_STATUS" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无组件，点击右上角新建" />
        </template>
      </el-table>
      <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                     :page-size="pageSize" :current-page="page"
                     @current-change="loadData" />
    </el-card>

    <el-dialog v-model="showDialog" :title="editingId ? '编辑组件' : '新建组件'" width="520px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="组件名称，如 OkHttp" />
        </el-form-item>
        <el-form-item label="厂商">
          <el-input v-model="form.vendor" placeholder="厂商名称，可选" />
        </el-form-item>
        <el-form-item label="类型" prop="component_kind">
          <el-select v-model="form.component_kind" style="width:100%">
            <el-option v-for="(item, value) in COMPONENT_KIND" :key="value" :label="item.label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="一级分类">
          <el-input v-model="form.category_l1" placeholder="如：统计分析 / 广告 / 推送" />
        </el-form-item>
        <el-form-item label="二级分类">
          <el-input v-model="form.category_l2" placeholder="可选" />
        </el-form-item>
        <el-form-item label="敏感度">
          <el-select v-model="form.sensitivity_level" clearable style="width:100%">
            <el-option v-for="(item, value) in SENSITIVITY" :key="value" :label="item.label" :value="value" />
          </el-select>
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
import { useRouter } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { sdkApi } from '@/api/sdks'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { COMPONENT_KIND, SENSITIVITY, VERIFICATION_STATUS } from '@/utils/dict'

interface SdkItem {
  id: number
  component_key: string
  name: string
  vendor: string | null
  component_kind: string
  category_l1: string | null
  category_l2: string | null
  sensitivity_level: string | null
  confidence_level: string | null
  verification_status: string | null
  is_active: boolean
  fingerprint_count: number
}

const router = useRouter()

const loading = ref(false)
const sdks = ref<SdkItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const filters = reactive({ keyword: '', kind: '', category: '' })

/** 分类选项：从已加载数据中收集 category_l1 去重（allow-create 支持直接输入新分类） */
const categoryOptions = ref<string[]>([])
function collectCategories(items: SdkItem[]) {
  const set = new Set(categoryOptions.value)
  for (const it of items) {
    if (it.category_l1) set.add(it.category_l1)
  }
  categoryOptions.value = Array.from(set).sort()
}

const showDialog = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  name: '',
  vendor: '',
  component_kind: 'SDK',
  category_l1: '',
  category_l2: '',
  sensitivity_level: '',
})
const formRules: FormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  component_kind: [{ required: true, message: '请选择类型', trigger: 'change' }],
}

async function loadData(p = 1) {
  page.value = p
  loading.value = true
  try {
    const res: any = await sdkApi.list({
      keyword: filters.keyword || undefined,
      kind: filters.kind || undefined,
      category: filters.category || undefined,
      page: page.value, page_size: pageSize,
    })
    sdks.value = res.data.items
    total.value = res.data.total
    collectCategories(sdks.value)
  } finally { loading.value = false }
}

function resetFilters() {
  filters.keyword = ''
  filters.kind = ''
  filters.category = ''
  loadData(1)
}

function goDetail(row: SdkItem) {
  router.push(`/sdks/${row.id}`)
}

function resetForm() {
  editingId.value = null
  form.name = ''
  form.vendor = ''
  form.component_kind = 'SDK'
  form.category_l1 = ''
  form.category_l2 = ''
  form.sensitivity_level = ''
  formRef.value?.clearValidate()
}

function openCreate() {
  editingId.value = null
  showDialog.value = true
}

function openEdit(row: SdkItem) {
  editingId.value = row.id
  form.name = row.name
  form.vendor = row.vendor || ''
  form.component_kind = row.component_kind || 'SDK'
  form.category_l1 = row.category_l1 || ''
  form.category_l2 = row.category_l2 || ''
  form.sensitivity_level = row.sensitivity_level || ''
  showDialog.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = {
      name: form.name,
      vendor: form.vendor || undefined,
      component_kind: form.component_kind,
      category_l1: form.category_l1 || undefined,
      category_l2: form.category_l2 || undefined,
      sensitivity_level: form.sensitivity_level || undefined,
    }
    if (editingId.value) {
      await sdkApi.update(editingId.value, payload)
      ElMessage.success('保存成功')
    } else {
      await sdkApi.create(payload)
      ElMessage.success('创建成功')
    }
    showDialog.value = false
    loadData(page.value)
  } finally { saving.value = false }
}

onMounted(() => loadData(1))
</script>

<style scoped>
.cat-l2 { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
