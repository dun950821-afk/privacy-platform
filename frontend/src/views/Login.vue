<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <div class="logo-icon">
          <el-icon :size="32" color="#2B5AED"><Lock /></el-icon>
        </div>
        <h1 class="login-title">App个人信息保护检测与治理平台</h1>
        <p class="login-subtitle">隐私合规检测 · 智能治理 · 证据闭环</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码"
                    :prefix-icon="Lock" size="large" show-password @keyup.enter="handleLogin" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" style="width:100%" :loading="loading"
                     @click="handleLogin">登 录</el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <span class="hint">默认账号: admin / admin123</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { authApi } from '@/api/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({ username: 'admin', password: 'admin123' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res: any = await authApi.login(form.username, form.password)
      const d = res.data
      userStore.setAuth(d.access_token, d.refresh_token, d.user)
      ElMessage.success('登录成功')
      router.push('/workspace')
    } catch {
      // 错误已由拦截器处理
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #EEF3FE 0%, #F7F8FA 50%, #F0F4F8 100%);
}
.login-card {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(43, 90, 237, 0.08);
}
.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.logo-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  background: #EEF3FE;
  border-radius: 12px;
  margin-bottom: 16px;
}
.login-title {
  font-size: 18px;
  font-weight: 600;
  color: #1F2329;
  margin-bottom: 4px;
}
.login-subtitle {
  font-size: 13px;
  color: #8F959E;
}
.login-footer {
  text-align: center;
  margin-top: 16px;
}
.hint {
  font-size: 12px;
  color: #C0C4CC;
}
</style>
