<template>
  <div class="page-container">
    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="never">
          <div class="header-bar">
            <span class="page-title">{{ finding.title }}</span>
            <el-button @click="$router.back()">返回</el-button>
          </div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="风险等级">
              <el-tag :type="severityType(finding.severity)" size="small">{{ finding.severity }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="状态">{{ finding.status }}</el-descriptions-item>
            <el-descriptions-item label="数据类型">{{ finding.data_type }}</el-descriptions-item>
            <el-descriptions-item label="置信度">{{ finding.confidence }}</el-descriptions-item>
            <el-descriptions-item label="场景">{{ finding.scenario?.type }}</el-descriptions-item>
            <el-descriptions-item label="同意状态">{{ finding.scenario?.consent_status }}</el-descriptions-item>
            <el-descriptions-item label="规则">{{ finding.rule?.name }}</el-descriptions-item>
            <el-descriptions-item label="SDK">{{ finding.sdk?.name }}</el-descriptions-item>
            <el-descriptions-item label="网络域名">{{ finding.network_domain }}</el-descriptions-item>
            <el-descriptions-item label="API">{{ finding.api_path }}</el-descriptions-item>
          </el-descriptions>
          <el-divider />
          <h4>描述</h4><p>{{ finding.description }}</p>
          <h4 style="margin-top:12px">整改建议</h4><p>{{ finding.remediation_advice }}</p>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" header="操作">
          <el-button type="primary" @click="showAssign = true">分派</el-button>
          <el-button @click="showRemediation = true">提交整改</el-button>
          <el-button type="success" @click="handleClose">关闭</el-button>
        </el-card>
        <el-card shadow="never" header="关联证据" style="margin-top:16px">
          <el-table :data="evidence" size="small">
            <el-table-column prop="evidence_type" label="类型" />
            <el-table-column prop="relation_type" label="关系" />
          </el-table>
        </el-card>
        <el-card shadow="never" header="关联事件" style="margin-top:16px">
          <el-table :data="events" size="small">
            <el-table-column prop="event_type" label="类型" />
            <el-table-column prop="data_type" label="数据" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="showRemediation" title="提交整改" width="480px">
      <el-form :model="remediationForm" label-width="80px">
        <el-form-item label="类型">
          <el-select v-model="remediationForm.remediation_type" style="width:100%">
            <el-option label="代码修复" value="code_fix" />
            <el-option label="配置调整" value="config_adjust" />
            <el-option label="政策更新" value="policy_update" />
            <el-option label="风险接受" value="accepted" />
            <el-option label="误报" value="false_positive" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="remediationForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRemediation = false">取消</el-button>
        <el-button type="primary" @click="handleRemediation">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { findingApi } from '@/api/findings'

const route = useRoute()
const findingId = Number(route.params.id)
const finding = ref<any>({})
const evidence = ref<any[]>([])
const events = ref<any[]>([])
const showRemediation = ref(false)
const showAssign = ref(false)
const remediationForm = reactive({ remediation_type: 'code_fix', description: '' })

function severityType(s:string){const m:Record<string,string>={critical:'danger',high:'danger',medium:'warning',low:'info'};return m[s]||''}

async function loadData() {
  const res: any = await findingApi.get(findingId)
  finding.value = res.data
  const e: any = await findingApi.evidence(findingId)
  evidence.value = e.data
  const ev: any = await findingApi.events(findingId)
  events.value = ev.data
}

async function handleRemediation() {
  await findingApi.createRemediation(findingId, remediationForm)
  ElMessage.success('整改已提交')
  showRemediation.value = false
  loadData()
}

async function handleClose() {
  await findingApi.close(findingId, { closed_reason: 'fixed' })
  ElMessage.success('已关闭')
  loadData()
}

onMounted(loadData)
</script>
<style scoped>
.header-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-title { font-size:15px; font-weight:600; }
</style>
