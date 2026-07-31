<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar">
        <span class="page-title">用户管理</span>
        <el-button type="primary" :icon="Plus" @click="showDialog = true">新建用户</el-button>
      </div>
      <el-table :data="users" v-loading="loading" stripe>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="full_name" label="姓名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="role" label="角色" width="120" />
        <el-table-column prop="status" label="状态" width="80" />
      </el-table>
    </el-card>
    <el-dialog v-model="showDialog" title="新建用户" width="480px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.full_name" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width:100%">
            <el-option label="平台管理员" value="platform_admin" />
            <el-option label="规则管理员" value="rule_admin" />
            <el-option label="项目负责人" value="project_owner" />
            <el-option label="检测人员" value="tester" />
            <el-option label="开发人员" value="developer" />
            <el-option label="合规人员" value="compliance" />
            <el-option label="审计人员" value="auditor" />
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
import { systemApi } from '@/api/system'

const loading = ref(false)
const users = ref<any[]>([])
const showDialog = ref(false)
const form = reactive({ username: '', password: '', full_name: '', email: '', role: 'tester' })

async function loadData() {
  loading.value = true
  try { const res: any = await systemApi.users(); users.value = res.data } finally { loading.value = false }
}
async function handleCreate() {
  await systemApi.createUser(form)
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
