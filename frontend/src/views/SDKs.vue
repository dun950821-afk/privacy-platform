<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar">
        <span class="page-title">SDK知识库</span>
        <el-button type="primary" :icon="Plus" @click="showDialog = true">新建SDK</el-button>
      </div>
      <el-table :data="sdks" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="vendor" label="厂商" />
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column prop="status" label="状态" width="80" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/sdks/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-dialog v-model="showDialog" title="新建SDK" width="520px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="厂商"><el-input v-model="form.vendor" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width:100%">
            <el-option label="统计分析" value="analytics" /><el-option label="广告" value="ads" />
            <el-option label="推送" value="push" /><el-option label="地图" value="map" />
            <el-option label="社交" value="social" /><el-option label="支付" value="payment" />
            <el-option label="崩溃收集" value="crash" /><el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { sdkApi } from '@/api/sdks'

const loading = ref(false)
const sdks = ref<any[]>([])
const showDialog = ref(false)
const form = reactive({ name: '', vendor: '', category: 'analytics' })

async function loadData() {
  loading.value = true
  try { const res: any = await sdkApi.list(); sdks.value = res.data } finally { loading.value = false }
}
async function handleCreate() {
  if (!form.name) { ElMessage.warning('请输入名称'); return }
  await sdkApi.create(form)
  ElMessage.success('创建成功')
  showDialog.value = false
  loadData()
}
onMounted(loadData)
</script>
<style scoped>
.header-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
</style>
