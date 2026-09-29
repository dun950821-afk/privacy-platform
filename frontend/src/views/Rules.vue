<template>
  <div class="page-container">
    <PageHeader title="判定规则库" subtitle="合规判定规则的登记与版本台账；当前不参与检测执行">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建规则</el-button>
    </PageHeader>

    <div class="filter-bar">
      <el-select v-model="filterCategory" placeholder="分类" clearable style="width: 140px" @change="loadData">
        <el-option v-for="(item, key) in RULE_CATEGORY" :key="key" :label="item.label" :value="key" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 120px" @change="loadData">
        <el-option v-for="(item, key) in RULE_STATUS" :key="key" :label="item.label" :value="key" />
      </el-select>
      <el-button type="primary" :icon="Search" @click="loadData">查询</el-button>
      <el-button :icon="RefreshLeft" @click="resetFilter">重置</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="rules" v-loading="loading" stripe>
        <el-table-column prop="rule_key" label="规则编号" width="180" />
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/rules/${row.id}`)">
              {{ row.name }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="110">
          <template #default="{ row }">
            <StatusTag :value="row.category" :map="RULE_CATEGORY" />
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="RULE_STATUS" />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.updated_at) }}</template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无规则" />
        </template>
      </el-table>
    </el-card>

    <!-- 新建规则 -->
    <el-dialog v-model="createVisible" title="新建规则" width="520px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="90px">
        <el-form-item label="规则编号" prop="rule_key">
          <el-input v-model="createForm.rule_key" placeholder="如 CONSENT_001，唯一标识" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="规则名称" />
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select v-model="createForm.category" placeholder="选择分类" style="width: 100%">
            <el-option v-for="(item, key) in RULE_CATEGORY" :key="key" :label="item.label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="规则用途与判定逻辑说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Search, RefreshLeft } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { ruleApi } from '@/api/rules'
import { RULE_CATEGORY, RULE_STATUS } from '@/utils/dict'
import { fmtDateTime } from '@/utils/format'

const router = useRouter()
const loading = ref(false)
const rules = ref<any[]>([])
const filterCategory = ref('')
const filterStatus = ref('')

async function loadData() {
  loading.value = true
  try {
    const res: any = await ruleApi.list({
      category: filterCategory.value || undefined,
      status: filterStatus.value || undefined,
    })
    rules.value = res.data
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  filterCategory.value = ''
  filterStatus.value = ''
  loadData()
}

const createVisible = ref(false)
const creating = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = ref({ rule_key: '', name: '', category: '', description: '' })
const createRules: FormRules = {
  rule_key: [{ required: true, message: '请输入规则编号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
}

function openCreate() {
  createForm.value = { rule_key: '', name: '', category: '', description: '' }
  createVisible.value = true
}

async function submitCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return
  creating.value = true
  try {
    await ruleApi.create({
      rule_key: createForm.value.rule_key,
      name: createForm.value.name,
      category: createForm.value.category,
      description: createForm.value.description || undefined,
    })
    ElMessage.success('规则创建成功')
    createVisible.value = false
    loadData()
  } finally {
    creating.value = false
  }
}

onMounted(loadData)
</script>
