<template>
  <div class="page-container">
    <PageHeader :title="rule.name || '判定规则详情'" :subtitle="rule.rule_key">
      <el-button :icon="Back" @click="router.push('/rules')">返回</el-button>
      <el-button type="primary" :icon="Plus" @click="openVersion">新建版本</el-button>
    </PageHeader>

    <el-card shadow="never" v-loading="loading">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="规则编号">{{ rule.rule_key || '-' }}</el-descriptions-item>
        <el-descriptions-item label="分类">
          <StatusTag :value="rule.category" :map="RULE_CATEGORY" />
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <StatusTag :value="rule.status" :map="RULE_STATUS" />
        </el-descriptions-item>
        <el-descriptions-item label="当前版本">{{ rule.current_version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ rule.description || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ fmtDateTime(rule.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ fmtDateTime(rule.updated_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <div class="section-title">当前规则内容</div>
    <el-card shadow="never">
      <pre v-if="contentText" class="json-view">{{ contentText }}</pre>
      <EmptyBox v-else description="尚未发布任何版本" />
    </el-card>

    <div class="section-title">版本历史</div>
    <el-card shadow="never">
      <el-table :data="rule.versions || []" stripe>
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="RULE_STATUS" />
          </template>
        </el-table-column>
        <el-table-column prop="changelog" label="变更说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.changelog || '-' }}</template>
        </el-table-column>
        <el-table-column label="发布人" width="120">
          <template #default="{ row }">{{ row.published_by || '-' }}</template>
        </el-table-column>
        <el-table-column label="发布时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.published_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'draft'"
              link
              type="primary"
              :loading="publishingId === row.id"
              @click="publishVersion(row)"
            >发布</el-button>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无版本" />
        </template>
      </el-table>
    </el-card>

    <!-- 新建版本 -->
    <el-dialog v-model="versionVisible" title="新建版本" width="640px" destroy-on-close>
      <el-form ref="versionFormRef" :model="versionForm" :rules="versionRules" label-width="90px">
        <el-form-item label="版本号" prop="version">
          <el-input v-model="versionForm.version" placeholder="如 1.0.0" style="width: 200px" />
        </el-form-item>
        <el-form-item label="规则内容" prop="rule_content">
          <el-input
            v-model="versionForm.rule_content"
            type="textarea"
            :rows="10"
            placeholder='JSON 格式，如 {"patterns": ["..."], "severity": "high"}'
            class="mono-input"
          />
        </el-form-item>
        <el-form-item label="变更说明">
          <el-input v-model="versionForm.changelog" type="textarea" :rows="2" placeholder="本次版本的变更内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="versionVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitVersion">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Back, Plus } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { ruleApi } from '@/api/rules'
import { RULE_CATEGORY, RULE_STATUS } from '@/utils/dict'
import { fmtDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const ruleId = Number(route.params.id)

const loading = ref(false)
const rule = ref<any>({})
const publishingId = ref<number | null>(null)

const contentText = computed(() => {
  if (!rule.value.current_content) return ''
  try {
    return JSON.stringify(rule.value.current_content, null, 2)
  } catch {
    return String(rule.value.current_content)
  }
})

async function loadData() {
  loading.value = true
  try {
    const res: any = await ruleApi.get(ruleId)
    rule.value = res.data
  } finally {
    loading.value = false
  }
}

async function publishVersion(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定发布版本 ${row.version} 吗？发布后将成为当前生效版本。`,
      '发布确认',
      { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  publishingId.value = row.id
  try {
    await ruleApi.publishVersion(ruleId, row.id)
    ElMessage.success(`版本 ${row.version} 已发布`)
    loadData()
  } finally {
    publishingId.value = null
  }
}

const versionVisible = ref(false)
const creating = ref(false)
const versionFormRef = ref<FormInstance>()
const versionForm = ref({ version: '', rule_content: '', changelog: '' })

const validateJson = (_rule: any, value: string, callback: (e?: Error) => void) => {
  if (!value) {
    callback(new Error('请输入规则内容'))
    return
  }
  try {
    JSON.parse(value)
    callback()
  } catch {
    callback(new Error('JSON 格式不正确，请检查'))
  }
}

const versionRules: FormRules = {
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
  rule_content: [{ required: true, validator: validateJson, trigger: 'blur' }],
}

function openVersion() {
  versionForm.value = { version: '', rule_content: '', changelog: '' }
  versionVisible.value = true
}

async function submitVersion() {
  const valid = await versionFormRef.value?.validate().catch(() => false)
  if (!valid) return
  creating.value = true
  try {
    await ruleApi.createVersion(ruleId, {
      rule_id: ruleId,
      version: versionForm.value.version,
      rule_content: JSON.parse(versionForm.value.rule_content),
      changelog: versionForm.value.changelog || undefined,
    })
    ElMessage.success('版本创建成功')
    versionVisible.value = false
    loadData()
  } finally {
    creating.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.json-view {
  margin: 0;
  padding: 16px;
  background: #F7F8FA;
  border-radius: 6px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.mono-input :deep(textarea) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
}
</style>
