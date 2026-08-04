<template>
  <div class="page-container">
    <PageHeader title="用户管理" subtitle="平台账号与角色权限">
      <el-button type="primary" :icon="Plus" @click="openCreate">新建用户</el-button>
    </PageHeader>

    <el-card shadow="never">
      <el-table :data="pagedUsers" v-loading="loading" stripe>
        <el-table-column prop="username" label="用户名" min-width="120" show-overflow-tooltip />
        <el-table-column label="姓名" min-width="110">
          <template #default="{ row }">{{ row.full_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <StatusTag :value="row.role" :map="USER_ROLE" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <StatusTag :value="row.status" :map="USER_STATUS" />
          </template>
        </el-table-column>
        <el-table-column label="最近登录" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.last_login_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBox description="暂无用户" />
        </template>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="users.length"
          layout="total, prev, pager, next"
          background
        />
      </div>
    </el-card>

    <!-- 新建用户 -->
    <el-dialog v-model="createVisible" title="新建用户" width="480px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item label="姓名" prop="full_name">
          <el-input v-model="createForm.full_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="createForm.email" placeholder="邮箱地址" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="createForm.phone" placeholder="手机号码" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="初始密码" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option v-for="(item, key) in USER_ROLE" :key="key" :label="item.label" :value="key" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户 -->
    <el-dialog v-model="editVisible" title="编辑用户" width="480px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="editForm.full_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="邮箱地址" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="editForm.phone" placeholder="手机号码" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editForm.role" style="width: 100%">
            <el-option v-for="(item, key) in USER_ROLE" :key="key" :label="item.label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width: 100%">
            <el-option label="启用" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { fmtDateTime } from '@/utils/format'
import { USER_ROLE, USER_STATUS } from '@/utils/dict'
import { systemApi } from '@/api/system'

interface UserRow {
  id: number
  username: string
  full_name: string | null
  email: string | null
  phone?: string | null
  role: string
  status: string
  last_login_at: string | null
  created_at?: string | null
}

const loading = ref(false)
const submitting = ref(false)
const users = ref<UserRow[]>([])
const page = ref(1)
const pageSize = 10

const pagedUsers = computed(() =>
  users.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)

async function loadUsers() {
  loading.value = true
  try {
    // 后端暂不支持分页参数，一次拉全量，前端分页
    const res: any = await systemApi.users()
    users.value = res.data || []
    page.value = 1
  } finally {
    loading.value = false
  }
}

// --- 新建 ---
const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = ref({
  username: '',
  full_name: '',
  email: '',
  phone: '',
  password: '',
  role: 'viewer',
})
const createRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

function openCreate() {
  createForm.value = { username: '', full_name: '', email: '', phone: '', password: '', role: 'viewer' }
  createVisible.value = true
}

async function submitCreate() {
  if (!createFormRef.value) return
  try {
    await createFormRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    await systemApi.createUser({
      username: createForm.value.username,
      password: createForm.value.password,
      full_name: createForm.value.full_name || undefined,
      email: createForm.value.email || undefined,
      phone: createForm.value.phone || undefined,
      role: createForm.value.role,
    })
    ElMessage.success('创建成功')
    createVisible.value = false
    loadUsers()
  } finally {
    submitting.value = false
  }
}

// --- 编辑 ---
const editVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = ref({
  id: 0,
  username: '',
  full_name: '',
  email: '',
  phone: '',
  role: 'viewer',
  status: 'active',
})

function openEdit(row: UserRow) {
  editForm.value = {
    id: row.id,
    username: row.username,
    full_name: row.full_name || '',
    email: row.email || '',
    phone: row.phone || '',
    role: row.role,
    status: row.status,
  }
  editVisible.value = true
}

async function submitEdit() {
  submitting.value = true
  try {
    await systemApi.updateUser(editForm.value.id, {
      full_name: editForm.value.full_name || undefined,
      email: editForm.value.email || undefined,
      phone: editForm.value.phone || undefined,
      role: editForm.value.role,
      status: editForm.value.status,
    })
    ElMessage.success('保存成功')
    editVisible.value = false
    loadUsers()
  } finally {
    submitting.value = false
  }
}

// --- 删除 ---
async function handleDelete(row: UserRow) {
  try {
    await ElMessageBox.confirm(
      `确认删除用户「${row.username}」？删除后该账号将被禁用。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await systemApi.deleteUser(row.id)
  ElMessage.success('删除成功')
  loadUsers()
}

onMounted(loadUsers)
</script>
